from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional, Any
from core.math3d import Vec3, Mat4
from core.components.rendering.particle_system import ParticleSystem


class ParticleRenderer:
    """Renders billboarded particle systems."""

    def __init__(self, ctx: moderngl.Context, prog: moderngl.Program):
        self._ctx = ctx
        self._prog = prog
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._textures: dict[str, Any] = {}
        self._build_buffers()

    def _build_buffers(self):
        self._vbo = self._ctx.buffer(reserve=4 * 1024 * 1024, dynamic=True)
        self._ibo = self._ctx.buffer(reserve=6 * 1024 * 1024, dynamic=True)
        self._vao = self._ctx.vertex_array(
            self._prog,
            [
                (self._vbo, "3f 4f 2f 2f 1f", "in_position", "in_color", "in_texcoord", "in_size", "in_rotation"),
            ],
            self._ibo
        )

    def load_texture(self, path: str) -> Optional[Any]:
        if not path:
            return None
        if path in self._textures:
            return self._textures[path]
        abs_path = path
        if not __import__('os').path.isabs(path):
            abs_path = __import__('os').path.join(__import__('os').getcwd(), path)
            if not __import__('os').path.exists(abs_path):
                alt = __import__('os').path.join("assets", path)
                if __import__('os').path.exists(alt):
                    abs_path = alt
        if not __import__('os').path.exists(abs_path):
            return None
        try:
            from PIL import Image
            img = Image.open(abs_path).convert("RGBA")
            tex = self._ctx.texture(img.size, 4, img.tobytes())
            tex.build_mipmaps()
            tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
            tex.repeat_x = True
            tex.repeat_y = True
            self._textures[path] = tex
            return tex
        except Exception:
            return None

    def render_snapshot(self, particle_items: list, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3):
        if not self._prog or not self._vao or not particle_items:
            return
        prog = self._prog
        vp_mat = view_mat * proj_mat
        cam_right = Vec3(float(view_mat._d[0, 0]), float(view_mat._d[1, 0]), float(view_mat._d[2, 0]))
        cam_up = Vec3(float(view_mat._d[0, 1]), float(view_mat._d[1, 1]), float(view_mat._d[2, 1]))
        right_arr = np.array([cam_right.x, cam_right.y, cam_right.z], dtype=np.float32)
        up_arr = np.array([cam_up.x, cam_up.y, cam_up.z], dtype=np.float32)
        fwd_arr = np.array([-float(view_mat._d[0, 2]), -float(view_mat._d[1, 2]), -float(view_mat._d[2, 2])], dtype=np.float32)
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.depth_mask = False
        for item in particle_items:
            vertices, indices = item.vertices, item.indices
            if vertices is None or indices is None:
                continue
            n_indices = len(indices)
            particle_tex = self.load_texture(item.texture_path) if item.texture_path else None
            vp_f32 = vp_mat.to_f32()
            if "u_view_proj" in prog:
                prog["u_view_proj"].write(vp_f32.tobytes())
            if "u_camera_right" in prog:
                prog["u_camera_right"].write(right_arr.tobytes())
            if "u_camera_up" in prog:
                prog["u_camera_up"].write(up_arr.tobytes())
            if "u_camera_forward" in prog:
                prog["u_camera_forward"].write(fwd_arr.tobytes())
            if "u_use_texture" in prog:
                prog["u_use_texture"].value = 1 if particle_tex else 0
            if "u_albedo" in prog:
                prog["u_albedo"].write(np.array([1, 1, 1, 1], dtype=np.float32).tobytes())
            if particle_tex and "u_texture" in prog:
                particle_tex.use(0)
                prog["u_texture"].value = 0
            try:
                vert_bytes = vertices.tobytes()
                idx_bytes = indices.tobytes()
                if len(vert_bytes) > self._vbo.size:
                    self._vbo.orphan(len(vert_bytes))
                if len(idx_bytes) > self._ibo.size:
                    self._ibo.orphan(len(idx_bytes))
                self._vbo.write(vert_bytes)
                self._ibo.write(idx_bytes)
                self._vao.render(moderngl.TRIANGLES, vertices=n_indices)
            except Exception as e:
                from core.logger import Logger
                Logger.error(f"Particle render error: {e}")
        self._ctx.enable(moderngl.CULL_FACE)
        self._ctx.depth_mask = True

    def render(self, scene, view_mat: Mat4, proj_mat: Mat4, cam_pos: Vec3):
        if not self._prog or not self._vao:
            return
        prog = self._prog
        vp_mat = view_mat * proj_mat
        cam_right = Vec3(float(view_mat._d[0, 0]), float(view_mat._d[1, 0]), float(view_mat._d[2, 0]))
        cam_up = Vec3(float(view_mat._d[0, 1]), float(view_mat._d[1, 1]), float(view_mat._d[2, 1]))
        right_arr = np.array([cam_right.x, cam_right.y, cam_right.z], dtype=np.float32)
        up_arr = np.array([cam_up.x, cam_up.y, cam_up.z], dtype=np.float32)
        fwd_arr = np.array([-float(view_mat._d[0, 2]), -float(view_mat._d[1, 2]), -float(view_mat._d[2, 2])], dtype=np.float32)
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._ctx.depth_mask = False
        for ent in scene.get_entities_with_component(ParticleSystem):
            if not ent.active:
                continue
            ps = ent.get_component(ParticleSystem)
            if not ps or not ps.enabled or ps._alive_count == 0:
                continue
            data = ps.build_render_data(cam_right, cam_up, cam_pos)
            if data is None:
                continue
            vertices, indices = data
            n_indices = len(indices)
            tex_path = ps.texture_path
            particle_tex = self.load_texture(tex_path) if tex_path else None
            vp_f32 = vp_mat.to_f32()
            if "u_view_proj" in prog:
                prog["u_view_proj"].write(vp_f32.tobytes())
            if "u_camera_right" in prog:
                prog["u_camera_right"].write(right_arr.tobytes())
            if "u_camera_up" in prog:
                prog["u_camera_up"].write(up_arr.tobytes())
            if "u_camera_forward" in prog:
                prog["u_camera_forward"].write(fwd_arr.tobytes())
            if "u_use_texture" in prog:
                prog["u_use_texture"].value = 1 if particle_tex else 0
            if "u_albedo" in prog:
                prog["u_albedo"].write(np.array([1, 1, 1, 1], dtype=np.float32).tobytes())
            if particle_tex and "u_texture" in prog:
                particle_tex.use(0)
                prog["u_texture"].value = 0
            try:
                vert_bytes = vertices.tobytes()
                idx_bytes = indices.tobytes()
                if len(vert_bytes) > self._vbo.size:
                    self._vbo.orphan(len(vert_bytes))
                if len(idx_bytes) > self._ibo.size:
                    self._ibo.orphan(len(idx_bytes))
                self._vbo.write(vert_bytes)
                self._ibo.write(idx_bytes)
                self._vao.render(moderngl.TRIANGLES, vertices=n_indices)
            except Exception as e:
                from core.logger import Logger
                Logger.error(f"Particle render error: {e}")
        self._ctx.enable(moderngl.CULL_FACE)
        self._ctx.depth_mask = True

    def release(self):
        if self._vao:
            self._vao.release()
        if self._vbo:
            self._vbo.release()
        if self._ibo:
            self._ibo.release()
        for tex in self._textures.values():
            try:
                tex.release()
            except Exception:
                pass
