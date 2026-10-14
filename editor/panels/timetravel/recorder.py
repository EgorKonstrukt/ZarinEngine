# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
_H = chr(35)
class TimeTravelRecorderMixin:
    def _toggle_record(self):
        if self._recorder.is_recording:
            self._recorder.stop()
            self._record_btn.setChecked(False)
            self._status_lbl.setText("Stopped")
            self._refresh_timer.stop()
        else:
            self._recorder.clear()
            self._recorder.capture_interval = self._interval_sb.value()
            self._recorder.start()
            self._record_btn.setChecked(True)
            self._status_lbl.setText("Recording...")
            self._restored = False
            self._live_data = None
            self._live_btn.setEnabled(False)
            self._prev_frame_data = None
            self._diff_cache = None
            self._refresh_timer.start()
    def _on_interval_changed(self, v):
        if self._recorder:
            self._recorder.capture_interval = v
    def _set_breakpoint(self):
        if self._recorder:
            self._recorder.breakpoint_expr = self._bp_input.text().strip()
    def _clear_breakpoint(self):
        if self._recorder:
            self._recorder.breakpoint_expr = ""
        self._bp_input.clear()
    def _on_heatmap_toggled(self, on):
        self._timeline.set_heatmap(on)
    def _on_dedup_toggled(self, on):
        if self._recorder:
            self._recorder.filter_unchanged = on
    def _clear(self):
        if self._playing:
            self._toggle_play()
        if self._recorder:
            self._recorder.stop()
            self._recorder.clear()
        self._record_btn.setChecked(False)
        self._refresh_timer.stop()
        self._timeline.set_frames([])
        self._frame_lbl.setText("No frames")
        self._status_lbl.setText("Idle")
        self._live_btn.setEnabled(False)
        self._live_data = None
        self._restored = False
        self._prev_frame_data = None
        self._diff_cache = None
        self._diff_tree.clear()
        self._bk_tree.clear()
        self._search_tree.clear()
    def _refresh(self):
        if not self._recorder:
            return
        frames = self._recorder.frames()
        self._timeline.set_frames(frames)
        if self._restored:
            idx = self._timeline.current_index()
            if idx >= 0:
                snap = self._recorder.get_frame(idx)
                if snap:
                    self._update_labels(snap)
        else:
            n = self._recorder.num_frames
            if n > 0:
                snap = self._recorder.get_frame(n - 1)
                if snap:
                    self._frame_lbl.setText(
                        f"{n} frames  latest {_H}{snap.frame_number}")
                    self._status_lbl.setText("Recording")
        self._refresh_bookmarks()
