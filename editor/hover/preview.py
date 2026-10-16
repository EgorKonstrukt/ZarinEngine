# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import datetime
import json
import wave
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt, QObject, QEvent, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QPainter, QColor, QCursor, QImageReader
_PREVIEW_SIZE = 256
_PREVIEW_SQUARE = 240
_POPUP_WIDTH = 272
_SHOW_MS = 180
_HIDE_MS = 120
_popup_instance = None
def _get_popup():
    global _popup_instance
    try:
        if _popup_instance is None:
            _popup_instance = HoverPreview()
    except Exception:
        return None
    return _popup_instance
def _hover_delay() -> int:
    try:
        from core.config.config import get_global_config
        v = get_global_config().get("editor.hover_delay", 450)
        return max(0, min(2000, int(v)))
    except Exception:
        return 450
def _fmt_size(n) -> str:
    try:
        v = int(n)
    except Exception:
        return str(n)
    if v < 1024:
        return str(v) + " B"
    if v < 1024 * 1024:
        return str(round(v / 1024, 1)) + " KB"
    if v < 1024 * 1024 * 1024:
        return str(round(v / (1024 * 1024), 1)) + " MB"
    return str(round(v / (1024 * 1024 * 1024), 2)) + " GB"
def _type_name(path: str, is_dir: bool) -> str:
    if is_dir:
        return "Folder"
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".webp", ".hdr"):
        return "Image"
    if ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
        return "3D Model"
    if ext in (".wav", ".mp3", ".ogg", ".flac", ".aiff", ".m4a"):
        return "Audio"
    if ext == ".py":
        return "Python Script"
    if ext == ".zpes":
        return "Scene"
    if ext == ".zpep":
        return "Prefab"
    if ext in (".mat", ".zpem"):
        return "Material"
    if ext in (".shader", ".vert", ".frag", ".compute"):
        return "Shader"
    if ext == ".animclip":
        return "Animation Clip"
    if ext == ".animcontroller":
        return "Animator Controller"
    if ext in (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"):
        return "Font"
    if ext == ".zphysmat":
        return "Physics Material"
    if ext == ".zterr":
        return "Terrain Graph"
    if ext:
        return ext[1:].upper() + " File"
    return "File"
def _display_path(path: str) -> str:
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        root = getattr(eng, "project_root", "") if eng is not None else ""
        if root and os.path.abspath(path).startswith(os.path.abspath(root)):
            return os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except Exception:
        pass
    return path
def _resolve_path(path: str) -> str:
    if not path:
        return ""
    try:
        p = os.path.normpath(path)
        if os.path.isabs(p):
            return os.path.abspath(p)
    except Exception:
        pass
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        root = getattr(eng, "project_root", "") if eng is not None else ""
        if root:
            return os.path.abspath(os.path.normpath(os.path.join(root, path)))
    except Exception:
        pass
    try:
        return os.path.abspath(path)
    except Exception:
        return path
def _candidate_sizes() -> list:
    try:
        from editor.picker import _thumb_resolution
        res = int(_thumb_resolution())
    except Exception:
        res = _PREVIEW_SIZE
    try:
        from editor.constants import PREVIEW_SIZE
        prev = int(PREVIEW_SIZE)
    except Exception:
        prev = 160
    sizes = []
    for s in (res, _PREVIEW_SIZE, prev):
        if s not in sizes:
            sizes.append(s)
    return sizes
def _peek_cached(norm_path: str):
    if not norm_path:
        return None
    try:
        from editor.picker import _thumbnail_cache, _thumbnail_mutex
        for s in _candidate_sizes():
            key = "thumb:" + norm_path + ":" + str(s)
            _thumbnail_mutex.lock()
            pm = _thumbnail_cache.get(key)
            _thumbnail_mutex.unlock()
            if pm is not None and not pm.isNull():
                return pm
    except Exception:
        pass
    return None
class HoverPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._current_path = None
        self._current_entity = None
        self._kind = None
        self._thumb_size = _PREVIEW_SIZE
        self._hide_pending = False
        self.setFixedWidth(_POPUP_WIDTH)
        self.setStyleSheet("HoverPreview { background: " + chr(35) + "1e1e1e; border: 1px solid " + chr(35) + "3a3a3a; border-radius: 6px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._preview = QLabel(self)
        self._preview.setFixedSize(_PREVIEW_SQUARE, _PREVIEW_SQUARE)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet("background: " + chr(35) + "2a2a2a; border: 1px solid " + chr(35) + "444; border-radius: 4px; color: " + chr(35) + "666; font-size: 11px;")
        layout.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)
        self._title = QLabel(self)
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-weight: bold; font-size: 13px; color: " + chr(35) + "ffffff; background: transparent; border: none;")
        layout.addWidget(self._title)
        self._info = QLabel(self)
        self._info.setWordWrap(True)
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._info.setStyleSheet("font-size: 11px; color: " + chr(35) + "cccccc; background: transparent; border: none;")
        layout.addWidget(self._info)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(_SHOW_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(_SHOW_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hide_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._hide_anim.setDuration(_HIDE_MS)
        self._hide_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._hide_anim.finished.connect(self._on_hide_finished)
        try:
            from editor.picker import _get_thumb_service
            svc = _get_thumb_service()
            svc.thumbnail_ready.connect(self._on_thumb, Qt.ConnectionType.QueuedConnection)
        except Exception:
            pass
    def _on_thumb(self, path: str, size: int, pm):
        try:
            if self._kind != "resource":
                return
            if not self._current_path:
                return
            try:
                incoming = os.path.abspath(os.path.normpath(path))
            except Exception:
                incoming = path
            if incoming != self._current_path:
                return
            if size not in _candidate_sizes():
                return
            if pm is None or pm.isNull():
                return
            if not self.isVisible():
                return
            self._set_preview_pixmap(pm)
        except Exception:
            pass
    def _set_preview_pixmap(self, pm: QPixmap):
        try:
            scaled = pm.scaled(_PREVIEW_SQUARE, _PREVIEW_SQUARE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._preview.setPixmap(scaled)
        except Exception:
            pass
    def show_resource(self, path: str, global_pos: QPoint):
        try:
            from editor.hover.resource import _resource_info
            from editor.hover.resource import _resource_preview
            self._kind = "resource"
            self._current_path = _resolve_path(path)
            self._current_entity = None
            title, rows = _resource_info(self._current_path)
            pm = _resource_preview(self._current_path)
            self._present(title, rows, pm, global_pos)
        except Exception:
            pass
    def show_entity(self, entity, global_pos: QPoint):
        try:
            from editor.hover.entity import _entity_info
            from editor.hover.entity import _entity_preview
            self._kind = "entity"
            self._current_entity = entity
            self._current_path = None
            title, rows = _entity_info(entity)
            pm = _entity_preview(entity, _PREVIEW_SQUARE)
            self._present(title, rows, pm, global_pos)
        except Exception:
            pass
    def hide_animated(self):
        try:
            if not self.isVisible():
                self._hide_pending = False
                return
            try:
                self._fade.stop()
            except Exception:
                pass
            try:
                self._slide.stop()
            except Exception:
                pass
            self._hide_pending = True
            try:
                self._hide_anim.stop()
                self._hide_anim.setStartValue(self.windowOpacity())
                self._hide_anim.setEndValue(0.0)
                self._hide_anim.start()
            except Exception:
                self.hide()
                self._hide_pending = False
        except Exception:
            pass
    def _on_hide_finished(self):
        try:
            if self._hide_pending:
                self.hide()
                self._hide_pending = False
                self.setWindowOpacity(1.0)
        except Exception:
            pass
    def _present(self, title: str, rows, pm: QPixmap, global_pos: QPoint):
        try:
            self._hide_pending = False
            try:
                self._hide_anim.stop()
            except Exception:
                pass
            try:
                self._fade.stop()
            except Exception:
                pass
            try:
                self._slide.stop()
            except Exception:
                pass
            self._title.setText(title)
            lines = []
            for k, v in rows:
                lines.append(str(k) + ": " + str(v))
            self._info.setText("\n".join(lines))
            if pm is not None and not pm.isNull():
                self._set_preview_pixmap(pm)
            else:
                self._preview.clear()
                self._preview.setText("No preview")
            self.adjustSize()
            target = self._target_pos(global_pos)
            start = QPoint(target.x(), target.y() + 10)
            self.move(start)
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
            try:
                self._fade.setStartValue(0.0)
                self._fade.setEndValue(1.0)
                self._fade.start()
                self._slide.setStartValue(start)
                self._slide.setEndValue(target)
                self._slide.start()
            except Exception:
                self.move(target)
                self.setWindowOpacity(1.0)
        except Exception:
            pass
    def _target_pos(self, pos: QPoint) -> QPoint:
        try:
            if pos is None:
                return QPoint(0, 0)
            x = pos.x() + 18
            y = pos.y() + 18
            try:
                screen = QApplication.screenAt(pos)
                if screen is not None:
                    geo = screen.availableGeometry()
                    w = self.width()
                    h = self.height()
                    if x + w > geo.right():
                        x = pos.x() - w - 12
                    if y + h > geo.bottom():
                        y = pos.y() - h - 12
                    if x < geo.left():
                        x = geo.left() + 4
                    if y < geo.top():
                        y = geo.top() + 4
            except Exception:
                pass
            return QPoint(x, y)
        except Exception:
            return QPoint(0, 0)
