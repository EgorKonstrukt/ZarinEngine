# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
import numpy as np
import moderngl
from typing import Optional
from core.components.rendering.environment.dynacube import (
    _allocate_cube_mip_levels,
    _FACE_BASIS,
    _PREFILTER_MAX_LOD,
    _restore_framebuffer,
)
from core.components.rendering.environment.iblp.component import (
    _IBL_JOBS,
    _IBL_SLICE_BUDGET_MS,
    _PROC_LAST_GEN,
    _PROC_REGEN_CAP_DEG,
    _PROC_REGEN_COOLDOWN,
    _PROC_REGEN_COOLDOWN_MAX,
    _PROC_REGEN_STREAK_WINDOW,
    _PROC_SKY_IBL_CACHE,
    _PROC_SUN_DEFAULT_COLOR,
    _PROC_SUN_DEFAULT_DIR,
    _PROC_SUN_DEFAULT_INTENSITY,
    SkyIbl,
)
from core.components.rendering.environment.iblp.capture import (
    _begin_cube_face,
    _blit_cube_face_fallback,
    _get_ibl_progs,
    _get_scratch,
    _make_face_vao,
    _scratch_face_vao,
)
from core.components.rendering.environment.iblp.diffuse import (
    _ang_deg,
    _get_brdf_lut_tex,
    _note_ibl_regen,
    _quant,
    _release_ibl_job,
    _snap_sun_dir,
)
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
def _run_ibl_phase(ctx, job, phase):
    prog = job["prog"]
    fprogs = job["fprogs"]
    kind = phase[0]
    if kind == "cube":
        face = phase[1]
        vao = job["sky_vao"]
        prog["u_mvp"].write(job["mvps"][face])
        try:
            prog["u_use_env"].value = 0.0
        except Exception:
            pass
        try:
            prog["_SunDirection"].write(job["sun"])
            prog["_SunColor"].write(job["sunc"])
            prog["_SunIntensity"].value = job["intensity"]
        except Exception:
            pass
        rec = _get_scratch(ctx)
        direct = None
        if rec is not None:
            direct = _begin_cube_face(ctx, rec, job["cube"], face, 0, job["res"])
        if direct is not None:
            ctx.clear(0.0, 0.0, 0.0, 1.0)
            vao.render(moderngl.TRIANGLES)
        else:
            def draw():
                vao.render(moderngl.TRIANGLES)
            _blit_cube_face_fallback(ctx, job["cube"], face, 0, job["res"], draw)
    elif kind == "mips":
        try:
            job["cube"].build_mipmaps()
        except Exception:
            pass
    elif kind == "pref":
        _, level, face = phase
        s = max(1, job["res"] >> level)
        roughness = level / float(_PREFILTER_MAX_LOD)
        pprog = fprogs[1]
        vao = job["face_vao"]
        fx, fy, fz = _FACE_BASIS[face]
        pprog["u_roughness"].value = roughness
        pprog["u_face_x"].value = fx
        pprog["u_face_y"].value = fy
        pprog["u_face_z"].value = fz
        pprog["u_cubemap"].value = 0
        job["cube"].use(0)
        rec = _get_scratch(ctx)
        direct = None
        if rec is not None:
            direct = _begin_cube_face(ctx, rec, job["pref"], face, level, s)
        if direct is not None:
            ctx.clear(0.0, 0.0, 0.0, 1.0)
            vao.render(moderngl.TRIANGLES)
        else:
            def draw():
                vao.render(moderngl.TRIANGLES)
            _blit_cube_face_fallback(ctx, job["pref"], face, level, s, draw)
    elif kind == "irr":
        face = phase[1]
        iprog = fprogs[2]
        vao = job["irr_vao"]
        fx, fy, fz = _FACE_BASIS[face]
        iprog["u_face_x"].value = fx
        iprog["u_face_y"].value = fy
        iprog["u_face_z"].value = fz
        iprog["u_cubemap"].value = 0
        job["cube"].use(0)
        rec = _get_scratch(ctx)
        direct = None
        if rec is not None:
            direct = _begin_cube_face(ctx, rec, job["irr"], face, 0, job["irr_res"])
        if direct is not None:
            ctx.clear(0.0, 0.0, 0.0, 1.0)
            vao.render(moderngl.TRIANGLES)
        else:
            def draw():
                vao.render(moderngl.TRIANGLES)
            _blit_cube_face_fallback(ctx, job["irr"], face, 0, job["irr_res"], draw)
def _pump_ibl_job(ctx, job, budget_ms):
    try:
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        prev_fbo = ctx.fbo
    except Exception:
        return False
    try:
        t_end = time.perf_counter() + max(budget_ms, 0.5) / 1000.0
        phases = job["phases"]
        pos = job["pos"]
        n = len(phases)
        while pos < n:
            _run_ibl_phase(ctx, job, phases[pos])
            pos += 1
            job["pos"] = pos
            if pos < n and time.perf_counter() >= t_end:
                break
        return pos >= n
    except Exception:
        return False
    finally:
        try:
            ctx.enable(moderngl.DEPTH_TEST)
            ctx.enable(moderngl.CULL_FACE)
            _restore_framebuffer(ctx, prev_fbo)
        except Exception:
            pass
def _finish_ibl_job(ctx, job):
    try:
        brdf = _get_brdf_lut_tex(ctx)
    except Exception:
        brdf = None
    if brdf is None:
        _release_ibl_job(job)
        return None
    ibl = SkyIbl()
    ibl._prefilter_tex = job["pref"]
    ibl._irradiance_tex = job["irr"]
    ibl._brdf_lut_tex = brdf
    ibl.ready = True
    try:
        from core.components.rendering.environment.iblp.capture import _give_pooled_src_cube as _give
        _give(job.get("ctx"), job.get("res", 128), job.get("cube"))
    except Exception:
        pass
    try:
        _note_ibl_regen(id(ctx), job["key"], time.perf_counter(), job["true"], ibl, job["settings_ident"])
    except Exception:
        pass
    return ibl
def _drop_ibl_job(ctx, job):
    try:
        _release_ibl_job(job)
    except Exception:
        pass
    try:
        cid = id(ctx)
        if _IBL_JOBS.get(cid) is job:
            _IBL_JOBS.pop(cid, None)
    except Exception:
        pass
def get_procedural_sky_ibl(ctx: moderngl.Context, sky_prog: moderngl.Program, material_path: str, sun_dir=None, sun_color=None, sun_intensity=None, res: int = 128, settings_key=None) -> Optional[SkyIbl]:
    from core.components.rendering.environment.iblp.component import _create_ibl_job as _mk
    if sun_dir is None:
        sun_dir = _PROC_SUN_DEFAULT_DIR
    if sun_color is None:
        sun_color = _PROC_SUN_DEFAULT_COLOR
    if sun_intensity is None:
        sun_intensity = _PROC_SUN_DEFAULT_INTENSITY
    true_dir = np.asarray(sun_dir, dtype=np.float64).reshape(3)
    sun_dir = _snap_sun_dir(sun_dir)
    key = "|".join([material_path or "", repr(_quant(sun_dir, 3)), repr(_quant(sun_color, 2)), str(round(float(sun_intensity), 2))])
    if settings_key is not None:
        key += "|" + repr(settings_key)
    key = str(str(id(ctx)) + "|" + key)
    cid = id(ctx)
    if key in _PROC_SKY_IBL_CACHE:
        ibl = _PROC_SKY_IBL_CACHE.pop(key)
        _PROC_SKY_IBL_CACHE[key] = ibl
        return ibl
    settings_ident = (material_path or "", settings_key, repr(_quant(sun_color, 2)), str(round(float(sun_intensity), 2)))
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
    try:
        _prev_ibl = last_ibl if last_ibl is not None and last_ibl.ready else None
    except Exception:
        _prev_ibl = None
    try:
        _sun_b = np.asarray(sun_dir, dtype=np.float32).reshape(3).tobytes()
    except Exception:
        _sun_b = b""
    try:
        _col_a = np.asarray(sun_color, dtype=np.float32).reshape(-1)[:3]
        _col_t = (float(_col_a[0]), float(_col_a[1]), float(_col_a[2]))
    except Exception:
        _col_t = (1.0, 0.95, 0.85)
    try:
        _sint = float(sun_intensity)
    except Exception:
        _sint = 1.0
    _params = (material_path or "", res, sky_prog, _sun_b, _col_t, _sint, settings_key)
    try:
        _job = _IBL_JOBS.get(cid)
    except Exception:
        _job = None
    if _job is not None:
        try:
            _same = _job.get("params") == _params and _job.get("prog") is sky_prog
        except Exception:
            _same = False
        if not _same:
            _drop_ibl_job(ctx, _job)
            _job = None
    if _job is None:
        _job = _mk(ctx, sky_prog, material_path, res, sun_dir, sun_color, sun_intensity, settings_key, key, true_dir, _prev_ibl)
        if _job is None:
            return _prev_ibl
        try:
            if len(_IBL_JOBS) > 8:
                _IBL_JOBS.clear()
            _IBL_JOBS[cid] = _job
        except Exception:
            pass
    try:
        _pos_before = _job.get("pos", 0)
    except Exception:
        _pos_before = 0
    try:
        _budget = 1e9 if _prev_ibl is None else _IBL_SLICE_BUDGET_MS
    except Exception:
        _budget = _IBL_SLICE_BUDGET_MS
    try:
        _done = _pump_ibl_job(ctx, _job, _budget)
    except Exception:
        _done = False
    if _done:
        try:
            _new = _finish_ibl_job(ctx, _job)
        except Exception:
            _new = None
        try:
            if _IBL_JOBS.get(cid) is _job:
                _IBL_JOBS.pop(cid, None)
        except Exception:
            pass
        if _new is not None and _new.ready:
            return _new
        return _prev_ibl
    try:
        _pos_after = _job.get("pos", 0)
    except Exception:
        _pos_after = _pos_before
    if _pos_after <= _pos_before:
        try:
            _fails = int(_job.get("fails", 0)) + 1
        except Exception:
            _fails = 1
        if _fails >= 3:
            _drop_ibl_job(ctx, _job)
        else:
            try:
                _job["fails"] = _fails
            except Exception:
                pass
    return _prev_ibl
