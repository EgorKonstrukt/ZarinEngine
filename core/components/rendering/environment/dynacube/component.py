# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.foundation.logger import Logger
from core.maths.math3d import Mat4
from core.components.rendering.environment.dynacube.capture import DynamicCubemapCaptureMixin, _allocate_cube_mip_levels, _PREFILTER_MAX_LOD
from core.components.rendering.environment.dynacube.filter import DynamicCubemapFilterMixin, _FULLSCREEN_QUAD_VERT, _IRRADIANCE_FRAG, _PREFILTER_FRAG, _BRDF_LUT_FRAG
@ComponentRegistry.register
class DynamicCubemaps(DynamicCubemapCaptureMixin, DynamicCubemapFilterMixin, Component):
    _allow_multiple = False
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Dynamic Cubemaps", FieldType.HEADER),
            InspectorField("follow_camera", "Follow Camera", FieldType.BOOL),
            InspectorField("resolution", "Resolution", FieldType.INT_SLIDER, 32, 512),
            InspectorField("update_interval", "Update Interval (s)", FieldType.FLOAT, 0.05, 2.0),
            InspectorField("near_plane", "Near Plane", FieldType.FLOAT, 0.01, 10.0),
            InspectorField("far_plane", "Far Plane", FieldType.FLOAT, 1.0, 500.0),
            InspectorField("intensity", "Intensity", FieldType.FLOAT, 0.0, 5.0),
        ]
    def __init__(self):
        super().__init__()
        self.follow_camera: bool = True
        self.resolution: int = 128
        self.update_interval: float = 0.33
        self.near_plane: float = 0.1
        self.far_plane: float = 100.0
        self.intensity: float = 1.0
        self._ctx_id: int = 0
        self._face_fbos: list[Optional[moderngl.Framebuffer]] = [None] * 6
        self._face_depth: list[Optional[moderngl.Renderbuffer]] = [None] * 6
        self._face_color_texs: list[Optional[moderngl.Texture]] = [None] * 6
        self._cubemap_tex: Optional[moderngl.Texture] = None
        self._irradiance_tex: Optional[moderngl.Texture] = None
        self._irradiance_face_texs: list[Optional[moderngl.Texture]] = [None] * 6
        self._irradiance_face_fbos: list[Optional[moderngl.Framebuffer]] = [None] * 6
        self._prefilter_tex: Optional[moderngl.Texture] = None
        self._prefilter_fbos: list[Optional[moderngl.Framebuffer]] = []
        self._brdf_lut_tex: Optional[moderngl.Texture] = None
        self._brdf_lut_fbo: Optional[moderngl.Framebuffer] = None
        self._irradiance_prog: Optional[moderngl.Program] = None
        self._prefilter_prog: Optional[moderngl.Program] = None
        self._brdf_prog: Optional[moderngl.Program] = None
        self._current_face: int = 0
        self._last_update_time: float = 0.0
        self._all_faces_updated: bool = False
        self._quad_vaos: dict[int, moderngl.VertexArray] = {}
        self._proj_cache_key: Optional[tuple] = None
        self._proj_mat: Optional[Mat4] = None
        self._proj_f32: Optional[np.ndarray] = None
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "follow_camera": self.follow_camera,
            "resolution": self.resolution,
            "update_interval": self.update_interval,
            "near_plane": self.near_plane,
            "far_plane": self.far_plane,
            "intensity": self.intensity,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> DynamicCubemaps:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.follow_camera = bool(data.get("follow_camera", True))
        c.resolution = int(data.get("resolution", 128))
        c.update_interval = float(data.get("update_interval", 0.33))
        c.near_plane = float(data.get("near_plane", 0.1))
        c.far_plane = float(data.get("far_plane", 100.0))
        c.intensity = float(data.get("intensity", 1.0))
        return c
    def _ensure_resources(self, ctx: moderngl.Context) -> bool:
        ctx_id = id(ctx)
        if self._ctx_id == ctx_id and self._cubemap_tex is not None:
            return True
        self._release_gl()
        self._ctx_id = ctx_id
        res = self.resolution
        try:
            self._cubemap_tex = ctx.texture_cube((res, res), 4, dtype="f4")
            self._cubemap_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._cubemap_tex.repeat_x = False
            self._cubemap_tex.repeat_y = False
        except Exception as e:
            Logger.error(f"DynamicCubemaps: failed to create cubemap: {e}")
            return False
        for i in range(6):
            try:
                self._face_color_texs[i] = ctx.texture((res, res), 4, dtype="f4")
                self._face_color_texs[i].filter = (moderngl.LINEAR, moderngl.LINEAR)
                self._face_depth[i] = ctx.depth_renderbuffer((res, res))
                self._face_fbos[i] = ctx.framebuffer(
                    color_attachments=[self._face_color_texs[i]],
                    depth_attachment=self._face_depth[i],
                )
            except Exception as e:
                Logger.error(f"DynamicCubemaps: failed to create face FBO {i}: {e}")
                return False
        irr_res = max(32, res // 4)
        try:
            self._irradiance_tex = ctx.texture_cube((irr_res, irr_res), 4, dtype="f4")
            self._irradiance_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._irradiance_tex.repeat_x = False
            self._irradiance_tex.repeat_y = False
            for i in range(6):
                self._irradiance_face_texs[i] = ctx.texture((irr_res, irr_res), 4, dtype="f4")
                self._irradiance_face_texs[i].filter = (moderngl.LINEAR, moderngl.LINEAR)
                self._irradiance_face_fbos[i] = ctx.framebuffer(
                    color_attachments=[self._irradiance_face_texs[i]]
                )
        except Exception as e:
            Logger.error(f"DynamicCubemaps: failed to create irradiance: {e}")
            return False
        prefilter_mip_count = 5
        self._prefilter_fbos = []
        try:
            self._prefilter_tex = ctx.texture_cube((res, res), 4, dtype="f4")
            self._prefilter_tex.repeat_x = False
            self._prefilter_tex.repeat_y = False
            _allocate_cube_mip_levels(self._prefilter_tex, res, _PREFILTER_MAX_LOD)
            for mip in range(prefilter_mip_count):
                mip_res = max(1, res // (2 ** mip))
                mip_tex = ctx.texture((mip_res, mip_res), 4, dtype="f4")
                mip_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                mip_fbo = ctx.framebuffer(color_attachments=[mip_tex])
                self._prefilter_fbos.append((mip_fbo, mip_tex, mip_res, mip))
        except Exception as e:
            Logger.error(f"DynamicCubemaps: failed to create prefilter: {e}")
            return False
        brdf_res = 256
        try:
            self._brdf_lut_tex = ctx.texture((brdf_res, brdf_res), 2, dtype="f4")
            self._brdf_lut_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._brdf_lut_fbo = ctx.framebuffer(color_attachments=[self._brdf_lut_tex])
        except Exception as e:
            Logger.error(f"DynamicCubemaps: failed to create BRDF LUT: {e}")
            return False
        self._ensure_shaders(ctx)
        return True
    def _ensure_shaders(self, ctx: moderngl.Context):
        if self._irradiance_prog is None:
            try:
                self._irradiance_prog = ctx.program(
                    vertex_shader=_FULLSCREEN_QUAD_VERT,
                    fragment_shader=_IRRADIANCE_FRAG,
                )
            except Exception as e:
                Logger.error(f"DynamicCubemaps: irradiance shader compile error: {e}")
        if self._prefilter_prog is None:
            try:
                self._prefilter_prog = ctx.program(
                    vertex_shader=_FULLSCREEN_QUAD_VERT,
                    fragment_shader=_PREFILTER_FRAG,
                )
            except Exception as e:
                Logger.error(f"DynamicCubemaps: prefilter shader compile error: {e}")
        if self._brdf_prog is None:
            try:
                self._brdf_prog = ctx.program(
                    vertex_shader=_FULLSCREEN_QUAD_VERT,
                    fragment_shader=_BRDF_LUT_FRAG,
                )
            except Exception as e:
                Logger.error(f"DynamicCubemaps: BRDF LUT shader compile error: {e}")
    def _make_face_vao(self, ctx: moderngl.Context, prog: moderngl.Program) -> Optional[moderngl.VertexArray]:
        verts = np.array([
            -1, -1, 0, 0,
             1, -1, 1, 0,
             1,  1, 1, 1,
            -1, -1, 0, 0,
             1,  1, 1, 1,
            -1,  1, 0, 1,
        ], dtype=np.float32)
        vbo = ctx.buffer(verts.tobytes())
        return ctx.vertex_array(prog, [(vbo, "2f 2f", "in_position", "in_uv")])
    def _get_quad_vao(self, ctx: moderngl.Context, prog: moderngl.Program) -> Optional[moderngl.VertexArray]:
        key = id(prog)
        vao = self._quad_vaos.get(key)
        if vao is None:
            vao = self._make_face_vao(ctx, prog)
            self._quad_vaos[key] = vao
        return vao
    def on_destroy(self):
        self._release_gl()
    def on_disable(self):
        self._release_gl()
    def _release_gl(self):
        for fbo in self._face_fbos:
            if fbo:
                try:
                    fbo.release()
                except Exception:
                    pass
        self._face_fbos = [None] * 6
        for tex in self._face_color_texs:
            if tex:
                try:
                    tex.release()
                except Exception:
                    pass
        self._face_color_texs = [None] * 6
        for d in self._face_depth:
            if d:
                try:
                    d.release()
                except Exception:
                    pass
        self._face_depth = [None] * 6
        for tex in [self._cubemap_tex, self._irradiance_tex, self._brdf_lut_tex]:
            if tex:
                try:
                    tex.release()
                except Exception:
                    pass
        self._cubemap_tex = None
        self._irradiance_tex = None
        self._brdf_lut_tex = None
        for tex in self._irradiance_face_texs:
            if tex:
                try:
                    tex.release()
                except Exception:
                    pass
        self._irradiance_face_texs = [None] * 6
        for fbo in self._irradiance_face_fbos:
            if fbo:
                try:
                    fbo.release()
                except Exception:
                    pass
        self._irradiance_face_fbos = [None] * 6
        for item in getattr(self, "_prefilter_fbos", []):
            if item:
                try:
                    item[0].release()
                    item[1].release()
                except Exception:
                    pass
        self._prefilter_fbos = []
        for fbo in [self._brdf_lut_fbo]:
            if fbo:
                try:
                    fbo.release()
                except Exception:
                    pass
        self._brdf_lut_fbo = None
        for prog in [self._irradiance_prog, self._prefilter_prog, self._brdf_prog]:
            if prog:
                try:
                    prog.release()
                except Exception:
                    pass
        self._irradiance_prog = None
        self._prefilter_prog = None
        self._brdf_prog = None
        for vao in self._quad_vaos.values():
            if vao:
                try:
                    vao.release()
                except Exception:
                    pass
        self._quad_vaos = {}
        self._proj_cache_key = None
        self._proj_mat = None
        self._proj_f32 = None
        self._ctx_id = 0
        self._current_face = 0
        self._all_faces_updated = False
        self._last_update_time = 0.0
