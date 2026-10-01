# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""
Build Settings вЂ” Unity-style scene list and build configuration.
First scene in the list is loaded on game startup.
"""
from __future__ import annotations
import concurrent.futures
import json
import os
from typing import Optional
from core.foundation.logger import Logger


_DEFAULT_BUILD_SETTINGS = {
    "scenes": [],
    "active_scene_index": 0,
    "build_options": {
        "strip_unused_assets": True,
        "compression": "lz4",
    }
}


class BuildSettings:
    _instance: Optional["BuildSettings"] = None

    def __init__(self):
        self._path: Optional[str] = None
        self._scenes: list[str] = []          # relative scene paths
        self._active_scene_index: int = 0
        self._build_plugins: list[str] = []
        self._build_options: dict = dict(_DEFAULT_BUILD_SETTINGS["build_options"])
        BuildSettings._instance = self

    @classmethod
    def instance(cls) -> Optional["BuildSettings"]:
        return cls._instance

    # в”Ђв”Ђв”Ђ Scenes в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

    @property
    def scenes(self) -> list[str]:
        return list(self._scenes)

    @property
    def active_scene_index(self) -> int:
        return self._active_scene_index

    @active_scene_index.setter
    def active_scene_index(self, idx: int):
        if 0 <= idx < len(self._scenes):
            self._active_scene_index = idx

    @property
    def startup_scene(self) -> Optional[str]:
        """First scene in the list вЂ” loaded on game start."""
        if self._scenes:
            return self._scenes[0]
        return None

    def set_scenes(self, scenes: list[str]):
        self._scenes = list(scenes)
        if self._active_scene_index >= len(self._scenes):
            self._active_scene_index = max(0, len(self._scenes) - 1)

    def add_scene(self, scene_path: str, index: int = -1):
        if scene_path in self._scenes:
            return
        if index < 0:
            self._scenes.append(scene_path)
        else:
            self._scenes.insert(index, scene_path)

    def remove_scene(self, scene_path: str):
        if scene_path in self._scenes:
            idx = self._scenes.index(scene_path)
            self._scenes.remove(scene_path)
            if self._active_scene_index >= len(self._scenes):
                self._active_scene_index = max(0, len(self._scenes) - 1)
            elif self._active_scene_index > idx:
                self._active_scene_index -= 1

    def move_scene(self, old_index: int, new_index: int):
        if 0 <= old_index < len(self._scenes) and 0 <= new_index < len(self._scenes):
            scene = self._scenes.pop(old_index)
            self._scenes.insert(new_index, scene)
            if self._active_scene_index == old_index:
                self._active_scene_index = new_index

    @property
    def build_plugins(self) -> list[str]:
        return list(self._build_plugins)

    def set_plugins(self, names: list[str]):
        self._build_plugins = list(names)

    def add_plugin(self, name: str):
        if name not in self._build_plugins:
            self._build_plugins.append(name)

    def remove_plugin(self, name: str):
        if name in self._build_plugins:
            self._build_plugins.remove(name)

    def save(self, path: Optional[str] = None):
        save_path = path or self._path
        if not save_path:
            Logger.warning("BuildSettings: no path to save.")
            return
        data = {
            "scenes": self._scenes,
            "active_scene_index": self._active_scene_index,
            "build_options": self._build_options,
            "build_plugins": self._build_plugins,
        }
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        Logger.info(f"BuildSettings saved: {save_path}")

    def load(self, path: str):
        self._path = path
        if not os.path.exists(path):
            Logger.info("BuildSettings: no file found, using defaults.")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._scenes = list(data.get("scenes", []))
            self._active_scene_index = data.get("active_scene_index", 0)
            self._build_plugins = list(data.get("build_plugins", []))
            self._build_options = data.get("build_options", _DEFAULT_BUILD_SETTINGS["build_options"])
            Logger.info(f"BuildSettings loaded: {len(self._scenes)} scenes, {len(self._build_plugins)} plugins")
        except Exception as e:
            Logger.error(f"BuildSettings load failed: {e}")

    def get_included_scene_paths(self, project_root: str) -> list[str]:
        """Resolve scene paths relative to project root."""
        scenes_dir = os.path.join(project_root, "scenes")
        result = []
        for scene in self._scenes:
            if os.path.isabs(scene):
                full = scene
            else:
                # Strip leading "scenes/" or "scenes\\" prefix
                s = scene
                for prefix in ("scenes/", "scenes\\"):
                    if s.startswith(prefix):
                        s = s[len(prefix):]
                        break
                full = os.path.join(scenes_dir, s)
            if os.path.exists(full):
                result.append(full)
            else:
                Logger.warning(f"BuildSettings: scene not found: {full}")
        return result

    def get_all_referenced_assets(self, project_root: str) -> set[str]:
        scenes_dir = os.path.join(project_root, "scenes")
        referenced: set[str] = set()
        scene_paths: list[str] = []
        for scene in self._scenes:
            if os.path.isabs(scene):
                scene_path = scene
            else:
                s = scene
                for prefix in ("scenes/", "scenes\\"):
                    if s.startswith(prefix):
                        s = s[len(prefix):]
                        break
                scene_path = os.path.join(scenes_dir, s)
            if not os.path.exists(scene_path):
                continue
            scene_paths.append(scene_path)
        if not scene_paths:
            return referenced
        def load_one(p: str):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return (p, json.load(f), None)
            except Exception as e:
                return (p, None, e)
        datas: list[dict] = []
        if len(scene_paths) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(scene_paths))) as ex:
                for p, d, e in ex.map(load_one, scene_paths):
                    if e is not None:
                        Logger.warning(f"BuildSettings: failed to scan {p}: {e}")
                    elif d is not None:
                        datas.append(d)
        else:
            for p in scene_paths:
                pp, d, e = load_one(p)
                if e is not None:
                    Logger.warning(f"BuildSettings: failed to scan {pp}: {e}")
                elif d is not None:
                    datas.append(d)
        for data in datas:
            try:
                self._collect_assets_from_scene(data, project_root, referenced)
            except Exception:
                pass
        return referenced

    def _collect_assets_from_scene(self, data: dict, project_root: str, result: set[str]):
        PATH_FIELDS = {"mesh_path", "material_path", "clip_path", "script_path", "texture_path",
                       "ply_path", "shader_path", "env_path", "svg_path", "font_path",
                       "video_path", "graph_path"}
        entities = data.get("entities", {})
        jobs: list[tuple[str, str]] = []
        for eid, entity_data in entities.items():
            components = entity_data.get("components", [])
            for comp in components:
                for key, value in comp.items():
                    if key in PATH_FIELDS and isinstance(value, str) and value:
                        jobs.append((key, value))
        if not jobs:
            return
        def resolve_one(item: tuple[str, str]):
            key, value = item
            abs_path = self._resolve_asset_path(value, project_root)
            return (key, value, abs_path)
        resolved: list[tuple[str, str, str | None]] = []
        if len(jobs) > 16:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(2, os.cpu_count() or 4))) as ex:
                for r in ex.map(resolve_one, jobs):
                    resolved.append(r)
        else:
            for j in jobs:
                resolved.append(resolve_one(j))
        mat_jobs: list[str] = []
        for key, value, abs_path in resolved:
            if not abs_path:
                continue
            if os.path.isdir(abs_path):
                result.add(abs_path)
                try:
                    for root, dirs, files in os.walk(abs_path):
                        for fn in files:
                            result.add(os.path.join(root, fn))
                except Exception:
                    pass
            else:
                result.add(abs_path)
            if key == "material_path":
                if os.path.exists(abs_path):
                    result.add(abs_path)
                    mat_jobs.append(abs_path)
        if mat_jobs:
            uniq_mats = list(dict.fromkeys(mat_jobs))
            def scan_one(mp: str):
                found: list[str] = []
                try:
                    with open(mp, "r", encoding="utf-8") as f:
                        mat_data = json.load(f)
                    for tex_path in mat_data.get("textures", {}).values():
                        if isinstance(tex_path, str) and tex_path:
                            ap = self._resolve_asset_path(tex_path, project_root)
                            if ap:
                                found.append(ap)
                except Exception:
                    pass
                return found
            if len(uniq_mats) > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(uniq_mats))) as ex:
                    for lst in ex.map(scan_one, uniq_mats):
                        for p in lst:
                            result.add(p)
            else:
                for p in scan_one(uniq_mats[0]):
                    result.add(p)

    def _scan_material(self, mat_path: str, project_root: str, result: set[str]):
        try:
            with open(mat_path, "r", encoding="utf-8") as f:
                mat_data = json.load(f)
            for tex_path in mat_data.get("textures", {}).values():
                if isinstance(tex_path, str) and tex_path:
                    abs_path = self._resolve_asset_path(tex_path, project_root)
                    if abs_path:
                        result.add(abs_path)
        except Exception:
            pass

    @staticmethod
    def _resolve_asset_path(path: str, project_root: str) -> Optional[str]:
        if not path:
            return None
        if os.path.isabs(path) and os.path.exists(path):
            return path
        candidates = [
            os.path.join(project_root, path),
            os.path.join(project_root, "assets", path),
            os.path.join(project_root, "assets", os.path.basename(path)),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None
