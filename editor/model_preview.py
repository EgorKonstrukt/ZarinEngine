# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtCore import Qt
from typing import Optional

_MDL_VSHADER = """
#version 330 core
in vec3 in_pos;
in vec3 in_nrm;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat3 u_normal_mat;
out vec3 v_normal;
out vec3 v_pos;
void main() {
    vec4 world_pos = u_model * vec4(in_pos, 1.0);
    v_pos = world_pos.xyz;
    v_normal = u_normal_mat * in_nrm;
    gl_Position = u_proj * u_view * world_pos;
}
"""

_MDL_FSHADER = """
#version 330 core
in vec3 v_normal;
in vec3 v_pos;
out vec4 frag_color;
uniform vec3 u_light_dir;
uniform vec3 u_cam_pos;
uniform vec3 u_color;
uniform float u_ambient;
void main() {
    vec3 n = normalize(v_normal);
    if (!gl_FrontFacing) n = -n;
    vec3 l = normalize(u_light_dir);
    vec3 v = normalize(u_cam_pos - v_pos);
    vec3 h = normalize(l + v);
    float diff = max(dot(n, l), 0.0);
    float spec = pow(max(dot(n, h), 0.0), 32.0);
    vec3 color = u_color * (u_ambient + diff * (1.0 - u_ambient)) + vec3(spec * 0.3);
    frag_color = vec4(color, 1.0);
}
"""


class ModelPreviewWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._verts: Optional[np.ndarray] = None
        self._normals: Optional[np.ndarray] = None
        self._indices: Optional[np.ndarray] = None
        self._radius: float = 1.0
        self._theta: float = 0.5
        self._phi: float = 0.3
        self._zoom: float = 1.0
        self._last_mouse: Optional[tuple[int, int]] = None
        self._ctx = None
        self._prog = None
        self._vao = None
        self._vbo = None
        self._ibo = None
        self._screen_fbo = None
        self._last_fbo_id = None
        self._gl_ready: bool = False
        self._mesh_dirty: bool = False
        self.setMinimumSize(120, 120)
        self.setMouseTracking(True)

    def set_mesh(self, verts: np.ndarray, indices: np.ndarray, normals: Optional[np.ndarray] = None):
        try:
            self._verts = verts
            self._normals = normals
            self._indices = indices
            if verts is not None and len(verts) >= 3:
                pts = verts.reshape(-1, 3)
                center = pts.mean(axis=0)
                r = np.max(np.linalg.norm(pts - center, axis=1))
                self._radius = max(float(r), 0.01)
            self._mesh_dirty = True
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def _release_resources(self):
        try:
            try:
                self.makeCurrent()
            except Exception:
                pass
            try:
                if self._vao is not None:
                    self._vao.release()
            except Exception:
                pass
            try:
                if self._vbo is not None:
                    self._vbo.release()
            except Exception:
                pass
            try:
                if self._ibo is not None:
                    self._ibo.release()
            except Exception:
                pass
            try:
                if self._prog is not None:
                    self._prog.release()
            except Exception:
                pass
        except Exception:
            pass
        self._vao = None
        self._vbo = None
        self._ibo = None
        self._prog = None
        self._screen_fbo = None
        self._last_fbo_id = None
        self._gl_ready = False
        self._mesh_dirty = True
        try:
            self.doneCurrent()
        except Exception:
            pass

    def hideEvent(self, event):
        try:
            self._release_resources()
        except Exception:
            pass
        super().hideEvent(event)

    def initializeGL(self):
        try:
            import moderngl
            self._ctx = moderngl.create_context(standalone=False)
            try:
                self._ctx.gc_mode = "context_gc"
            except Exception:
                pass
            self._prog = self._ctx.program(vertex_shader=_MDL_VSHADER, fragment_shader=_MDL_FSHADER)
            self._gl_ready = True
            self._mesh_dirty = True
        except Exception:
            self._ctx = None
            self._prog = None
            self._gl_ready = False

    def resizeGL(self, w: int, h: int):
        try:
            if self._ctx is not None:
                dpr = self.devicePixelRatio()
                self._ctx.viewport = (0, 0, max(2, int(w * dpr)), max(2, int(h * dpr)))
        except Exception:
            pass
        self._screen_fbo = None
        self._last_fbo_id = None

    def _build_mesh(self) -> bool:
        try:
            if self._verts is None or self._indices is None:
                return False
            import moderngl
            pts = self._verts.reshape(-1, 3).astype(np.float32)
            n_vert = len(pts)
            if n_vert < 1:
                return False
            try:
                if self._normals is not None and len(self._normals) >= n_vert * 3:
                    nrm = self._normals.reshape(-1, 3).astype(np.float32)
                else:
                    nrm = self._compute_normals(pts, self._indices)
            except Exception:
                nrm = np.zeros((n_vert, 3), dtype=np.float32)
                nrm[:, 1] = 1.0
            data = np.zeros((n_vert, 6), dtype=np.float32)
            data[:, :3] = pts
            data[:, 3:6] = nrm
            try:
                if self._vao is not None:
                    self._vao.release()
            except Exception:
                pass
            try:
                if self._vbo is not None:
                    self._vbo.release()
            except Exception:
                pass
            try:
                if self._ibo is not None:
                    self._ibo.release()
            except Exception:
                pass
            self._vbo = self._ctx.buffer(data.tobytes())
            self._ibo = self._ctx.buffer(self._indices.astype(np.int32).tobytes())
            self._vao = self._ctx.vertex_array(
                self._prog,
                [(self._vbo, "3f 3f", "in_pos", "in_nrm")],
                self._ibo,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _compute_normals(pts: np.ndarray, indices: np.ndarray) -> np.ndarray:
        try:
            n_vert = len(pts)
            nrm = np.zeros((n_vert, 3), dtype=np.float32)
            idx_arr = np.asarray(indices).reshape(-1, 3)
            for tri in idx_arr:
                try:
                    i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
                except Exception:
                    continue
                if i0 < 0 or i1 < 0 or i2 < 0 or i0 >= n_vert or i1 >= n_vert or i2 >= n_vert:
                    continue
                e1 = pts[i1] - pts[i0]
                e2 = pts[i2] - pts[i0]
                fn = np.cross(e1, e2)
                nl = float(np.linalg.norm(fn))
                if nl > 1e-10:
                    fn = fn / nl
                nrm[i0] += fn
                nrm[i1] += fn
                nrm[i2] += fn
            for i in range(n_vert):
                nl = float(np.linalg.norm(nrm[i]))
                if nl > 1e-10:
                    nrm[i] = nrm[i] / nl
                else:
                    nrm[i] = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            return nrm
        except Exception:
            n = len(pts)
            out = np.zeros((n, 3), dtype=np.float32)
            out[:, 1] = 1.0
            return out

    def paintGL(self):
        try:
            if self._ctx is None or self._prog is None:
                return
            import moderngl
            from core.maths.math3d import Mat4, Vec3
            try:
                fbo_id = self.defaultFramebufferObject()
                if self._screen_fbo is None or self._last_fbo_id != fbo_id:
                    self._screen_fbo = self._ctx.detect_framebuffer(fbo_id)
                    self._last_fbo_id = fbo_id
                self._screen_fbo.use()
            except Exception:
                try:
                    self._ctx.screen.use()
                except Exception:
                    pass
            w = max(2, self.width())
            h = max(2, self.height())
            dpr = self.devicePixelRatio()
            try:
                self._ctx.viewport = (0, 0, max(2, int(w * dpr)), max(2, int(h * dpr)))
            except Exception:
                pass
            if self._mesh_dirty:
                try:
                    ok = self._build_mesh()
                    self._mesh_dirty = False
                    if not ok:
                        try:
                            self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                        except Exception:
                            pass
                        return
                except Exception:
                    self._mesh_dirty = False
                    return
            if self._vao is None:
                try:
                    self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                except Exception:
                    pass
                return
            try:
                self._ctx.clear(0.1, 0.1, 0.1, 1.0)
                self._ctx.enable(moderngl.DEPTH_TEST)
            except Exception:
                pass
            try:
                dist = self._radius * 3.5 / max(self._zoom, 0.01)
                aspect = w / h if h > 0 else 1.0
                proj = Mat4.perspective(30.0, aspect, 0.1, 100.0).to_f32()
                phi = max(-math.pi / 2 + 0.05, min(math.pi / 2 - 0.05, self._phi))
                eye = Vec3(
                    dist * math.sin(self._theta) * math.cos(phi),
                    dist * math.sin(phi),
                    dist * math.cos(self._theta) * math.cos(phi),
                )
                view = Mat4.look_at(eye, Vec3(0, 0, 0), Vec3(0, 1, 0)).to_f32()
                model = Mat4.identity().to_f32()
                self._prog["u_proj"].write(proj.tobytes())
                self._prog["u_view"].write(view.tobytes())
                self._prog["u_model"].write(model.tobytes())
                self._prog["u_normal_mat"].write(np.eye(3, dtype=np.float32).tobytes())
                self._prog["u_color"].value = (0.7, 0.7, 0.7)
                self._prog["u_ambient"].value = 0.3
                ld = (-0.5, 0.7, 0.8)
                n = math.sqrt(sum(d * d for d in ld))
                self._prog["u_light_dir"].value = (ld[0] / n, ld[1] / n, ld[2] / n)
                self._prog["u_cam_pos"].value = (eye.x, eye.y, eye.z)
            except Exception:
                pass
            try:
                self._vao.render(moderngl.TRIANGLES)
            except Exception:
                pass
        except Exception:
            pass

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = (int(event.position().x()), int(event.position().y()))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = None

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse is None:
            return
        dx = event.position().x() - self._last_mouse[0]
        dy = event.position().y() - self._last_mouse[1]
        self._theta += dx * 0.01
        self._phi += dy * 0.01
        self._phi = max(-math.pi / 2 + 0.05, min(math.pi / 2 - 0.05, self._phi))
        self._last_mouse = (int(event.position().x()), int(event.position().y()))
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        self._zoom *= 1.0 + event.angleDelta().y() * 0.001
        self._zoom = max(0.2, min(5.0, self._zoom))
        self.update()
