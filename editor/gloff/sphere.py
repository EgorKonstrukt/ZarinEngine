# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import os
import numpy as np
import moderngl
from typing import Optional
from PySide6.QtGui import QImage, QPixmap
from core.maths.math3d import Mat4, Vec3
from core.foundation.logger import Logger

_ctx: Optional[moderngl.Context] = None
_sph_prog: Optional[moderngl.Program] = None
_sph_vao: Optional[moderngl.VertexArray] = None
_sph_vbo: Optional[moderngl.Buffer] = None
_sph_ibo: Optional[moderngl.Buffer] = None
_sph_count: int = 0
_ready: bool = False
_safe: bool = True

SPH_VSHADER = """
#version 330 core
in vec3 in_pos;
in vec3 in_normal;
in vec2 in_uv;
out vec3 v_normal;
out vec3 v_pos;
out vec2 v_uv;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
void main() {
    vec4 world_pos = u_model * vec4(in_pos, 1.0);
    v_pos = world_pos.xyz;
    v_normal = mat3(u_model) * in_normal;
    v_uv = in_uv;
    gl_Position = u_proj * u_view * world_pos;
}
"""

SPH_FSHADER = """
#version 330 core
in vec3 v_normal;
in vec3 v_pos;
in vec2 v_uv;
out vec4 frag_color;
uniform vec3 u_albedo;
uniform float u_metallic;
uniform float u_smoothness;
uniform vec3 u_emission;
uniform vec3 u_light_dir;
uniform vec3 u_cam_pos;
uniform bool u_has_tex;
uniform sampler2D u_tex;
void main() {
    vec3 n = normalize(v_normal);
    if (!gl_FrontFacing) n = -n;
    vec3 albedo = u_albedo;
    if (u_has_tex) {
        albedo *= texture(u_tex, v_uv).rgb;
    }
    vec3 l = normalize(u_light_dir);
    vec3 v = normalize(u_cam_pos - v_pos);
    vec3 h = normalize(l + v);
    float diff = max(dot(n, l), 0.0);
    float spec = pow(max(dot(n, h), 0.0), mix(1.0, 256.0, u_smoothness));
    vec3 ambient = 0.25 * albedo;
    vec3 diffuse = diff * albedo;
    vec3 specular = spec * mix(vec3(0.04), albedo, u_metallic);
    vec3 color = ambient + diffuse + specular + u_emission;
    frag_color = vec4(color, 1.0);
}
"""


def _ensure() -> bool:
    global _ctx, _ready, _safe
    if _ready:
        try:
            from PySide6.QtGui import QOpenGLContext
            try:
                if QOpenGLContext.currentContext() is not None:
                    return False
            except Exception:
                pass
        except Exception:
            pass
        return _safe
    if not _safe:
        return False
    try:
        from PySide6.QtGui import QOpenGLContext
        try:
            if QOpenGLContext.currentContext() is not None:
                return False
        except Exception:
            pass
    except Exception:
        pass
    try:
        _ctx = moderngl.create_standalone_context(require=430)
        _ctx.pixel_alignment = 1
        _ready = True
        return True
    except Exception as e:
        Logger.warn(f"gl_offscreen: cannot create GL context: {e}")
        _safe = False
        return False


def _ensure_sph():
    global _sph_prog, _sph_vao, _sph_vbo, _sph_ibo, _sph_count
    if _sph_prog is not None:
        return
    _sph_prog = _ctx.program(vertex_shader=SPH_VSHADER, fragment_shader=SPH_FSHADER)
    verts, idxs = _make_uv_sphere(48, 32)
    _sph_count = len(idxs)
    _sph_vbo = _ctx.buffer(verts.tobytes())
    _sph_ibo = _ctx.buffer(idxs.tobytes())
    _sph_vao = _ctx.vertex_array(
        _sph_prog,
        [(_sph_vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
        _sph_ibo,
    )


def _make_uv_sphere(rows, cols):
    verts = []
    idxs = []
    for r in range(rows + 1):
        phi = math.pi * r / rows
        for c in range(cols + 1):
            theta = 2.0 * math.pi * c / cols
            x = math.sin(phi) * math.cos(theta)
            y = math.cos(phi)
            z = math.sin(phi) * math.sin(theta)
            u = 1.0 - c / cols
            v = 1.0 - r / rows
            verts.extend([x, y, z, x, y, z, u, v])
    for r in range(rows):
        for c in range(cols):
            a = r * (cols + 1) + c
            b = a + cols + 1
            idxs.extend([a, b, a + 1, b, b + 1, a + 1])
    return np.array(verts, dtype=np.float32), np.array(idxs, dtype=np.int32)


def _load_tex(path: str) -> Optional[moderngl.Texture]:
    try:
        img = QImage(path)
        if img.isNull():
            return None
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        data = np.frombuffer(ptr, dtype=np.uint8)
        tex = _ctx.texture((w, h), 4, data.tobytes())
        tex.build_mipmaps()
        tex.anisotropy = 4.0
        return tex
    except Exception:
        return None


def _set_view(prog, theta, phi, dist, aspect):
    proj = Mat4.perspective(30.0, aspect, 0.1, 100.0).to_f32()
    eye = Vec3(
        dist * math.sin(theta) * math.cos(phi),
        dist * math.sin(phi),
        dist * math.cos(theta) * math.cos(phi),
    )
    view = Mat4.look_at(eye, Vec3(0, 0, 0), Vec3(0, 1, 0)).to_f32()
    prog["u_proj"].write(proj.tobytes())
    prog["u_view"].write(view.tobytes())
    prog["u_cam_pos"].value = (eye.x, eye.y, eye.z)


def render_sphere(w: int, h: int, albedo, metallic, smoothness,
                  emission, emit_intensity, theta, phi, dist,
                  tex_path: str = "") -> Optional[QPixmap]:
    try:
        if not _ensure() or w < 1 or h < 1:
            return None
        try:
            _ensure_sph()
        except Exception:
            return None
        tex = None
        try:
            if tex_path and os.path.exists(tex_path):
                tex = _load_tex(tex_path)
        except Exception:
            tex = None
        try:
            fbo = _ctx.framebuffer(
                color_attachments=[_ctx.texture((w, h), 4)],
                depth_attachment=_ctx.depth_texture((w, h)),
            )
        except Exception:
            return None
        try:
            fbo.use()
            _ctx.clear(0.1, 0.1, 0.1, 1.0)
            _ctx.enable(moderngl.DEPTH_TEST)
            _set_view(_sph_prog, theta, phi, dist, w / h if h > 0 else 1.0)
            model = Mat4.identity().to_f32()
            _sph_prog["u_model"].write(model.tobytes())
            try:
                c = list(albedo[:3]) if len(albedo) >= 3 else [1.0, 1.0, 1.0]
            except Exception:
                c = [1.0, 1.0, 1.0]
            try:
                _sph_prog["u_albedo"].value = tuple(c)
            except Exception:
                pass
            try:
                _sph_prog["u_metallic"].value = float(metallic)
            except Exception:
                pass
            try:
                _sph_prog["u_smoothness"].value = float(smoothness)
            except Exception:
                pass
            try:
                if emission is not None and len(emission) >= 3:
                    _sph_prog["u_emission"].value = (
                        float(emission[0]) * float(emit_intensity),
                        float(emission[1]) * float(emit_intensity),
                        float(emission[2]) * float(emit_intensity),
                    )
                else:
                    _sph_prog["u_emission"].value = (0.0, 0.0, 0.0)
            except Exception:
                pass
            ld = (-0.5, 0.7, 0.8)
            n = math.sqrt(sum(d * d for d in ld))
            try:
                _sph_prog["u_light_dir"].value = (ld[0] / n, ld[1] / n, ld[2] / n)
            except Exception:
                pass
            try:
                if tex is not None:
                    tex.use(0)
                    _sph_prog["u_tex"].value = 0
                    _sph_prog["u_has_tex"].value = True
                else:
                    _sph_prog["u_has_tex"].value = False
            except Exception:
                pass
            try:
                _sph_vao.render(moderngl.TRIANGLES)
            except Exception:
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
            try:
                if tex is not None:
                    tex.release()
            except Exception:
                pass
            if data is None or len(data) < w * h * 4:
                return None
            try:
                img = QImage(data, w, h, QImage.Format.Format_RGBA8888)
                img = img.copy()
                pm = QPixmap.fromImage(img)
                return pm
            except Exception:
                return None
        except Exception:
            return None
    except Exception:
        return None


_ensure()
