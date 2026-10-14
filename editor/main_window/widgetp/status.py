# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal


class _HwMonitorWorker(QObject):
    hw_updated = pyqtSignal(float, float, float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll)

    def start(self):
        import psutil
        psutil.cpu_percent(interval=None)
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _poll(self):
        cpu = 0.0
        ram_used = 0.0
        ram_total = 0.0
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            ram_used = mem.used / (1024 * 1024)
            ram_total = mem.total / (1024 * 1024)
        except Exception:
            pass
        self.hw_updated.emit(cpu, ram_used, ram_total, 0.0, 0.0, 0.0)


class _StatusMixin:
    def _update_status(self):
        if self._status_fps_lbl:
            vp = getattr(self._engine, "viewport", None)
            render_fps = vp._fps if vp and hasattr(vp, "_fps") else 0.0
            tps = self._engine.tps
            s = f"FPS: {render_fps:.0f} | TPS: {tps:.0f}"
            if s != self._status_fps_lbl.text():
                self._status_fps_lbl.setText(s)
        if self._status_gpu_name_lbl:
            try:
                vp = getattr(self._engine, "viewport", None)
                info = getattr(vp, "_gl_info_cache", None) if vp else None
                if info:
                    name = info.get("GL_RENDERER", "")
                    if name and self._status_gpu_name_lbl.text() != name:
                        self._status_gpu_name_lbl.setText(name)
            except Exception:
                pass
        if self._engine.scene and self._engine.scene.dirty:
            name = self._engine.scene.name
            self.setWindowTitle(f"Zarin Engine Editor - {name}*")
        try:
            mgr = getattr(self, "_scene_tab_manager", None)
            if mgr is not None:
                mgr.refresh_all_tab_titles()
        except Exception:
            pass
        from core.foundation.cmd import get_history
        h = get_history()
        self._undo_act.setEnabled(h.can_undo)
        self._undo_act.setText(f"Undo ({h.undo_text.split()[-1] if h.can_undo else ''})" if h.can_undo else "Undo")
        self._redo_act.setEnabled(h.can_redo)
        self._redo_act.setText(f"Redo ({h.redo_text.split()[-1] if h.can_redo else ''})" if h.can_redo else "Redo")

    def _on_hw_updated(self, cpu, ram_used, ram_total, gpu, vram_used, vram_total):
        if self._status_cpu_lbl:
            s = f"CPU: {cpu:.0f}%"
            if s != self._status_cpu_lbl.text():
                self._status_cpu_lbl.setText(s)
        if self._status_ram_lbl:
            s = f"RAM: {ram_used:.0f} / {ram_total:.0f} MB"
            if s != self._status_ram_lbl.text():
                self._status_ram_lbl.setText(s)
