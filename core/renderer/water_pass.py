# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Water simulation and water passes."""

from __future__ import annotations
import time
import numpy as np
import moderngl
from core.foundation.logger import Logger
from core.maths.math3d import Mat4, Vec3
from core.renderer.mesh_data import MeshData, read_shader
from core.renderer.meshes import make_cube_mesh, make_sphere_mesh, make_plane_mesh, make_quad_mesh, make_water_plane, make_water_box


class WaterPassMixin:
    """Water simulation and water passes."""


    def _init_water_sim(self):
        try:
            self._water_sim_prog = self._ctx.program(
                vertex_shader=read_shader("shadow_overlay.vert"),
                fragment_shader=self._load_water_sim_frag(),
            )
        except Exception as e:
            Logger.error(f"Failed to init water sim: {e}", e)
            self._water_sim_prog = None
        if self._water_sim_prog is not None:
            quad_verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
            quad_indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
            vbo = self._ctx.buffer(quad_verts.tobytes())
            ibo = self._ctx.buffer(quad_indices.tobytes())
            self._sim_quad_vbo = vbo
            self._sim_quad_ibo = ibo
            self._water_sim_vao = self._ctx.vertex_array(
                self._water_sim_prog,
                [(vbo, '2f', 'in_position')],
                ibo
            )
        self._ensure_water_sim_textures(self._water_sim_size)


    def _load_water_sim_frag(self) -> str:
        from core.assets.material import _extract_glsl_from_shader
        import os as _os
        path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "core", "shaders", "WaterSim.shader")
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        _, frag = _extract_glsl_from_shader(text)
        return frag


    def _ensure_water_sim_textures(self, size: int):
        if self._water_sim_a is not None and self._water_sim_size == size:
            return
        for obj in [self._water_sim_a, self._water_sim_b, self._water_sim_fbo_a, self._water_sim_fbo_b]:
            if obj:
                try:
                    obj.release()
                except Exception:
                    pass
        self._water_sim_a = self._ctx.texture((size, size), 2, dtype='f2')
        self._water_sim_b = self._ctx.texture((size, size), 2, dtype='f2')
        self._water_sim_a.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._water_sim_b.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._water_sim_a.repeat_x = False
        self._water_sim_a.repeat_y = False
        self._water_sim_b.repeat_x = False
        self._water_sim_b.repeat_y = False
        self._water_sim_fbo_a = self._ctx.framebuffer(self._water_sim_a)
        self._water_sim_fbo_b = self._ctx.framebuffer(self._water_sim_b)
        self._water_sim_size = size
        self._water_sim_fbo_a.clear(color=(0.0, 0.0, 0.0, 1.0))
        self._water_sim_fbo_b.clear(color=(0.0, 0.0, 0.0, 1.0))


    def _step_water_sim(self, water_component, grid_center, grid_size, rest_y, dt):
        prog = self._water_sim_prog
        if prog is None or self._water_sim_vao is None:
            return None
        if not getattr(water_component, "interaction_enabled", True):
            return None
        size = self._water_sim_size
        self._ensure_water_sim_textures(size)
        interactors = getattr(self, "_last_interactors", [])
        count = min(len(interactors), 64)
        pos_arr = np.zeros((64, 4), dtype=np.float32)
        vel_arr = np.zeros((64, 4), dtype=np.float32)
        for i in range(count):
            ent, center, radius, vel = interactors[i][:4]
            vradius = interactors[i][4] if len(interactors[i]) > 4 else radius
            vy = vel.y if vel is not None else 0.0
            vx = vel.x if vel is not None else 0.0
            vz = vel.z if vel is not None else 0.0
            depth = center.y - rest_y
            pos_arr[i] = [center.x, center.z, max(radius, 0.05), depth]
            vel_arr[i] = [vx, vy, vz, max(vradius, 0.05)]
        prev = self._water_sim_a
        dst_fbo = self._water_sim_fbo_b
        prev.use(10)
        prog["_PrevState"] = 10
        prog["_Texel"] = (1.0 / size, 1.0 / size)
        prog["_Dt"] = float(min(dt, 0.05))
        prog["_Damping"] = float(getattr(water_component, "sim_damping", 0.04))
        prog["_Propagation"] = float(getattr(water_component, "sim_propagation", 18.0))
        prog["_Saturation"] = float(getattr(water_component, "sim_saturation", 4.0))
        prog["_GridSize"] = float(grid_size)
        prog["_GridCenter"] = (float(grid_center[0]), float(grid_center[2]))
        prog["_InteractionStrength"] = float(getattr(water_component, "interaction_strength", 1.0))
        prog["_InteractorCount"] = int(count)
        try:
            prog["_Interactors"].write(pos_arr.tobytes())
            prog["_InteractorVel"].write(vel_arr.tobytes())
        except Exception:
            pass
        old_fbo = self._ctx.fbo
        old_vp = self._ctx.viewport
        dst_fbo.use()
        dst_fbo.viewport = (0, 0, size, size)
        self._ctx.viewport = (0, 0, size, size)
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.disable(moderngl.BLEND)
        self._water_sim_vao.render()
        old_fbo.use()
        self._ctx.viewport = old_vp
        self._ctx.enable(moderngl.DEPTH_TEST)
        self._water_sim_a, self._water_sim_b = self._water_sim_b, self._water_sim_a
        self._water_sim_fbo_a, self._water_sim_fbo_b = self._water_sim_fbo_b, self._water_sim_fbo_a
        return self._water_sim_a


    def _get_water_plane_mesh(self, res: int) -> MeshData:
        key = ("plane", int(res))
        m = self._water_mesh_cache.get(key)
        if m is None:
            m = make_water_plane(1.0, max(2, int(res)))
            m.build_gl(self._ctx, self._default_prog)
            self._water_mesh_cache[key] = m
        return m


    def _get_water_box_mesh(self, res: int) -> MeshData:
        key = ("box", int(res))
        m = self._water_mesh_cache.get(key)
        if m is None:
            m = make_water_box(max(2, int(res)), max(2, int(res) // 8), 1.0)
            m.build_gl(self._ctx, self._default_prog)
            self._water_mesh_cache[key] = m
        return m


    def _compute_water_chunk_models(self, cam_pos, water_y, ocean_size, chunk_size=200):
        from core.maths.math3d import Mat4, Vec3
        grid_radius = max(1, int(round(ocean_size / (2.0 * chunk_size))))
        gcx = round(cam_pos.x / chunk_size) * chunk_size
        gcz = round(cam_pos.z / chunk_size) * chunk_size
        models = []
        for i in range(-grid_radius, grid_radius + 1):
            for j in range(-grid_radius, grid_radius + 1):
                cx = gcx + i * chunk_size
                cz = gcz + j * chunk_size
                model = Mat4.scale(Vec3(chunk_size, 1.0, chunk_size)) * Mat4.translation(Vec3(cx, water_y, cz))
                models.append(model)
        return models


    def _render_underwater_pass(self, w, h, view_f32, proj_f32, cam_pos,
                                sun_dir, sun_color, sun_intensity,
                                fog_color, caustic_color, depth_below,
                                cam_near, cam_far,
                                water_component=None, inv_view_proj_f32=None):
        if self._underwater_prog is None or self._underwater_vao is None:
            return
        self._ensure_pp_fbo(w, h)
        self._ctx.copy_framebuffer(self._pp_fbo_a, self._scene_fbo)
        self._scene_fbo.use()
        self._scene_fbo.viewport = (0, 0, w, h)
        self._ctx.viewport = (0, 0, w, h)
        old_mask = self._ctx.depth_mask
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.depth_mask = False
        prog = self._underwater_prog
        if "u_scene" in prog:
            self._pp_color_tex_a.use(0)
            prog["u_scene"] = 0
        if "u_depth" in prog:
            self._scene_depth_tex.use(1)
            prog["u_depth"] = 1



        t = time.time()
        if water_component is not None:
            try:
                t = time.time() - water_component._time_origin
            except Exception:
                pass
        if "u_time" in prog:
            prog["u_time"].value = t
        if "u_resolution" in prog:
            prog["u_resolution"].value = (float(w), float(h))
        if "u_cam_pos" in prog:
            prog["u_cam_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        if "u_sun_dir" in prog:
            prog["u_sun_dir"].write(np.array([sun_dir.x, sun_dir.y, sun_dir.z], dtype=np.float32).tobytes())
        if "u_sun_color" in prog:
            prog["u_sun_color"].write(np.array(sun_color, dtype=np.float32).tobytes())
        if "u_sun_intensity" in prog:
            prog["u_sun_intensity"].value = float(sun_intensity)
        if "u_fog_color" in prog:
            prog["u_fog_color"].write(np.array(fog_color, dtype=np.float32).tobytes())
        if "u_caustic_color" in prog:
            prog["u_caustic_color"].write(np.array(caustic_color, dtype=np.float32).tobytes())
        if "u_depth_below" in prog:
            prog["u_depth_below"].value = float(depth_below)
        if "u_cam_near" in prog:
            prog["u_cam_near"].value = float(cam_near)
        if "u_cam_far" in prog:
            prog["u_cam_far"].value = float(cam_far)
        if "u_view" in prog:
            prog["u_view"].write(view_f32)
        if "u_proj" in prog:
            prog["u_proj"].write(proj_f32)
        if "u_inv_view_proj" in prog and inv_view_proj_f32 is not None:
            prog["u_inv_view_proj"].write(inv_view_proj_f32)
        if "u_fog_density" in prog:
            prog["u_fog_density"].value = 0.045


        if water_component is not None:
            surface_y = 0.0
            tr = water_component.transform
            if tr is not None:
                surface_y = float(tr.position.y)
            if "u_surface_y" in prog:
                prog["u_surface_y"].value = surface_y
            if "u_caustics_strength" in prog:
                prog["u_caustics_strength"].value = float(getattr(water_component, "caustics", 0.0))
            ws = water_component.get_wave_uniforms(t, cam_pos.x, cam_pos.z)
            if "_WaveCount" in prog:
                prog["_WaveCount"].value = ws["wave_count"]
                prog["_WaveDirection"].write(ws["dirs"].tobytes())
                prog["_WaveParams"].write(ws["params"].tobytes())
            if "_WindDir" in prog:
                prog["_WindDir"].write(np.array([ws["wind_dir"][0], ws["wind_dir"][1]], dtype=np.float32).tobytes())
            if "_WindSpeed" in prog:
                prog["_WindSpeed"].value = ws["wind_speed"]
            if "_WindGust" in prog:
                prog["_WindGust"].value = ws["wind_gust"]
            if "_WindTurbulence" in prog:
                prog["_WindTurbulence"].value = ws["wind_turbulence"]
            if "_WindAlign" in prog:
                prog["_WindAlign"].value = ws["wind_align"]
            if "_Choppiness" in prog:
                prog["_Choppiness"].value = ws["choppiness"]
            if "_MacroWave" in prog:
                prog["_MacroWave"].value = ws["macro_wave"]
            if "_Chaos" in prog:
                prog["_Chaos"].value = ws["chaos"]
        try:
            self._underwater_vao.render()
        finally:
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.depth_mask = old_mask


    def _render_caustics_pass(self, w, h, view_f32, proj_f32, cam_pos,
                              sun_dir, sun_color, sun_intensity,
                              caustic_color, caustics_strength, surface_y,
                              water_component, inv_view_proj_f32,
                              cam_near, cam_far):
        """Material-independent underwater caustics.

        Projects physically based caustics (see caustics.glsl) onto every
        submerged pixel of the scene, regardless of the material / shader used
        by the geometry below the water. Runs from above or below the surface.
        """
        if self._caustics_prog is None or self._caustics_vao is None:
            return
        if water_component is None or caustics_strength <= 0.0:
            return
        self._ensure_pp_fbo(w, h)
        self._ctx.copy_framebuffer(self._pp_fbo_a, self._scene_fbo)
        self._scene_fbo.use()
        self._scene_fbo.viewport = (0, 0, w, h)
        self._ctx.viewport = (0, 0, w, h)
        old_mask = self._ctx.depth_mask
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.depth_mask = False
        prog = self._caustics_prog
        if "u_scene" in prog:
            self._pp_color_tex_a.use(0)
            prog["u_scene"] = 0
        if "u_depth" in prog:
            self._scene_depth_tex.use(1)
            prog["u_depth"] = 1
        if "u_time" in prog:
            try:
                prog["u_time"].value = time.time() - water_component._time_origin
            except Exception:
                prog["u_time"].value = time.time()
        if "u_resolution" in prog:
            prog["u_resolution"].value = (float(w), float(h))
        if "u_cam_pos" in prog:
            prog["u_cam_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        if "u_sun_dir" in prog:
            prog["u_sun_dir"].write(np.array([sun_dir.x, sun_dir.y, sun_dir.z], dtype=np.float32).tobytes())
        if "u_sun_color" in prog:
            prog["u_sun_color"].write(np.array(sun_color, dtype=np.float32).tobytes())
        if "u_sun_intensity" in prog:
            prog["u_sun_intensity"].value = float(sun_intensity)
        if "u_caustic_tint" in prog:
            prog["u_caustic_tint"].write(np.array(caustic_color, dtype=np.float32).tobytes())
        if "u_caustics_strength" in prog:
            prog["u_caustics_strength"].value = float(caustics_strength)
        if "u_surface_y" in prog:
            prog["u_surface_y"].value = float(surface_y)
        if "u_cam_near" in prog:
            prog["u_cam_near"].value = float(cam_near)
        if "u_cam_far" in prog:
            prog["u_cam_far"].value = float(cam_far)
        if "u_inv_view_proj" in prog and inv_view_proj_f32 is not None:
            prog["u_inv_view_proj"].write(inv_view_proj_f32)

        ws = water_component.get_wave_uniforms(time.time() - water_component._time_origin, cam_pos.x, cam_pos.z)
        if "_WaveCount" in prog:
            prog["_WaveCount"].value = ws["wave_count"]
            prog["_WaveDirection"].write(ws["dirs"].tobytes())
            prog["_WaveParams"].write(ws["params"].tobytes())
        if "_WindDir" in prog:
            prog["_WindDir"].write(np.array([ws["wind_dir"][0], ws["wind_dir"][1]], dtype=np.float32).tobytes())
        if "_WindSpeed" in prog:
            prog["_WindSpeed"].value = ws["wind_speed"]
        if "_WindGust" in prog:
            prog["_WindGust"].value = ws["wind_gust"]
        if "_WindTurbulence" in prog:
            prog["_WindTurbulence"].value = ws["wind_turbulence"]
        if "_WindAlign" in prog:
            prog["_WindAlign"].value = ws["wind_align"]
        if "_Choppiness" in prog:
            prog["_Choppiness"].value = ws["choppiness"]
        if "_MacroWave" in prog:
            prog["_MacroWave"].value = ws["macro_wave"]
        if "_Chaos" in prog:
            prog["_Chaos"].value = ws["chaos"]
        try:
            self._caustics_vao.render()
        finally:
            self._ctx.enable(moderngl.DEPTH_TEST)
            self._ctx.depth_mask = old_mask


    def _set_overlay_uniforms(self, overlay_prog, view_f32, inv_vp_f32):
        overlay_prog["u_inv_vp"].write(inv_vp_f32.tobytes())
        overlay_prog["u_view"].write(view_f32.tobytes())
        overlay_prog["u_scene_color"] = 13
        overlay_prog["u_depth_tex"] = 14
        self._scene_color_tex.use(13)
        self._scene_depth_tex.use(14)
        self._shadows.set_uniforms(overlay_prog)
        if "u_shadow_bias" in overlay_prog:
            overlay_prog["u_shadow_bias"].value = 0.0008
