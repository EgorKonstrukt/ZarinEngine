# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import math
import numpy as np
import moderngl
from core.components.rendering.environment.dynacube import (
    _FACE_BASIS,
    _restore_framebuffer,
)
from core.components.rendering.environment.iblp.component import (
    _BRDF_BYTES,
    _PROC_LAST_GEN,
    _PROC_REGEN_CAP_DEG,
    _PROC_REGEN_COOLDOWN,
    _PROC_REGEN_COOLDOWN_MAX,
    _PROC_REGEN_STREAK_WINDOW,
    _PROC_SKY_IBL_CACHE,
    _PROC_SKY_IBL_CACHE_MAX,
    _PROC_SUN_DEFAULT_DIR,
    _SUN_DIR_GRID,
)
from core.components.rendering.environment.iblp.capture import (
    _begin_cube_face,
    _blit_cube_face_fallback,
    _get_ibl_progs,
    _get_scratch,
    _make_face_vao,
    _scratch_face_vao,
)
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
    d = float(np.clip(np.dot(np.asarray(a, dtype=np.float64).ravel(), np.asarray(b, dtype=np.float64).ravel()), -1.0, 1.0))
    return math.degrees(math.acos(d))
def _quant(v, ndig: int):
    return tuple(round(float(x), ndig) for x in np.asarray(v).ravel())
def _note_ibl_regen(cid: int, key: str, now: float, true_dir, ibl, settings_ident):
    try:
        _PROC_SKY_IBL_CACHE[key] = ibl
    except Exception:
        pass
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
    try:
        while len(_PROC_SKY_IBL_CACHE) > _PROC_SKY_IBL_CACHE_MAX:
            _old_key, _old = _PROC_SKY_IBL_CACHE.popitem(last=False)
            try:
                _old.release()
            except Exception:
                pass
    except Exception:
        pass
def _release_ibl_job(job):
    try:
        ctx = job.get("ctx")
        res = job.get("res", 128)
    except Exception:
        ctx = None
        res = 128
    try:
        src = job.get("cube")
    except Exception:
        src = None
    if src is not None and ctx is not None:
        try:
            from core.components.rendering.environment.iblp.capture import _give_pooled_src_cube as _give
            _give(ctx, res, src)
        except Exception:
            pass
    else:
        try:
            if src is not None:
                src.release()
        except Exception:
            pass
    try:
        for tex in (job.get("pref"), job.get("irr")):
            if tex is not None:
                try:
                    tex.release()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        for owned in (job.get("sky_res"), job.get("face_res"), job.get("irr_own")):
            if not owned:
                continue
            for obj in owned:
                try:
                    obj.release()
                except Exception:
                    pass
    except Exception:
        pass
