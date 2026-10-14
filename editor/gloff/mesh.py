# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
import moderngl
from typing import Optional
from PyQt6.QtGui import QImage, QPixmap
from core.maths.math3d import Mat4
from editor.gloff.sphere import _ensure
from editor.gloff.sphere import _set_view
import editor.gloff.sphere as _sph

_mdl_prog: Optional[moderngl.Program] = None

MDL_VSHADER = """
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

MDL_FSHADER = """
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


def _compute_normals(pts: np.ndarray, indices: np.ndarray) -> np.ndarray:
    n_vert = len(pts)
    nrm = np.zeros((n_vert, 3), dtype=np.float32)
    idx_arr = indices.reshape(-1, 3)
    for tri in idx_arr:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        e1 = pts[i1] - pts[i0]
        e2 = pts[i2] - pts[i0]
        fn = np.cross(e1, e2)
        fn_len = np.linalg.norm(fn)
        if fn_len > 1e-10:
            fn /= fn_len
        nrm[i0] += fn
        nrm[i1] += fn
        nrm[i2] += fn
    for i in range(n_vert):
        nl = np.linalg.norm(nrm[i])
        if nl > 1e-10:
            nrm[i] /= nl
        else:
            nrm[i] = np.array([0.0, 1.0, 0.0])
    return nrm


def render_mesh(w: int, h: int, verts: np.ndarray, indices: np.ndarray,
                theta, phi, dist, color=(0.7, 0.7, 0.7),
                normals: Optional[np.ndarray] = None) -> Optional[QPixmap]:
    try:
        if not _ensure() or w < 4 or h < 4 or len(verts) < 3 or len(indices) < 3:
            return None
        global _mdl_prog
        try:
            if _mdl_prog is None:
                _mdl_prog = _sph._ctx.program(vertex_shader=MDL_VSHADER, fragment_shader=MDL_FSHADER)
        except Exception:
            return None
        try:
            pts = verts.reshape(-1, 3).astype(np.float32)
            n_vert = len(pts)
            if normals is not None and len(normals) >= n_vert * 3:
                nrm = normals.reshape(-1, 3).astype(np.float32)
            else:
                nrm = _compute_normals(pts, indices)
            data = np.zeros((n_vert, 6), dtype=np.float32)
            data[:, :3] = pts
            data[:, 3:6] = nrm
            vbo = _sph._ctx.buffer(data.tobytes())
            ibo = _sph._ctx.buffer(indices.astype(np.int32).tobytes())
            vao = _sph._ctx.vertex_array(
                _mdl_prog,
                [(vbo, "3f 3f", "in_pos", "in_nrm")],
                ibo,
            )
            fbo = _sph._ctx.framebuffer(
                color_attachments=[_sph._ctx.texture((w, h), 4)],
                depth_attachment=_sph._ctx.depth_texture((w, h)),
            )
        except Exception:
            return None
        try:
            fbo.use()
            phi = max(-math.pi / 2 + 0.05, min(math.pi / 2 - 0.05, phi))
            _sph._ctx.clear(0.1, 0.1, 0.1, 1.0)
            _sph._ctx.enable(moderngl.DEPTH_TEST)
            _set_view(_mdl_prog, theta, phi, dist, w / h if h > 0 else 1.0)
            model = Mat4.identity().to_f32()
            _mdl_prog["u_model"].write(model.tobytes())
            _mdl_prog["u_normal_mat"].write(np.eye(3, dtype=np.float32).tobytes())
            try:
                _mdl_prog["u_color"].value = tuple(list(color[:3]))
            except Exception:
                pass
            try:
                _mdl_prog["u_ambient"].value = 0.3
            except Exception:
                pass
            ld = (-0.5, 0.7, 0.8)
            n = math.sqrt(sum(d * d for d in ld))
            try:
                _mdl_prog["u_light_dir"].value = (ld[0] / n, ld[1] / n, ld[2] / n)
            except Exception:
                pass
            try:
                vao.render(moderngl.TRIANGLES)
            except Exception:
                try:
                    vao.release()
                except Exception:
                    pass
                try:
                    vbo.release()
                except Exception:
                    pass
                try:
                    ibo.release()
                except Exception:
                    pass
                try:
                    color_tex = fbo.color_attachments[0]
                    depth_tex = fbo.depth_attachment
                    fbo.release()
                    try:
                        color_tex.release()
                    except Exception:
                        pass
                    try:
                        depth_tex.release()
                    except Exception:
                        pass
                except Exception:
                    pass
                return None
            try:
                data = fbo.read(components=4, dtype="f1")
            except Exception:
                data = None
            try:
                vao.release()
            except Exception:
                pass
            try:
                vbo.release()
            except Exception:
                pass
            try:
                ibo.release()
            except Exception:
                pass
            try:
                color_tex = fbo.color_attachments[0]
                depth_tex = fbo.depth_attachment
            except Exception:
                color_tex = None
                depth_tex = None
            try:
                fbo.release()
            except Exception:
                pass
            try:
                if color_tex is not None:
                    color_tex.release()
            except Exception:
                pass
            try:
                if depth_tex is not None:
                    depth_tex.release()
            except Exception:
                pass
            if data is None or len(data) < w * h * 4:
                return None
            try:
                img = QImage(data, w, h, QImage.Format.Format_RGBA8888)
                img = img.copy()
                return QPixmap.fromImage(img)
            except Exception:
                return None
        except Exception:
            return None
    except Exception:
        return None
