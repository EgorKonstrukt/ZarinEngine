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
from core.components.rendering.environment.dynacube import (
    _allocate_cube_mip_levels,
    _FACE_DIRS,
    _PREFILTER_MAX_LOD,
)
_EQUIRECT_TO_CUBE_FRAG = (
    "\n"
    + chr(35) + "version 330 core\n"
    + "in vec2 v_uv;\n"
    + "out vec4 frag_color;\n"
    + "uniform sampler2D u_equirect;\n"
    + "uniform vec3 u_face_x;\n"
    + "uniform vec3 u_face_y;\n"
    + "uniform vec3 u_face_z;\n"
    + "uniform float u_exposure;\n"
    + "uniform float u_intensity;\n"
    + "uniform vec3 u_tint;\n"
    + "uniform float u_saturation;\n"
    + "uniform mat3 u_rotation;\n"
    + "uniform float u_flip_y;\n"
    + "const float PI = 3.14159265359;\n"
    + "void main() {\n"
    + "    vec2 tc = v_uv * 2.0 - 1.0;\n"
    + "    vec3 dir = normalize(u_rotation * normalize(u_face_x * tc.x + u_face_y * tc.y + u_face_z));\n"
    + "    vec2 uv = vec2(0.5 + atan(dir.z, dir.x) / 6.28318530718, acos(clamp(dir.y, -1.0, 1.0)) / PI);\n"
    + "    if (u_flip_y > 0.5) {\n"
    + "        uv.y = 1.0 - uv.y;\n"
    + "    }\n"
    + "    vec3 col = texture(u_equirect, uv).rgb;\n"
    + "    col *= exp2(u_exposure) * u_intensity;\n"
    + "    float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));\n"
    + "    col = mix(vec3(luma), col, u_saturation) * u_tint;\n"
    + "    frag_color = vec4(col, 1.0);\n"
    + "}\n"
)
_IDENTITY_MAT3 = np.eye(3, dtype=np.float32).T.tobytes()
_SKY_IBL_CACHE: dict = {}
_SKY_IBL_CACHE_MAX = 8
_SCRATCH: dict[int, tuple] = {}
_SCRATCH_MAX: int = 8
_BRDF_BYTES: dict[int, tuple] = {}
_IBL_PROGS: dict[int, tuple] = {}
_PROC_SKY_IBL_CACHE: OrderedDict[str, SkyIbl] = OrderedDict()
_PROC_SKY_IBL_CACHE_MAX = 8
_IBL_SLICE_BUDGET_MS = 3.0
_IBL_JOBS: dict[int, tuple] = {}
_IBL_SRC_POOL: dict = {}
_IBL_SRC_POOL_MAX = 8
_PROC_SUN_DEFAULT_DIR = np.array([0.0, -0.3, -1.0], dtype=np.float32)
_PROC_SUN_DEFAULT_COLOR = np.array([1.0, 0.95, 0.85], dtype=np.float32)
_PROC_SUN_DEFAULT_INTENSITY = 1.0
_SUN_DIR_GRID = 1024.0
_PROC_REGEN_COOLDOWN = 0.15
_PROC_REGEN_COOLDOWN_MAX = 2.0
_PROC_REGEN_STREAK_WINDOW = 2.5
_PROC_REGEN_CAP_DEG = 2.0
_PROC_LAST_GEN: dict[int, tuple] = {}
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
def _generate_ibl_from_cube(ctx: moderngl.Context, src_cube: moderngl.TextureCube, res: int = 128) -> Optional[SkyIbl]:
    from core.components.rendering.environment.iblp.diffuse import _render_irradiance as _ri
    from core.components.rendering.environment.iblp.diffuse import _get_brdf_lut_tex as _gb
    from core.components.rendering.environment.iblp.specular import _render_prefilter as _rp
    ibl = SkyIbl()
    try:
        ibl._prefilter_tex = _rp(ctx, src_cube, res)
        ibl._irradiance_tex = _ri(ctx, src_cube, res)
        ibl._brdf_lut_tex = _gb(ctx)
        ibl.ready = True
    except Exception:
        ibl.release()
        return None
    return ibl
def _generate_ibl(ctx: moderngl.Context, env_tex: moderngl.Texture, res: int = 128, grade=None) -> Optional[SkyIbl]:
    from core.components.rendering.environment.iblp.capture import _render_cubemap_from_equirect as _rc
    src_cube = None
    try:
        src_cube = _rc(ctx, env_tex, res, grade)
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
def _create_ibl_job(ctx, prog, material_path, res, sun_dir, sun_color, sun_intensity, settings_key, key, true_dir, prev):
    from core.maths.math3d import Mat4, Vec3
    from core.components.rendering.environment.iblp.capture import _take_pooled_src_cube as _take
    from core.components.rendering.environment.iblp.capture import _get_scratch as _gs
    from core.components.rendering.environment.iblp.capture import _scratch_sky_mesh as _ssm
    from core.components.rendering.environment.iblp.capture import _scratch_face_vao as _sfv
    from core.components.rendering.environment.iblp.capture import _make_face_vao as _mfv
    from core.components.rendering.environment.iblp.capture import _get_ibl_progs as _gip
    from core.components.rendering.environment.iblp.diffuse import _quant as _q
    try:
        cube = _take(ctx, res)
    except Exception:
        cube = None
    if cube is None:
        try:
            cube = ctx.texture_cube((res, res), 4, dtype="f4")
            cube.filter = (moderngl.LINEAR, moderngl.LINEAR)
            cube.repeat_x = False
            cube.repeat_y = False
        except Exception:
            return None
    try:
        pref = ctx.texture_cube((res, res), 4, dtype="f4")
        pref.filter = (moderngl.LINEAR, moderngl.LINEAR)
        pref.repeat_x = False
        pref.repeat_y = False
        _allocate_cube_mip_levels(pref, res, _PREFILTER_MAX_LOD)
    except Exception:
        try:
            cube.release()
        except Exception:
            pass
        return None
    try:
        irr_res = max(32, res // 4)
        irr = ctx.texture_cube((irr_res, irr_res), 4, dtype="f4")
        irr.filter = (moderngl.LINEAR, moderngl.LINEAR)
        irr.repeat_x = False
        irr.repeat_y = False
    except Exception:
        try:
            cube.release()
        except Exception:
            pass
        try:
            pref.release()
        except Exception:
            pass
        return None
    try:
        rec = _gs(ctx)
        sky_vao = None
        sky_res = []
        if rec is not None:
            try:
                sent = _ssm(ctx, rec, prog)
                if sent is not None:
                    sky_vao = sent[0]
            except Exception:
                sky_vao = None
        if sky_vao is None:
            from core.renderer.meshes import make_cube_mesh
            mesh = make_cube_mesh()
            vbo = ctx.buffer(mesh.vertices.tobytes())
            ibo = ctx.buffer(mesh.indices.astype(np.uint32).tobytes())
            sky_vao = ctx.vertex_array(prog, [(vbo, "3f", "in_position")], ibo)
            sky_res = [sky_vao, vbo, ibo]
        fprogs = _gip(ctx)
        face_vao = None
        face_res = []
        if rec is not None:
            try:
                fent = _sfv(ctx, rec, fprogs[1])
                if fent is not None:
                    face_vao = fent[0]
            except Exception:
                face_vao = None
        if face_vao is None:
            fvao, fvbo = _mfv(ctx, fprogs[1])
            face_vao = fvao
            face_res = [fvao, fvbo]
        irr_vao = None
        irr_own = []
        if rec is not None:
            try:
                ient = _sfv(ctx, rec, fprogs[2])
                if ient is not None:
                    irr_vao = ient[0]
            except Exception:
                irr_vao = None
        if irr_vao is None:
            ivao, ivbo = _mfv(ctx, fprogs[2])
            irr_vao = ivao
            irr_own = [ivao, ivbo]
    except Exception:
        try:
            cube.release()
        except Exception:
            pass
        try:
            pref.release()
        except Exception:
            pass
        try:
            irr.release()
        except Exception:
            pass
        return None
    try:
        mvps = []
        for face in range(6):
            fwd, up = _FACE_DIRS[face]
            face_view = Mat4.look_at(Vec3(0.0, 0.0, 0.0), Vec3(fwd.x, fwd.y, fwd.z), Vec3(up.x, up.y, up.z))
            face_proj = Mat4.perspective(90.0, 1.0, 0.1, 100.0)
            mvps.append((face_view * face_proj).to_f32().tobytes())
    except Exception:
        try:
            cube.release()
        except Exception:
            pass
        try:
            pref.release()
        except Exception:
            pass
        try:
            irr.release()
        except Exception:
            pass
        return None
    try:
        sun_b = np.asarray(sun_dir, dtype=np.float32).reshape(3).tobytes()
        col_a = np.asarray(sun_color, dtype=np.float32).reshape(-1)[:3]
        col_b = col_a.tobytes()
        col_t = (float(col_a[0]), float(col_a[1]), float(col_a[2]))
    except Exception:
        sun_b = b""
        col_b = b""
        col_t = (1.0, 0.95, 0.85)
    phases = [("cube", f) for f in range(6)]
    phases.append(("mips",))
    for level in range(_PREFILTER_MAX_LOD + 1):
        for face in range(6):
            phases.append(("pref", level, face))
    for face in range(6):
        phases.append(("irr", face))
    try:
        sun_key = np.asarray(sun_dir, dtype=np.float32).reshape(3).tobytes()
    except Exception:
        sun_key = b""
    params = (material_path or "", res, prog, sun_key, col_t, float(sun_intensity), settings_key)
    return {"ctx": ctx, "prog": prog, "material": material_path or "", "res": res, "sun": sun_b, "sunc": col_b, "color": col_t, "intensity": float(sun_intensity), "skey": settings_key, "key": key, "true": np.asarray(true_dir, dtype=np.float64).reshape(3).copy(), "settings_ident": (material_path or "", settings_key, repr(_q(np.asarray(sun_color, dtype=np.float32).reshape(-1)[:3], 2)), str(round(float(sun_intensity), 2))), "params": params, "pending": None, "prev": prev, "cube": cube, "pref": pref, "irr": irr, "irr_res": irr_res, "sky_vao": sky_vao, "sky_res": sky_res, "face_vao": face_vao, "face_res": face_res, "irr_vao": irr_vao, "irr_own": irr_own, "fprogs": fprogs, "mvps": mvps, "phases": phases, "pos": 0}
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
