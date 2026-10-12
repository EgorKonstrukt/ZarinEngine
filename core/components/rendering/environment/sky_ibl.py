# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import os
import time
from collections import OrderedDict
import numpy as np
import moderngl
from typing import Optional
from core.components.rendering.environment.dynamic_cubemap import (
    _allocate_cube_mip_levels,
    _attach_cubemap_face,
    _BRDF_LUT_FRAG,
    _FACE_BASIS,
    _FACE_DIRS,
    _FULLSCREEN_QUAD_VERT,
    _IRRADIANCE_FRAG,
    _PREFILTER_FRAG,
    _PREFILTER_MAX_LOD,
    _restore_framebuffer,
    _write_cube_face_mip,
)

_EQUIRECT_TO_CUBE_FRAG = """
#version 330 core
in vec2 v_uv;
out vec4 frag_color;
uniform sampler2D u_equirect;
uniform vec3 u_face_x;
uniform vec3 u_face_y;
uniform vec3 u_face_z;
uniform float u_exposure;
uniform float u_intensity;
uniform vec3 u_tint;
uniform float u_saturation;
uniform mat3 u_rotation;
uniform float u_flip_y;
const float PI = 3.14159265359;
void main() {
    vec2 tc = v_uv * 2.0 - 1.0;
    vec3 dir = normalize(u_rotation * normalize(u_face_x * tc.x + u_face_y * tc.y + u_face_z));
    vec2 uv = vec2(0.5 + atan(dir.z, dir.x) / 6.28318530718, acos(clamp(dir.y, -1.0, 1.0)) / PI);
    if (u_flip_y > 0.5) {
        uv.y = 1.0 - uv.y;
    }
    vec3 col = texture(u_equirect, uv).rgb;
    col *= exp2(u_exposure) * u_intensity;
    float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
    col = mix(vec3(luma), col, u_saturation) * u_tint;
    frag_color = vec4(col, 1.0);
}
"""

_IDENTITY_MAT3 = np.eye(3, dtype=np.float32).T.tobytes()

_SKY_IBL_CACHE: dict = {}
_SKY_IBL_CACHE_MAX = 8


class SkyIbl:
    def __init__(self):
        self._irradiance_tex: Optional[moderngl.TextureCube] = None
        self._prefilter_tex: Optional[moderngl.TextureCube] = None
        self._brdf_lut_tex: Optional[moderngl.Texture] = None
        self.ready = False

    def bind(self, prog: moderngl.Program, start_unit: int = 14):
        unit = start_unit
        if self._irradiance_tex is not None:
            self._irradiance_tex.use(unit)
            try:
                prog["u_irradiance_map"].value = unit
                prog["u_irradiance_map_Active"].value = 1
            except Exception:
                pass
            unit += 1
        if self._prefilter_tex is not None:
            self._prefilter_tex.use(unit)
            try:
                prog["u_prefilter_map"].value = unit
                prog["u_prefilter_map_Active"].value = 1
            except Exception:
                pass
            unit += 1
        if self._brdf_lut_tex is not None:
            self._brdf_lut_tex.use(unit)
            try:
                prog["u_brdf_lut"].value = unit
                prog["u_brdf_lut_Active"].value = 1
            except Exception:
                pass
            unit += 1
        try:
            if "u_env_map_rotation" in prog:
                prog["u_env_map_rotation"].value = 0.0
        except Exception:
            pass
        return unit

    def release(self):
        seen = set()
        for tex in (self._irradiance_tex, self._prefilter_tex, self._brdf_lut_tex):
            if tex is not None and id(tex) not in seen:
                seen.add(id(tex))
                try:
                    tex.release()
                except Exception:
                    pass
        self._irradiance_tex = None
        self._prefilter_tex = None
        self._brdf_lut_tex = None
        self.ready = False


def _make_face_vao(ctx: moderngl.Context, prog: moderngl.Program):
    verts = np.array([
        -1, -1, 0, 0,
         1, -1, 1, 0,
         1,  1, 1, 1,
        -1, -1, 0, 0,
         1,  1, 1, 1,
        -1,  1, 0, 1,
    ], dtype=np.float32)
    vbo = ctx.buffer(verts.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "2f 2f", "in_position", "in_uv")])
    return vao, vbo


_SCRATCH: dict[int, tuple] = {}
_SCRATCH_MAX: int = 8
_BRDF_BYTES: dict[int, tuple] = {}
_BRDF_BYTES: dict[int, tuple] = {}


def _get_scratch(ctx: moderngl.Context):
    import weakref
    cid = id(ctx)
    ent = _SCRATCH.get(cid)
    if ent is not None:
        try:
            if ent[0]() is ctx:
                return ent[1]
        except Exception:
            pass
    try:
        ref = weakref.ref(ctx)
    except Exception:
        ref = None
    try:
        dummy = ctx.texture((1, 1), 4, dtype="f4")
        fbo = ctx.framebuffer(color_attachments=[dummy])
    except Exception:
        return None
    rec = {"fbo": fbo, "dummy": dummy, "face_vaos": {}, "sky_mesh": None, "sky_vaos": {}}
    try:
        if len(_SCRATCH) >= _SCRATCH_MAX:
            for k in [k for k, v in _SCRATCH.items() if v[0] is None or v[0]() is None]:
                _SCRATCH.pop(k, None)
        if len(_SCRATCH) >= _SCRATCH_MAX:
            _SCRATCH.pop(next(iter(_SCRATCH)), None)
        _SCRATCH[cid] = (ref, rec)
    except Exception:
        pass
    return rec


def _scratch_face_vao(ctx: moderngl.Context, rec, prog):
    try:
        d = rec["face_vaos"]
    except Exception:
        return None
    try:
        ent = d.get(id(prog))
    except Exception:
        ent = None
    if ent is not None:
        return ent
    try:
        vao, vbo = _make_face_vao(ctx, prog)
    except Exception:
        return None
    try:
        if len(d) >= 32:
            d.clear()
        d[id(prog)] = (vao, vbo)
    except Exception:
        pass
    return (vao, vbo)


def _scratch_sky_mesh(ctx: moderngl.Context, rec, prog):
    try:
        cached = rec.get("sky_mesh")
    except Exception:
        cached = None
    if cached is not None:
        vbo, ibo = cached
        try:
            vao = rec["sky_vaos"].get(id(prog))
        except Exception:
            vao = None
        if vao is not None:
            return vao
        try:
            vao = ctx.vertex_array(prog, [(vbo, "3f", "in_position")], ibo)
            rec["sky_vaos"][id(prog)] = vao
            return vao
        except Exception:
            return None
    try:
        from core.renderer.meshes import make_cube_mesh
        mesh = make_cube_mesh()
        vbo = ctx.buffer(mesh.vertices.tobytes())
        ibo = ctx.buffer(mesh.indices.astype(np.uint32).tobytes())
        vao = ctx.vertex_array(prog, [(vbo, "3f", "in_position")], ibo)
    except Exception:
        return None
    try:
        rec["sky_mesh"] = (vbo, ibo)
        rec["sky_vaos"][id(prog)] = vao
    except Exception:
        pass
    return vao


def _begin_cube_face(ctx: moderngl.Context, rec, tex, face: int, level: int, size: int):
    try:
        fbo = rec["fbo"]
    except Exception:
        return None
    try:
        fbo.use()
    except Exception:
        return None
    try:
        ok = _attach_cubemap_face(tex.glo, face, level)
    except Exception:
        ok = False
    if not ok:
        return None
    try:
        fbo.viewport = (0, 0, size, size)
    except Exception:
        pass
    return fbo


def _blit_cube_face_fallback(ctx: moderngl.Context, tex, face: int, level: int, size: int, draw):
    try:
        face_tex = ctx.texture((size, size), 4, dtype="f4")
        fbo = ctx.framebuffer(color_attachments=[face_tex])
        fbo.use()
        fbo.viewport = (0, 0, size, size)
        ctx.clear(0.0, 0.0, 0.0, 1.0)
        draw()
        _write_cube_face_mip(tex, face, level, size, face_tex.read())
        fbo.release()
        face_tex.release()
        return True
    except Exception:
        return False


_IBL_PROGS: dict[int, tuple] = {}


def _get_ibl_progs(ctx: moderngl.Context):
    import weakref
    cid = id(ctx)
    cached = _IBL_PROGS.get(cid)
    if cached is not None:
        try:
            if cached[0]() is ctx:
                return cached[1]
        except Exception:
            pass
    try:
        ref = weakref.ref(ctx)
    except Exception:
        ref = None
    equirect = ctx.program(vertex_shader=_FULLSCREEN_QUAD_VERT, fragment_shader=_EQUIRECT_TO_CUBE_FRAG)
    prefilter = ctx.program(vertex_shader=_FULLSCREEN_QUAD_VERT, fragment_shader=_PREFILTER_FRAG)
    irradiance = ctx.program(vertex_shader=_FULLSCREEN_QUAD_VERT, fragment_shader=_IRRADIANCE_FRAG)
    brdf = ctx.program(vertex_shader=_FULLSCREEN_QUAD_VERT, fragment_shader=_BRDF_LUT_FRAG)
    if len(_IBL_PROGS) > 16:
        for k in [k for k, v in _IBL_PROGS.items() if v[0]() is None]:
            _IBL_PROGS.pop(k, None)
    _IBL_PROGS[cid] = (ref, (equirect, prefilter, irradiance, brdf))
    return equirect, prefilter, irradiance, brdf


def _render_cubemap_from_equirect(ctx: moderngl.Context, env_tex: moderngl.Texture, res: int, grade=None):
    cube_tex = ctx.texture_cube((res, res), 4, dtype="f4")
    cube_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    cube_tex.repeat_x = False
    cube_tex.repeat_y = False
    prog = _get_ibl_progs(ctx)[0]
    vao, vbo = _make_face_vao(ctx, prog)
    env_tex.use(0)
    prog["u_equirect"].value = 0
    try:
        prog["u_exposure"].value = float(grade.get("exposure", 0.0)) if grade else 0.0
    except Exception:
        pass
    try:
        prog["u_intensity"].value = float(grade.get("intensity", 1.0)) if grade else 1.0
    except Exception:
        pass
    try:
        _t = grade.get("tint", (1.0, 1.0, 1.0)) if grade else (1.0, 1.0, 1.0)
        prog["u_tint"].value = (float(_t[0]), float(_t[1]), float(_t[2]))
    except Exception:
        pass
    try:
        prog["u_saturation"].value = float(grade.get("saturation", 1.0)) if grade else 1.0
    except Exception:
        pass
    try:
        _r = grade.get("rotation") if grade else None
        prog["u_rotation"].write(_r if _r else _IDENTITY_MAT3)
    except Exception:
        pass
    try:
        prog["u_flip_y"].value = float(grade.get("flip_y", 0.0)) if grade else 0.0
    except Exception:
        pass
    ctx.disable(moderngl.DEPTH_TEST)
    ctx.disable(moderngl.CULL_FACE)
    prev_fbo = ctx.fbo
    try:
        for face in range(6):
            fx, fy, fz = _FACE_BASIS[face]
            face_tex = ctx.texture((res, res), 4, dtype="f4")
            fbo = ctx.framebuffer(color_attachments=[face_tex])
            fbo.use()
            fbo.viewport = (0, 0, res, res)
            ctx.clear(0.0, 0.0, 0.0, 1.0)
            prog["u_face_x"].value = fx
            prog["u_face_y"].value = fy
            prog["u_face_z"].value = fz
            vao.render(moderngl.TRIANGLES)
            cube_tex.write(face, face_tex.read())
            fbo.release()
            face_tex.release()
    finally:
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
        vao.release()
        vbo.release()
    return cube_tex


def _render_irradiance(ctx: moderngl.Context, src_tex: moderngl.TextureCube, res: int):
    irr_res = max(32, res // 4)
    irr_tex = ctx.texture_cube((irr_res, irr_res), 4, dtype="f4")
    irr_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    irr_tex.repeat_x = False
    irr_tex.repeat_y = False
    prog = _get_ibl_progs(ctx)[2]
    rec = _get_scratch(ctx)
    fe = _scratch_face_vao(ctx, rec, prog) if rec is not None else None
    if fe is None:
        vao, vbo = _make_face_vao(ctx, prog)
        own = True
    else:
        vao, vbo = fe
        own = False
    src_tex.use(0)
    prog["u_cubemap"].value = 0
    ctx.disable(moderngl.DEPTH_TEST)
    ctx.disable(moderngl.CULL_FACE)
    prev_fbo = ctx.fbo
    try:
        for face in range(6):
            fx, fy, fz = _FACE_BASIS[face]
            prog["u_face_x"].value = fx
            prog["u_face_y"].value = fy
            prog["u_face_z"].value = fz
            src_tex.use(0)
            direct = None
            if rec is not None:
                direct = _begin_cube_face(ctx, rec, irr_tex, face, 0, irr_res)
            if direct is not None:
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                vao.render(moderngl.TRIANGLES)
            else:
                def draw():
                    vao.render(moderngl.TRIANGLES)
                _blit_cube_face_fallback(ctx, irr_tex, face, 0, irr_res, draw)
    finally:
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
        if own:
            vao.release()
            vbo.release()
    return irr_tex


def _get_brdf_lut_tex(ctx: moderngl.Context):
    import weakref
    cid = id(ctx)
    try:
        ent = _BRDF_BYTES.get(cid)
    except Exception:
        ent = None
    if ent is not None:
        try:
            if ent[0]() is ctx:
                tex = ctx.texture((256, 256), 2, dtype="f4")
                tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                tex.repeat_x = False
                tex.repeat_y = False
                tex.write(ent[1])
                return tex
        except Exception:
            pass
    tex = _render_brdf_lut(ctx)
    try:
        payload = tex.read()
    except Exception:
        payload = None
    if payload is not None:
        try:
            ref = weakref.ref(ctx)
        except Exception:
            ref = None
        try:
            if len(_BRDF_BYTES) >= 8:
                for k in [k for k, v in _BRDF_BYTES.items() if v[0] is None or v[0]() is None]:
                    _BRDF_BYTES.pop(k, None)
            if len(_BRDF_BYTES) >= 8:
                _BRDF_BYTES.pop(next(iter(_BRDF_BYTES)), None)
            _BRDF_BYTES[cid] = (ref, payload)
        except Exception:
            pass
    return tex


def _render_brdf_lut(ctx: moderngl.Context):
    res = 256
    brdf_tex = ctx.texture((res, res), 2, dtype="f4")
    brdf_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    brdf_tex.repeat_x = False
    brdf_tex.repeat_y = False
    prog = _get_ibl_progs(ctx)[3]
    vao, vbo = _make_face_vao(ctx, prog)
    prev_fbo = ctx.fbo
    fbo = ctx.framebuffer(color_attachments=[brdf_tex])
    fbo.use()
    fbo.viewport = (0, 0, res, res)
    ctx.clear(0.0, 0.0, 0.0, 1.0)
    ctx.disable(moderngl.DEPTH_TEST)
    ctx.disable(moderngl.CULL_FACE)
    try:
        vao.render(moderngl.TRIANGLES)
    finally:
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
        fbo.release()
        vao.release()
        vbo.release()
    return brdf_tex


def _render_prefilter(ctx: moderngl.Context, src_cube: moderngl.TextureCube, res: int):
    pref = ctx.texture_cube((res, res), 4, dtype="f4")
    pref.filter = (moderngl.LINEAR, moderngl.LINEAR)
    pref.repeat_x = False
    pref.repeat_y = False
    _allocate_cube_mip_levels(pref, res, _PREFILTER_MAX_LOD)
    prog = _get_ibl_progs(ctx)[1]
    rec = _get_scratch(ctx)
    fe = _scratch_face_vao(ctx, rec, prog) if rec is not None else None
    if fe is None:
        vao, vbo = _make_face_vao(ctx, prog)
        own = True
    else:
        vao, vbo = fe
        own = False
    src_cube.use(0)
    prog["u_cubemap"].value = 0
    ctx.disable(moderngl.DEPTH_TEST)
    ctx.disable(moderngl.CULL_FACE)
    prev_fbo = ctx.fbo
    try:
        for level in range(_PREFILTER_MAX_LOD + 1):
            s = max(1, res >> level)
            roughness = level / float(_PREFILTER_MAX_LOD)
            for face in range(6):
                fx, fy, fz = _FACE_BASIS[face]
                prog["u_roughness"].value = roughness
                prog["u_face_x"].value = fx
                prog["u_face_y"].value = fy
                prog["u_face_z"].value = fz
                src_cube.use(0)
                direct = None
                if rec is not None:
                    direct = _begin_cube_face(ctx, rec, pref, face, level, s)
                if direct is not None:
                    ctx.clear(0.0, 0.0, 0.0, 1.0)
                    vao.render(moderngl.TRIANGLES)
                else:
                    def draw():
                        vao.render(moderngl.TRIANGLES)
                    _blit_cube_face_fallback(ctx, pref, face, level, s, draw)
    finally:
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
        if own:
            vao.release()
            vbo.release()
    return pref


def _generate_ibl_from_cube(ctx: moderngl.Context, src_cube: moderngl.TextureCube, res: int = 128) -> Optional[SkyIbl]:
    ibl = SkyIbl()
    try:
        ibl._prefilter_tex = _render_prefilter(ctx, src_cube, res)
        ibl._irradiance_tex = _render_irradiance(ctx, src_cube, res)
        ibl._brdf_lut_tex = _get_brdf_lut_tex(ctx)
        ibl.ready = True
    except Exception:
        ibl.release()
        return None
    return ibl


def _generate_ibl(ctx: moderngl.Context, env_tex: moderngl.Texture, res: int = 128, grade=None) -> Optional[SkyIbl]:
    src_cube = None
    try:
        src_cube = _render_cubemap_from_equirect(ctx, env_tex, res, grade)
        src_cube.build_mipmaps()
        return _generate_ibl_from_cube(ctx, src_cube, res)
    except Exception:
        return None
    finally:
        if src_cube is not None:
            try:
                src_cube.release()
            except Exception:
                pass


def _render_cubemap_from_sky(ctx: moderngl.Context, sky_prog: moderngl.Program,
                             sun_dir, sun_color, sun_intensity, res: int = 128) -> moderngl.TextureCube:
    from core.maths.math3d import Mat4, Vec3

    cube_tex = ctx.texture_cube((res, res), 4, dtype="f4")
    cube_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    cube_tex.repeat_x = False
    cube_tex.repeat_y = False
    rec = _get_scratch(ctx)
    if rec is not None:
        vao = _scratch_sky_mesh(ctx, rec, sky_prog)
    else:
        vao = None
    own_mesh = False
    if vao is None:
        try:
            from core.renderer.meshes import make_cube_mesh
            mesh = make_cube_mesh()
            vbo = ctx.buffer(mesh.vertices.tobytes())
            ibo = ctx.buffer(mesh.indices.astype(np.uint32).tobytes())
            vao = ctx.vertex_array(sky_prog, [(vbo, "3f", "in_position")], ibo)
            own_mesh = True
        except Exception:
            cube_tex.release()
            raise
    else:
        vbo = None
        ibo = None
        mesh = None
    sun_dir = np.asarray(sun_dir, dtype=np.float32).reshape(3)
    sun_color = np.asarray(sun_color, dtype=np.float32).reshape(-1)[:3]
    ctx.disable(moderngl.DEPTH_TEST)
    ctx.disable(moderngl.CULL_FACE)
    prev_fbo = ctx.fbo
    try:
        for face in range(6):
            fwd, up = _FACE_DIRS[face]
            face_view = Mat4.look_at(Vec3(0.0, 0.0, 0.0),
                                     Vec3(fwd.x, fwd.y, fwd.z),
                                     Vec3(up.x, up.y, up.z))
            face_proj = Mat4.perspective(90.0, 1.0, 0.1, 100.0)
            mvp = face_view * face_proj
            sky_prog["u_mvp"].write(mvp.to_f32().tobytes())
            try:
                sky_prog["u_use_env"].value = 0.0
            except Exception:
                pass
            try:
                sky_prog["_SunDirection"].write(sun_dir.tobytes())
                sky_prog["_SunColor"].write(sun_color.tobytes())
                sky_prog["_SunIntensity"].value = float(sun_intensity)
            except Exception:
                pass
            direct = None
            if rec is not None:
                direct = _begin_cube_face(ctx, rec, cube_tex, face, 0, res)
            if direct is not None:
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                if mesh is not None:
                    vao.render(moderngl.TRIANGLES, vertices=mesh.indices.size)
                else:
                    vao.render(moderngl.TRIANGLES)
            else:
                if mesh is None:
                    from core.renderer.meshes import make_cube_mesh as _mcm
                    mesh = _mcm()
                def draw():
                    vao.render(moderngl.TRIANGLES, vertices=mesh.indices.size)
                _blit_cube_face_fallback(ctx, cube_tex, face, 0, res, draw)
    finally:
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
        if own_mesh:
            vao.release()
            vbo.release()
            ibo.release()
    return cube_tex


_PROC_SKY_IBL_CACHE: "OrderedDict[str, SkyIbl]" = OrderedDict()
_PROC_SKY_IBL_CACHE_MAX = 8

_PROC_SUN_DEFAULT_DIR = np.array([0.0, -0.3, -1.0], dtype=np.float32)
_PROC_SUN_DEFAULT_COLOR = np.array([1.0, 0.95, 0.85], dtype=np.float32)
_PROC_SUN_DEFAULT_INTENSITY = 1.0

_SUN_DIR_GRID = 1024.0

_PROC_REGEN_COOLDOWN = 0.15
_PROC_REGEN_COOLDOWN_MAX = 2.0
_PROC_REGEN_STREAK_WINDOW = 2.5
_PROC_REGEN_CAP_DEG = 2.0
_PROC_LAST_GEN: dict[int, tuple] = {}


def _snap_sun_dir(v):
    a = np.asarray(v, dtype=np.float64).reshape(3)
    n = np.linalg.norm(a)
    if n <= 1e-9:
        return _PROC_SUN_DEFAULT_DIR.copy()
    a = a / n
    a = np.round(a * _SUN_DIR_GRID) / _SUN_DIR_GRID
    n2 = np.linalg.norm(a)
    if n2 <= 1e-9:
        return _PROC_SUN_DEFAULT_DIR.copy()
    return (a / n2).astype(np.float32)


def _ang_deg(a, b):
    d = float(np.clip(np.dot(np.asarray(a, dtype=np.float64).ravel(),
                              np.asarray(b, dtype=np.float64).ravel()), -1.0, 1.0))
    return math.degrees(math.acos(d))


def _quant(v, ndig: int):
    return tuple(round(float(x), ndig) for x in np.asarray(v).ravel())


def get_procedural_sky_ibl(ctx: moderngl.Context, sky_prog: moderngl.Program,
                           material_path: str, sun_dir=None, sun_color=None,
                           sun_intensity=None, res: int = 128,
                           settings_key=None) -> Optional[SkyIbl]:
    if sun_dir is None:
        sun_dir = _PROC_SUN_DEFAULT_DIR
    if sun_color is None:
        sun_color = _PROC_SUN_DEFAULT_COLOR
    if sun_intensity is None:
        sun_intensity = _PROC_SUN_DEFAULT_INTENSITY
    true_dir = np.asarray(sun_dir, dtype=np.float64).reshape(3)
    sun_dir = _snap_sun_dir(sun_dir)
    key = "|".join([
        material_path or "",
        repr(_quant(sun_dir, 3)),
        repr(_quant(sun_color, 2)),
        str(round(float(sun_intensity), 2)),
    ])
    if settings_key is not None:
        key += "|" + repr(settings_key)
    key = f"{id(ctx)}|{key}"
    cid = id(ctx)
    if key in _PROC_SKY_IBL_CACHE:
        ibl = _PROC_SKY_IBL_CACHE.pop(key)
        _PROC_SKY_IBL_CACHE[key] = ibl
        return ibl
    settings_ident = (material_path or "", settings_key,
                      repr(_quant(sun_color, 2)), str(round(float(sun_intensity), 2)))
    now = time.perf_counter()
    last = _PROC_LAST_GEN.get(cid)
    if last is not None:
        try:
            last_t, last_dir, last_ibl, last_settings = last[0], last[1], last[2], last[3]
            streak = last[4] if len(last) >= 6 else 0
            last_regen = last[5] if len(last) >= 6 else last_t
        except Exception:
            last_t, last_dir, last_ibl, last_settings, streak, last_regen = now, true_dir, None, None, 0, now
        try:
            cooldown = min(_PROC_REGEN_COOLDOWN * (2.0 ** streak), _PROC_REGEN_COOLDOWN_MAX)
        except Exception:
            cooldown = _PROC_REGEN_COOLDOWN
        try:
            mat_match = last_settings is not None and last_settings[0] == (material_path or "")
        except Exception:
            mat_match = False
        if last_ibl is not None and last_ibl.ready and (now - last_regen) < cooldown:
            try:
                settings_match = (last_settings == settings_ident)
            except Exception:
                settings_match = False
            if (settings_match or mat_match) and _ang_deg(last_dir, true_dir) < _PROC_REGEN_CAP_DEG:
                return last_ibl
    src_cube = None
    ibl = None
    try:
        src_cube = _render_cubemap_from_sky(ctx, sky_prog, sun_dir, sun_color, sun_intensity, res)
        src_cube.build_mipmaps()
        ibl = _generate_ibl_from_cube(ctx, src_cube, res)
    except Exception:
        ibl = None
    finally:
        if src_cube is not None:
            try:
                src_cube.release()
            except Exception:
                pass
    if ibl is not None:
        _PROC_SKY_IBL_CACHE[key] = ibl
        try:
            _prev = _PROC_LAST_GEN.get(cid)
            _pstreak = 0
            if _prev is not None and len(_prev) >= 6:
                try:
                    _gap = now - _prev[5]
                except Exception:
                    _gap = 99.0
                try:
                    _ps = int(_prev[4])
                except Exception:
                    _ps = 0
                if _gap < _PROC_REGEN_STREAK_WINDOW:
                    _pstreak = _ps + 1
                    if _pstreak > 8:
                        _pstreak = 8
            _PROC_LAST_GEN[cid] = (now, true_dir, ibl, settings_ident, _pstreak, now)
        except Exception:
            try:
                _PROC_LAST_GEN[cid] = (now, true_dir, ibl, settings_ident, 0, now)
            except Exception:
                pass
        while len(_PROC_SKY_IBL_CACHE) > _PROC_SKY_IBL_CACHE_MAX:
            _old_key, _old = _PROC_SKY_IBL_CACHE.popitem(last=False)
            try:
                _old.release()
            except Exception:
                pass
    return ibl


def get_sky_ibl(ctx: moderngl.Context, env_path: str, env_tex: Optional[moderngl.Texture] = None, grade_key: str = "", grade=None) -> Optional[SkyIbl]:
    if not env_path:
        return None
    abs_path = os.path.abspath(env_path)
    if not os.path.exists(abs_path):
        return None
    mtime = os.path.getmtime(abs_path)
    key = (abs_path, grade_key or "")
    cached = _SKY_IBL_CACHE.get(key)
    if cached is not None:
        cctx, cm, ibl = cached
        if cctx == id(ctx) and abs(mtime - cm) < 0.001:
            _SKY_IBL_CACHE.pop(key, None)
            _SKY_IBL_CACHE[key] = cached
            return ibl
        if ibl is not None:
            try:
                ibl.release()
            except Exception:
                pass
            _SKY_IBL_CACHE.pop(key, None)
    ibl = _generate_ibl(ctx, env_tex, 128, grade) if env_tex is not None else None
    _SKY_IBL_CACHE[key] = (id(ctx), mtime, ibl)
    while len(_SKY_IBL_CACHE) > _SKY_IBL_CACHE_MAX:
        _old_key, (_c, _m, _old) = _SKY_IBL_CACHE.popitem(last=False)
        if _old is not None:
            try:
                _old.release()
            except Exception:
                pass
    return ibl


def release_sky_ibl_cache():
    for _c, _m, ibl in _SKY_IBL_CACHE.values():
        if ibl is not None:
            try:
                ibl.release()
            except Exception:
                pass
    _SKY_IBL_CACHE.clear()
    for ibl in _PROC_SKY_IBL_CACHE.values():
        if ibl is not None:
            try:
                ibl.release()
            except Exception:
                pass
    _PROC_SKY_IBL_CACHE.clear()
    _PROC_LAST_GEN.clear()
