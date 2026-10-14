# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
import traceback
from core.foundation.logger import Logger


class ViewportOverlayMixin:

    def _toggle_stats(self, checked: bool):
        self._stats_enabled = checked
        if checked:
            self._fps_history.clear()
        self.update()

    def _toggle_audio_viz(self, checked: bool):
        self._audio_viz_enabled = checked
        if checked:
            an = self._audio_analyzer
            if an is None:
                from core.audio.audio_analyzer import get_analyzer
                an = get_analyzer()
                self._audio_analyzer = an
            an.reset()
        self.update()

    def _render_audio_osd(self, now):
        if not getattr(self, "_audio_viz_enabled", False):
            return
        an = self._audio_analyzer
        if an is None:
            from core.audio.audio_analyzer import get_analyzer
            an = get_analyzer()
            self._audio_analyzer = an
        av = getattr(self, "_audio_viz", None)
        if av is None or not av.ready():
            return
        try:
            an.update()
            opts = getattr(self, "_audio_viz_opts", None) or {}
            if opts.get("hold_decay") is not None:
                try:
                    an.hold_decay = float(opts["hold_decay"])
                except Exception:
                    pass
            fw, fh = self._get_physical_dims()
            av.set_options(**self._audio_viz_opts)
            av.render(an, fw, fh, self._screen_fbo, now=now)
        except Exception:
            traceback.print_exc()

    def _set_audio_viz_opt(self, key: str, value):
        opts = getattr(self, "_audio_viz_opts", None)
        if opts is None:
            return
        opts[key] = value
        self.update()

    def _toggle_bvh_debug(self, checked: bool):
        self._show_bvh_debug = checked
        self.update()

    def _toggle_rt_heatmap(self, checked: bool):
        self._show_rt_heatmap = checked
        try:
            from core.components.rendering.renderers.raytrace import RaytracingRenderer
            sc = self._engine.scene if hasattr(self, "_engine") and self._engine else None
            if sc:
                for ent in sc.get_entities_with_component(RaytracingRenderer):
                    rr = ent.get_component(RaytracingRenderer)
                    if rr:
                        rr._heatmap_mode = 1 if checked else 0
                        rr._heatmap_scale = 50.0 if checked else 40.0
                        rr._accum_frame = 1
        except Exception:
            pass
        self.update()

    def _render_bvh_debug(self):
        if not hasattr(self, "_engine") or not self._engine:
            return
        scene = self._engine.scene
        if not scene:
            return
        sel_list = getattr(self, "_selected_entities", [])
        if not sel_list:
            return
        sel = sel_list[0]
        from core.components.rendering.renderers.mesh_filter import MeshFilter
        mf = sel.get_component(MeshFilter)
        if not mf:
            return
        from editor.viewport.pick import _get_mesh_for
        mesh = _get_mesh_for(sel, mf.mesh_name or "cube", mf.mesh_path)
        if not mesh or mesh.vertices is None or len(mesh.vertices) < 3:
            return
        from core.spatial.bvhv import get_mesh_bvh
        bvh = get_mesh_bvh(mesh.vertices, mesh.indices)
        if not bvh or not bvh.nodes:
            return
        tr = sel.transform
        if not tr:
            return
        wm = tr.world_matrix
        fw, fh = self._get_physical_dims()
        vp_mat = self._cam.get_view_matrix() * self._cam.get_projection_matrix(fw / max(1, fh))
        if not hasattr(self, "_bvh_dbg"):
            from core.renderer.bvh_debug import BVHDebugRenderer
            self._bvh_dbg = BVHDebugRenderer()
        try:
            self._bvh_dbg.render(self._ctx, bvh, wm, vp_mat, max_depth=4)
        except Exception:
            pass

    def _update_status_labels(self):
        if self._no_qt_overlay:
            return
        now = time.perf_counter()
        if now - self._last_status_update < 0.2:
            return
        self._last_status_update = now
        pos = self._cam.position
        _s = f"Cam: {pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f}"
        if getattr(self, "_cam_pos_cache", "") != _s:
            self._cam_pos_label.setText(_s)
            self._cam_pos_cache = _s

    def _collab_tick(self):
        if not self._engine.play_mode:
            from editor.viewport.collaboration import send_collab_camera
            send_collab_camera(self)
            self._update_status_labels()

    def _paint_overlay_tick(self):
        if self._no_qt_overlay:
            return
        try:
            if self._overlay_widget.width() != self.width() or self._overlay_widget.height() != self.height():
                self._overlay_widget.resize(self.width(), self.height())
        except Exception:
            pass
        now_overlay = time.perf_counter()
        if self._stats_enabled:
            if now_overlay - self._last_overlay_update >= 0.5:
                self._last_overlay_update = now_overlay
                self._overlay_widget.update()
        else:
            if now_overlay - self._last_overlay_update >= 0.1:
                _dyn = (self._audio_viz_enabled or self._area_selecting or self._overlay_canvas is not None or getattr(self._gizmo, "_dragging", False) or bool(getattr(self._gizmo, "delta_text", "")))
                if not _dyn:
                    try:
                        _collab = getattr(self._engine, "collab_manager", None)
                        _dyn = bool(getattr(_collab, "connected", False))
                    except Exception:
                        pass
                if _dyn or now_overlay - self._last_overlay_update >= 2.0:
                    self._last_overlay_update = now_overlay
                    self._overlay_widget.update()


__all__ = ["ViewportOverlayMixin"]
