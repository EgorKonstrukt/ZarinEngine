# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Scene uniforms and transparency helpers."""

from __future__ import annotations
import time
import moderngl
from core.components import LightType, LightAreaType
from core.components.lighting import Light, Projector
from core.renderer.types import RenderMode


class SceneUniformsMixin:
    """Scene uniforms and transparency helpers."""


    def _set_scene_uniforms(self, prog, view_f32, proj_f32, cam_pos, lights, disable_shadows=False):
        if "u_view" in prog:
            prog["u_view"].write(view_f32.tobytes())
        if "u_proj" in prog:
            prog["u_proj"].write(proj_f32.tobytes())
        if "u_camera_pos" in prog:
            buf = self._vec3_buf_a
            ca = cam_pos.to_array()
            buf[0] = ca[0]; buf[1] = ca[1]; buf[2] = ca[2]
            prog["u_camera_pos"].write(buf.tobytes())
        if "u_time" in prog:
            prog["u_time"].value = time.time()
        n_lights = min(len(lights), self._max_lights)
        abuf = self._ambient_buf
        proc_sun = None
        for i in range(n_lights):
            l, lt = lights[i]
            if l.light_type == LightType.DIRECTIONAL and getattr(l, "procedural_sky_lighting", False):
                proc_sun = (l, lt)
                break
        if self._render_mode == RenderMode.FLAT:
            if "u_ambient" in prog:
                abuf[0] = 1.0; abuf[1] = 1.0; abuf[2] = 1.0
                prog["u_ambient"].write(abuf.tobytes())
            if "u_light_count" in prog:
                prog["u_light_count"].value = 0
            n_lights = 0
        else:
            if "u_ambient" in prog:
                amb = self._ambient
                if proc_sun is not None:
                    try:
                        p_l, p_t = proc_sun
                        p_c, p_i = Light.shader_radiance(p_l, p_t)
                        e = -p_t.forward.y



                        day = Light._smoothstep(-0.14, 0.05, float(e))
                        scale = 0.3 + 0.7 * day
                        tint = [0.3 + 0.5 * p_c[0], 0.35 + 0.5 * p_c[1], 0.55 + 0.5 * p_c[2]]
                        abuf[0] = amb[0] * tint[0] * scale
                        abuf[1] = amb[1] * tint[1] * scale
                        abuf[2] = amb[2] * tint[2] * scale
                    except Exception:
                        abuf[0] = amb[0]; abuf[1] = amb[1]; abuf[2] = amb[2]
                else:
                    abuf[0] = amb[0]; abuf[1] = amb[1]; abuf[2] = amb[2]
                prog["u_ambient"].write(abuf.tobytes())
            if "u_light_count" in prog:
                prog["u_light_count"].value = n_lights
        if disable_shadows:
            shadow_light_idx = -1
        else:
            shadow_light_idx = -1
            for i, (l, lt) in enumerate(lights):
                if l.light_type == LightType.DIRECTIONAL and l.cast_shadows:
                    shadow_light_idx = i
                    break
        if "u_shadow_light_index" in prog:
            prog["u_shadow_light_index"].value = shadow_light_idx if shadow_light_idx >= 0 else -1
        for i in range(n_lights):
            l, lt = lights[i]
            unames = self._light_uniforms[i]
            if l.light_type == LightType.DIRECTIONAL:
                ltype_int = 0
            elif l.light_type == LightType.POINT:
                ltype_int = 1
            elif l.light_type == LightType.SPOT:
                ltype_int = 2
            else:
                ltype_int = 3
            if unames["type"] in prog:
                prog[unames["type"]].value = ltype_int
            pos = lt.position
            fwd = lt.forward
            if unames["position"] in prog:
                buf = self._vec3_buf_a
                buf[0] = pos.x; buf[1] = pos.y; buf[2] = pos.z
                prog[unames["position"]].write(buf.tobytes())
            if unames["direction"] in prog:
                buf = self._vec3_buf_b
                buf[0] = fwd.x; buf[1] = fwd.y; buf[2] = fwd.z
                prog[unames["direction"]].write(buf.tobytes())
            effective_color, effective_intensity = Light.shader_radiance(l, lt)
            if unames["color"] in prog:
                buf = self._vec3_buf_c
                ec = effective_color
                buf[0] = ec[0]; buf[1] = ec[1]; buf[2] = ec[2]
                prog[unames["color"]].write(buf.tobytes())
            if unames["intensity"] in prog:
                prog[unames["intensity"]].value = float(effective_intensity)
            if unames["range"] in prog:
                prog[unames["range"]].value = float(l.range)
            if unames["spot_angle"] in prog:
                prog[unames["spot_angle"]].value = float(l.spot_angle)
            if unames["spot_inner_angle"] in prog:
                prog[unames["spot_inner_angle"]].value = float(l.spot_inner_angle)
            if unames["right"] in prog:
                rv = lt.right
                buf = self._vec3_buf_a
                buf[0] = rv.x; buf[1] = rv.y; buf[2] = rv.z
                prog[unames["right"]].write(buf.tobytes())
            if unames["up"] in prog:
                uv = lt.up
                buf = self._vec3_buf_b
                buf[0] = uv.x; buf[1] = uv.y; buf[2] = uv.z
                prog[unames["up"]].write(buf.tobytes())
            if unames["area_width"] in prog:
                prog[unames["area_width"]].value = float(l.area_width)
            if unames["area_height"] in prog:
                prog[unames["area_height"]].value = float(l.area_height)
            if unames["area_type"] in prog:
                prog[unames["area_type"]].value = 0 if l.area_type == LightAreaType.RECT else 1
            if unames["area_samples"] in prog:
                prog[unames["area_samples"]].value = int(l.area_samples)
            if unames["area_double_sided"] in prog:
                prog[unames["area_double_sided"]].value = 1.0 if l.area_double_sided else 0.0
        if not disable_shadows:
            self._shadows.set_uniforms(prog)

        if "_WindDir" in prog or "_WindInfluence" in prog or "_WindStrength" in prog:
            try:
                wz = None
                if self._snap_cache and self._snap_cache.wind_zones:
                    for w in self._snap_cache.wind_zones:
                        if w.enabled:
                            wz = w
                            break
                if wz is not None:
                    s = wz.sample(0.0, 0.0)
                    d = s["dir"]
                    vboost = s.get("vertical_boost", 0.2)
                    if "_WindDir" in prog:
                        buf = self._vec3_buf_a
                        buf[0] = d[0]; buf[1] = vboost * 0.3; buf[2] = d[1]
                        prog["_WindDir"].write(buf.tobytes())
                    if "_WindInfluence" in prog:
                        prog["_WindInfluence"].value = 1.0
                    if "_WindStrength" in prog:
                        prog["_WindStrength"].value = min(3.0, s["speed"] * 0.015 + s["gust"] * 0.04)
                    if "_WindSpeed" in prog:
                        prog["_WindSpeed"].value = max(0.1, s["speed"] * 0.3)
                    if "_TurbulenceScale" in prog:
                        prog["_TurbulenceScale"].value = s.get("turbulence_scale", 1.5)
                    if "_TurbulenceAmount" in prog:
                        prog["_TurbulenceAmount"].value = s["turbulence"]
                    if "_LeafFlutterSpeed" in prog:
                        prog["_LeafFlutterSpeed"].value = 6.0 + s["speed"] * 0.5
                    if "_LeafFlutterAmount" in prog:
                        prog["_LeafFlutterAmount"].value = 0.02 + s.get("micro_turbulence", 0.0) * 0.1
                else:
                    if "_WindInfluence" in prog:
                        prog["_WindInfluence"].value = 0.0
            except Exception:
                pass


    def _mat_double_sided(self, mat) -> bool:
        if mat is None:
            return False
        props = mat.properties
        return bool(props.get("double_sided") or props.get("_double_sided"))


    def _uniform_names(self, prog) -> frozenset:
        key = id(prog)
        cached = self._prog_member_cache.get(key)
        if cached is not None:
            return cached
        try:
            names = frozenset(prog)
        except Exception:
            names = frozenset()
        self._prog_member_cache[key] = names
        return names


    def _render_mesh_double_sided(self, prog, mesh, double_sided: bool):
        ctx = self._ctx
        cull_on = bool(ctx.cull_face)
        if double_sided and cull_on:
            ctx.disable(moderngl.CULL_FACE)
        try:
            if "u_double_sided" in self._uniform_names(prog):
                try:
                    prog["u_double_sided"].value = 1 if double_sided else 0
                except Exception:
                    pass
            mesh.render(prog)
        finally:
            if double_sided and cull_on:
                ctx.enable(moderngl.CULL_FACE)


    def _partition_transparent(self, renderable):
        opaque = []
        transparent = []
        mm = self._materials
        if mm is None:
            try:
                self._last_has_sprite = False
            except Exception:
                pass
            return list(renderable), transparent
        try:
            ism = mm.mesh_transparency
            lm = mm.load_material
        except Exception:
            try:
                self._last_has_sprite = False
            except Exception:
                pass
            return list(renderable), transparent
        uniq = set()
        has_sprite = False
        uniq_add = uniq.add
        for e in renderable:
            mr = e[3]
            if mr is None:
                uniq_add("")
                continue
            sp = mr.sprite_texture
            if sp:
                has_sprite = True
                break
            mats = mr.materials
            if not mats:
                uniq_add("")
            else:
                sub = e[5]
                if sub < len(mats):
                    uniq_add(mats[sub].get("path", ""))
                else:
                    uniq_add(mats[-1].get("path", ""))
        if has_sprite:
            try:
                self._last_has_sprite = True
                self._last_uniq = None
                self._last_trans = None
            except Exception:
                pass
            for e in renderable:
                try:
                    mr = e[3]
                    sub = e[5] if len(e) > 5 else 0
                    mat = lm(mr.get_material_path(sub) if mr else "")
                    if ism(mr, mat):
                        transparent.append(e)
                    else:
                        opaque.append(e)
                except Exception:
                    opaque.append(e)
            return opaque, transparent
        trans_set = set()
        for p in uniq:
            try:
                mat = lm(p)
                if ism(None, mat):
                    trans_set.add(p)
            except Exception:
                pass
        try:
            self._last_has_sprite = False
            self._last_uniq = frozenset(uniq)
            self._last_trans = frozenset(trans_set)
        except Exception:
            pass
        if not trans_set:
            return list(renderable), transparent
        for e in renderable:
            mr = e[3]
            if mr is None:
                opaque.append(e)
                continue
            mats = mr.materials
            if not mats:
                opaque.append(e)
            else:
                sub = e[5]
                if sub < len(mats):
                    p = mats[sub].get("path", "")
                else:
                    p = mats[-1].get("path", "")
                if p in trans_set:
                    transparent.append(e)
                else:
                    opaque.append(e)
        return opaque, transparent


    def _sort_transparent_far_first(self, entries, cam_pos):
        try:
            cx = float(cam_pos.x)
            cy = float(cam_pos.y)
            cz = float(cam_pos.z)
        except Exception:
            return
        try:
            entries.sort(key=lambda e: -(((float(e[4]._d[3, 0]) - cx) ** 2) + ((float(e[4]._d[3, 1]) - cy) ** 2) + ((float(e[4]._d[3, 2]) - cz) ** 2)))
        except Exception:
            pass


    def _sort_opaque_front_first(self, entries, cam_pos):
        try:
            n = len(entries)
        except Exception:
            return
        if n < 64:
            return
        try:
            cx = float(cam_pos.x)
            cy = float(cam_pos.y)
            cz = float(cam_pos.z)
        except Exception:
            return
        try:
            import numpy as _np
            try:
                from core._render_utils import build_frustum_cull_inputs as _bfci
                centers, _ = _bfci(entries)
            except ImportError:
                centers = _np.empty((n, 3), dtype=_np.float64)
                for _i, _e in enumerate(entries):
                    _d = _e[4]._d
                    centers[_i, 0] = _d[3, 0]
                    centers[_i, 1] = _d[3, 1]
                    centers[_i, 2] = _d[3, 2]
            _dx = centers[:, 0] - cx
            _dy = centers[:, 1] - cy
            _dz = centers[:, 2] - cz
            _idx = _np.argsort(_dx * _dx + _dy * _dy + _dz * _dz, kind="stable")
            _ordered = [entries[int(_i)] for _i in _idx]
            entries[:] = _ordered
        except Exception:
            pass
