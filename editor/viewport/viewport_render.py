# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
import traceback
from typing import Optional
from core.maths.math3d import Vec3
from core.foundation.logger import Logger


class ViewportRenderMixin:

    _render_suspended = False

    def _on_render_tick(self):
        try:
            if type(self)._render_suspended:
                return
        except Exception:
            pass
        if not self._vsync_enabled and self.isVisible():
            if not self._pacer.should_run():
                return
            self.update()

    def _display_quantum(self) -> float:
        try:
            scr = self.screen()
            rate = float(scr.refreshRate()) if scr is not None else 0.0
        except Exception:
            rate = 0.0
        if rate < 20.0 or rate > 1000.0:
            rate = 60.0
        return 1.0 / rate

    def _play_throttle_wait(self, step: int) -> float:
        now = time.perf_counter()
        if self._throttle_next_t <= 0.0 or now >= self._throttle_next_t:
            self._throttle_next_t = now + max(2, step) * self._display_quantum()
            return 0.0
        return self._throttle_next_t - now

    def _throttle_resume(self):
        self._throttle_armed = False
        if self.isVisible():
            self.update()

    def _report_block(self, gap_raw, now):
        if gap_raw <= 0.025:
            return
        if now - getattr(self, "_last_block_log", 0.0) < 2.0:
            return
        self._last_block_log = now
        try:
            total, top = self._block_watch.heaviest(gap_raw)
        except Exception:
            return
        if total <= 1 or not top:
            return
        parts = []
        for stack, pct in top:
            parts.append(str(pct) + "pct " + stack)
        Logger.warning("block gap=" + str(int(round(gap_raw * 1000.0))) + "ms samples=" + str(total) + " " + " | ".join(parts))

    def _bind_screen_fbo(self):
        fbo_id = self.defaultFramebufferObject()
        if self._screen_fbo is None or not hasattr(self, "_last_fbo_id") or self._last_fbo_id != fbo_id:
            try:
                self._screen_fbo = self._ctx.detect_framebuffer(fbo_id)
            except Exception:
                self._screen_fbo = None
                return
            self._last_fbo_id = fbo_id
        self._screen_fbo.use()

    def _get_physical_dims(self):
        pw = self._physical_w
        ph = self._physical_h
        if pw > 0 and ph > 0:
            return pw, ph
        dpr = self.devicePixelRatio()
        return int(self.width() * dpr), int(self.height() * dpr)

    def _disable_dwm_throttle(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_NOREDIRECTIONBITMAP = 0x00200000
            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            def _collect_hwnds(h):
                items = {h}
                c = user32.GetWindow(h, 5)
                while c:
                    items.add(c)
                    items |= _collect_hwnds(c)
                    c = user32.GetWindow(c, 2)
                return items
            hwnd = int(self.winId())
            root = user32.GetAncestor(hwnd, 2)
            for h in _collect_hwnds(root):
                try:
                    cur = user32.GetWindowLongW(h, GWL_EXSTYLE)
                    user32.SetWindowLongW(h, GWL_EXSTYLE, cur | WS_EX_NOREDIRECTIONBITMAP)
                    user32.SetWindowPos(h, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                except Exception:
                    pass
        except Exception:
            pass

    def _retry_float_fbo(self):
        self._screen_fbo = None
        self._last_fbo_id = None
        self.update()

    def update_scene(self):
        self.update()

    def _update_editor_particles(self, dt: float, selected: list = None):
        if not selected:
            return
        from core.components import ParticleSystem
        scene = self._engine.scene
        if not scene:
            return
        selected_ids = {e.id for e in selected}
        for ent in scene.get_entities_with_component(ParticleSystem):
            if not ent.active:
                continue
            ps = ent.get_component(ParticleSystem)
            if not ps or not ps.enabled:
                continue
            if ent.id not in selected_ids:
                continue
            try:
                ps.on_update(dt)
            except Exception:
                pass

    def _get_selected_set(self):
        if self._engine.play_mode:
            return None
        lst = self._selected_entities
        v = (id(lst), len(lst), self._selected_set_version)
        if v != self._selected_set_key:
            self._selected_set_key = v
            self._selected_set = frozenset(lst) if lst else frozenset()
        return self._selected_set

    def _forward_to_overlay(self, event):
        if self._overlay_canvas and not self._overlay_canvas.edit_mode:
            return True
        return False

    def _init_gl_resources(self):
        self._ctx = __import__("moderngl").create_context(standalone=False)
        try:
            self._ctx.gc_mode = "context_gc"
        except Exception:
            pass
        try:
            self._gl_info_cache = dict(self._ctx.info)
        except Exception:
            self._gl_info_cache = {}
        try:
            self._gl_extensions_cache = list(self._ctx.extensions) if hasattr(self._ctx, "extensions") else []
        except Exception:
            self._gl_extensions_cache = []
        self._bind_screen_fbo()
        self._disable_dwm_throttle()
        try:
            import ctypes
            opengl32 = ctypes.windll.opengl32
            addr = opengl32.wglGetProcAddress(b"wglSwapIntervalEXT")
            if addr:
                func = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(addr)
                func(0 if not self._vsync_enabled else 1)
        except Exception:
            pass
        from core.renderer.renderer import Renderer
        self._renderer = Renderer(self._ctx)
        self._renderer.initialize()
        try:
            from core.config.config import get_global_config
            self._renderer.load_config(get_global_config())
        except Exception:
            pass
        self._renderer.request_render(lambda: self.update())
        try:
            from editor.viewport.audio_viz_gl import AudioVizGL
            self._audio_viz = AudioVizGL(self._ctx)
        except Exception as e:
            self._audio_viz = None
            print(f"[Zarin Engine] AudioViz init error: {e}", flush=True)
        from editor.gizmo.pb_scale_gizmo import PbScaleGizmo
        from editor.gizmo.phys_bone_grab import PhysBoneGrabGizmo
        self._pb_scale_gizmo = PbScaleGizmo(self)
        self._pb_grab = PhysBoneGrabGizmo(self)
        self._engine.on("scene_loaded", self._on_scene_loaded)
        self._engine.on("play_stop", self._on_play_stop)
        self._engine.on("play_start", self._on_play_start)

    def _render_cursor(self, vp_mat, fw: int, fh: int, cam_pos):
        try:
            cam = getattr(self, "_cam", None)
            if cam is None:
                return
            if self._renderer is None:
                return
            if getattr(self._engine, "play_mode", False):
                return
            target = getattr(cam, "_orbit_target", None)
            if target is None:
                return
            from editor.viewport.projection import project_world_pos
            sp = project_world_pos(self, target, vp_mat, fw, fh)
            if not sp:
                return
            sx, sy = sp[0], sp[1]
            cache_key = "__cursor_blender_ring"
            try:
                tex = self._renderer._icon_textures.get(cache_key)
            except Exception:
                tex = None
            if tex is None:
                from PySide6.QtCore import Qt
                from PySide6.QtGui import QImage, QPainter, QPen, QColor
                S = 96
                C = S // 2
                R = 21
                T = 31
                qimg = QImage(S, S, QImage.Format.Format_RGBA8888)
                qimg.fill(Qt.GlobalColor.transparent)
                p = QPainter(qimg)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                outline = QColor(10, 10, 12, 210)
                main = QColor(245, 245, 245, 255)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(outline, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawEllipse(C - R, C - R, R * 2, R * 2)
                p.drawLine(C - T, C, C + T, C)
                p.drawLine(C, C - T, C, C + T)
                p.setPen(QPen(main, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawEllipse(C - R, C - R, R * 2, R * 2)
                p.drawLine(C - T, C, C + T, C)
                p.drawLine(C, C - T, C, C + T)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(outline)
                p.drawEllipse(C - 5, C - 5, 10, 10)
                p.setBrush(main)
                p.drawEllipse(C - 3, C - 3, 6, 6)
                p.end()
                rgba = bytes(qimg.bits()[:S * S * 4])
                tex = self._renderer.create_icon_texture_from_data(rgba, S, S, cache_key)
                try:
                    self._renderer._icon_textures[cache_key] = tex
                except Exception:
                    pass
            if tex:
                try:
                    dpr = float(self.devicePixelRatio())
                except Exception:
                    dpr = 1.0
                if dpr < 1.0:
                    dpr = 1.0
                self._renderer.render_icon(tex, sx, sy, 30.0 * dpr, 1.0, fw, fh)
        except Exception:
            pass

    def screen_to_ray(self, sx: int, sy: int):
        from editor.viewport.projection import screen_to_ray as _screen_to_ray
        return _screen_to_ray(self, sx, sy)

    def screen_to_plane(self, sx: int, sy: int, plane_point: Vec3):
        from editor.viewport.projection import screen_to_plane as _screen_to_plane
        return _screen_to_plane(self, sx, sy, plane_point)

    def add_debug_line(self, start: Vec3, end: Vec3, color: list[float]):
        self._debug_lines.append((start, end, color))

    def _render_api_gizmos(self, override_vp_mat=None, fw=None, fh=None):
        gm = self._gizmos_api
        if not gm or not gm.enabled:
            return
        if self._engine and self._engine.play_mode and not gm.show_in_runtime:
            return
        if override_vp_mat is not None:
            vp_mat = override_vp_mat
            if fw is None or fh is None:
                fw, fh = self._get_physical_dims()
        else:
            fw, fh = self._get_physical_dims()
            view = self._cam.get_view_matrix()
            proj = self._cam.get_projection_matrix(fw / max(1, fh))
            vp_mat = view * proj
        starts, ends, colors = gm.build_render_arrays()
        if starts is not None:
            rev = getattr(gm, "_revision", 0)
            dirty = (rev != getattr(self, "_gizmo_api_last_rev", -1))
            self._gizmo_api_last_rev = rev
            self._renderer.render_gizmo_arrays(starts, ends, colors, vp_mat, fw, fh, thickness_multiplier=1.0, dirty=dirty, cam_pos=self._cam.position if self._cam else None)
        labels = gm.get_label_data()
        if labels:
            self._render_api_labels(labels, vp_mat, fw, fh)
        icons = gm.get_icon_data()
        if icons:
            self._render_api_icons(icons, vp_mat, fw, fh)

    def _render_api_labels(self, labels: list[dict], vp_mat, fw: int, fh: int):
        from editor.viewport.projection import project_world_pos
        dpr = self.devicePixelRatio()
        for label in labels:
            pos = label["position"]
            text = label["text"]
            color = label["color"]
            font_size = label["font_size"]
            world_pos = Vec3(pos[0], pos[1], pos[2])
            sp = project_world_pos(self, world_pos, vp_mat, fw, fh)
            if not sp:
                continue
            cache_key = f"__gizmo_label_{text}_{font_size}_{int(color[0]*255)}_{int(color[1]*255)}_{int(color[2]*255)}"
            tex = self._renderer._icon_textures.get(cache_key)
            if tex is None:
                from PySide6.QtCore import QRect, Qt
                from PySide6.QtGui import QFont, QFontMetrics, QPainter, QColor, QImage
                f = QFont("Segoe UI", font_size, QFont.Weight.Bold)
                f.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
                fm = QFontMetrics(f)
                pad = font_size
                tw = fm.horizontalAdvance(text) + pad * 2
                th = fm.height() + pad
                tex_size = max(tw, th)
                qimg = QImage(tex_size, tex_size, QImage.Format.Format_RGBA8888)
                qimg.fill(Qt.GlobalColor.transparent)
                p = QPainter(qimg)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setFont(f)
                p.setPen(QColor(int(color[0]*255), int(color[1]*255), int(color[2]*255)))
                p.drawText(QRect(0, 0, tex_size, tex_size), Qt.AlignmentFlag.AlignCenter, text)
                p.end()
                rgba = bytes(qimg.bits()[:tex_size * tex_size * 4])
                tex = self._renderer.create_icon_texture_from_data(rgba, tex_size, tex_size, cache_key)
                self._renderer._icon_textures[cache_key] = tex
            if tex:
                sx, sy = sp[0], sp[1]
                sz = max(font_size * 2.5, 32) * dpr
                self._renderer.render_icon(tex, sx, sy, sz, 1.0, fw, fh)

    def _render_api_icons(self, icons: list[dict], vp_mat, fw: int, fh: int):
        from editor.viewport.projection import project_world_pos
        dpr = self.devicePixelRatio()
        for icon in icons:
            pos = icon["position"]
            text = icon.get("text", "")
            color = icon["color"]
            font_size = icon["font_size"]
            world_pos = Vec3(pos[0], pos[1], pos[2])
            sp = project_world_pos(self, world_pos, vp_mat, fw, fh)
            if not sp:
                continue
            if icon.get("texture_path"):
                cache_key = f"__gizmo_icon_tex_{icon['texture_path']}"
                tex = self._renderer._icon_textures.get(cache_key)
                if tex is None:
                    from PySide6.QtCore import Qt
                    from PySide6.QtGui import QImage
                    qimg = QImage(icon["texture_path"])
                    if not qimg.isNull():
                        size = max(qimg.width(), qimg.height())
                        qimg = qimg.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        sw = max(1, int(qimg.width()))
                        sh = max(1, int(qimg.height()))
                        rgba = bytes(qimg.bits()[:sw * sh * 4])
                        tex = self._renderer.create_icon_texture_from_data(rgba, sw, sh, cache_key)
                        if tex:
                            self._renderer._icon_textures[cache_key] = tex
            elif text:
                cache_key = f"__gizmo_icon_text_{text}_{font_size}_{int(color[0]*255)}_{int(color[1]*255)}_{int(color[2]*255)}"
                tex = self._renderer._icon_textures.get(cache_key)
                if tex is None:
                    from PySide6.QtCore import QRect, Qt
                    from PySide6.QtGui import QFont, QFontMetrics, QPainter, QBrush, QColor, QImage
                    f = QFont("Segoe UI", font_size, QFont.Weight.Bold)
                    f.setStyleStrategy(QFont.StyleStrategy.ForceOutline)
                    fm = QFontMetrics(f)
                    pad = font_size
                    tw = fm.horizontalAdvance(text) + pad * 2
                    th = fm.height() + pad
                    tex_size = max(tw, th)
                    qimg = QImage(tex_size, tex_size, QImage.Format.Format_RGBA8888)
                    qimg.fill(Qt.GlobalColor.transparent)
                    p = QPainter(qimg)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    bg = QColor(int(color[0] * 255), int(color[1] * 255), int(color[2] * 255), 180)
                    p.setBrush(QBrush(bg))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(0, 0, tex_size, tex_size, 6, 6)
                    p.setFont(f)
                    p.setPen(QColor(255, 255, 255))
                    p.drawText(QRect(0, 0, tex_size, tex_size), Qt.AlignmentFlag.AlignCenter, text)
                    p.end()
                    rgba = bytes(qimg.bits()[:tex_size * tex_size * 4])
                    tex = self._renderer.create_icon_texture_from_data(rgba, tex_size, tex_size, cache_key)
                    self._renderer._icon_textures[cache_key] = tex
            if tex:
                sx, sy = sp[0], sp[1]
                sz = max(font_size * 2.5, 32) * dpr
                self._renderer.render_icon(tex, sx, sy, sz, 1.0, fw, fh)


__all__ = ["ViewportRenderMixin"]
