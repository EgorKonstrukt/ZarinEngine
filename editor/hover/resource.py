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
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QColor, QCursor, QImageReader
from editor.hover.preview import _resolve_path
from editor.hover.preview import _display_path
from editor.hover.preview import _fmt_size
from editor.hover.preview import _type_name
from editor.hover.preview import _peek_cached
from editor.hover.preview import _candidate_sizes
from editor.hover.preview import _get_popup
from editor.hover.preview import _hover_delay
from editor.hover.preview import _PREVIEW_SIZE
def _resource_info(path: str):
    path = _resolve_path(path)
    base = os.path.basename(path.rstrip(os.sep)) if path else ""
    if not base:
        base = path if path else "None"
    rows: list[tuple[str, str]] = []
    is_dir = False
    try:
        is_dir = os.path.isdir(path)
    except Exception:
        is_dir = False
    if is_dir:
        rows.append(("Type", _type_name(path, True)))
        try:
            entries = os.listdir(path)
            vis = [e for e in entries if not e.startswith(".")]
            rows.append(("Items", str(len(vis))))
            total = 0
            for e in vis:
                try:
                    fp = os.path.join(path, e)
                    if os.path.isfile(fp):
                        total += os.path.getsize(fp)
                except Exception:
                    continue
            rows.append(("Size", _fmt_size(total)))
        except Exception:
            pass
        rows.append(("Path", _display_path(path)))
        return base, rows
    if not path or not os.path.exists(path):
        rows.append(("Type", _type_name(path if path else "", False)))
        rows.append(("Status", "Missing"))
        rows.append(("Path", path if path else ""))
        return base, rows
    try:
        st = os.stat(path)
        rows.append(("Type", _type_name(path, False)))
        rows.append(("Size", _fmt_size(st.st_size)))
        rows.append(("Modified", datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")))
    except Exception:
        pass
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".tif", ".tiff", ".webp", ".hdr"):
        try:
            reader = QImageReader(path)
            if reader.canRead():
                sz = reader.size()
                rows.append(("Resolution", str(sz.width()) + "x" + str(sz.height())))
        except Exception:
            pass
    elif ext == ".wav":
        try:
            with wave.open(path, "rb") as wf:
                ch = wf.getnchannels()
                rate = wf.getframerate()
                frames = wf.getnframes()
                dur = frames / float(rate) if rate else 0
                rows.append(("Duration", str(round(dur, 2)) + " s"))
                rows.append(("Channels", str(ch)))
                rows.append(("Sample Rate", str(rate) + " Hz"))
        except Exception:
            pass
    elif ext in (".py", ".txt", ".shader", ".vert", ".frag", ".compute", ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".csv"):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read(2 * 1024 * 1024)
            rows.append(("Lines", str(data.count("\n") + 1)))
        except Exception:
            pass
    elif ext in (".mat", ".zpem"):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            props = data.get("properties", data) if isinstance(data, dict) else {}
            if isinstance(props, dict):
                alb = props.get("_BaseColor", props.get("albedo_color", None))
                if alb is not None:
                    try:
                        rows.append(("Albedo", str(list(alb)[:4])))
                    except Exception:
                        pass
                for k in ("_Metallic", "_Smoothness", "_EmissionIntensity", "shader"):
                    if k in props:
                        rows.append((k.replace("_", ""), str(props.get(k))))
        except Exception:
            pass
    elif ext in (".zpes", ".zpep"):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key in ("entities", "roots", "objects"):
                    v = data.get(key, None)
                    if isinstance(v, list):
                        rows.append(("Objects", str(len(v))))
                        break
                nm = data.get("name", None)
                if nm:
                    rows.append(("Scene Name", str(nm)))
        except Exception:
            pass
    elif ext == ".obj":
        try:
            vc = 0
            fc = 0
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if i > 200000:
                        break
                    if line.startswith("v "):
                        vc += 1
                    elif line.startswith("f "):
                        fc += 1
            if vc or fc:
                rows.append(("Vertices", str(vc)))
                rows.append(("Faces", str(fc)))
        except Exception:
            pass
    rows.append(("Path", _display_path(path)))
    return base, rows
def _resource_preview(path: str) -> QPixmap:
    norm = _resolve_path(path)
    pm = _peek_cached(norm)
    if pm is not None:
        return pm
    try:
        from editor.picker import _get_thumbnail, _thumb_resolution
        size = int(_thumb_resolution())
    except Exception:
        try:
            from editor.picker import _get_thumbnail
        except Exception:
            pm = QPixmap(_PREVIEW_SIZE, _PREVIEW_SIZE)
            pm.fill(Qt.GlobalColor.transparent)
            return pm
        size = _PREVIEW_SIZE
    try:
        pm = _get_thumbnail(norm, size)
        if pm is not None and not pm.isNull():
            return pm
    except Exception:
        pass
    try:
        from editor.picker import _draw_file_icon
        return _draw_file_icon(size)
    except Exception:
        pass
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm
class _ResourceHover(QObject):
    def __init__(self, widget: QWidget, path_fn):
        super().__init__(widget)
        self._w = widget
        self._fn = path_fn
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
            p = self._fn() if self._fn is not None else None
            if not p:
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
            p = self._fn() if self._fn is not None else None
            if not p:
                return
            popup = _get_popup()
            if popup is None:
                return
            popup.show_resource(p, QCursor.pos())
        except Exception:
            pass
    def _hide(self):
        try:
            self._inside = False
            self._timer.stop()
            popup = _get_popup()
            if popup is not None and popup.isVisible() and popup._kind == "resource":
                popup.hide_animated()
        except Exception:
            pass
def attach_resource_hover(widget: QWidget, path_fn):
    try:
        filt = _ResourceHover(widget, path_fn)
        widget._hover_preview_filter = filt
        return filt
    except Exception:
        return None
