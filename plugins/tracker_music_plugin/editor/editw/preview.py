# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from ...rend import _RENDER_VERSION, TrackerSoftwareRenderer, load_module, render_to_wav_file

_METER_MAX_BLOCKS = 2048

def _downsample_peaks(peaks: list, max_blocks: int) -> list:
    try:
        n = len(peaks)
        if n <= max_blocks or n == 0:
            return [list(b) for b in peaks]
        stride = n / max_blocks
        out = []
        for i in range(max_blocks):
            lo = int(i * stride)
            hi = max(lo + 1, int((i + 1) * stride))
            cols = list(zip(*peaks[lo:hi]))
            out.append([max(c) for c in cols] if cols else [])
        return out
    except Exception:
        return []

def _write_peaks_sidecar(wav_path: str, block_sec: float, peaks: list, playmap: list = ()):
    try:
        with open(wav_path + ".peaks.json", "w", encoding="utf-8") as f:
            json.dump({"block_sec": block_sec,
                       "peaks": [[round(float(v), 3) for v in b] for b in peaks],
                       "playmap": [[round(float(e), 4), int(s), int(r)] for e, s, r in playmap]}, f)
    except Exception:
        pass

def _load_peaks_sidecar(wav_path: str):
    try:
        with open(wav_path + ".peaks.json", "r", encoding="utf-8") as f:
            d = json.load(f)
        block_sec = float(d.get("block_sec") or 0.1)
        peaks = [[float(v) for v in b] for b in (d.get("peaks") or [])]
        playmap = [(float(e), int(s), int(r)) for e, s, r in (d.get("playmap") or [])]
        return block_sec, peaks, playmap
    except Exception:
        return None

class _PreviewJob(QObject):
    progress = pyqtSignal(float, object)
    done = pyqtSignal(int, str, float, float, object, object)
    failed = pyqtSignal(int, str)

    def __init__(self, job_id: int, kind: str, path: str, out_path: str,
                 sample_rate: int, muted: set, gains_db: list,
                 bake_master_gain: float | None):
        super().__init__()
        self._job_id = job_id
        self._kind = kind
        self._path = path
        self._out_path = out_path
        self._sample_rate = sample_rate
        self._muted = set(muted)
        self._gains_db = list(gains_db)
        self._bake_master_gain = bake_master_gain
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            if self._kind == "save":
                song = load_module(self._path)
                if song is None:
                    self.failed.emit(self._job_id, "Failed to load module.")
                    return
                song.save(self._out_path, verbose=False)
                self.done.emit(self._job_id, self._out_path, 0.0, 0.1, [], [])
                return
            if os.path.isfile(self._out_path):
                self._emit_cached()
                return
            song = load_module(self._path)
            if song is None:
                self.failed.emit(self._job_id, "Failed to load module.")
                return
            for ch in self._muted:
                try:
                    song.mute_channel(ch)
                except Exception:
                    pass
            renderer = TrackerSoftwareRenderer(self._sample_rate)
            for ch, db in enumerate(self._gains_db):
                try:
                    renderer.set_channel_db(ch, float(db))
                except Exception:
                    pass
            last_emit = [0.0]

            def prog(elapsed: float, total):
                now = time.perf_counter()
                if now - last_emit[0] >= 0.15:
                    last_emit[0] = now
                    self.progress.emit(float(elapsed), total)

            pcm = renderer.render(song, progress=prog, should_cancel=self._cancel.is_set)
            if pcm is None:
                self.failed.emit(self._job_id, "cancelled")
                return
            if self._bake_master_gain is not None and self._bake_master_gain != 1.0:
                try:
                    pcm = (pcm.astype(np.float32) * float(self._bake_master_gain)).clip(
                        -32768.0, 32767.0).astype(np.int16)
                except Exception:
                    pass
            render_to_wav_file(pcm, self._out_path, self._sample_rate)
            block_sec, peaks = renderer.get_meter_data()
            peaks = _downsample_peaks(peaks, _METER_MAX_BLOCKS)
            try:
                playmap = renderer.get_playback_map()
            except Exception:
                playmap = []
            _write_peaks_sidecar(self._out_path, block_sec, peaks, playmap)
            duration = len(pcm) / float(self._sample_rate)
            self.done.emit(self._job_id, self._out_path, duration, block_sec, peaks, playmap)
        except Exception as e:
            try:
                self.failed.emit(self._job_id, str(e))
            except Exception:
                pass

    def _emit_cached(self):
        try:
            import wave
            duration = 0.0
            block_sec = TrackerSoftwareRenderer.METER_BLOCK_SEC
            peaks: list = []
            playmap: list = []
            try:
                with wave.open(self._out_path, "rb") as wf:
                    duration = wf.getnframes() / float(wf.getframerate() or self._sample_rate)
            except Exception:
                pass
            try:
                sidecar = _load_peaks_sidecar(self._out_path)
                if sidecar is not None:
                    block_sec, peaks, playmap = sidecar
            except Exception:
                pass
            self.done.emit(self._job_id, self._out_path, duration, block_sec, peaks, playmap)
        except Exception as e:
            self.failed.emit(self._job_id, str(e))

class TrackerPreviewMixin:

    def _schedule_rerender(self):
        if self._song is None:
            return
        self._rerender_timer.stop()
        self._rerender_timer.start()

    def _on_rerender_timeout(self):
        if self._song is None:
            return
        resume = self._playing or self._pending_autoplay
        self._start_render(autoplay=resume)

    def _preview_cache_path(self, bake_master_gain: float | None) -> str:
        h = hashlib.sha1()
        try:
            st = os.stat(self._song_path)
            h.update(f"{self._song_path}|{st.st_mtime}|{st.st_size}".encode())
        except Exception:
            h.update(self._song_path.encode("utf-8", "ignore"))
        gains = self._mixer.all_gains_db()
        muted = sorted(self._mixer.muted_channels())
        h.update(f"|{_RENDER_VERSION}|{self._sample_rate()}|{self._quality()}|{muted}|{gains}|{bake_master_gain}|rev{self._edit_rev}".encode())
        return os.path.join(self._cache_dir(), f"prev_{h.hexdigest()[:16]}.wav")

    def _busy(self) -> bool:
        return self._worker is not None

    def _start_render(self, autoplay: bool, kind: str = "preview", dest: str = "",
                      bake_master: bool = False):
        if self._song is None or not self._song_path:
            return
        self._cancel_worker()
        self._job_id += 1
        self._job_kind = kind
        self._job_dest = dest
        self._pending_autoplay = autoplay
        bake_gain = self._master_gain() if bake_master else None
        out_path = dest if kind == "save" else self._preview_cache_path(bake_gain)
        if kind != "save" and os.path.isfile(out_path):
            self._on_cached_preview(out_path, bake_gain)
            if autoplay:
                self._play()
            return
        worker = _PreviewJob(
            self._job_id, kind, self._song_path, out_path,
            self._sample_rate(), self._mixer.muted_channels(),
            self._mixer.all_gains_db(), bake_gain,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_job_progress)
        worker.done.connect(self._on_job_done)
        worker.failed.connect(self._on_job_failed)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._cancel_btn.setVisible(True)
        thread.start()

    def _on_cached_preview(self, out_path: str, bake_gain):
        self._preview_wav = out_path
        self._meter_peaks = []
        self._meter_block_sec = TrackerSoftwareRenderer.METER_BLOCK_SEC
        self._playback_map = []
        self._playback_ends = []
        try:
            sidecar = _load_peaks_sidecar(out_path)
            if sidecar is not None:
                self._meter_block_sec, self._meter_peaks, self._playback_map = sidecar
                self._playback_ends = [e for e, _s, _r in self._playback_map]
        except Exception:
            pass
        try:
            import wave
            with wave.open(out_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or self._sample_rate()
                self._preview_duration = frames / float(rate)
        except Exception:
            pass

    def _cancel_worker(self):
        worker = self._worker
        self._worker = None
        self._thread = None
        if worker is not None:
            try:
                worker.cancel()
            except Exception:
                pass
        self._progress.setVisible(False)
        self._cancel_btn.setVisible(False)

    def _cancel_job(self):
        self._pending_autoplay = False
        self._cancel_worker()

    def _on_job_progress(self, elapsed: float, total):
        try:
            if total:
                pct = max(0, min(100, int(elapsed * 100.0 / max(1e-6, float(total)))))
                self._progress.setRange(0, 100)
                self._progress.setValue(pct)
            else:
                self._progress.setRange(0, 0)
        except Exception:
            pass

    def _on_job_done(self, job_id: int, out_path: str, duration: float,
                     block_sec: float, peaks, playmap):
        if job_id != self._job_id:
            return
        kind = self._job_kind
        self._cancel_worker()
        if kind == "save":
            QMessageBox.information(self, "Tracker", f"Module exported to\n{out_path}")
            return
        self._preview_wav = out_path
        if duration > 0:
            self._preview_duration = duration
        try:
            self._meter_block_sec = float(block_sec) or TrackerSoftwareRenderer.METER_BLOCK_SEC
        except Exception:
            self._meter_block_sec = TrackerSoftwareRenderer.METER_BLOCK_SEC
        try:
            self._meter_peaks = [list(b) for b in (peaks or [])]
        except Exception:
            self._meter_peaks = []
        try:
            self._playback_map = [(float(e), int(s), int(r)) for e, s, r in (playmap or [])]
            self._playback_ends = [e for e, _s, _r in self._playback_map]
        except Exception:
            self._playback_map = []
            self._playback_ends = []
        if kind == "export":
            try:
                shutil.copyfile(out_path, self._job_dest)
                self._time_lbl.setText(f"Exported to {os.path.basename(self._job_dest)}")
            except Exception as e:
                QMessageBox.warning(self, "Tracker", f"Export failed: {e}")
            return
        if self._pending_autoplay:
            self._pending_autoplay = False
            self._stop_audio()
            self._play()

    def _on_job_failed(self, job_id: int, message: str):
        if job_id != self._job_id:
            return
        self._cancel_worker()
        self._pending_autoplay = False
        if message != "cancelled":
            QMessageBox.warning(self, "Tracker", f"Render failed: {message}")

    def _clear_cache(self):
        try:
            cache = self._cache_dir()
            removed = 0
            for fn in os.listdir(cache):
                if fn.startswith("prev_") and (fn.endswith(".wav") or fn.endswith(".peaks.json")):
                    try:
                        os.remove(os.path.join(cache, fn))
                        removed += 1
                    except Exception:
                        pass
            QMessageBox.information(self, "Tracker", f"Preview cache cleared ({removed} files).")
        except Exception as e:
            QMessageBox.warning(self, "Tracker", f"Failed to clear cache: {e}")

    def _save_module(self):
        if self._song is None or not self._song_path:
            return
        try:
            self._stop()
            self._song.save(self._song_path, verbose=False)
            self._time_lbl.setText(f"Saved {os.path.basename(self._song_path)}")
            self._start_render(autoplay=False)
        except Exception as e:
            QMessageBox.warning(self, "Tracker", f"Save failed: {e}")

    def _export_wav(self):
        if self._song is None:
            return
        if self._busy():
            QMessageBox.information(self, "Tracker", "Please wait for the current render to finish.")
            return
        default = os.path.splitext(os.path.basename(self._song_path))[0] + ".wav"
        path, _ = QFileDialog.getSaveFileName(self, "Export WAV", default, "WAV (*.wav)")
        if not path:
            return
        self._start_render(autoplay=False, kind="export", dest=path, bake_master=True)

    def _export_module(self):
        if self._song is None or not self._song_path:
            return
        if self._busy():
            QMessageBox.information(self, "Tracker", "Please wait for the current render to finish.")
            return
        try:
            ext = str(getattr(self._song, "file_extension", "") or "").lower().strip(".")
        except Exception:
            ext = ""
        if not ext:
            ext = os.path.splitext(self._song_path)[1].lower().strip(".") or "mod"
        default = os.path.splitext(os.path.basename(self._song_path))[0] + f".{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Module", default, f"{ext.upper()} (*.{ext})")
        if not path:
            return
        self._start_render(autoplay=False, kind="save", dest=path)
