# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import gc
import time
import json
import os
import shutil
import threading
from typing import Optional, Any
from core.ecs import Scene
from core.foundation.logger import Logger
from core.config.constants import PATH_FIELDS as _PATH_FIELDS
from core.ecs.embed import embed_scene_resources as _embed_scene_resources
from core.ecs.embed import extract_embedded_resources as _extract_embedded_resources
from core.foundation.progress import task_complete, task_start, task_update
_SCENE_BACKUP_KEEP = 2


def _rotate_scene_backups(path: str, keep: int = _SCENE_BACKUP_KEEP) -> None:
    try:
        if not path or not os.path.isfile(path):
            return
        if keep <= 1:
            try:
                shutil.copyfile(path, path + ".bak")
            except OSError:
                pass
            return
        oldest = f"{path}.bak{keep}"
        try:
            if os.path.isfile(oldest):
                os.remove(oldest)
        except OSError:
            pass
        for i in range(keep, 1, -1):
            src = f"{path}.bak{i - 1}" if i > 2 else f"{path}.bak"
            dst = f"{path}.bak{i}"
            try:
                if os.path.isfile(src):
                    os.replace(src, dst)
            except OSError:
                pass
        try:
            shutil.copyfile(path, path + ".bak")
        except OSError:
            pass
    except Exception:
        pass


def _atomic_write_scene_json(path: str, data: dict) -> None:
    tmp_path = path + ".build"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)


class EngineScenesMixin:
    def _persist_scene_data(self, data: dict, path: str, level: int, task_id: str, existing_storage: Optional[dict] = None) -> dict:
        def _cb(done: int, total_: int, name: str) -> None:
            frac = None if total_ <= 0 else done / max(1, total_)
            task_update(task_id, fraction=frac, detail=name)
        _embed_scene_resources(data, self.project_root, existing_storage, compress_level=level, progress_cb=_cb)
        storage = data.get("embedded_resources", {})
        self.relativize_scene_paths(data)
        _rotate_scene_backups(path)
        build_path = path + ".build"
        with open(build_path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(build_path, path)
        return storage
    def save_scene_async(self, path: Optional[str] = None, on_done: Optional[Any] = None):
        scene = self._scene
        if scene is None:
            return
        save_path = path or scene.path
        if not save_path:
            Logger.warning("No path for scene save.")
            return
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
        level = self._compress_level()
        task_id = "scene:save"
        task_start(task_id, f"Saving scene {os.path.basename(save_path)}...", fraction=0.0, total=1.0)
        snapshot = scene.serialize()
        if scene.embedded_resources:
            snapshot["embedded_resources"] = dict(scene.embedded_resources)
        existing = scene.embedded_resources
        def _worker():
            ok = True
            storage = {}
            try:
                storage = self._persist_scene_data(snapshot, save_path, level, task_id, existing)
            except Exception as e:
                ok = False
                Logger.error(f"Failed to save scene: {e}", e)
            def _finish():
                if ok:
                    scene.embedded_resources = storage
                    scene.path = save_path
                    scene.mark_clean()
                    self._emit_event("scene_saved", scene)
                task_complete(task_id)
                if callable(on_done):
                    on_done(ok)
            self._defer_gui(_finish)
        threading.Thread(target=_worker, name="scene-save-worker", daemon=True).start()
    def load_scene_async(self, path: str, data: Optional[dict] = None, on_done: Optional[Any] = None):
        task_id = "scene:load"
        task_start(task_id, f"Loading scene {os.path.basename(path)}...", fraction=0.0, total=1.0)
        throttle_state = [0.0, -1.0]
        def _cb(done: int, total_: int, name: str) -> None:
            if total_ <= 0:
                return
            frac = done / max(1, total_)
            now = time.monotonic()
            last_t = throttle_state[0]
            last_f = throttle_state[1]
            if done >= total_ or (frac - last_f) >= 0.02 or (now - last_t) >= 0.08:
                throttle_state[0] = now
                throttle_state[1] = frac
                task_update(task_id, fraction=frac, detail=name)
        def _worker(snapshot: dict | None):
            if snapshot is None:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        snapshot = json.load(f)
                except Exception as e:
                    Logger.error(f"Failed to load scene '{path}': {e}", e)
                    msg = str(e)
                    def _err():
                        from core.foundation import progress
                        progress.notify_error(f"Failed to load scene: {msg}")
                        task_complete(task_id)
                    self._defer_gui(_err)
                    return
            try:
                embedded = _extract_embedded_resources(snapshot, self.project_root, self._embedded_cache_mode(), progress_cb=_cb)
                self.resolve_scene_paths(snapshot)
            except Exception as ex:
                msg = str(ex)
                Logger.error(f"Failed to load scene '{path}': {ex}", ex)
                def _err():
                    from core.foundation import progress
                    progress.notify_error(f"Failed to load scene: {msg}")
                    task_complete(task_id)
                self._defer_gui(_err)
                return
            gc_was_enabled = gc.isenabled()
            if gc_was_enabled:
                gc.disable()
            try:
                new_scene = Scene.deserialize(snapshot, self._component_registry)
                new_scene.embedded_resources = embedded
                new_scene.path = path
                new_scene.name = os.path.splitext(os.path.basename(path))[0]
                self._ensure_shadow_system(new_scene)
                new_scene.mark_clean()
            except Exception as ex:
                msg = str(ex)
                Logger.error(f"Failed to load scene '{path}': {ex}", ex)
                def _err():
                    from core.foundation import progress
                    progress.notify_error(f"Failed to load scene: {msg}")
                    task_complete(task_id)
                self._defer_gui(_err)
                return
            finally:
                if gc_was_enabled:
                    gc.enable()
            self._defer_gui(lambda: self._swap_loaded(new_scene, path, task_id, on_done))
        threading.Thread(target=_worker, args=(data,), name="scene-load-worker", daemon=True).start()
    def _swap_loaded(self, new_scene: Scene, path: str, task_id: str, on_done: Optional[Any] = None):
        try:
            old = None
            with self._scene_lock:
                old = self._scene
            if old is not None:
                self._plugin_manager.notify_scene_unloaded(old)
            from core.components.rendering.postfx.graphics_effect import GraphicsEffect
            GraphicsEffect.cleanup_registry()
            with self._scene_lock:
                self._scene = new_scene
            self._plugin_manager.notify_scene_loaded(self._scene)
            Logger.info(f"Scene loaded: {path}")
            self._emit_event("scene_loaded", self._scene)
        except Exception as e:
            Logger.error(f"Failed to load scene '{path}': {e}", e)
            return None
        finally:
            type(self)._settle_scene_heap()
            task_complete(task_id)
        if callable(on_done):
            on_done(self._scene)
    def _apply_loaded(self, data: dict, embedded: dict, path: str, task_id: str, on_done: Optional[Any] = None):
        try:
            if isinstance(data, Scene):
                new_scene = data
                new_scene.embedded_resources = embedded
                new_scene.path = path
                old = None
                with self._scene_lock:
                    old = self._scene
                if old is not None:
                    self._plugin_manager.notify_scene_unloaded(old)
                from core.components.rendering.postfx.graphics_effect import GraphicsEffect as _GE
                _GE.cleanup_registry()
                with self._scene_lock:
                    self._scene = new_scene
                self._plugin_manager.notify_scene_loaded(self._scene)
                Logger.info(f"Scene loaded: {path}")
                self._emit_event("scene_loaded", self._scene)
            else:
                gc_enabled = gc.isenabled()
                if gc_enabled:
                    gc.disable()
                try:
                    if self._scene:
                        self._plugin_manager.notify_scene_unloaded(self._scene)
                    from core.components.rendering.postfx.graphics_effect import GraphicsEffect
                    GraphicsEffect.cleanup_registry()
                    new_scene = Scene.deserialize(data, self._component_registry)
                    new_scene.embedded_resources = embedded
                    new_scene.path = path
                    new_scene.name = os.path.splitext(os.path.basename(path))[0]
                    self._ensure_shadow_system(new_scene)
                    new_scene.mark_clean()
                finally:
                    if gc_enabled:
                        gc.enable()
                self._plugin_manager.notify_scene_loaded(new_scene)
                with self._scene_lock:
                    self._scene = new_scene
                Logger.info(f"Scene loaded: {path}")
                self._emit_event("scene_loaded", new_scene)
        except Exception as e:
            Logger.error(f"Failed to load scene '{path}': {e}", e)
            return None
        finally:
            type(self)._settle_scene_heap()
            task_complete(task_id)
        if callable(on_done):
            on_done(self._scene)
    @staticmethod
    def _resolve_component_paths(comp: dict, root: str, cache: dict | None = None):
        for key, val in comp.items():
            if key in _PATH_FIELDS and val and isinstance(val, str):
                comp[key] = EngineScenesMixin._resolve_path(val, root, cache)
        mats = EngineScenesMixin._copy_materials(comp.get("materials"))
        if mats is not None:
            for mat in mats.values() if isinstance(mats, dict) else mats:
                if isinstance(mat, dict) and "path" in mat:
                    mat["path"] = EngineScenesMixin._resolve_path(mat["path"], root, cache)
            comp["materials"] = mats
    @staticmethod
    def _relativize_component_paths(comp: dict, root: str, cache: dict | None = None):
        for key, val in comp.items():
            if key in _PATH_FIELDS and val and isinstance(val, str):
                comp[key] = EngineScenesMixin._relativize_path(val, root, cache)
        mats = EngineScenesMixin._copy_materials(comp.get("materials"))
        if mats is not None:
            for mat in mats.values() if isinstance(mats, dict) else mats:
                if isinstance(mat, dict) and "path" in mat:
                    mat["path"] = EngineScenesMixin._relativize_path(mat["path"], root, cache)
            comp["materials"] = mats
    @staticmethod
    def _copy_materials(mats):
        if isinstance(mats, list):
            return [dict(e) if isinstance(e, dict) else e for e in mats]
        if isinstance(mats, dict):
            return {k: dict(e) if isinstance(e, dict) else e for k, e in mats.items()}
        return None
    @staticmethod
    def _resolve_path(val: str, root: str, cache: dict | None = None) -> str:
        if cache is not None:
            try:
                hit = cache.get(val)
                if hit is not None:
                    return hit
            except Exception:
                pass
        res = EngineScenesMixin._resolve_path_uncached(val, root)
        if cache is not None:
            try:
                cache[val] = res
            except Exception:
                pass
        return res
    @staticmethod
    def _resolve_path_uncached(val: str, root: str) -> str:
        if not val or os.path.exists(val):
            return val
        candidate = os.path.normpath(os.path.join(root, val))
        if os.path.exists(candidate):
            return candidate.replace("\\", "/")
        if len(val) > 1 and val[1] == ":":
            parts = val.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(c):
                        return c.replace("\\", "/")
        return val
    @staticmethod
    def _relativize_path(val: str, root: str, cache: dict | None = None) -> str:
        if cache is not None:
            try:
                hit = cache.get(val)
                if hit is not None:
                    return hit
            except Exception:
                pass
        if not val:
            res = ""
        elif not os.path.isabs(val):
            res = val.replace("\\", "/")
        else:
            try:
                res = os.path.relpath(val, root).replace("\\", "/")
            except ValueError:
                res = val
        if cache is not None:
            try:
                cache[val] = res
            except Exception:
                pass
        return res
    def load_scene(self, path: str) -> Optional[Scene]:
        task_start("scene:load", f"Loading scene {os.path.basename(path)}...")
        gc_enabled = gc.isenabled()
        if gc_enabled:
            gc.disable()
        try:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["_source"] = path
                embedded = _extract_embedded_resources(data, self.project_root, self._embedded_cache_mode())
                self.resolve_scene_paths(data)
                if self._scene:
                    self._plugin_manager.notify_scene_unloaded(self._scene)
                from core.components.rendering.postfx.graphics_effect import GraphicsEffect
                GraphicsEffect.cleanup_registry()
                self._scene = Scene.deserialize(data, self._component_registry)
                self._scene.embedded_resources = embedded
                self._scene.path = path
                self._scene.name = os.path.splitext(os.path.basename(path))[0]
                self._ensure_shadow_system(self._scene)
                self._scene.mark_clean()
                self._plugin_manager.notify_scene_loaded(self._scene)
                Logger.info(f"Scene loaded: {path}")
                self._emit_event("scene_loaded", self._scene)
                return self._scene
            except Exception as e:
                Logger.error(f"Failed to load scene '{path}': {e}", e)
                return None
        finally:
            if gc_enabled:
                gc.enable()
            type(self)._settle_scene_heap()
            task_complete("scene:load")
    def load_scene_from_data(self, data: dict) -> Optional[Scene]:
        task_start("scene:load_data", "Loading scene data...")
        gc_enabled = gc.isenabled()
        if gc_enabled:
            gc.disable()
        try:
            try:
                if self._scene:
                    self._plugin_manager.notify_scene_unloaded(self._scene)
                from core.components.rendering.postfx.graphics_effect import GraphicsEffect
                GraphicsEffect.cleanup_registry()
                self._scene = Scene.deserialize(data, self._component_registry)
                self._ensure_shadow_system(self._scene)
                self._scene.mark_clean()
                self._plugin_manager.notify_scene_loaded(self._scene)
                Logger.info(f"Scene synced: {self._scene.name}")
                self._emit_event("scene_loaded", self._scene)
                return self._scene
            except Exception as e:
                Logger.error(f"Failed to load synced scene: {e}", e)
                return None
        finally:
            if gc_enabled:
                gc.enable()
            type(self)._settle_scene_heap()
            task_complete("scene:load_data")
    def save_scene(self, path: Optional[str] = None):
        if not self._scene:
            return
        save_path = path or self._scene.path
        if not save_path:
            Logger.warning("No path for scene save.")
            return
        level = self._compress_level()
        task_start("scene:save", f"Saving scene {os.path.basename(save_path)}...")
        try:
            data = self._scene.serialize()
            _embed_scene_resources(data, self.project_root, self._scene.embedded_resources, compress_level=level)
            self._scene.embedded_resources = data.get("embedded_resources", {})
            self.relativize_scene_paths(data)
            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
            _rotate_scene_backups(save_path)
            _atomic_write_scene_json(save_path, data)
            self._scene.path = save_path
            self._scene.mark_clean()
            Logger.info(f"Scene saved: {save_path}")
            self._emit_event("scene_saved", self._scene)
        except Exception as e:
            Logger.error(f"Failed to save scene: {e}", e)
        finally:
            task_complete("scene:save")
    def save_scene_object(self, scene, path: Optional[str] = None) -> bool:
        if scene is None:
            return False
        save_path = path or getattr(scene, "path", None)
        if not save_path:
            Logger.warning("No path for scene save.")
            return False
        level = self._compress_level()
        task_start("scene:save", f"Saving scene {os.path.basename(save_path)}...")
        try:
            data = scene.serialize()
            _embed_scene_resources(data, self.project_root, scene.embedded_resources, compress_level=level)
            scene.embedded_resources = data.get("embedded_resources", {})
            self.relativize_scene_paths(data)
            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
            _rotate_scene_backups(save_path)
            _atomic_write_scene_json(save_path, data)
            scene.path = save_path
            scene.mark_clean()
            Logger.info(f"Scene saved: {save_path}")
            self._emit_event("scene_saved", scene)
            return True
        except Exception as e:
            Logger.error(f"Failed to save scene: {e}", e)
            return False
        finally:
            task_complete("scene:save")
