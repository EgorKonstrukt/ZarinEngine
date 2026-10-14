# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
import moderngl
from core.components import LightType, LightAreaType
from core.components.lighting import Light
from core.renderer.origin import origin_for, relativize_view_bytes
from core.renderer.types import RenderMode


class SceneUniformsCoreMixin:
    def _set_scene_uniforms(self, prog, view_f32, proj_f32, cam_pos, lights, disable_shadows=False):
        names = self._uniform_names(prog)
        origin = origin_for(cam_pos)
        try:
            ox = float(origin[0]); oy = float(origin[1]); oz = float(origin[2])
        except Exception:
            origin = None
            ox = 0.0; oy = 0.0; oz = 0.0
        if "u_view" in names:
            prog["u_view"].write(relativize_view_bytes(view_f32, origin))
        if "u_proj" in names:
            prog["u_proj"].write(proj_f32.tobytes())
        if "u_camera_pos" in names:
            buf = self._vec3_buf_a
            ca = cam_pos.to_array()
            buf[0] = ca[0] - ox; buf[1] = ca[1] - oy; buf[2] = ca[2] - oz
            prog["u_camera_pos"].write(buf.tobytes())
        if "u_time" in names:
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
            if "u_ambient" in names:
                abuf[0] = 1.0; abuf[1] = 1.0; abuf[2] = 1.0
                prog["u_ambient"].write(abuf.tobytes())
            if "u_light_count" in names:
                prog["u_light_count"].value = 0
            n_lights = 0
        else:
            if "u_ambient" in names:
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
            if "u_light_count" in names:
                prog["u_light_count"].value = n_lights
        if disable_shadows:
            shadow_light_idx = -1
        else:
            shadow_light_idx = -1
            for i, (l, lt) in enumerate(lights):
                if l.light_type == LightType.DIRECTIONAL and l.cast_shadows:
                    shadow_light_idx = i
                    break
        if "u_shadow_light_index" in names:
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
            if unames["type"] in names:
                prog[unames["type"]].value = ltype_int
            pos = lt.position
            fwd = lt.forward
            if unames["position"] in names:
                buf = self._vec3_buf_a
                buf[0] = pos.x - ox; buf[1] = pos.y - oy; buf[2] = pos.z - oz
                prog[unames["position"]].write(buf.tobytes())
            if unames["direction"] in names:
                buf = self._vec3_buf_b
                buf[0] = fwd.x; buf[1] = fwd.y; buf[2] = fwd.z
                prog[unames["direction"]].write(buf.tobytes())
            effective_color, effective_intensity = Light.shader_radiance(l, lt)
            if unames["color"] in names:
                buf = self._vec3_buf_c
                ec = effective_color
                buf[0] = ec[0]; buf[1] = ec[1]; buf[2] = ec[2]
                prog[unames["color"]].write(buf.tobytes())
            if unames["intensity"] in names:
                prog[unames["intensity"]].value = float(effective_intensity)
            if unames["range"] in names:
                prog[unames["range"]].value = float(l.range)
            if unames["spot_angle"] in names:
                prog[unames["spot_angle"]].value = float(l.spot_angle)
            if unames["spot_inner_angle"] in names:
                prog[unames["spot_inner_angle"]].value = float(l.spot_inner_angle)
            if unames["right"] in names:
                rv = lt.right
                buf = self._vec3_buf_a
                buf[0] = rv.x; buf[1] = rv.y; buf[2] = rv.z
                prog[unames["right"]].write(buf.tobytes())
            if unames["up"] in names:
                uv = lt.up
                buf = self._vec3_buf_b
                buf[0] = uv.x; buf[1] = uv.y; buf[2] = uv.z
                prog[unames["up"]].write(buf.tobytes())
            if unames["area_width"] in names:
                prog[unames["area_width"]].value = float(l.area_width)
            if unames["area_height"] in names:
                prog[unames["area_height"]].value = float(l.area_height)
            if unames["area_type"] in names:
                prog[unames["area_type"]].value = 0 if l.area_type == LightAreaType.RECT else 1
            if unames["area_samples"] in names:
                prog[unames["area_samples"]].value = int(l.area_samples)
            if unames["area_double_sided"] in names:
                prog[unames["area_double_sided"]].value = 1.0 if l.area_double_sided else 0.0
        if not disable_shadows:
            self._shadows.set_uniforms(prog, origin)
        if "_WindDir" in names or "_WindInfluence" in names or "_WindStrength" in names:
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
                    if "_WindDir" in names:
                        buf = self._vec3_buf_a
                        buf[0] = d[0]; buf[1] = vboost * 0.3; buf[2] = d[1]
                        prog["_WindDir"].write(buf.tobytes())
                    if "_WindInfluence" in names:
                        prog["_WindInfluence"].value = 1.0
                    if "_WindStrength" in names:
                        prog["_WindStrength"].value = min(3.0, s["speed"] * 0.015 + s["gust"] * 0.04)
                    if "_WindSpeed" in names:
                        prog["_WindSpeed"].value = max(0.1, s["speed"] * 0.3)
                    if "_TurbulenceScale" in names:
                        prog["_TurbulenceScale"].value = s.get("turbulence_scale", 1.5)
                    if "_TurbulenceAmount" in names:
                        prog["_TurbulenceAmount"].value = s["turbulence"]
                    if "_LeafFlutterSpeed" in names:
                        prog["_LeafFlutterSpeed"].value = 6.0 + s["speed"] * 0.5
                    if "_LeafFlutterAmount" in names:
                        prog["_LeafFlutterAmount"].value = 0.02 + s.get("micro_turbulence", 0.0) * 0.1
                else:
                    if "_WindInfluence" in names:
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

    def _render_mesh_double_sided(self, prog, mesh, double_sided: bool, two_pass: bool = False):
        ctx = self._ctx
        cull_on = bool(ctx.cull_face)
        if double_sided and cull_on and not two_pass:
            ctx.disable(moderngl.CULL_FACE)
        try:
            if "u_double_sided" in self._uniform_names(prog):
                try:
                    prog["u_double_sided"].value = 1 if double_sided else 0
                except Exception:
                    pass
            if double_sided and cull_on and two_pass:
                try:
                    ctx.cull_face = "front"
                except Exception:
                    pass
                mesh.render(prog)
                try:
                    ctx.cull_face = "back"
                except Exception:
                    pass
                mesh.render(prog)
            else:
                mesh.render(prog)
        finally:
            if double_sided and cull_on and two_pass:
                try:
                    ctx.cull_face = "back"
                except Exception:
                    pass
                try:
                    ctx.enable(moderngl.CULL_FACE)
                except Exception:
                    pass
            elif double_sided and cull_on:
                ctx.enable(moderngl.CULL_FACE)
