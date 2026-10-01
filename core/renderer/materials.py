# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

import moderngl
import numpy as np

from core.assets.material import Material, MaterialLibrary
from core.assets.texture_import_settings import TextureImportSettings
from core.engine.engine import Engine
from core.foundation.logger import Logger
from core.foundation.progress import task_complete, task_set_detail, task_start


_TEX_MAX_PER_FRAME = 2
_TEX_MAX_PIXELS_PER_FRAME = 8 * 1024 * 1024
_TEX_MTIME_TTL = 2.0
_TEX_MISSING_TTL = 2.0


class MaterialManager:
    """Loads, caches and applies materials and textures to shader programs."""

    _TEX_UNIFORM_MAP = {
        "albedo_texture": "u_albedo_tex",
        "normal_texture": "u_normal_tex",
        "roughness_texture": "u_roughness_tex",
        "_BaseMap": "_BaseMap",
        "_NormalMap": "_NormalMap",
        "_OcclusionMap": "_OcclusionMap",
    }

    _WHITE4 = np.array([1, 1, 1, 1], dtype=np.float32).tobytes()
    _ZERO3 = np.zeros(3, dtype=np.float32).tobytes()

    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._material_cache: dict[str, Material] = {}
        self._missing_warned: set[str] = set()
        self._prog_uniform_names: dict[int, frozenset] = {}
        self._prog_tex_active_names: dict[int, dict] = {}
        self._texture_cache: dict[str, Any] = {}
        self._tex_alpha_cache: dict[str, tuple] = {}
        self._tex_wrap_cache: dict[str, bool] = {}
        self._tex_path_cache: dict[str, str] = {}
        self._transparency_cache: dict[tuple, bool] = {}
        self._pending_texture_queue: list = []
        try:
            self._async_lock = threading.Lock()
        except Exception:
            self._async_lock = None
        self._tex_mtime_checked: dict[str, float] = {}
        self._tex_inflight: set[str] = set()
        self._tex_missing: dict[str, float] = {}
        self._default_white = ctx.texture((1, 1), 4, b'\xff\xff\xff\xff')

    def set_async_lock(self, lock):
        self._async_lock = lock

    def load_material(self, path: str) -> Optional[Material]:
        if not path:
            return None
        cached = self._material_cache.get(path)
        if cached is not None:
            return cached
        eng = Engine.instance()
        root = eng.project_root if eng and eng.project_root else os.getcwd()
        abs_path = self._resolve_material_path(path, root)
        if not os.path.exists(abs_path):
            if os.path.splitext(os.path.basename(path))[0] == "ProBuilderPrototype":
                synth = self._synth_prototype_material(path)
                if synth is not None:
                    return synth
            if abs_path not in self._missing_warned:
                self._missing_warned.add(abs_path)
                Logger.warning(f"Material file not found: '{path}', using default")
            return None
        self._missing_warned.discard(abs_path)
        lib_mat = MaterialLibrary._materials.get(abs_path)
        if lib_mat is not None:
            self._material_cache[path] = lib_mat
            return lib_mat
        m = Material.load(abs_path, root)
        if m:
            self._material_cache[path] = m
        return m

    def _synth_prototype_material(self, path: str) -> Optional[Material]:
        try:
            eng_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tex = os.path.join(eng_root, "assets", "textures", "prototype_texture.png")
            if not os.path.exists(tex):
                tex = os.path.join(eng_root, "prototype_texture.png")
            m = Material("ProBuilderPrototype")
            m.shader_path = "default"
            m.properties = {
                "_BaseColor": [1.0, 1.0, 1.0, 1.0],
                "_Metallic": 0.0,
                "_Smoothness": 0.5,
                "_EmissionColor": [0.0, 0.0, 0.0, 0.0],
                "_EmissionIntensity": 0.0,
            }
            if os.path.exists(tex):
                m.properties["albedo_texture"] = tex
            self._material_cache[path] = m
            return m
        except Exception:
            return None

    def _resolve_material_path(self, path: str, root: str) -> str:
        if os.path.isabs(path):
            return os.path.normpath(path)
        if os.path.exists(path):
            return os.path.normpath(os.path.abspath(path))
        # Stored Windows absolute path ("C:/Users/...") — probe subpaths under root.
        if len(path) > 1 and path[1] == ":":
            parts = path.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(c):
                        return c
            return os.path.normpath(os.path.join(root, path))
        return os.path.normpath(os.path.join(root, path))

    def load_texture(self, path: str) -> Optional[Any]:
        if not path:
            return None
        abs_path = self._resolve_tex_path(path)
        if not abs_path:
            return None
        cached = self._texture_cache.get(abs_path)
        if cached is not None:
            try:
                now = time.monotonic()
            except Exception:
                now = 0.0
            try:
                last = self._tex_mtime_checked.get(abs_path, 0.0)
            except Exception:
                last = 0.0
            if (now - last) < _TEX_MTIME_TTL:
                try:
                    return cached[1]
                except Exception:
                    pass
            try:
                self._tex_mtime_checked[abs_path] = now
            except Exception:
                pass
            try:
                import_mtime = TextureImportSettings.import_mtime(abs_path)
            except Exception:
                try:
                    return cached[1]
                except Exception:
                    return None
            try:
                if abs(import_mtime - cached[0]) < 0.001:
                    return cached[1]
            except Exception:
                try:
                    return cached[1]
                except Exception:
                    return None
            try:
                try:
                    cached[1].release()
                except Exception:
                    pass
                self._texture_cache.pop(abs_path, None)
            except Exception:
                pass
            cached = None
        else:
            try:
                now = time.monotonic()
            except Exception:
                now = 0.0
            try:
                miss_at = self._tex_missing.get(abs_path, 0.0)
                if miss_at and (now - miss_at) < _TEX_MISSING_TTL:
                    return None
            except Exception:
                pass
            try:
                exists = os.path.exists(abs_path)
            except Exception:
                exists = False
            if not exists:
                try:
                    self._tex_missing[abs_path] = now
                    if len(self._tex_missing) > 1024:
                        self._tex_missing.clear()
                        self._tex_missing[abs_path] = now
                except Exception:
                    pass
                return None
            try:
                self._tex_missing.pop(abs_path, None)
            except Exception:
                pass
        try:
            if abs_path in self._tex_inflight:
                return None
        except Exception:
            pass
        try:
            if len(self._tex_inflight) > 1024:
                self._tex_inflight.clear()
            self._tex_inflight.add(abs_path)
        except Exception:
            pass
        try:
            self.load_texture_async(abs_path, lambda tex, p=abs_path: self._tex_inflight.discard(p))
        except Exception:
            try:
                self._tex_inflight.discard(abs_path)
            except Exception:
                pass
        return None

    def _resolve_tex_path(self, path: str) -> str:
        try:
            cached = self._tex_path_cache.get(path)
            if cached is not None:
                return cached
        except Exception:
            pass
        try:
            if os.path.exists(path):
                res = os.path.abspath(path)
                try:
                    self._tex_path_cache[path] = res
                    if len(self._tex_path_cache) > 2048:
                        self._tex_path_cache.clear()
                        self._tex_path_cache[path] = res
                except Exception:
                    pass
                return res
        except Exception:
            pass
        try:
            if not os.path.isabs(path):
                candidate = os.path.join(os.getcwd(), path)
                try:
                    if os.path.exists(candidate):
                        try:
                            self._tex_path_cache[path] = candidate
                            if len(self._tex_path_cache) > 2048:
                                self._tex_path_cache.clear()
                                self._tex_path_cache[path] = candidate
                        except Exception:
                            pass
                        return candidate
                except Exception:
                    pass
        except Exception:
            pass
        try:
            eng = Engine.instance()
        except Exception:
            eng = None
        try:
            root = eng.project_root if eng and eng.project_root else os.getcwd()
        except Exception:
            root = os.getcwd()
        try:
            if len(path) > 1 and path[1] == ":":
                parts = path.replace("\\", "/").split("/")
                for i in range(len(parts)):
                    sub = "/".join(parts[i:])
                    if sub:
                        c = os.path.normpath(os.path.join(root, sub))
                        try:
                            if os.path.exists(c):
                                res = c.replace("\\", "/")
                                try:
                                    self._tex_path_cache[path] = res
                                    if len(self._tex_path_cache) > 2048:
                                        self._tex_path_cache.clear()
                                        self._tex_path_cache[path] = res
                                except Exception:
                                    pass
                                return res
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            candidate = os.path.normpath(os.path.join(root, path))
        except Exception:
            try:
                self._tex_path_cache[path] = path
            except Exception:
                pass
            return path
        try:
            if os.path.exists(candidate):
                try:
                    self._tex_path_cache[path] = candidate
                    if len(self._tex_path_cache) > 2048:
                        self._tex_path_cache.clear()
                        self._tex_path_cache[path] = candidate
                except Exception:
                    pass
                return candidate
        except Exception:
            pass
        try:
            self._tex_path_cache[path] = path
            if len(self._tex_path_cache) > 2048:
                keep = self._tex_path_cache.get(path)
                self._tex_path_cache.clear()
                if keep is not None:
                    self._tex_path_cache[path] = keep
        except Exception:
            pass
        return path

    def load_texture_async(self, path: str, callback) -> None:
        try:
            if not path:
                try:
                    callback(None)
                except Exception:
                    pass
                return
        except Exception:
            return
        try:
            abs_path = self._resolve_tex_path(path)
        except Exception:
            abs_path = path
        try:
            if not abs_path or not os.path.exists(abs_path):
                try:
                    callback(None)
                except Exception:
                    pass
                return
        except Exception:
            try:
                callback(None)
            except Exception:
                pass
            return
        try:
            cached = self._texture_cache.get(abs_path)
            if cached is not None:
                try:
                    cached_mtime, cached_tex = cached
                except Exception:
                    cached = None
                if cached is not None:
                    try:
                        import_mtime = TextureImportSettings.import_mtime(abs_path)
                    except Exception:
                        import_mtime = cached_mtime
                    try:
                        if abs(import_mtime - cached_mtime) < 0.001:
                            try:
                                callback(cached_tex)
                            except Exception:
                                pass
                            return
                    except Exception:
                        try:
                            callback(cached_tex)
                        except Exception:
                            pass
                        return
        except Exception:
            pass
        try:
            from core.ecs.pool import asset as _get_asset_pool
        except Exception:
            try:
                callback(None)
            except Exception:
                pass
            return
        try:
            file_size = os.path.getsize(abs_path)
        except OSError:
            file_size = 0
        try:
            task_start("tex_load:" + abs_path, f"Loading texture {os.path.basename(abs_path)}...",
                       total=float(file_size) if file_size else None, units="bytes")
        except Exception:
            pass

        def _task():
            try:
                from PIL import Image
                img = Image.open(abs_path).convert("RGBA")
            except (ImportError, OSError, ValueError):
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
                return
            except Exception:
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
                return
            try:
                import_settings = TextureImportSettings.for_file(abs_path)
                w, h = img.size
                longest = max(w, h)
                if longest > import_settings.max_size:
                    scale = import_settings.max_size / longest
                    img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            except Exception:
                pass
            try:
                task_set_detail("tex_load:" + abs_path, f"{img.size[0]}×{img.size[1]}")
            except Exception:
                pass
            try:
                lock = self._async_lock
                if lock is not None:
                    with lock:
                        self._pending_texture_queue.append((abs_path, callback, img))
                else:
                    self._pending_texture_queue.append((abs_path, callback, img))
            except Exception:
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
        try:
            _get_asset_pool().submit(_task)
        except Exception:
            try:
                task_complete("tex_load:" + abs_path)
            except Exception:
                pass
            try:
                callback(None)
            except Exception:
                pass

    def process_texture_pending(self, max_textures: int | None = None, max_pixels: int | None = None) -> None:
        try:
            if not self._pending_texture_queue:
                return
        except Exception:
            return
        if max_textures is None:
            max_textures = _TEX_MAX_PER_FRAME
        if max_pixels is None:
            max_pixels = _TEX_MAX_PIXELS_PER_FRAME
        try:
            lock = self._async_lock
            if lock is not None:
                with lock:
                    items = self._pending_texture_queue
                    self._pending_texture_queue = []
            else:
                items = self._pending_texture_queue
                self._pending_texture_queue = []
        except Exception:
            return
        done = 0
        pixels = 0
        idx = 0
        for abs_path, callback, img in items:
            try:
                w, h = img.size
            except Exception:
                w, h = 0, 0
            if done >= max_textures or pixels + w * h > max_pixels:
                break
            try:
                import_settings = TextureImportSettings.for_file(abs_path)
                tex = self._ctx.texture(img.size, 4, img.tobytes())
                import_settings.apply_to_texture(tex)
                if os.path.basename(abs_path) == "prototype_texture.png":
                    try:
                        tex.repeat_x = True
                        tex.repeat_y = True
                    except Exception:
                        pass
                import_mtime = TextureImportSettings.import_mtime(abs_path)
                try:
                    old = self._texture_cache.get(abs_path)
                    if old is not None:
                        try:
                            old[1].release()
                        except Exception:
                            pass
                except Exception:
                    pass
                self._texture_cache[abs_path] = (import_mtime, tex)
                try:
                    self._tex_mtime_checked[abs_path] = time.monotonic()
                except Exception:
                    pass
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(tex)
                except Exception:
                    pass
            except Exception:
                try:
                    task_complete("tex_load:" + abs_path)
                except Exception:
                    pass
                try:
                    callback(None)
                except Exception:
                    pass
            done += 1
            pixels += w * h
            idx += 1
        if idx < len(items):
            try:
                rest = items[idx:]
                lock = self._async_lock
                if lock is not None:
                    with lock:
                        self._pending_texture_queue = rest + self._pending_texture_queue
                else:
                    self._pending_texture_queue = rest + self._pending_texture_queue
            except Exception:
                pass

    # Maps URP-style/PBR property names to default shader uniform names
    _UNIFORM_ALIASES = {
        "_EmissionColor": "u_emission",
        "emission_color": "u_emission",
        "_EmissionIntensity": None,
        "_Metallic": "u_metallic",
        "_Smoothness": "u_smoothness",
        "_BaseColor": "u_albedo_color",
        "_DoubleSided": "u_double_sided",
        "_Transmission": None,
        "_IOR": None,
    }

    def apply_material(self, mat: Optional[Material], prog: moderngl.Program, mr=None):
        pid = id(prog)
        names = self._prog_uniform_names.get(pid)
        if names is None:
            try:
                names = frozenset(prog)
            except Exception:
                names = frozenset()
            self._prog_uniform_names[pid] = names
        try:
            tiling = self._mesh_wants_tiling(mr)
        except Exception:
            tiling = False
        self._default_white.use(0)
        white4 = self._WHITE4
        zero3 = self._ZERO3
        if "u_albedo_tex" in names:
            prog["u_albedo_tex"].value = 0
        if "u_albedo_color" in names:
            prog["u_albedo_color"].write(white4)
        if "u_metallic" in names:
            prog["u_metallic"].value = 0.0
        if "u_smoothness" in names:
            prog["u_smoothness"].value = 0.5
        if "u_emission" in names:
            prog["u_emission"].write(zero3)
        if "u_normal_tex" in names:
            prog["u_normal_tex"].value = 0
        if "u_roughness_tex" in names:
            prog["u_roughness_tex"].value = 0
        if "u_use_albedo_tex" in names:
            prog["u_use_albedo_tex"].value = 0
        if "u_use_normal_tex" in names:
            prog["u_use_normal_tex"].value = 0
        if "u_use_roughness_tex" in names:
            prog["u_use_roughness_tex"].value = 0
        if "_BaseMap" in names:
            prog["_BaseMap"].value = 0
        if "_BaseColor" in names:
            prog["_BaseColor"].write(white4)
        if "_Metallic" in names:
            prog["_Metallic"].value = 0.0
        if "_Smoothness" in names:
            prog["_Smoothness"].value = 0.5
        if "_EmissionColor" in names:
            prog["_EmissionColor"].write(zero3)
        if "_EmissionIntensity" in names:
            prog["_EmissionIntensity"].value = 0.0
        if "_Transmission" in names:
            prog["_Transmission"].value = 0.0
        if "_IOR" in names:
            prog["_IOR"].value = 1.5
        if "_NormalMap" in names:
            prog["_NormalMap"].value = 0
        if "_OcclusionMap" in names:
            prog["_OcclusionMap"].value = 0
        if "_BaseMap_Active" in names:
            prog["_BaseMap_Active"].value = 0
        if "_NormalMap_Active" in names:
            prog["_NormalMap_Active"].value = 0
        if "_OcclusionMap_Active" in names:
            prog["_OcclusionMap_Active"].value = 0
        if "_HeightMap_Active" in names:
            prog["_HeightMap_Active"].value = 0
        if "_EmissionMap_Active" in names:
            prog["_EmissionMap_Active"].value = 0
        if "_DetailAlbedoMap_Active" in names:
            prog["_DetailAlbedoMap_Active"].value = 0
        if "_DetailNormalMap_Active" in names:
            prog["_DetailNormalMap_Active"].value = 0
        self._apply_mesh_uv(prog, names, mr)
        if mat is None:
            self._apply_mesh_sprite(prog, names, mr)
            return
        props = mat.properties
        try:
            _emit_scale = None
            for _ek in ("_EmissionIntensity", "emission_intensity"):
                if _ek in props:
                    _emit_scale = max(0.0, float(props[_ek]))
                    break
            if _emit_scale is None:
                _emit_scale = 1.0
        except Exception:
            _emit_scale = 1.0
        tex_unit = 1
        tex_uniform_map = self._TEX_UNIFORM_MAP
        active_names = self._prog_tex_active_names.setdefault(pid, {})
        for key, value in props.items():
            if isinstance(value, str):
                if not value:
                    tex_name = tex_uniform_map.get(key, key)
                    tex_active = 0
                    candidates = active_names.get(tex_name)
                    if candidates is None:
                        cand = []
                        a1 = f"{tex_name}_Active"
                        if a1 in names:
                            cand.append(a1)
                        if tex_name.startswith("u_"):
                            a2 = f"u_use_{tex_name[2:]}"
                            if a2 in names:
                                cand.append(a2)
                        active_names[tex_name] = cand
                        candidates = cand
                    for aname in candidates:
                        prog[aname].value = 0
                    continue
                tex_name = tex_uniform_map.get(key, key)
                if tex_name not in names:
                    continue
                tex = self.load_texture(value)
                if tex is not None:
                    tex.use(tex_unit)
                    self._ensure_tiling_wrap(tex, value, tiling)
                    prog[tex_name].value = tex_unit
                    tex_unit += 1
                    tex_active = 1
                else:
                    prog[tex_name].value = 0
                    tex_active = 0
                candidates = active_names.get(tex_name)
                if candidates is None:
                    cand = []
                    a1 = f"{tex_name}_Active"
                    if a1 in names:
                        cand.append(a1)
                    if tex_name.startswith("u_"):
                        a2 = f"u_use_{tex_name[2:]}"
                        if a2 in names:
                            cand.append(a2)
                    active_names[tex_name] = cand
                    candidates = cand
                for aname in candidates:
                    prog[aname].value = tex_active
                continue
            if key in names:
                self._set_uniform_value(prog, key, value)
            else:
                ukey = f"u_{key}"
                if ukey in names:
                    self._set_uniform_value(prog, ukey, value)
                else:
                    alias = self._UNIFORM_ALIASES.get(key)
                    if alias is not None and alias in names:
                        if alias == "u_emission" and key in ("_EmissionColor", "emission_color"):
                            self._set_emission_uniform(prog, alias, value, _emit_scale)
                        else:
                            self._set_uniform_value(prog, alias, value)
        self._apply_mesh_sprite(prog, names, mr)

    def _mesh_uv_sprite_state(self, mr):
        sx, sy = 1.0, 1.0
        ox, oy = 0.0, 0.0
        world = False
        sprite = ""
        if mr is None:
            return sx, sy, ox, oy, world, sprite
        try:
            v = getattr(mr, "uv_scale", None)
            if v is not None:
                try:
                    sx = float(v.x)
                    sy = float(v.y)
                except Exception:
                    sx = float(v[0])
                    sy = float(v[1])
        except Exception:
            pass
        try:
            v = getattr(mr, "uv_offset", None)
            if v is not None:
                try:
                    ox = float(v.x)
                    oy = float(v.y)
                except Exception:
                    ox = float(v[0])
                    oy = float(v[1])
        except Exception:
            pass
        try:
            world = bool(getattr(mr, "uv_scale_by_transform", False))
        except Exception:
            pass
        try:
            sprite = getattr(mr, "sprite_texture", "") or ""
        except Exception:
            pass
        return sx, sy, ox, oy, world, sprite

    def _apply_mesh_uv(self, prog, names, mr):
        try:
            sx, sy, ox, oy, world, _sprite = self._mesh_uv_sprite_state(mr)
            if "u_uv_scale" in names:
                prog["u_uv_scale"].write(np.array([sx, sy], dtype=np.float32).tobytes())
            if "u_uv_offset" in names:
                prog["u_uv_offset"].write(np.array([ox, oy], dtype=np.float32).tobytes())
            if "u_uv_world_scale" in names:
                prog["u_uv_world_scale"].value = 1.0 if world else 0.0
        except Exception:
            pass

    def _apply_mesh_sprite(self, prog, names, mr):
        try:
            _sx, _sy, _ox, _oy, _world, sprite = self._mesh_uv_sprite_state(mr)
        except Exception:
            sprite = ""
        if not sprite:
            return
        slot = None
        for tex_name, active_name in (("u_albedo_tex", "u_use_albedo_tex"), ("_BaseMap", "_BaseMap_Active")):
            if tex_name in names:
                slot = (tex_name, active_name)
                break
        if slot is None:
            return
        try:
            tex = self.load_texture(sprite)
        except Exception:
            tex = None
        if tex is None:
            return
        try:
            tex.use(1)
            try:
                self._ensure_tiling_wrap(tex, sprite, self._mesh_wants_tiling(mr))
            except Exception:
                pass
            prog[slot[0]].value = 1
            if slot[1] in names:
                prog[slot[1]].value = 1
        except Exception:
            pass

    def texture_has_alpha(self, path: str) -> bool:
        if not path:
            return False
        try:
            abs_path = self._resolve_tex_path(path)
        except Exception:
            return False
        if not abs_path or not os.path.exists(abs_path):
            return False
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            return False
        try:
            cached = self._tex_alpha_cache.get(abs_path)
            if cached is not None and abs(cached[0] - mtime) < 0.001:
                return cached[1]
        except Exception:
            pass
        result = False
        try:
            from PIL import Image
            with Image.open(abs_path) as img:
                bands = img.getbands()
                if "A" in bands:
                    try:
                        ext = img.split()[bands.index("A")].getextrema()
                        result = ext[0] < 255
                    except Exception:
                        result = True
                else:
                    try:
                        result = img.info.get("transparency", None) is not None
                    except Exception:
                        result = False
        except Exception:
            result = False
        try:
            self._tex_alpha_cache[abs_path] = (mtime, result)
            if len(self._tex_alpha_cache) > 1024:
                self._tex_alpha_cache.clear()
                self._tex_alpha_cache[abs_path] = (mtime, result)
        except Exception:
            pass
        return result

    def mesh_transparency(self, mr, mat) -> bool:
        alpha = 1.0
        alb = ""
        try:
            if mat is not None:
                props = mat.properties
                for k in ("_BaseColor", "albedo_color"):
                    v = props.get(k)
                    if isinstance(v, (list, tuple)) and len(v) > 3:
                        alpha = float(v[3])
                        break
                for k in ("albedo_texture", "_BaseMap"):
                    v = props.get(k)
                    if isinstance(v, str) and v:
                        alb = v
                        break
        except Exception:
            pass
        sprite = ""
        try:
            if mr is not None:
                sprite = getattr(mr, "sprite_texture", "") or ""
        except Exception:
            pass
        try:
            akey = round(float(alpha), 3)
        except Exception:
            akey = 1.0
        try:
            ckey = (id(mat) if mat is not None else 0, akey, alb, sprite)
            cached = self._transparency_cache.get(ckey)
            if cached is not None:
                return cached
        except Exception:
            ckey = None
        result = False
        try:
            if akey < 0.999:
                result = True
            elif alb and self.texture_has_alpha(alb):
                result = True
            elif sprite and self.texture_has_alpha(sprite):
                result = True
        except Exception:
            result = False
        try:
            if ckey is not None:
                self._transparency_cache[ckey] = result
                if len(self._transparency_cache) > 1024:
                    self._transparency_cache.clear()
                    self._transparency_cache[ckey] = result
        except Exception:
            pass
        return result

    def _mesh_wants_tiling(self, mr) -> bool:
        if mr is None:
            return False
        try:
            v = getattr(mr, "uv_scale", None)
            if v is not None:
                try:
                    sx = float(v.x)
                    sy = float(v.y)
                except Exception:
                    sx = float(v[0])
                    sy = float(v[1])
                if abs(sx - 1.0) > 1e-6 or abs(sy - 1.0) > 1e-6:
                    return True
        except Exception:
            pass
        try:
            v = getattr(mr, "uv_offset", None)
            if v is not None:
                try:
                    ox = float(v.x)
                    oy = float(v.y)
                except Exception:
                    ox = float(v[0])
                    oy = float(v[1])
                if abs(ox) > 1e-9 or abs(oy) > 1e-9:
                    return True
        except Exception:
            pass
        try:
            if bool(getattr(mr, "uv_scale_by_transform", False)):
                return True
        except Exception:
            pass
        return False

    def _texture_import_repeat(self, path_value: str) -> bool:
        try:
            cached = self._tex_wrap_cache.get(path_value)
            if cached is not None:
                return cached
        except Exception:
            pass
        rep = False
        try:
            abs_path = self._resolve_tex_path(path_value)
            if abs_path and os.path.exists(abs_path):
                rep = TextureImportSettings.for_file(abs_path).wrap_mode != "clamp"
        except Exception:
            pass
        try:
            self._tex_wrap_cache[path_value] = rep
            if len(self._tex_wrap_cache) > 1024:
                self._tex_wrap_cache.clear()
        except Exception:
            pass
        return rep

    def _ensure_tiling_wrap(self, tex, path_value: str, tiling: bool):
        try:
            if tiling or self._texture_import_repeat(path_value):
                tex.repeat_x = True
                tex.repeat_y = True
        except Exception:
            pass

    def _has_uniform(self, prog, name: str) -> bool:
        names = self._prog_uniform_names.get(id(prog))
        if names is None:
            try:
                names = frozenset(prog)
            except Exception:
                names = frozenset()
            self._prog_uniform_names[id(prog)] = names
        return name in names

    def _set_emission_uniform(self, prog, name: str, value, scale: float):
        try:
            arr = np.array(value, dtype=np.float32).ravel()
        except Exception:
            return
        try:
            rgb = np.zeros(3, dtype=np.float32)
            n = min(3, int(arr.size))
            if n > 0:
                rgb[:n] = arr[:n]
            rgb *= np.float32(max(0.0, float(scale)))
        except Exception:
            return
        if self._has_uniform(prog, name):
            try:
                prog[name].write(rgb.tobytes())
            except Exception as e:
                Logger.error(f"set_uniform {name} emission failed: {e}")

    def _set_uniform_value(self, prog, name: str, value):
        if isinstance(value, (float, int)):
            if self._has_uniform(prog, name):
                try:
                    prog[name].value = value
                except Exception as e:
                    Logger.error(f"set_uniform {name}={value} float failed: {e}")
        elif isinstance(value, (list, tuple)):
            if self._has_uniform(prog, name):
                try:
                    arr = np.array(value, dtype=np.float32)
                    uni = prog[name]
                    expected = uni.dimension
                    if len(arr) != expected:
                        arr = arr[:expected] if len(arr) > expected else np.pad(arr, (0, expected - len(arr)), 'constant')
                    uni.write(arr.tobytes())
                except Exception as e:
                    Logger.error(f"set_uniform {name}={value} list failed: {e}")
        elif isinstance(value, bool):
            if self._has_uniform(prog, name):
                try:
                    prog[name].value = 1 if value else 0
                except Exception as e:
                    Logger.error(f"set_uniform {name}={value} bool failed: {e}")

    def clear_caches(self):
        for _mtime, tex in self._texture_cache.values():
            try:
                tex.release()
            except Exception:
                pass
        self._texture_cache.clear()
        self._material_cache.clear()
        self._tex_alpha_cache.clear()
        self._tex_wrap_cache.clear()
        self._tex_path_cache.clear()
        self._transparency_cache.clear()

    def release(self):
        for _mtime, tex in self._texture_cache.values():
            try:
                tex.release()
            except Exception:
                pass
        try:
            self._default_white.release()
        except Exception:
            pass