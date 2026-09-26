# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Central renderer facade."""

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional, Any, Callable
from core.foundation.logger import Logger
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.maths.math3d import Mat4, Vec3
from core.renderer.types import RenderMode
from core.renderer.mesh_data import MeshData, read_shader
from core.renderer.grid import GridRenderer
from core.renderer.gizmo import GizmoRenderer, FATLINE_VERT, FATLINE_FRAG
from core.renderer.shadows import ShadowRenderer
from core.renderer.particles import ParticleRenderer
from core.renderer.sprites import SpriteRendererGL
from core.renderer.svgs import SvgRendererGL
from core.renderer.video import VideoRendererGL
from core.renderer.icons import IconRenderer
from core.renderer.gaussian_splat_renderer import GaussianSplatRenderer
from core.renderer.text import TextRendererGL
from core.renderer.materials import MaterialManager
from core.renderer.shaders import ShaderManager, program_with_fallback
from core.renderer.mesh_loader import MeshLoader
from core.renderer.batcher import RenderBatcher, resolve_normal_matrix
from core.renderer.gpu_culling import GpuStorage, GpuCulling
from core.renderer.render_items import _ProjectorItem, _SpriteItem, _SvgItem, _TAAU_JITTER, _VideoItem, _halton
from core.renderer.render_snapshot import _RenderSnapshot
from core.renderer.renderer_config import RendererConfigMixin
from core.renderer.renderer_programs import RendererProgramsMixin
from core.renderer.voxel_pass import VoxelPassMixin
from core.renderer.object_fx_pass import ObjectFxPassMixin
from core.renderer.framebuffers import FramebuffersMixin
from core.renderer.water_pass import WaterPassMixin
from core.renderer.scene_uniforms import SceneUniformsMixin
from core.renderer.skinned_pass import SkinnedPassMixin
from core.renderer.scene_collector import SceneCollectorMixin
from core.renderer.geometry_cache import GeometryCacheMixin
from core.renderer.outline_pass import OutlinePassMixin
from core.renderer.gizmo_pass import GizmoPassMixin
from core.renderer.icon_pass import IconPassMixin
from core.renderer.cubemap_pass import CubemapPassMixin
from core.renderer.post_pass import PostPassMixin
from core.renderer.scene_renderer import SceneRendererMixin


__all__ = ["Renderer", "_RenderSnapshot", "_SpriteItem", "_SvgItem", "_VideoItem", "_ProjectorItem", "_TAAU_JITTER", "_halton"]


class Renderer(RendererConfigMixin, RendererProgramsMixin, VoxelPassMixin, ObjectFxPassMixin, FramebuffersMixin, WaterPassMixin, SceneUniformsMixin, SkinnedPassMixin, SceneCollectorMixin, GeometryCacheMixin, OutlinePassMixin, GizmoPassMixin, IconPassMixin, CubemapPassMixin, PostPassMixin, SceneRendererMixin):
    """Central renderer composing all rendering subsystems."""

    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._default_prog: Optional[moderngl.Program] = None
        self._grid_prog: Optional[moderngl.Program] = None
        self._gizmo_prog: Optional[moderngl.Program] = None
        self._skybox_cube: Optional[MeshData] = None
        self._wireframe_prog: Optional[moderngl.Program] = None
        self._outline_prog: Optional[moderngl.Program] = None
        self._object_fx_prog: Optional[moderngl.Program] = None
        self._gizmo_fatline_prog: Optional[moderngl.Program] = None
        self._gizmo_solid_prog: Optional[moderngl.Program] = None
        self._shadow_prog: Optional[moderngl.Program] = None
        self._particle_prog: Optional[moderngl.Program] = None
        self._icon_prog: Optional[moderngl.Program] = None
        self._icon_textures: dict = {}
        self._sprite_prog: Optional[moderngl.Program] = None
        self._video_prog: Optional[moderngl.Program] = None
        self._text_prog: Optional[moderngl.Program] = None
        self._overlay_prog: Optional[moderngl.Program] = None
        self._projector_prog: Optional[moderngl.Program] = None
        self._projector_vao: Optional[moderngl.VertexArray] = None
        self._quad_vbo: Optional[moderngl.Buffer] = None
        self._quad_ibo: Optional[moderngl.Buffer] = None
        self._quad_vao: Optional[moderngl.VertexArray] = None
        self._scene_fbo: Optional[moderngl.Framebuffer] = None
        self._scene_color_tex: Optional[moderngl.Texture] = None
        self._scene_depth_tex: Optional[moderngl.Texture] = None
        self._scene_fbo_size: tuple = (0, 0)
        self._initialized: bool = False
        self._render_mode: RenderMode = RenderMode.SHADED
        self._max_lights: int = 8
        self._light_uniforms = [
            {
                "type": f"u_lights[{i}].type",
                "position": f"u_lights[{i}].position",
                "direction": f"u_lights[{i}].direction",
                "color": f"u_lights[{i}].color",
                "intensity": f"u_lights[{i}].intensity",
                "range": f"u_lights[{i}].range",
                "spot_angle": f"u_lights[{i}].spot_angle",
                "spot_inner_angle": f"u_lights[{i}].spot_inner_angle",
                "right": f"u_lights[{i}].right",
                "up": f"u_lights[{i}].up",
                "area_width": f"u_lights[{i}].area_width",
                "area_height": f"u_lights[{i}].area_height",
                "area_type": f"u_lights[{i}].area_type",
                "area_samples": f"u_lights[{i}].area_samples",
                "area_double_sided": f"u_lights[{i}].area_double_sided",
            }
            for i in range(self._max_lights)
        ]
        self._ambient: list[float] = [0.26, 0.28, 0.34]
        self._selection_outline_color: list[float] = [0.8, 0.5, 0.1, 1.0]
        self._selection_outline_thickness: float = 0.03
        self._draw_calls: int = 0
        self._opaque_draws: int = 0
        self._trans_draws: int = 0
        self._triangles_drawn: int = 0
        self._vertices_drawn: int = 0
        self._particle_count: int = 0
        self._culled_total: int = 0
        self._culled_visible: int = 0
        self._rt_rays_per_frame: int = 0
        self._render_callback: Optional[Callable] = None
        self._shadow_resolution: int = 2048
        self._shadow_distance: float = 50.0
        self._cascade_count: int = 4
        self._cascade_splits_norm: Optional[list] = None
        self._point_shadow_resolution: int = 512
        self._area_shadow_resolution: int = 512
        self._spot_shadow_resolution: int = 1024
        self._shadow_enabled: bool = True
        self._shadow_type_flags: dict = {'directional': True, 'point': True, 'spot': True, 'area': True}
        self._render_scale: float = 1.0
        self._line_width: float = 0.6667
        self._clear_color: list = [0.18, 0.18, 0.18]
        self._import_meta_cache: dict[str, tuple] = {}
        self._import_meta_mtime: dict[str, float] = {}
        self._snap_cache: Optional[_RenderSnapshot] = None
        self._snap_cache_reuse: Optional[_RenderSnapshot] = None
        self._snap_version: int = -1
        self._snap_struct_version: int = -1
        self._snap_mesh_gen: int = -1
        self._snap_scene: object = None
        self._normal_cache: dict[int, np.ndarray] = {}
        self._prog_member_cache: dict[int, frozenset] = {}
        self._skinning_cache: dict[tuple, tuple] = {}
        self._skinning_frame: int = -1
        self._morph_cache: dict[str, object] = {}
        self._morph_sig: dict[str, tuple] = {}
        self._snap_morph_sig: tuple = ()
        self._rendering_cubemap_face: bool = False
        self._vec3_buf_a = np.zeros(3, dtype=np.float32)
        self._vec3_buf_b = np.zeros(3, dtype=np.float32)
        self._vec3_buf_c = np.zeros(3, dtype=np.float32)
        self._ambient_buf = np.zeros(3, dtype=np.float32)
        self._white3 = np.ones(3, dtype=np.float32)
        self._view_proj_cache: dict[int, tuple[bytes, bytes, bytes]] = {}
        self._lights_cache: dict[int, bytes] = {}

        self._pp_fbo_a: Optional[moderngl.Framebuffer] = None
        self._pp_fbo_b: Optional[moderngl.Framebuffer] = None
        self._pp_color_tex_a: Optional[moderngl.Texture] = None
        self._pp_color_tex_b: Optional[moderngl.Texture] = None
        self._pp_fbo_size: tuple = (0, 0)
        self._pp_copy_prog: Optional[moderngl.Program] = None
        self._pp_copy_vao: Optional[moderngl.VertexArray] = None
        self._pp_tonemap_prog: Optional[moderngl.Program] = None
        self._pp_tonemap_vao: Optional[moderngl.VertexArray] = None
        self._exposure: float = 0.0

        self._se_fbo_a: Optional[moderngl.Framebuffer] = None
        self._se_fbo_b: Optional[moderngl.Framebuffer] = None
        self._se_color_tex_a: Optional[moderngl.Texture] = None
        self._se_color_tex_b: Optional[moderngl.Texture] = None
        self._se_fbo_size: tuple = (0, 0)

        self._velocity_tex: Optional[moderngl.Texture] = None
        self._velocity_fbo: Optional[moderngl.Framebuffer] = None
        self._velocity_depth: Optional[moderngl.Renderbuffer] = None
        self._velocity_prog: Optional[moderngl.Program] = None
        self._velocity_vao: Optional[moderngl.VertexArray] = None
        self._velocity_geom_prog: Optional[moderngl.Program] = None
        self._prev_view_proj_by_target: dict[int, Mat4] = {}
        self._prev_model_by_entity: dict[int, Mat4] = {}
        self._velocity_fbo_size: tuple = (0, 0)

        self._grid: Optional[GridRenderer] = None
        self._gizmo: Optional[GizmoRenderer] = None
        self._shadows: Optional[ShadowRenderer] = None
        self._skybox_enabled: bool = True
        self._particles: Optional[ParticleRenderer] = None
        self._sprites: Optional[SpriteRendererGL] = None
        self._videos: Optional[VideoRendererGL] = None
        self._text: Optional[TextRendererGL] = None
        self._svgs: Optional[SvgRendererGL] = None
        self._icons: Optional[IconRenderer] = None
        self._gaussians: Optional[GaussianSplatRenderer] = None
        self._materials: Optional[MaterialManager] = None
        self._shaders: Optional[ShaderManager] = None
        self._mesh_loader: Optional[MeshLoader] = None
        self._cloud_quad: Optional[MeshData] = None
        self._cloud_plane: Optional[MeshData] = None
        self._water_plane: Optional[MeshData] = None
        self._water_chunk_mesh: Optional[MeshData] = None
        self._water_box_mesh: Optional[MeshData] = None
        self._water_mesh_cache: dict = {}
        self._water_fbo: Optional[moderngl.Framebuffer] = None
        self._water_color_tex: Optional[moderngl.Texture] = None
        self._water_sim_prog: Optional[moderngl.Program] = None
        self._water_sim_vao: Optional[moderngl.VertexArray] = None
        self._water_sim_a: Optional[moderngl.Texture] = None
        self._water_sim_b: Optional[moderngl.Texture] = None
        self._water_sim_fbo_a: Optional[moderngl.Framebuffer] = None
        self._water_sim_fbo_b: Optional[moderngl.Framebuffer] = None
        self._water_sim_size: int = 512
        self._water_sim_world: dict = {}
        self._water_depth_rb: Optional[moderngl.Renderbuffer] = None
        self._water_fbo_size: tuple = (0, 0)
        self._batcher: Optional[RenderBatcher] = None
        self._gpu_storage: Optional[GpuStorage] = None
        self._gpu_culling: Optional[GpuCulling] = None
        self._skinned_bone_ssbo: Optional[Any] = None
        self._skinned_bone_ssbo_capacity: int = 0
        self._render_count: int = 0
        self._vox_prog: Optional[moderngl.Program] = None
        self._vox_vao: Optional[moderngl.VertexArray] = None
        self._vox_cube_vbo: Optional[moderngl.Buffer] = None
        self._vox_cube_ibo: Optional[moderngl.Buffer] = None
        self._vox_inst_vbo: Optional[moderngl.Buffer] = None
        self._vox_inst_cap: int = 0
        self._vox_compute: Optional[moderngl.ComputeShader] = None


    def request_render(self, callback: Callable) -> None:
        self._render_callback = callback
        if self._mesh_loader:
            self._mesh_loader.set_render_callback(callback)


    def release(self):
        GraphicsEffect.cleanup_registry()
        self._prev_view_proj_by_target.clear()
        self._release_scene_fbo()
        self._release_pp_fbo()
        self._release_se_fbo()
        self._release_water_fbo()
        if self._batcher:
            self._batcher.release()
        if self._mesh_loader:
            self._mesh_loader.release()
        if self._grid:
            pass
        if self._gizmo:
            self._gizmo.release()
        if self._shadows:
            self._shadows.release()
        if self._particles:
            self._particles.release()
        if self._svgs:
            self._svgs.release()
        if self._text:
            self._text.release()
        if self._cloud_quad:
            self._cloud_quad.release()
        if self._cloud_plane:
            self._cloud_plane.release()
        if self._icons:
            self._icons.release()
        if self._materials:
            self._materials.release()
        if self._shaders:
            self._shaders.release()
        for buff in [self._quad_vbo, self._quad_ibo]:
            if buff:
                try:
                    buff.release()
                except Exception:
                    pass
        if self._quad_vao:
            try:
                self._quad_vao.release()
            except Exception:
                pass
        if self._pp_copy_vao:
            try:
                self._pp_copy_vao.release()
            except Exception:
                pass
        if self._pp_tonemap_vao:
            try:
                self._pp_tonemap_vao.release()
            except Exception:
                pass
        if self._projector_vao:
            try:
                self._projector_vao.release()
            except Exception:
                pass
        if self._velocity_vao:
            try:
                self._velocity_vao.release()
            except Exception:
                pass
        self._release_velocity_fbo()
        if self._gpu_storage:
            self._gpu_storage.release()
        for prog in [self._default_prog, self._grid_prog, self._gizmo_prog,
                     self._wireframe_prog, self._outline_prog,
                     self._gizmo_fatline_prog, self._gizmo_solid_prog,
                     self._shadow_prog, self._particle_prog, self._icon_prog, self._sprite_prog,
                     self._text_prog, self._overlay_prog, self._projector_prog, self._pp_copy_prog,
                     self._pp_tonemap_prog,
                     self._velocity_prog]:
            if prog:
                try:
                    prog.release()
                except Exception:
                    pass
        Logger.info("Renderer released.")
