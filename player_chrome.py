# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
import os
from PySide6.QtCore import QObject, QEvent, Qt

_PLAYER_DEFAULTS = {
    "game_title": "",
    "version": "1.0.0",
    "show_splash": True,
    "window_width": 1280,
    "window_height": 720,
    "fullscreen": False,
    "show_fps_in_title": False,
    "debug_shift_f3": True,
}


def player_options(code_root: str) -> dict:
    opts = dict(_PLAYER_DEFAULTS)
    try:
        with open(os.path.join(code_root, "BuildSettings.json")) as f:
            raw = json.load(f).get("player", {}) or {}
        for k, v in opts.items():
            if k in raw:
                opts[k] = raw[k]
    except Exception:
        pass
    return opts


def format_title(opts: dict, fps=None) -> str:
    try:
        title = str(opts.get("game_title", "") or "").strip() or "Zarin Player"
    except Exception:
        title = "Zarin Player"
    try:
        ver = str(opts.get("version", "") or "").strip()
    except Exception:
        ver = ""
    if ver:
        title = f"{title} v{ver}"
    try:
        if fps is not None and opts.get("show_fps_in_title", False):
            title = f"{title} - {float(fps):.0f} FPS"
    except Exception:
        pass
    return title


class FullscreenFilter(QObject):
    def __init__(self, window):
        super().__init__(window)
        self._window = window

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_F11:
                try:
                    if self._window.isFullScreen():
                        self._window.showNormal()
                    else:
                        self._window.showFullScreen()
                except Exception:
                    pass
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


def apply_window_options(app, window, viewport, opts):
    try:
        viewport._debug_shift_f3 = bool(opts.get("debug_shift_f3", True))
    except Exception:
        pass
    try:
        keeper = FullscreenFilter(window)
        app.installEventFilter(keeper)
    except Exception:
        keeper = None
    try:
        ww = int(opts.get("window_width", 1280) or 0)
        wh = int(opts.get("window_height", 720) or 0)
    except Exception:
        ww, wh = 0, 0
    try:
        screen = app.primaryScreen()
    except Exception:
        screen = None
    if ww > 0 and wh > 0:
        window.resize(ww, wh)
    elif screen:
        window.resize(screen.size() * 0.8)
    else:
        window.resize(1280, 720)
    if opts.get("show_fps_in_title", False):
        try:
            from PySide6.QtCore import QTimer
            timer = QTimer(window)
            def tick_title(w=window, vp=viewport, o=opts):
                try:
                    fps = float(getattr(vp, "_fps", 0.0) or 0.0)
                except Exception:
                    fps = 0.0
                try:
                    w.setWindowTitle(format_title(o, fps if fps > 0 else None))
                except Exception:
                    pass
            timer.timeout.connect(tick_title)
            timer.start(500)
        except Exception:
            pass
    return keeper
