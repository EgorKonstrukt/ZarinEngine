# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import ctypes
import time
import numpy as np
import moderngl
from ctypes import c_void_p
from core.maths.math3d import Mat4, Vec3
_GL_TEXTURE_CUBE_MAP = 0x8513
_GL_TEXTURE_CUBE_MAP_POSITIVE_X = 0x8515
_GL_RGBA16F = 0x881A
_GL_RGBA = 0x1908
_GL_FLOAT = 0x1406
_GL_TEXTURE_MAX_LEVEL = 0x813D
_GL_TEXTURE_MIN_FILTER = 0x2801
_GL_TEXTURE_MAG_FILTER = 0x2800
_GL_TEXTURE_WRAP_S = 0x2802
_GL_TEXTURE_WRAP_T = 0x2803
_GL_TEXTURE_WRAP_R = 0x8072
_GL_LINEAR_MIPMAP_LINEAR = 0x2703
_GL_LINEAR = 0x2601
_GL_CLAMP_TO_EDGE = 0x812F
_PREFILTER_MAX_LOD = 4
_opengl32 = ctypes.windll.opengl32
_opengl32.glGetError.restype = ctypes.c_uint
_opengl32.glBindTexture.restype = None
_opengl32.glBindTexture.argtypes = (ctypes.c_uint, ctypes.c_uint)
_opengl32.glTexImage2D.restype = None
_opengl32.glTexImage2D.argtypes = (
    ctypes.c_uint, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_uint, ctypes.c_uint, c_void_p,
)
_opengl32.glTexSubImage2D.restype = None
_opengl32.glTexSubImage2D.argtypes = (
    ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, c_void_p,
)
_opengl32.glTexParameteri.restype = None
_opengl32.glTexParameteri.argtypes = (ctypes.c_uint, ctypes.c_uint, ctypes.c_int)
_wglGetProcAddress = _opengl32.wglGetProcAddress
_wglGetProcAddress.restype = ctypes.c_void_p
_wglGetProcAddress.argtypes = (ctypes.c_char_p,)
_glFramebufferTexture2D_fn = None
_glCheckFramebufferStatus_fn = None
def _resolve_gl_function(name: bytes, restype, argtypes):
    addr = _wglGetProcAddress(name)
    if addr:
        return ctypes.CFUNCTYPE(restype, *argtypes)(addr)
    try:
        return getattr(_opengl32, name.decode())
    except AttributeError:
        return None
def _glFramebufferTexture2D(*args):
    global _glFramebufferTexture2D_fn
    if _glFramebufferTexture2D_fn is None:
        _glFramebufferTexture2D_fn = _resolve_gl_function(
            b"glFramebufferTexture2D", None,
            (ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int),
        )
    if _glFramebufferTexture2D_fn is not None:
        _glFramebufferTexture2D_fn(*args)
def _glCheckFramebufferStatus(target):
    global _glCheckFramebufferStatus_fn
    if _glCheckFramebufferStatus_fn is None:
        _glCheckFramebufferStatus_fn = _resolve_gl_function(
            b"glCheckFramebufferStatus", ctypes.c_uint, (ctypes.c_uint,),
        )
    if _glCheckFramebufferStatus_fn is None:
        return 0
    return _glCheckFramebufferStatus_fn(target)
_GL_TEXTURE_2D = 0x0DE1
_GL_FRAMEBUFFER = 0x8D40
_GL_COLOR_ATTACHMENT0 = 0x8CE0
_GL_FRAMEBUFFER_COMPLETE = 0x8CD5
def _attach_cubemap_face(tex_glo: int, face: int, level: int = 0) -> bool:
    _glFramebufferTexture2D(
        _GL_FRAMEBUFFER, _GL_COLOR_ATTACHMENT0,
        _GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, tex_glo, level,
    )
    return _glCheckFramebufferStatus(_GL_FRAMEBUFFER) == _GL_FRAMEBUFFER_COMPLETE
def _allocate_cube_mip_levels(tex: moderngl.TextureCube, res: int, max_level: int):
    _opengl32.glBindTexture(_GL_TEXTURE_CUBE_MAP, tex.glo)
    for level in range(max_level + 1):
        s = max(1, res >> level)
        for face in range(6):
            _opengl32.glTexImage2D(
                _GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, level, _GL_RGBA16F,
                s, s, 0, _GL_RGBA, _GL_FLOAT, None,
            )
    _opengl32.glTexParameteri(_GL_TEXTURE_CUBE_MAP, _GL_TEXTURE_MAX_LEVEL, max_level)
    _opengl32.glTexParameteri(_GL_TEXTURE_CUBE_MAP, _GL_TEXTURE_MIN_FILTER, _GL_LINEAR_MIPMAP_LINEAR)
    _opengl32.glTexParameteri(_GL_TEXTURE_CUBE_MAP, _GL_TEXTURE_MAG_FILTER, _GL_LINEAR)
    _opengl32.glTexParameteri(_GL_TEXTURE_CUBE_MAP, _GL_TEXTURE_WRAP_S, _GL_CLAMP_TO_EDGE)
    _opengl32.glTexParameteri(_GL_TEXTURE_CUBE_MAP, _GL_TEXTURE_WRAP_T, _GL_CLAMP_TO_EDGE)
    _opengl32.glTexParameteri(_GL_TEXTURE_CUBE_MAP, _GL_TEXTURE_WRAP_R, _GL_CLAMP_TO_EDGE)
    _opengl32.glBindTexture(_GL_TEXTURE_CUBE_MAP, 0)
def _write_cube_face_mip(tex: moderngl.TextureCube, face: int, level: int, size: int, data: bytes):
    buf = np.frombuffer(data, np.float32)
    _opengl32.glBindTexture(_GL_TEXTURE_CUBE_MAP, tex.glo)
    _opengl32.glTexSubImage2D(
        _GL_TEXTURE_CUBE_MAP_POSITIVE_X + face, level, 0, 0,
        size, size, _GL_RGBA, _GL_FLOAT, buf.ctypes.data_as(c_void_p),
    )
    _opengl32.glBindTexture(_GL_TEXTURE_CUBE_MAP, 0)
def _restore_framebuffer(ctx: moderngl.Context, prev_fbo):
    if prev_fbo is not None:
        try:
            prev_fbo.use()
        except Exception:
            pass
_FACE_DIRS = [
    (Vec3(1, 0, 0), Vec3(0, -1, 0)),
    (Vec3(-1, 0, 0), Vec3(0, -1, 0)),
    (Vec3(0, 1, 0), Vec3(0, 0, 1)),
    (Vec3(0, -1, 0), Vec3(0, 0, -1)),
    (Vec3(0, 0, 1), Vec3(0, -1, 0)),
    (Vec3(0, 0, -1), Vec3(0, -1, 0)),
]
_FACE_BASIS = [
    ((0.0, 0.0, -1.0), (0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
    ((0.0, 0.0, 1.0), (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0)),
    ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, -1.0, 0.0)),
    ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)),
]
class DynamicCubemapCaptureMixin:
    def render_face(self, ctx: moderngl.Context, face: int, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3, scene, renderer, main_snap=None, skip_entity=None) -> bool:
        if not self._ensure_resources(ctx):
            return False
        if face < 0 or face > 5:
            return False
        fbo = self._face_fbos[face]
        cubemap = self._cubemap_tex
        if fbo is None or cubemap is None:
            return False
        res = self.resolution
        fwd, up = _FACE_DIRS[face]
        target = cam_pos + fwd
        face_view = Mat4.look_at(cam_pos, target, up)
        if self._proj_cache_key != (self.near_plane, self.far_plane):
            face_proj = Mat4.perspective(90.0, 1.0, self.near_plane, self.far_plane)
            self._proj_mat = face_proj
            self._proj_f32 = face_proj.to_f32()
            self._proj_cache_key = (self.near_plane, self.far_plane)
        else:
            face_proj = self._proj_mat
        view_f32 = face_view.to_f32()
        proj_f32 = self._proj_f32
        prev_fbo = None
        try:
            prev_fbo = ctx.fbo
        except Exception:
            prev_fbo = None
        if main_snap is not None:
            snap = main_snap
        else:
            snap = renderer._collect_snapshot(scene, self.near_plane, self.far_plane, 90.0, face_view, face_proj, cam_pos)
        fbo.use()
        if not _attach_cubemap_face(cubemap.glo, face, 0):
            _restore_framebuffer(ctx, prev_fbo)
            return False
        renderer._rendering_cubemap_face = True
        try:
            renderer.render_cubemap_face(snap, fbo, res, view_f32, proj_f32, cam_pos, snap.lights, skip_entity=skip_entity, face_index=face)
        finally:
            renderer._rendering_cubemap_face = False
        _restore_framebuffer(ctx, prev_fbo)
        return True
    def update(self, ctx: moderngl.Context, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3, scene, renderer, main_snap=None, skip_entity=None) -> bool:
        if not self._ensure_resources(ctx):
            return False
        now = time.perf_counter()
        needs_update = False
        if not self._all_faces_updated:
            needs_update = True
        elif self.update_interval <= 0.0:
            needs_update = True
        elif (now - self._last_update_time) >= self.update_interval:
            needs_update = True
        if not needs_update:
            return self._all_faces_updated
        if not self._all_faces_updated:
            face = self._current_face
            self.render_face(ctx, face, view_mat, proj_mat, cam_pos, scene, renderer, main_snap=main_snap, skip_entity=skip_entity)
            self._current_face = (self._current_face + 1) % 6
            if self._current_face == 0:
                self._all_faces_updated = True
                self._last_update_time = now
                self.generate_irradiance(ctx)
                self.generate_prefilter(ctx)
                self.generate_brdf_lut(ctx)
        else:
            for face in range(6):
                self.render_face(ctx, face, view_mat, proj_mat, cam_pos, scene, renderer, main_snap=main_snap, skip_entity=skip_entity)
            self._all_faces_updated = True
            self._last_update_time = now
            self.generate_irradiance(ctx)
            self.generate_prefilter(ctx)
            self.generate_brdf_lut(ctx)
            self._current_face = 0
        return True
