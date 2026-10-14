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

from core.assets.matp import Material, MaterialLibrary
from core.assets.texture_import_settings import TextureImportSettings
from core.engine.eng import Engine
from core.foundation.logger import Logger
from core.foundation.progress import task_complete, task_set_detail, task_start

class MaterialPropsMixin:

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
        if "_Thickness" in names:
            prog["_Thickness"].value = 0.1
        if "_Cutoff" in names:
            prog["_Cutoff"].value = 0.5
        if "_NormalStrength" in names:
            prog["_NormalStrength"].value = 1.0
        if "_OcclusionStrength" in names:
            prog["_OcclusionStrength"].value = 1.0
        if "_HeightScale" in names:
            prog["_HeightScale"].value = 0.05
        if "_ClearCoat" in names:
            prog["_ClearCoat"].value = 0.0
        if "_ClearCoatRoughness" in names:
            prog["_ClearCoatRoughness"].value = 0.1
        if "_Anisotropy" in names:
            prog["_Anisotropy"].value = 0.0
        if "_AnisotropyDirection" in names:
            prog["_AnisotropyDirection"].value = 0.0
        if "_DetailNormalStrength" in names:
            prog["_DetailNormalStrength"].value = 1.0
        if "_DetailUVScale" in names:
            prog["_DetailUVScale"].value = 4.0
        if "_SubsurfaceAmount" in names:
            prog["_SubsurfaceAmount"].value = 0.0
        if "_SubsurfaceColor" in names:
            prog["_SubsurfaceColor"].write(np.array([1.0, 1.0, 1.0], dtype=np.float32).tobytes())
        if "_ThinFilmThickness" in names:
            prog["_ThinFilmThickness"].value = 0.0
        if "_ThinFilmIntensity" in names:
            prog["_ThinFilmIntensity"].value = 0.0
        if "u_transmission_bg_active" in names:
            prog["u_transmission_bg_active"].value = 0.0
        if "u_transmission_bg_lod" in names:
            prog["u_transmission_bg_lod"].value = 5.0
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
        try:
            bg = self._transmission_bg
        except Exception:
            bg = None
        if bg is not None and "u_transmission_bg" in names:
            try:
                trans = 0.0
                if mat is not None:
                    props = mat.properties
                    trans = float(props.get("_Transmission", props.get("transmission", 0.0)))
            except Exception:
                trans = 0.0
            if trans > 0.001:
                try:
                    btex, bw, bh = bg
                except Exception:
                    btex, bw, bh = bg, 0, 0
                try:
                    unit = tex_unit if tex_unit > 1 else 2
                    btex.use(unit)
                    prog["u_transmission_bg"].value = unit
                    if "u_transmission_bg_texel" in names and bw and bh:
                        prog["u_transmission_bg_texel"].write(np.array([1.0 / float(bw), 1.0 / float(bh)], dtype=np.float32).tobytes())
                    if "u_transmission_bg_lod" in names:
                        try:
                            _mw = max(int(bw), int(bh))
                            _lod = _mw.bit_length() - 4
                            if _lod < 2:
                                _lod = 2
                            if _lod > 6:
                                _lod = 6
                            prog["u_transmission_bg_lod"].value = float(_lod)
                        except Exception:
                            pass
                    if "u_transmission_bg_active" in names:
                        prog["u_transmission_bg_active"].value = 1.0
                except Exception:
                    pass

    def mesh_transparency(self, mr, mat) -> bool:
        alpha = 1.0
        alb = ""
        trans = 0.0
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
                for k in ("_Transmission", "transmission"):
                    v = props.get(k)
                    if v is not None:
                        try:
                            trans = max(trans, float(v))
                        except Exception:
                            pass
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
            tkey = round(float(trans), 3)
        except Exception:
            tkey = 0.0
        try:
            ckey = (id(mat) if mat is not None else 0, akey, alb, sprite, tkey)
            cached = self._transparency_cache.get(ckey)
            if cached is not None:
                return cached
        except Exception:
            ckey = None
        result = False
        try:
            if akey < 0.999:
                result = True
            elif tkey > 0.001:
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

    def shadow_transparency_class(self, path: str) -> int:
        try:
            mat = self.load_material(path)
        except Exception:
            return 0
        if mat is None:
            return 0
        try:
            props = mat.properties
        except Exception:
            return 0
        try:
            alpha = 1.0
            for k in ("_BaseColor", "albedo_color"):
                v = props.get(k)
                if isinstance(v, (list, tuple)) and len(v) > 3:
                    alpha = float(v[3])
                    break
            trans = 0.0
            for k in ("_Transmission", "transmission"):
                v = props.get(k)
                if v is not None:
                    try:
                        trans = max(trans, float(v))
                    except Exception:
                        pass
        except Exception:
            return 0
        try:
            if trans > 0.001:
                return 1
            if alpha < 0.999:
                return 1
        except Exception:
            pass
        return 0

    def stained_tint(self, path: str) -> tuple:
        try:
            mat = self.load_material(path)
        except Exception:
            return (1.0, 1.0, 1.0)
        if mat is None:
            return (1.0, 1.0, 1.0)
        try:
            props = mat.properties
            alb = props.get("_BaseColor", props.get("albedo_color", None))
            if isinstance(alb, (list, tuple)) and len(alb) >= 3:
                r = max(0.0, min(1.0, float(alb[0])))
                g = max(0.0, min(1.0, float(alb[1])))
                b = max(0.0, min(1.0, float(alb[2])))
                a = float(alb[3]) if len(alb) > 3 else 1.0
            else:
                r, g, b, a = 1.0, 1.0, 1.0, 1.0
            try:
                trans = max(float(props.get("_Transmission", 0.0)), float(props.get("transmission", 0.0)))
            except Exception:
                trans = 0.0
            if trans > 0.001:
                return (r, g, b)
            a = max(0.0, min(1.0, a))
            return (1.0 + (r - 1.0) * a, 1.0 + (g - 1.0) * a, 1.0 + (b - 1.0) * a)
        except Exception:
            return (1.0, 1.0, 1.0)

