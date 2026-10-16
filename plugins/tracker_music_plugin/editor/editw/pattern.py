# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import bisect
import os
import time

from PySide6.QtWidgets import QMessageBox

class TrackerPatternMixin:

    def _refresh_sequence_ui(self, select: int | None = None) -> None:
        idx = select if select is not None else self._pattern_seq_index
        self._seq_combo.blockSignals(True)
        self._seq_combo.clear()
        for i, pat in enumerate(self._song.pattern_seq or []):
            self._seq_combo.addItem(f"Position {i}  -  Pattern {pat}")
        self._seq_combo.blockSignals(False)
        if self._seq_combo.count():
            idx = max(0, min(idx, self._seq_combo.count() - 1))
            self._seq_combo.setCurrentIndex(idx)
        self._pattern_seq_index = self._seq_combo.currentIndex()
        self._rebuild_timeline()

    def _rebuild_timeline(self) -> None:
        try:
            self._timeline = [(float(v.end_sec), int(v.sequence_idx), int(v.row))
                              for v in self._song.iter_playback_rows()]
            self._timeline_ends = [t[0] for t in self._timeline]
        except Exception:
            self._timeline = []
            self._timeline_ends = []
        try:
            info = self._song.get_song_info() or {}
            self._preview_duration = float(info.get("duration_seconds") or 0.0)
        except Exception:
            pass

    def _refresh_pattern(self):
        if self._song is None:
            return
        idx = self._pattern_seq_index
        seq = self._song.pattern_seq or []
        if 0 <= idx < len(seq):
            pat_idx = seq[idx]
            patterns = getattr(self._song, "patterns", []) or []
            if 0 <= pat_idx < len(patterns):
                self._pattern_editor.load_pattern(patterns[pat_idx])
                return
        self._pattern_editor.load_pattern(None)

    def _on_seq_changed(self, index: int):
        self._pattern_seq_index = max(0, index)
        self._refresh_pattern()

    def _seq_insert(self):
        if self._song is None:
            return
        idx = self._pattern_seq_index
        if 0 <= idx < len(self._song.pattern_seq):
            self._song.insert_pattern(idx, after=False)
            self._refresh_sequence_ui(idx + 1)
            self._refresh_pattern()
            self._mark_edited()

    def _seq_add(self):
        if self._song is None:
            return
        idx = self._pattern_seq_index
        if 0 <= idx < len(self._song.pattern_seq):
            self._song.duplicate_pattern(idx)
            self._refresh_sequence_ui(len(self._song.pattern_seq) - 1)
            self._refresh_pattern()
            self._mark_edited()

    def _seq_remove(self):
        if self._song is None:
            return
        idx = self._pattern_seq_index
        if 0 <= idx < len(self._song.pattern_seq):
            self._song.remove_pattern(idx)
            self._refresh_sequence_ui(min(idx, len(self._song.pattern_seq) - 1))
            self._refresh_pattern()
            self._mark_edited()

    def _seq_move(self, delta: int):
        if self._song is None:
            return
        idx = self._pattern_seq_index
        n = len(self._song.pattern_seq)
        if not n or not (0 <= idx < n):
            return
        j = idx + delta
        if not (0 <= j < n):
            return
        seq = list(self._song.pattern_seq)
        seq[idx], seq[j] = seq[j], seq[idx]
        self._song.set_sequence(seq)
        self._refresh_sequence_ui(j)
        self._refresh_pattern()
        self._mark_edited()

    def _mark_edited(self):
        self._edit_rev += 1
        self._schedule_rerender()

    def _on_pattern_edited(self):
        self._update_edit_state()
        self._mark_edited()

    def _on_samples_changed(self):
        self._mark_edited()

    def _on_metadata_edited(self, key: str, value: str):
        try:
            title = str(getattr(self._song, "songname", "") or "")
            if not title:
                title = os.path.basename(self._song_path or "module")
            self._module_lbl.setText(f"{os.path.basename(self._song_path)}   -   {title}")
        except Exception:
            pass
        self._schedule_rerender()

    def _update_edit_state(self):
        if self._song is None:
            self._edit_undo_btn.setEnabled(False)
            self._edit_redo_btn.setEnabled(False)
            self._edit_ins_btn.setEnabled(False)
            self._edit_del_btn.setEnabled(False)
            self._edit_clear_btn.setEnabled(False)
            self._edit_down_btn.setEnabled(False)
            self._edit_up_btn.setEnabled(False)
            self._edit_copy_btn.setEnabled(False)
            self._edit_cut_btn.setEnabled(False)
            self._edit_paste_btn.setEnabled(False)
            return
        self._edit_undo_btn.setEnabled(self._pattern_editor.can_undo())
        self._edit_redo_btn.setEnabled(self._pattern_editor.can_redo())
        self._edit_ins_btn.setEnabled(True)
        self._edit_del_btn.setEnabled(True)
        self._edit_clear_btn.setEnabled(True)
        self._edit_down_btn.setEnabled(True)
        self._edit_up_btn.setEnabled(True)
        self._edit_copy_btn.setEnabled(True)
        self._edit_cut_btn.setEnabled(True)
        self._edit_paste_btn.setEnabled(True)

    def _lookup_map(entries, ends, elapsed: float):
        try:
            if entries and ends:
                i = bisect.bisect_left(ends, elapsed)
                if i >= len(entries):
                    i = len(entries) - 1
                _e, s, r = entries[i]
                return int(s), int(r)
        except Exception:
            pass
        return None

    def _resolve_position(self, elapsed: float):
        pos = self._lookup_map(self._playback_map, self._playback_ends, elapsed)
        if pos is not None:
            return pos
        pos = self._lookup_map(self._timeline, self._timeline_ends, elapsed)
        if pos is not None:
            return pos
        return None, self._estimate_row(elapsed)

    def _resolve_row(self, elapsed: float) -> int:
        return int(self._resolve_position(elapsed)[1])

    def _estimate_row(self, elapsed: float) -> int:
        try:
            info = self._song.get_song_info()
            bpm = int(info.get("bpm") or 125)
            speed = int(info.get("speed") or 6)
        except Exception:
            bpm, speed = 125, 6
        try:
            row_dur = (2.5 / max(32, bpm)) * max(1, speed)
        except Exception:
            row_dur = 0.12
        return int(elapsed / max(1e-6, row_dur))

    def _on_tick(self):
        if not self._playing or not self._song:
            return
        elapsed = time.perf_counter() - self._play_start
        dur = self._song_duration()
        if dur > 0 and elapsed > dur + 0.4:
            self._stop_audio()
            return
        seq_idx, row = self._resolve_position(elapsed)
        if (seq_idx is not None and self._seq_combo.count() > 0
                and 0 <= seq_idx < self._seq_combo.count()
                and seq_idx != self._pattern_seq_index):
            self._seq_combo.setCurrentIndex(seq_idx)
        idx = self._pattern_seq_index
        seq = self._song.pattern_seq or []
        if 0 <= idx < len(seq):
            pat_idx = seq[idx]
            patterns = getattr(self._song, "patterns", []) or []
            if 0 <= pat_idx < len(patterns):
                nrows = int(getattr(patterns[pat_idx], "n_rows", 0) or 0)
                if nrows > 0:
                    self._pattern_editor.highlight_row(row % nrows)
        try:
            if self._meter_peaks and self._meter_block_sec > 0:
                mi = int(elapsed / self._meter_block_sec)
                if 0 <= mi < len(self._meter_peaks):
                    block = self._meter_peaks[mi]
                    self._mixer.set_levels(block)
                    peak = 0.0
                    for v in block:
                        try:
                            if float(v) > peak:
                                peak = float(v)
                        except Exception:
                            pass
                    self._mixer.set_master_level(peak * self._master_gain())
        except Exception:
            pass
        m = int(elapsed) // 60
        s = int(elapsed) % 60
        cs = int((elapsed % 1.0) * 100)
        self._time_lbl.setText(f"{m}:{s:02d}.{cs:02d}")

    def _toggle_play(self):
        if self._playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        if self._song is None:
            return
        if self._source_id:
            mgr = self._audio_mgr()
            if mgr:
                mgr.resume(self._source_id)
                self._playing = True
                self._play_start = time.perf_counter() - self._paused_elapsed
                self._play_btn.setText("Pause")
            return
        if self._busy():
            self._pending_autoplay = True
            return
        if not self._preview_wav or not os.path.isfile(self._preview_wav):
            self._start_render(autoplay=True)
            return
        mgr = self._audio_mgr()
        if mgr is None:
            QMessageBox.information(self, "Tracker", "Audio engine is not available for preview.")
            return
        src = mgr.play(clip_path=self._preview_wav, loop=False,
                       volume=self._master_gain(), spatial_blend=0.0)
        if src is None:
            QMessageBox.information(self, "Tracker", "Failed to start audio preview.")
            return
        self._source_id = src
        self._playing = True
        self._paused_elapsed = 0.0
        self._play_start = time.perf_counter()
        self._play_btn.setText("Pause")

    def _pause(self):
        mgr = self._audio_mgr()
        if mgr and self._source_id:
            mgr.pause(self._source_id)
            self._paused_elapsed = time.perf_counter() - self._play_start
        self._playing = False
        self._play_btn.setText("Play")

    def _stop_audio(self):
        if self._source_id:
            mgr = self._audio_mgr()
            if mgr:
                try:
                    mgr.stop(self._source_id)
                except Exception:
                    pass
            self._source_id = 0
        self._playing = False
        self._paused_elapsed = 0.0
        self._play_btn.setText("Play")
        try:
            self._mixer.reset_levels()
        except Exception:
            pass
        self._pattern_editor.clear_rows()
        self._time_lbl.setText("0:00.00")

    def _stop(self):
        self._pending_autoplay = False
        self._rerender_timer.stop()
        self._cancel_worker()
        self._stop_audio()

    def _song_duration(self) -> float:
        try:
            if self._preview_duration > 0:
                return float(self._preview_duration)
        except Exception:
            pass
        return 0.0

    def _audio_mgr():
        from core.audio.sys import AudioSourceManager
        return AudioSourceManager.instance()
