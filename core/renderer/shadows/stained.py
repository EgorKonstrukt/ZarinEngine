# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
import moderngl
from core.renderer.shaderp import program_with_fallback
from .bind import _mat4_inv_fast
from .mathx import _tr_fwd_xyz
class StainedMixin:
    def _clear_atlas_tile(self, fbo, rect):
        try:
            prog = getattr(self, '_tile_clear_prog', None)
            if prog is None:
                prog = program_with_fallback(self._ctx, vertex_shader='#version 330 core\nvoid main() { vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)); gl_Position = vec4(p * 2.0 - 1.0, 1.0, 1.0); }', fragment_shader='#version 330 core\nvoid main() {}', label="tile_clear")
                self._tile_clear_prog = prog; self._tile_clear_vao = self._ctx.vertex_array(prog, [])
            fbo.use(); self._ctx.viewport = (rect[0], rect[1], rect[2], rect[3]); self._ctx.enable(moderngl.DEPTH_TEST); self._ctx.depth_func = '>='
            try:
                self._ctx.disable(moderngl.CULL_FACE)
            except Exception:
                pass
            self._tile_clear_vao.render(moderngl.TRIANGLES, vertices=3)
            try:
                self._ctx.enable(moderngl.CULL_FACE); self._ctx.cull_face = 'back'
            except Exception:
                pass
            self._ctx.depth_func = '<'
        except Exception:
            try:
                self._ctx.depth_func = '<'
            except Exception:
                pass
    def _ensure_stained_resources(self):
        try:
            if self._stained_tex is not None and self._stained_fbo is not None and self._stained_prog is not None and self._stained_depth_tex is not None and self._stained_depth_fbo is not None and self._stained_depth_prog is not None:
                return
        except Exception:
            pass
        try:
            if self._stained_tex is None:
                self._stained_tex = self._ctx.texture((1024, 1024), 4); self._stained_tex.filter = (moderngl.LINEAR, moderngl.LINEAR); self._stained_tex.repeat_x = False; self._stained_tex.repeat_y = False
            if self._stained_fbo is None:
                self._stained_fbo = self._ctx.framebuffer(self._stained_tex)
            if self._stained_depth_tex is None:
                self._stained_depth_tex = self._ctx.texture((1024, 1024), 1, dtype="f4"); self._stained_depth_tex.filter = (moderngl.NEAREST, moderngl.NEAREST); self._stained_depth_tex.repeat_x = False; self._stained_depth_tex.repeat_y = False
            if self._stained_depth_fbo is None:
                self._stained_depth_fbo = self._ctx.framebuffer(self._stained_depth_tex)
            if self._stained_prog is None:
                self._stained_prog = self._ctx.program(vertex_shader="#version 330 core\nin vec3 in_position;\nuniform mat4 u_model;\nuniform mat4 u_tint_vp;\nvoid main() {\n    gl_Position = u_tint_vp * u_model * vec4(in_position, 1.0);\n}\n", fragment_shader="#version 330 core\nuniform vec4 u_tint_color;\nout vec4 o;\nvoid main() {\n    o = u_tint_color;\n}\n")
            if self._stained_depth_prog is None:
                self._stained_depth_prog = self._ctx.program(vertex_shader="#version 330 core\nin vec3 in_position;\nuniform mat4 u_model;\nuniform mat4 u_tint_vp;\nout float v_depth01;\nvoid main() {\n    vec4 clip = u_tint_vp * u_model * vec4(in_position, 1.0);\n    gl_Position = clip;\n    v_depth01 = clamp(clip.z / max(clip.w, 1e-5) * 0.5 + 0.5, 0.0, 1.0);\n}\n", fragment_shader="#version 330 core\nin float v_depth01;\nout float o;\nvoid main() {\n    o = v_depth01;\n}\n")
        except Exception:
            pass
    def _render_stained_pass(self, sun_lt, tint_casters, material_manager, cam_near, cam_far, cam_fov, aspect, view_mat):
        try:
            self._stained_valid = False
        except Exception:
            pass
        try:
            if not tint_casters or material_manager is None or sun_lt is None:
                return
            try:
                ld_x, ld_y, ld_z = _tr_fwd_xyz(sun_lt)
            except Exception:
                try:
                    _fd = sun_lt.forward.normalized(); ld_x, ld_y, ld_z = float(_fd.x), float(_fd.y), float(_fd.z)
                except Exception:
                    return
            try:
                from core.maths.math3d import Vec3 as _Vec3
                _ld = _Vec3(ld_x, ld_y, ld_z)
            except Exception:
                return
            try:
                vd = view_mat._d
                inv_view = _mat4_inv_fast(np.ascontiguousarray(vd, dtype=np.float64)) if _mat4_inv_fast is not None else np.linalg.inv(vd)
            except Exception:
                try:
                    inv_view = np.linalg.inv(view_mat._d)
                except Exception:
                    return
            try:
                corners = self._get_frustum_corners(max(cam_near, 0.01), cam_far, cam_fov, aspect, inv_view)
                vp = self._build_directional_cascade(_ld, corners, max(cam_far - cam_near, 1.0))
                vp_bytes = np.ascontiguousarray(np.asarray(vp, dtype=np.float32).reshape(4, 4), dtype=np.float32).tobytes()
            except Exception:
                return
            self._ensure_stained_resources()
            if self._stained_tex is None or self._stained_fbo is None or self._stained_prog is None or self._stained_depth_tex is None or self._stained_depth_fbo is None or self._stained_depth_prog is None:
                return
            try:
                self._stained_vp_bytes = vp_bytes
            except Exception:
                pass
            prog = self._stained_prog
            try:
                names = self._uniform_names(prog)
            except Exception:
                names = frozenset()
            try:
                prog["u_tint_vp"].write(vp_bytes)
            except Exception:
                pass
            dprog = self._stained_depth_prog
            try:
                dnames = self._uniform_names(dprog)
            except Exception:
                dnames = frozenset()
            try:
                dprog["u_tint_vp"].write(vp_bytes)
            except Exception:
                pass
            try:
                self._stained_fbo.use(); self._stained_fbo.viewport = (0, 0, 1024, 1024); self._ctx.viewport = (0, 0, 1024, 1024)
            except Exception:
                pass
            try:
                self._ctx.disable(moderngl.DEPTH_TEST)
            except Exception:
                pass
            try:
                self._ctx.disable(moderngl.CULL_FACE)
            except Exception:
                pass
            try:
                self._ctx.enable(moderngl.BLEND); self._ctx.blend_func = moderngl.ZERO, moderngl.SRC_COLOR
            except Exception:
                pass
            try:
                self._stained_fbo.clear(1.0, 1.0, 1.0, 1.0)
            except Exception:
                pass
            try:
                origin = self._shadow_origin
            except Exception:
                origin = None
            drew = False
            for _tc in tint_casters:
                try:
                    _mesh, _tr, _mp = _tc
                except Exception:
                    continue
                try:
                    _tint = material_manager.stained_tint(_mp); _trr = float(_tint[0]); _tg = float(_tint[1]); _tb = float(_tint[2])
                except Exception:
                    _trr, _tg, _tb = 1.0, 1.0, 1.0
                try:
                    _wm = _tr.world_matrix
                except Exception:
                    continue
                try:
                    from core.renderer.origin import relativize_model_f32
                    _mb = relativize_model_f32(_wm, origin)
                except Exception:
                    try:
                        _mb = _wm.to_f32()
                    except Exception:
                        continue
                try:
                    if "u_model" in names:
                        prog["u_model"].write(_mb)
                    if "u_tint_color" in names:
                        prog["u_tint_color"].write(np.array([_trr, _tg, _tb, 1.0], dtype=np.float32).tobytes())
                    _mesh.render(prog); drew = True
                except Exception:
                    continue
            try:
                self._stained_depth_fbo.use(); self._stained_depth_fbo.viewport = (0, 0, 1024, 1024); self._ctx.viewport = (0, 0, 1024, 1024)
            except Exception:
                pass
            try:
                self._ctx.disable(moderngl.BLEND)
            except Exception:
                pass
            try:
                self._stained_depth_fbo.clear(1.0, 0.0, 0.0, 1.0)
            except Exception:
                pass
            for _tc in tint_casters:
                try:
                    _mesh, _tr, _mp = _tc
                except Exception:
                    continue
                try:
                    _wm = _tr.world_matrix
                except Exception:
                    continue
                try:
                    from core.renderer.origin import relativize_model_f32 as _rel_f32
                    _mb = _rel_f32(_wm, origin)
                except Exception:
                    try:
                        _mb = _wm.to_f32()
                    except Exception:
                        continue
                try:
                    if "u_model" in dnames:
                        dprog["u_model"].write(_mb)
                    _mesh.render(dprog)
                except Exception:
                    continue
            try:
                self._ctx.enable(moderngl.DEPTH_TEST)
            except Exception:
                pass
            try:
                self._ctx.enable(moderngl.CULL_FACE); self._ctx.cull_face = "back"
            except Exception:
                pass
            try:
                self._ctx.disable(moderngl.BLEND)
            except Exception:
                pass
            try:
                self._ctx.depth_mask = True
            except Exception:
                pass
            if drew:
                try:
                    self._stained_valid = True
                except Exception:
                    pass
        except Exception:
            try:
                self._stained_valid = False
            except Exception:
                pass
            try:
                self._ctx.enable(moderngl.DEPTH_TEST)
            except Exception:
                pass
            try:
                self._ctx.enable(moderngl.CULL_FACE)
            except Exception:
                pass
            try:
                self._ctx.disable(moderngl.BLEND)
            except Exception:
                pass
            try:
                self._ctx.depth_mask = True
            except Exception:
                pass
