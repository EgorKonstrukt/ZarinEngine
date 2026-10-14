# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import numpy as np
from core.foundation.logger import Logger
from core.renderer.meshd import MeshData, read_shader, read_shader_pair
from core.renderer.meshes import make_cube_mesh, make_sphere_mesh, make_plane_mesh, make_quad_mesh, make_water_plane, make_water_box
from core.renderer.grid import GridRenderer
from core.renderer.gizmor import GizmoRenderer, FATLINE_VERT, FATLINE_FRAG
from core.renderer.shadows import ShadowRenderer
from core.renderer.particles import ParticleRenderer
from core.renderer.spr import SpriteRendererGL
from core.renderer.svgr import SvgRendererGL
from core.renderer.videor import VideoRendererGL
from core.renderer.icons import IconRenderer
from core.renderer.splat import GaussianSplatRenderer
from core.renderer.textr import TextRendererGL
from core.renderer.mats import MaterialManager
from core.renderer.shaderp import ShaderManager, program_with_fallback
from core.renderer.meshload import MeshLoader
from core.renderer.batch import RenderBatcher, resolve_normal_matrix
from core.renderer.gpu_culling import GpuStorage, GpuCulling
from core.renderer.programs.fragments import PP_COPY_FRAG, PP_TONEMAP_FRAG, VELOCITY_FRAG, VELOCITY_GEOM_VERT, VELOCITY_GEOM_FRAG


class RendererProgramsMixin:

    def initialize(self):
        try:
            try:
                from core.renderer.prec import install_precision_hooks
                install_precision_hooks()
            except Exception:
                pass
            try:
                from core.config.config import get_global_config
                self.load_config(get_global_config())
            except Exception:
                pass
            default_vert_src, default_frag_src = read_shader_pair("default")
            self._default_prog = program_with_fallback(
                self._ctx,
                vertex_shader=default_vert_src,
                fragment_shader=default_frag_src,
                label="default"
            )
            grid_vert_src, grid_frag_src = read_shader_pair("grid")
            self._grid_prog = program_with_fallback(
                self._ctx,
                vertex_shader=grid_vert_src,
                fragment_shader=grid_frag_src,
                label="grid"
            )
            gizmo_vert_src, gizmo_frag_src = read_shader_pair("gizmo")
            self._gizmo_prog = program_with_fallback(
                self._ctx,
                vertex_shader=gizmo_vert_src,
                fragment_shader=gizmo_frag_src,
                label="gizmo"
            )
            self._gizmo_fatline_prog = program_with_fallback(
                self._ctx,
                vertex_shader=FATLINE_VERT,
                fragment_shader=FATLINE_FRAG,
                label="gizmo_fatline"
            )
            gizmo_solid_vert_src, gizmo_solid_frag_src = read_shader_pair("gizmo_solid")
            self._gizmo_solid_prog = program_with_fallback(
                self._ctx,
                vertex_shader=gizmo_solid_vert_src,
                fragment_shader=gizmo_solid_frag_src,
                label="gizmo_solid"
            )
            self._wireframe_prog = program_with_fallback(
                self._ctx,
                vertex_shader=gizmo_vert_src,
                fragment_shader=gizmo_frag_src,
                label="wireframe"
            )
            outline_vert_src, outline_frag_src = read_shader_pair("outline")
            self._outline_prog = program_with_fallback(
                self._ctx,
                vertex_shader=outline_vert_src,
                fragment_shader=outline_frag_src,
                label="outline"
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
            self._icon_prog = program_with_fallback(
                self._ctx,
                vertex_shader=icon_vert_src,
                fragment_shader=icon_frag_src,
                label="icon"
            )
            sprite_vert_src, sprite_frag_src = read_shader_pair("sprite")
            self._sprite_prog = program_with_fallback(
                self._ctx,
                vertex_shader=sprite_vert_src,
                fragment_shader=sprite_frag_src,
                label="sprite"
            )
            video_vert_src, video_frag_src = read_shader_pair("video")
            self._video_prog = program_with_fallback(
                self._ctx,
                vertex_shader=video_vert_src,
                fragment_shader=video_frag_src,
                label="video"
            )
            text_vert_src, text_frag_src = read_shader_pair("text")
            self._text_prog = program_with_fallback(
                self._ctx,
                vertex_shader=text_vert_src,
                fragment_shader=text_frag_src,
                label="text"
            )
            overlay_vert_src, overlay_frag_src = read_shader_pair("shadow_overlay")
            self._overlay_prog = program_with_fallback(
                self._ctx,
                vertex_shader=overlay_vert_src,
                fragment_shader=overlay_frag_src,
                label="shadow_overlay"
            )
            projector_vert_src, projector_frag_src = read_shader_pair("projector")
            self._projector_prog = program_with_fallback(
                self._ctx,
                vertex_shader=projector_vert_src,
                fragment_shader=projector_frag_src,
                label="projector"
            )
            self._pp_copy_prog = program_with_fallback(
                self._ctx,
                vertex_shader=overlay_vert_src,
                fragment_shader=PP_COPY_FRAG,
                label="pp_copy"
            )
            self._pp_tonemap_prog = program_with_fallback(
                self._ctx,
                vertex_shader=overlay_vert_src,
                fragment_shader=PP_TONEMAP_FRAG,
                label="pp_tonemap"
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
                self._underwater_prog = program_with_fallback(
                    self._ctx,
                    vertex_shader=underwater_vert_src,
                    fragment_shader=underwater_frag_src,
                    label="underwater"
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
                self._caustics_prog = program_with_fallback(
                    self._ctx,
                    vertex_shader=caustics_vert_src,
                    fragment_shader=caustics_frag_src,
                    label="caustics"
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
            self._velocity_prog = program_with_fallback(
                self._ctx,
                vertex_shader=overlay_vert_src,
                fragment_shader=VELOCITY_FRAG,
                label="velocity"
            )
            self._velocity_vao = self._ctx.vertex_array(
                self._velocity_prog,
                [(self._quad_vbo, '2f', 'in_position')],
                self._quad_ibo
            )
            self._velocity_geom_prog = program_with_fallback(
                self._ctx,
                vertex_shader=VELOCITY_GEOM_VERT,
                fragment_shader=VELOCITY_GEOM_FRAG,
                label="velocity_geom"
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
