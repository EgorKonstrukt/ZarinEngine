# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QColor, QCursor
from editor.hover.preview import _get_popup
from editor.hover.preview import _hover_delay
from editor.hover.preview import _PREVIEW_SQUARE
def _entity_info(entity):
    try:
        title = entity.name if entity.name else "Entity"
    except Exception:
        title = "Entity"
    rows: list[tuple[str, str]] = []
    try:
        rows.append(("ID", str(entity.id)))
    except Exception:
        pass
    try:
        rows.append(("State", "Active" if entity.active else "Inactive"))
    except Exception:
        pass
    try:
        rows.append(("Layer", str(entity.layer)))
    except Exception:
        pass
    try:
        tags = entity.tags if isinstance(entity.tags, (set, list, tuple)) else []
        rows.append(("Tags", ", ".join(list(tags)) if tags else "-"))
    except Exception:
        pass
    try:
        p = entity.parent
        rows.append(("Parent", p.name if p is not None else "-"))
    except Exception:
        pass
    try:
        rows.append(("Children", str(len(entity.children))))
    except Exception:
        pass
    try:
        comps = entity.get_all_components()
        rows.append(("Components", str(len(comps))))
        names = [type(c).__name__ for c in comps]
        if names:
            shown = ", ".join(names[:6])
            if len(names) > 6:
                shown += " +" + str(len(names) - 6)
            rows.append(("Content", shown))
    except Exception:
        pass
    try:
        tr = entity.transform
        if tr is not None:
            lp = getattr(tr, "local_position", None)
            if lp is not None:
                rows.append(("Position", str(round(float(lp.x), 2)) + ", " + str(round(float(lp.y), 2)) + ", " + str(round(float(lp.z), 2))))
    except Exception:
        pass
    return title, rows
def _entity_preview(entity, size: int) -> QPixmap:
    try:
        from editor.inspector.helpersp import get_component_icon_pixmap
        for c in entity.get_all_components():
            try:
                if getattr(type(c), "_show_gizmo_icon", True) and type(c).__name__ != "Transform":
                    pix = get_component_icon_pixmap(type(c), size)
                    if pix is not None and not pix.isNull():
                        return pix
            except Exception:
                continue
    except Exception:
        pass
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    try:
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(58, 58, 66))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, size, size, 18, 18)
        try:
            nm = entity.name if entity.name else "?"
        except Exception:
            nm = "?"
        ch = nm[:1].upper() if nm else "?"
        p.setPen(QColor(235, 235, 235))
        f = p.font()
        f.setPixelSize(int(size * 0.45))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, ch)
        p.end()
    except Exception:
        pass
    return pm
class _EntityHover(QObject):
    def __init__(self, widget: QWidget, entity_fn):
        super().__init__(widget)
        self._w = widget
        self._fn = entity_fn
        self._inside = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_hover_delay())
        self._timer.timeout.connect(self._show)
        try:
            widget.setMouseTracking(True)
            widget.installEventFilter(self)
        except Exception:
            pass
    def eventFilter(self, obj, event):
        try:
            if obj is not self._w:
                return False
            t = event.type()
            if t == QEvent.Type.Enter:
                self._inside = True
                self._restart()
            elif t == QEvent.Type.MouseMove:
                self._inside = True
                self._restart()
            elif t in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.Close, QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate):
                self._hide()
            elif t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel, QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
                self._hide()
        except Exception:
            pass
        return False
    def _restart(self):
        try:
            self._timer.stop()
            e = self._fn() if self._fn is not None else None
            if e is None:
                self._hide()
                return
            self._timer.setInterval(_hover_delay())
            self._timer.start()
        except Exception:
            pass
    def _show(self):
        try:
            if not self._inside:
                return
            e = self._fn() if self._fn is not None else None
            if e is None:
                return
            popup = _get_popup()
            if popup is None:
                return
            popup.show_entity(e, QCursor.pos())
        except Exception:
            pass
    def _hide(self):
        try:
            self._inside = False
            self._timer.stop()
            popup = _get_popup()
            if popup is not None and popup.isVisible() and popup._kind == "entity":
                popup.hide_animated()
        except Exception:
            pass
def attach_entity_hover(widget: QWidget, entity_fn):
    try:
        filt = _EntityHover(widget, entity_fn)
        widget._hover_preview_filter = filt
        return filt
    except Exception:
        return None
