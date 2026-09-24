# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""GL program compilation and registry."""

from __future__ import annotations
import os
import numpy as np
from core.foundation.logger import Logger
from core.renderer.mesh_data import MeshData, read_shader, read_shader_pair
from core.renderer.meshes import make_cube_mesh, make_sphere_mesh, make_plane_mesh, make_quad_mesh, make_water_plane, make_water_box
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


class RendererProgramsMixin:
    """GL program compilation and registry."""


    def initialize(self):
        try:
            try:
                from core.config.config import get_global_config
                self.load_config(get_global_config())
            except Exception:
                pass
            default_vert_src, default_frag_src = read_shader_pair("default")
            default_frag_src = ShaderManager._inject_area_shadows(default_frag_src)
            self._default_prog = program_with_fallback(
                self._ctx,
                vertex_shader=default_vert_src,
                fragment_shader=default_frag_src,
                label="default"
            )
            grid_vert_src, grid_frag_src = read_shader_pair("grid")
            self._grid_prog = self._ctx.program(
                vertex_shader=grid_vert_src,
                fragment_shader=grid_frag_src
            )
            gizmo_vert_src, gizmo_frag_src = read_shader_pair("gizmo")
            self._gizmo_prog = self._ctx.program(
                vertex_shader=gizmo_vert_src,
                fragment_shader=gizmo_frag_src
            )
            self._gizmo_fatline_prog = self._ctx.program(
                vertex_shader=FATLINE_VERT,
                fragment_shader=FATLINE_FRAG
            )
            gizmo_solid_vert_src, gizmo_solid_frag_src = read_shader_pair("gizmo_solid")
            self._gizmo_solid_prog = self._ctx.program(
                vertex_shader=gizmo_solid_vert_src,
                fragment_shader=gizmo_solid_frag_src
            )
            self._wireframe_prog = self._ctx.program(
                vertex_shader=gizmo_vert_src,
                fragment_shader=gizmo_frag_src
            )
            outline_vert_src, outline_frag_src = read_shader_pair("outline")
            self._outline_prog = self._ctx.program(
                vertex_shader=outline_vert_src,
                fragment_shader=outline_frag_src
            )
            shadow_vert_src, shadow_frag_src = read_shader_pair("shadow")
            self._shadow_prog = program_with_fallback(
                self._ctx,
                vertex_shader=shadow_vert_src,
                fragment_shader=shadow_frag_src,
                label="shadow"
            )
            particle_vert_src, particle_frag_src = read_shader_pair("particle_gpu")
            self._particle_prog = program_with_fallback(
                self._ctx,
                vertex_shader=particle_vert_src,
                fragment_shader=particle_frag_src,
                label="particle_gpu"
            )
            icon_vert_src, icon_frag_src = read_shader_pair("icon")
            self._icon_prog = self._ctx.program(
                vertex_shader=icon_vert_src,
                fragment_shader=icon_frag_src
            )
            sprite_vert_src, sprite_frag_src = read_shader_pair("sprite")
            self._sprite_prog = self._ctx.program(
                vertex_shader=sprite_vert_src,
                fragment_shader=sprite_frag_src
            )
            video_vert_src, video_frag_src = read_shader_pair("video")
            self._video_prog = self._ctx.program(
                vertex_shader=video_vert_src,
                fragment_shader=video_frag_src
            )
            text_vert_src, text_frag_src = read_shader_pair("text")
            self._text_prog = self._ctx.program(
                vertex_shader=text_vert_src,
                fragment_shader=text_frag_src
            )
            overlay_vert_src, overlay_frag_src = read_shader_pair("shadow_overlay")
            self._overlay_prog = self._ctx.program(
                vertex_shader=overlay_vert_src,
                fragment_shader=overlay_frag_src
            )
            projector_vert_src, projector_frag_src = read_shader_pair("projector")
            self._projector_prog = self._ctx.program(
                vertex_shader=projector_vert_src,
                fragment_shader=projector_frag_src
            )
            PP_COPY_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    frag_color = vec4(texture(u_input_tex, v_uv).rgb, 1.0);
}
"""
            self._pp_copy_prog = self._ctx.program(
                vertex_shader=overlay_vert_src,
                fragment_shader=PP_COPY_FRAG
            )
            PP_TONEMAP_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
uniform float u_exposure;
in vec2 v_uv;
out vec4 frag_color;
vec3 tonemap_aces(vec3 c) {
    float a = 2.51;
    float b = 0.03;
    float c_ = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((c * (a * c + b)) / (c * (c_ * c + d) + e), 0.0, 1.0);
}
void main() {
    vec3 color = texture(u_input_tex, v_uv).rgb;
    color *= exp2(u_exposure);
    color = tonemap_aces(color);
    frag_color = vec4(color, 1.0);
}
"""
            self._pp_tonemap_prog = self._ctx.program(
                vertex_shader=overlay_vert_src,
                fragment_shader=PP_TONEMAP_FRAG
            )
            quad_verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
            quad_indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
            self._quad_vbo = self._ctx.buffer(quad_verts.tobytes())
            self._quad_ibo = self._ctx.buffer(quad_indices.tobytes())
            self._pp_copy_vao = self._ctx.vertex_array(
                self._pp_copy_prog,
                [(self._quad_vbo, '2f', 'in_position')],
                self._quad_ibo
            )
            self._pp_tonemap_vao = self._ctx.vertex_array(
                self._pp_tonemap_prog,
                [(self._quad_vbo, '2f', 'in_position')],
                self._quad_ibo
            )
            self._quad_vao = self._ctx.vertex_array(
                self._overlay_prog,
                [(self._quad_vbo, '2f', 'in_position')],
                self._quad_ibo
            )
            try:
                underwater_vert_src, underwater_frag_src = read_shader_pair("underwater")
                self._underwater_prog = self._ctx.program(
                    vertex_shader=underwater_vert_src,
                    fragment_shader=underwater_frag_src
                )
            except Exception:
                self._underwater_prog = None
            if self._underwater_prog is not None:
                self._underwater_vao = self._ctx.vertex_array(
                    self._underwater_prog,
                    [(self._quad_vbo, '2f', 'in_position')],
                    self._quad_ibo
                )
            else:
                self._underwater_vao = None
            try:
                caustics_vert_src, caustics_frag_src = read_shader_pair("caustics")
                self._caustics_prog = self._ctx.program(
                    vertex_shader=caustics_vert_src,
                    fragment_shader=caustics_frag_src
                )
            except Exception:
                self._caustics_prog = None
            if self._caustics_prog is not None:
                self._caustics_vao = self._ctx.vertex_array(
                    self._caustics_prog,
                    [(self._quad_vbo, '2f', 'in_position')],
                    self._quad_ibo
                )
            else:
                self._caustics_vao = None
            VELOCITY_FRAG = """
#version 330 core
uniform sampler2D u_depth_tex;
uniform mat4 u_inv_view_proj;
uniform mat4 u_prev_view_proj;
uniform vec2 u_pixel_size;
in vec2 v_uv;
out vec2 frag_velocity;
void main() {
    float depth = texture(u_depth_tex, v_uv).r;
    if (depth >= 0.99999) {
        frag_velocity = vec2(0.0);
        return;
    }
    vec4 clip_pos = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 world_pos = u_inv_view_proj * clip_pos;
    world_pos /= world_pos.w;
    vec4 prev_clip = u_prev_view_proj * world_pos;
    vec2 prev_uv = prev_clip.xy / prev_clip.w * 0.5 + 0.5;
    vec2 velocity = v_uv - prev_uv;
    if (isnan(velocity.x) || isnan(velocity.y) || isinf(velocity.x) || isinf(velocity.y)) {
        frag_velocity = vec2(0.0);
        return;
    }
    float max_v = 64.0 * max(u_pixel_size.x, u_pixel_size.y);
    velocity = clamp(velocity, -vec2(max_v), vec2(max_v));
    frag_velocity = velocity;
}
"""
            self._velocity_prog = self._ctx.program(
                vertex_shader=overlay_vert_src,
                fragment_shader=VELOCITY_FRAG
            )
            self._velocity_vao = self._ctx.vertex_array(
                self._velocity_prog,
                [(self._quad_vbo, '2f', 'in_position')],
                self._quad_ibo
            )
            VELOCITY_GEOM_VERT = """
#version 330 core
in vec3 in_position;
uniform mat4 u_view_proj;
uniform mat4 u_prev_view_proj;
uniform mat4 u_model;
uniform mat4 u_prev_model;
out vec2 v_velocity;
void main() {
    vec4 cur_clip = u_view_proj * u_model * vec4(in_position, 1.0);
    vec4 prev_clip = u_prev_view_proj * u_prev_model * vec4(in_position, 1.0);
    vec2 cur_ndc = cur_clip.xy / cur_clip.w;
    vec2 prev_ndc = prev_clip.xy / prev_clip.w;
    v_velocity = (prev_ndc - cur_ndc) * 0.5;
    gl_Position = cur_clip;
}
"""
            VELOCITY_GEOM_FRAG = """
#version 330 core
in vec2 v_velocity;
out vec2 frag_velocity;
void main() {
    vec2 vel = v_velocity;
    if (isnan(vel.x) || isnan(vel.y) || isinf(vel.x) || isinf(vel.y))
        vel = vec2(0.0);
    frag_velocity = vel;
}
"""
            self._velocity_geom_prog = self._ctx.program(
                vertex_shader=VELOCITY_GEOM_VERT,
                fragment_shader=VELOCITY_GEOM_FRAG
            )
            self._projector_vao = self._ctx.vertex_array(
                self._projector_prog,
                [(self._quad_vbo, '2f', 'in_position')],
                self._quad_ibo
            )
            self._shaders = ShaderManager(self._ctx)
            self._shaders.store("core/shaders/internal/Default", self._default_prog)
            self._materials = MaterialManager(self._ctx)
            self._mesh_loader = MeshLoader(self._ctx, self._default_prog, self._outline_prog)
            self._mesh_loader.register_primitives()
            self._batcher = RenderBatcher(self._ctx, self._default_prog)
            self._default_prog = self._batcher._default_prog
            self._compile_object_fx()
            self._init_voxel_instancing()
            self._gpu_storage = GpuStorage(self._ctx)
            self._gpu_culling = self._gpu_storage.get_or_create_culling()
            self._grid = GridRenderer(self._ctx, self._grid_prog)
            self._load_grid_config()
            self._gizmo = GizmoRenderer(self._ctx, self._gizmo_prog, self._gizmo_fatline_prog, self._gizmo_solid_prog)
            self._gizmo._line_width = self._line_width
            self._gizmo.initialize_instanced_meshes()
            self._gizmo.initialize_instanced_lines()
            self._shadows = ShadowRenderer(self._ctx, self._shadow_prog, self._shadow_resolution, self._shadow_distance, cascade_count=self._cascade_count, cascade_splits=self._cascade_splits_norm, point_shadow_resolution=self._point_shadow_resolution)
            self._skybox_cube = make_cube_mesh()
            self._skybox_cube.build_gl(self._ctx, self._default_prog)
            self._cloud_quad = make_quad_mesh(2.0)
            self._cloud_quad.build_gl(self._ctx, self._default_prog)
            self._cloud_plane = make_plane_mesh(1.0)
            self._cloud_plane.build_gl(self._ctx, self._default_prog)
            self._water_plane = self._get_water_plane_mesh(200)
            self._water_chunk_mesh = self._get_water_plane_mesh(32)
            self._water_box_mesh = self._get_water_box_mesh(128)
            self._init_water_sim()
            self._particles = ParticleRenderer(self._ctx, self._particle_prog)
            self._particles.load_compute_shader(
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "shaders", "compute", "particle.compute")
            )
            self._sprites = SpriteRendererGL(self._ctx, self._sprite_prog)
            self._sprites.set_texture_loader(self._materials.load_texture)
            self._videos = VideoRendererGL(self._ctx, self._video_prog)
            self._text = TextRendererGL(self._ctx, self._text_prog)
            self._svgs = SvgRendererGL(self._ctx, self._sprite_prog)
            self._icons = IconRenderer(self._ctx, self._icon_prog)
            self._gaussians = GaussianSplatRenderer(self._ctx)
            try:
                from core.config.config import get_global_config
                self.load_config(get_global_config())
            except Exception:
                pass
            self._initialized = True
            Logger.info("Renderer initialized.")
        except Exception as e:
            Logger.error(f"Renderer init error: {e}", e)


    def _compile_object_fx(self):
        self._fx_prog_cache: dict = {}


    def _get_fx_program(self, fx_list):
        key = tuple(sorted(type(fx).__name__ for fx in fx_list))
        cached = self._fx_prog_cache.get(key)
        if cached is not None:
            return cached
        prog = None
        try:
            fx_vert, fx_frag = read_shader_pair("object_fx")
            fx_frag = ShaderManager._inject_area_shadows(fx_frag)
            fx_frag = ShaderManager._inject_caustics(fx_frag)
            uniforms_block = "\n".join(fx.fx_fragment_uniforms() for fx in fx_list)
            main_block = "\n".join(fx.fx_fragment_snippet() for fx in fx_list)
            fx_frag = fx_frag.replace("// @FX_UNIFORMS", uniforms_block)
            fx_frag = fx_frag.replace("// @FX_MAIN", main_block)
            geom = self._FX_PASSTHROUGH_GEOM
            for fx in fx_list:
                gs = fx.fx_geometry_shader()
                if gs:
                    geom = gs
                    break
            prog = program_with_fallback(
                self._ctx,
                vertex_shader=fx_vert,
                fragment_shader=fx_frag,
                geometry_shader=geom,
                label="object_fx",
            )
        except Exception as e:
            Logger.error(f"Failed to compile object_fx program for {key}: {e}", e)
            prog = None
        self._fx_prog_cache[key] = prog
        return prog
