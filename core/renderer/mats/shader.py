# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Optional

import moderngl
import numpy as np

from core.assets.matp import Material, MaterialLibrary
from core.assets.texture_import_settings import TextureImportSettings
from core.engine.eng import Engine
from core.foundation.logger import Logger
from core.foundation.progress import task_complete, task_set_detail, task_start

class MaterialShaderMixin:
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

def extract_properties_block(text):
    idx = text.find("Properties")
    if idx < 0:
        return ""
    brace = text.find("{", idx)
    if brace < 0:
        return ""
    depth = 0
    start = brace
    n = len(text)
    i = brace
    while i < n:
        c = text[i]
        if c == "{":
            depth = depth + 1
        elif c == "}":
            depth = depth - 1
            if depth == 0:
                return text[start + 1:i]
        i = i + 1
    return ""

def _strip_parens(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == "(" and s[len(s) - 1] == ")":
        return s[1:len(s) - 1].strip()
    return s

def _split_top_commas(s):
    parts = []
    cur = ""
    depth = 0
    in_str = False
    q = ""
    for ch in s:
        if in_str:
            cur = cur + ch
            if ch == q:
                in_str = False
            continue
        if ch == "\"" or ch == "'":
            in_str = True
            q = ch
            cur = cur + ch
            continue
        if ch == "(" or ch == "[":
            depth = depth + 1
            cur = cur + ch
            continue
        if ch == ")" or ch == "]":
            depth = depth - 1
            cur = cur + ch
            continue
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
            continue
        cur = cur + ch
    if cur.strip() != "":
        parts.append(cur.strip())
    return parts

def _parse_default_value(raw):
    raw = raw.strip()
    if raw == "":
        return raw
    if raw[0] == "(" and raw[len(raw) - 1] == ")":
        inner = raw[1:len(raw) - 1].strip()
        items = _split_top_commas(inner)
        vals = []
        for it in items:
            it = it.strip()
            try:
                vals.append(float(it))
            except Exception:
                vals.append(it)
        return vals
    if len(raw) >= 2 and raw[0] == "\"" and raw[len(raw) - 1] == "\"":
        return raw[1:len(raw) - 1]
    if len(raw) >= 2 and raw[0] == "'" and raw[len(raw) - 1] == "'":
        return raw[1:len(raw) - 1]
    try:
        return float(raw)
    except Exception:
        return raw

def _parse_property_line(line):
    line = line.strip()
    if line == "" or line.startswith("["):
        return None
    if line.startswith("//"):
        return None
    eq = line.find("=")
    if eq < 0:
        return None
    left = line[:eq].strip()
    right = line[eq + 1:].strip()
    if right.endswith("{}"):
        right = right[:len(right) - 2].strip()
    sp = left.find(" ")
    if sp < 0:
        return None
    name = left[:sp].strip()
    rest = left[sp:].strip()
    display = ""
    ptype = ""
    if rest.startswith("("):
        close = rest.rfind(")")
        if close >= 0:
            inner = rest[1:close]
            parts = _split_top_commas(inner)
            if len(parts) >= 1:
                d = parts[0].strip()
                if len(d) >= 2 and d[0] == "\"" and d[len(d) - 1] == "\"":
                    display = d[1:len(d) - 1]
                else:
                    display = d
            if len(parts) >= 2:
                ptype = parts[1].strip()
            else:
                ptype = "Float"
        else:
            ptype = "Float"
    else:
        ptype = rest
    if name == "":
        return None
    return (name, {"display": display, "type": ptype, "default": _parse_default_value(right)})

def parse_shader_properties(text):
    block = extract_properties_block(text)
    if block == "":
        return {}
    out = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if line == "" or line == "{" or line == "}":
            continue
        parsed = _parse_property_line(line)
        if parsed is None:
            continue
        k, v = parsed
        out[k] = v
    return out

def load_shader_properties(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {}
    return parse_shader_properties(text)
