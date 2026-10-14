# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
from typing import Optional, TYPE_CHECKING
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QSurfaceFormat
from core.input.input_manager import InputManager
from core.engine.frame_pacer import FramePacer
from core.engine.gameview.rendering import GameViewportRenderMixin
from core.engine.gameview.interaction import GameViewportInteractionMixin

if TYPE_CHECKING:
    from core.engine.eng import Engine

__all__ = ["GameViewport"]


class GameViewport(GameViewportRenderMixin, GameViewportInteractionMixin, QOpenGLWidget):

    def __init__(self, engine: "Engine", parent=None):
        super().__init__(parent)
        self._engine = engine
        self._ctx: Optional[moderngl.Context] = None
        self._renderer = None
        self._screen_fbo = None
        self._mouse_captured: bool = False
        self._cursor_blank: bool = False
        self._input_manager = InputManager.instance()
        self._last_mouse_x: int = 0
        self._last_mouse_y: int = 0
        from core.config.config import get_global_config
        cfg = get_global_config()
        self._vsync_enabled = cfg.get("rendering.vsync", True)
        self._target_fps = cfg.get("rendering.target_fps", 60)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._pacer = FramePacer()
        engine.on("play_stop", self._on_play_stop)
        self._stats_enabled: bool = False
        self._fps: float = 0.0
        self._fps_accum: float = 0.0
        self._fps_frames: int = 0
        self._last_paint_time: float = 0.0
        self._paint_dt: float = 0.016
        self._last_render_ms: float = 0.0
        self._last_paint_full_ms: float = 0.0
        self._frame_times_ms: list[float] = []
        self._physical_w: int = 0
        self._physical_h: int = 0
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setVersion(4, 6)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setSwapInterval(1 if self._vsync_enabled else 0)
        self.setFormat(fmt)
        self._apply_config()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
