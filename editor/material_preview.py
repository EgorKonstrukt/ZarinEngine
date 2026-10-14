# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import os
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QImage
from PyQt6.QtCore import Qt
from typing import Optional


class MaterialPreviewWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._albedo: list[float] = [1.0, 1.0, 1.0]
        self._alpha: float = 1.0
        self._metallic: float = 0.0
        self._smoothness: float = 0.5
        self._emission: list[float] = [0.0, 0.0, 0.0]
        self._emit_intensity: float = 0.0
        self._tex_path: str = ""
        self._theta: float = 0.0
        self._phi: float = 0.0
        self._zoom: float = 1.0
        self._last_mouse: Optional[tuple[int, int]] = None
        self._ctx = None
        self._prog = None
        self._vao = None
        self._vbo = None
        self._ibo = None
        self._tex = None
        self._tex_key: str = ""
        self._screen_fbo = None
        self._last_fbo_id = None
        self._gl_ready: bool = False
        self.setMinimumSize(120, 120)
        self.setMouseTracking(True)

    @staticmethod
    def _get_pv(kwargs, *keys, default=None):
        for k in keys:
            v = kwargs.get(k)
            if v is not None:
                return v
        return default

    def set_properties(self, *args, **kwargs):
        if args:
            kwargs = args[0]
        albedo = self._get_pv(kwargs, "_BaseColor", "albedo", "u_albedo_color", default=[1.0, 1.0, 1.0, 1.0])
        metallic = self._get_pv(kwargs, "_Metallic", "metallic", "u_metallic", default=0.0)
        smoothness = self._get_pv(kwargs, "_Smoothness", "smoothness", "u_smoothness", default=0.5)
        emission = self._get_pv(kwargs, "_EmissionColor", "emission", "u_emission", default=[0.0, 0.0, 0.0])
        emit_intensity = self._get_pv(kwargs, "_EmissionIntensity", "emit_intensity", "u_emission_intensity", default=1.0)
        albedo_tex = self._get_pv(kwargs, "albedo_tex", "_BaseMap", "_BaseTex", "u_albedo_tex", default="")
        try:
            albedo3 = list(albedo[:3]) if len(albedo) >= 3 else [1.0, 1.0, 1.0]
        except Exception:
            albedo3 = [1.0, 1.0, 1.0]
        try:
            alpha = float(albedo[3]) if len(albedo) >= 4 else 1.0
        except Exception:
            alpha = 1.0
        try:
            emit3 = list(emission[:3]) if len(emission) >= 3 else [0.0, 0.0, 0.0]
        except Exception:
            emit3 = [0.0, 0.0, 0.0]
        try:
            metallic_f = float(metallic)
        except Exception:
            metallic_f = 0.0
        try:
            smooth_f = float(smoothness)
        except Exception:
            smooth_f = 0.5
        try:
            ei_f = float(emit_intensity)
        except Exception:
            ei_f = 0.0
        try:
            tex_s = str(albedo_tex) if isinstance(albedo_tex, str) else ""
        except Exception:
            tex_s = ""
        changed = (
            albedo3 != self._albedo or alpha != self._alpha or metallic_f != self._metallic or
            smooth_f != self._smoothness or emit3 != self._emission or
            ei_f != self._emit_intensity or tex_s != self._tex_path
        )
        if not changed:
            return
        self._albedo = albedo3
        self._alpha = max(0.0, min(1.0, alpha))
        self._metallic = metallic_f
        self._smoothness = smooth_f
        self._emission = emit3
        self._emit_intensity = ei_f
        if tex_s != self._tex_path:
            self._tex_path = tex_s
        self.update()

    def _resolve_tex(self) -> str:
        try:
            tp = self._tex_path
            if not isinstance(tp, str) or not tp:
                return ""
            if os.path.isabs(tp):
                return tp if os.path.exists(tp) else ""
            cand = os.path.normpath(tp)
            if os.path.exists(cand):
                return cand
            try:
                from core.engine.eng import Engine
                eng = Engine.instance()
                root = getattr(eng, "project_root", "") if eng is not None else ""
                if root:
                    cand2 = os.path.normpath(os.path.join(root, tp))
                    if os.path.exists(cand2):
                        return cand2
            except Exception:
                pass
            return ""
        except Exception:
            return ""

    def _release_resources(self):
        try:
            try:
                self.makeCurrent()
            except Exception:
                pass
            try:
                if self._tex is not None:
                    self._tex.release()
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
        self._tex = None
        self._vao = None
        self._vbo = None
        self._ibo = None
        self._prog = None
        self._tex_key = ""
        self._screen_fbo = None
        self._last_fbo_id = None
        self._gl_ready = False
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
            from editor.sphere_renderer import VSHADER, FSHADER, make_uv_sphere
            self._prog = self._ctx.program(vertex_shader=VSHADER, fragment_shader=FSHADER)
            verts, idxs = make_uv_sphere(48, 32)
            self._vbo = self._ctx.buffer(verts.tobytes())
            self._ibo = self._ctx.buffer(idxs.tobytes())
            self._vao = self._ctx.vertex_array(
                self._prog,
                [(self._vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
                self._ibo,
            )
            self._gl_ready = True
        except Exception:
            self._ctx = None
            self._prog = None
            self._vao = None
            self._vbo = None
            self._ibo = None
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

    def paintGL(self):
        try:
            if self._ctx is None or self._prog is None or self._vao is None:
                return
            import moderngl
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
            key = self._resolve_tex()
            if key != self._tex_key:
                try:
                    if self._tex is not None:
                        self._tex.release()
                except Exception:
                    pass
                self._tex = None
                self._tex_key = ""
                if key:
                    try:
                        from editor.sphere_renderer import load_texture
                        t = load_texture(self._ctx, key)
                        if t is not None:
                            self._tex = t
                            self._tex_key = key
                    except Exception:
                        self._tex = None
                        self._tex_key = ""
            try:
                from editor.sphere_renderer import render_view
                dist = 3.0 / max(self._zoom, 0.01)
                render_view(
                    self._prog, self._vao, self._ctx, w, h,
                    self._albedo, self._metallic, self._smoothness,
                    self._emission, self._emit_intensity,
                    self._theta, self._phi, dist,
                    tex=self._tex,
                )
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
        self._last_mouse = (int(event.position().x()), int(event.position().y()))
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        self._zoom *= 1.0 + event.angleDelta().y() * 0.001
        self._zoom = max(0.3, min(3.0, self._zoom))
        self.update()
