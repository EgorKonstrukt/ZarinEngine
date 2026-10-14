# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
import moderngl
from core.components.rendering.environment.dynacube import (
    _attach_cubemap_face,
    _BRDF_LUT_FRAG,
    _FACE_BASIS,
    _FACE_DIRS,
    _FULLSCREEN_QUAD_VERT,
    _IRRADIANCE_FRAG,
    _PREFILTER_FRAG,
    _restore_framebuffer,
    _write_cube_face_mip,
)
from core.components.rendering.environment.iblp.component import (
    _BRDF_BYTES,
    _EQUIRECT_TO_CUBE_FRAG,
    _IBL_PROGS,
    _IBL_SRC_POOL,
    _IBL_SRC_POOL_MAX,
    _IDENTITY_MAT3,
    _SCRATCH,
    _SCRATCH_MAX,
)
def _make_face_vao(ctx: moderngl.Context, prog: moderngl.Program):
    verts = np.array([-1, -1, 0, 0, 1, -1, 1, 0, 1, 1, 1, 1, -1, -1, 0, 0, 1, 1, 1, 1, -1, 1, 0, 1], dtype=np.float32)
    vbo = ctx.buffer(verts.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "2f 2f", "in_position", "in_uv")])
    return vao, vbo
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
def _render_cubemap_from_sky(ctx: moderngl.Context, sky_prog: moderngl.Program, sun_dir, sun_color, sun_intensity, res: int = 128) -> moderngl.TextureCube:
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
            face_view = Mat4.look_at(Vec3(0.0, 0.0, 0.0), Vec3(fwd.x, fwd.y, fwd.z), Vec3(up.x, up.y, up.z))
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
def _take_pooled_src_cube(ctx, res):
    try:
        lst = _IBL_SRC_POOL.get((id(ctx), res))
    except Exception:
        return None
    if not lst:
        return None
    while lst:
        try:
            cent, cube = lst.pop()
        except Exception:
            return None
        try:
            alive = cent is ctx
        except Exception:
            alive = False
        if alive and cube is not None:
            return cube
        try:
            if cube is not None:
                cube.release()
        except Exception:
            pass
    return None
def _give_pooled_src_cube(ctx, res, cube):
    if cube is None:
        return
    try:
        if len(_IBL_SRC_POOL) >= _IBL_SRC_POOL_MAX:
            _IBL_SRC_POOL.pop(next(iter(_IBL_SRC_POOL)), None)
        lst = _IBL_SRC_POOL.get((id(ctx), res))
        if lst is None:
            lst = []
            _IBL_SRC_POOL[(id(ctx), res)] = lst
        if len(lst) < 2:
            lst.append((ctx, cube))
        else:
            try:
                cube.release()
            except Exception:
                pass
    except Exception:
        pass
