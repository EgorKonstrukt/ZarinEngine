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
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QPainter, QColor, QCursor, QImageReader


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
        from core.engine.engine import Engine
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
        from core.engine.engine import Engine
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
        from editor.resource_picker import _thumb_resolution
        res = int(_thumb_resolution())
    except Exception:
        res = _PREVIEW_SIZE
    try:
        from editor.constants import PREVIEW_SIZE
        prev = int(PREV_SIZE)
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
        from editor.resource_picker import _thumbnail_cache, _thumbnail_mutex
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


def _resource_preview(path: str) -> QPixmap:
    norm = _resolve_path(path)
    pm = _peek_cached(norm)
    if pm is not None:
        return pm
    try:
        from editor.resource_picker import _get_thumbnail, _thumb_resolution
        size = int(_thumb_resolution())
    except Exception:
        try:
            from editor.resource_picker import _get_thumbnail
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
        from editor.resource_picker import _draw_file_icon
        return _draw_file_icon(size)
    except Exception:
        pass
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def _entity_preview(entity, size: int) -> QPixmap:
    try:
        from editor.inspector.helpers import get_component_icon_pixmap
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
        self.setStyleSheet("HoverPreview { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 6px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._preview = QLabel(self)
        self._preview.setFixedSize(_PREVIEW_SQUARE, _PREVIEW_SQUARE)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet("background: #2a2a2a; border: 1px solid #444; border-radius: 4px; color: #666; font-size: 11px;")
        layout.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)
        self._title = QLabel(self)
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff; background: transparent; border: none;")
        layout.addWidget(self._title)
        self._info = QLabel(self)
        self._info.setWordWrap(True)
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._info.setStyleSheet("font-size: 11px; color: #cccccc; background: transparent; border: none;")
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
            from editor.resource_picker import _get_thumb_service
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


class _ProjectHover(QObject):
    def __init__(self, view, mode: str):
        super().__init__(view)
        self._view = view
        self._mode = mode
        self._path = None
        self._pos = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_hover_delay())
        self._timer.timeout.connect(self._show)
        try:
            view.setMouseTracking(True)
            view.viewport().setMouseTracking(True)
            view.installEventFilter(self)
            view.viewport().installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            t = event.type()
            if t == QEvent.Type.MouseMove:
                vp = None
                pos = None
                try:
                    if obj is self._view.viewport():
                        pos = event.pos()
                        vp = obj
                    elif obj is self._view:
                        try:
                            gp = QCursor.pos()
                            pos = self._view.viewport().mapFromGlobal(gp)
                            vp = self._view.viewport()
                        except Exception:
                            return False
                    else:
                        return False
                except Exception:
                    return False
                self._on_move(vp, pos)
            elif t in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.Close, QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel, QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.DragLeave, QEvent.Type.Drop):
                self._hide()
        except Exception:
            pass
        return False

    def _path_at(self, pos):
        try:
            if self._mode == "list":
                item = self._view.itemAt(pos)
                if item is None:
                    return None
                return item.data(Qt.ItemDataRole.UserRole)
            else:
                item = self._view.itemAt(pos)
                if item is None:
                    return None
                return item.data(0, Qt.ItemDataRole.UserRole)
        except Exception:
            return None

    def _on_move(self, vp, pos):
        try:
            path = self._path_at(pos)
            if not path:
                self._hide()
                return
            try:
                gp = vp.mapToGlobal(pos)
            except Exception:
                gp = QCursor.pos()
            if path != self._path:
                self._path = path
                self._pos = gp
                self._timer.stop()
                self._timer.setInterval(_hover_delay())
                self._timer.start()
            else:
                self._pos = gp
        except Exception:
            pass

    def _show(self):
        try:
            if not self._path:
                return
            try:
                still = self._view.underMouse()
            except Exception:
                still = True
            if not still:
                return
            popup = _get_popup()
            if popup is None:
                return
            pos = self._pos if self._pos is not None else QCursor.pos()
            popup.show_resource(self._path, pos)
        except Exception:
            pass

    def _hide(self):
        try:
            self._path = None
            self._pos = None
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


def attach_entity_hover(widget: QWidget, entity_fn):
    try:
        filt = _EntityHover(widget, entity_fn)
        widget._hover_preview_filter = filt
        return filt
    except Exception:
        return None


def attach_project_list_hover(view):
    try:
        filt = _ProjectHover(view, "list")
        try:
            existing = getattr(view, "_hover_preview_filters", None)
            if existing is None:
                view._hover_preview_filters = [filt]
            else:
                existing.append(filt)
        except Exception:
            view._hover_preview_filter = filt
        return filt
    except Exception:
        return None


def attach_project_tree_hover(view):
    try:
        filt = _ProjectHover(view, "tree")
        try:
            existing = getattr(view, "_hover_preview_filters", None)
            if existing is None:
                view._hover_preview_filters = [filt]
            else:
                existing.append(filt)
        except Exception:
            view._hover_preview_filter = filt
        return filt
    except Exception:
        return None
