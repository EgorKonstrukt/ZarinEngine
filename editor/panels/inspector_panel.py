from __future__ import annotations
from typing import Optional, Callable, TYPE_CHECKING
import json, os
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                             QScrollArea, QLabel, QLineEdit, QPushButton,
                             QCheckBox, QDoubleSpinBox, QSpinBox, QComboBox,
                             QGroupBox, QFrame, QSizePolicy, QMenu, QColorDialog,
                              QDialog, QTextEdit, QHeaderView, QPlainTextEdit,
                             QListWidget, QListWidgetItem, QApplication,
                             QSlider)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData
from PyQt6.QtGui import QAction, QColor, QFont, QPixmap, QIcon, QCursor, QDrag, QPalette

from core.math3d import Vec2, Vec3, Quat
from core.logger import Logger
from core.commands import SetComponentCommand, CompoundCommand, get_history
from core.curve import Curve
from editor.curve_editor import CurvePreview, CurveEditorDialog
from core.gui.widgets import AnchorPresetSelector
from core.config import get_project_config
from core.physics.collision_layers import MAX_LAYERS, DEFAULT_LAYER_NAMES
from core.components.animation.animator_controller import (
    AnimatorController, AnimatorState, AnimatorTransition,
    AnimatorCondition, AnimatorConditionMode,
)
if TYPE_CHECKING:
    from core.ecs import Entity, Component, Scene
    from core.engine import Engine

from core.editor_scale import scale, scale_xy
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

_FUSION_BG = "#1e1e1e"
_FUSION_BG_CARD = "#252525"
_FUSION_BG_HEADER = "#2b2b2b"
_FUSION_BG_HOVER = "#333333"
_FUSION_BG_INPUT = "#2a2a2a"
_FUSION_BORDER = "#3c3c3c"
_FUSION_BORDER_LIGHT = "#4a4a4a"
_FUSION_TEXT = "#cccccc"
_FUSION_TEXT_DIM = "#888888"
_FUSION_TEXT_BRIGHT = "#eeeeee"
_FUSION_TEXT_DISABLED = "#666666"
_FUSION_ACCENT_GREEN = "#4ec9b0"
_FUSION_ACCENT_RED = "#f44747"
_FUSION_ACCENT_ORANGE = "#ce9178"
_FUSION_ACCENT_YELLOW = "#dcdcaa"
_FUSION_CARD_RADIUS = "4px"
_FUSION_INPUT_RADIUS = "3px"

_FUSION_ACCENT_CACHE = None
def _accent() -> str:
    global _FUSION_ACCENT_CACHE
    if _FUSION_ACCENT_CACHE is None:
        app = QApplication.instance()
        if app:
            c = app.palette().color(QPalette.ColorRole.Highlight)
            _FUSION_ACCENT_CACHE = c.name()
        else:
            _FUSION_ACCENT_CACHE = "#5a9cf5"
    return _FUSION_ACCENT_CACHE

def _border_focus() -> str:
    return _accent()

def _checkbox_style() -> str:
    a = _accent()
    return (
        f"QCheckBox {{ color: {_FUSION_TEXT}; spacing: 4px; background: transparent; }}"
        f"QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 2px; background: {_FUSION_BG_INPUT}; }}"
        f"QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}"
        f"QCheckBox::indicator:hover {{ border-color: {a}; }}"
    )


_COMPONENT_MIME = "application/x-zpe-component"

class SourceViewerDialog(QDialog):
    """Read-only dialog showing source code with line numbers."""
    def __init__(self, file_path: str, line_number: int = 1, title: str = "Source", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Source - {title}")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        abs_path = file_path
        if not os.path.isabs(file_path):
            abs_path = os.path.join(_PROJECT_ROOT, file_path)
        path_label = QLabel(f"  {abs_path} (line {line_number})")
        path_label.setStyleSheet(f"color: {_FUSION_TEXT_DIM}; font-size: 10px; padding: 2px 0;")
        layout.addWidget(path_label)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_FUSION_BG};
                color: #d4d4d4;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid {_FUSION_BORDER};
            }}
        """)

        try:
            if os.path.exists(abs_path):
                with open(abs_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                self._text_edit.setPlainText("".join(lines))
                self._highlight_line(line_number)
        except Exception:
            self._text_edit.setPlainText(f"# Could not read file: {abs_path}")

        layout.addWidget(self._text_edit)

    def _highlight_line(self, line_num: int):
        """Highlight a specific line in the text edit."""
        try:
            document = self._text_edit.document()
            block = document.findBlockByLineNumber(line_num - 1)
            if not block.isValid():
                return
            cursor = self._text_edit.textCursor()
            cursor.setPosition(block.position())
            cursor.select(cursor.BlockUnderCursor)
            fmt = cursor.charFormat()
            bg_color = QColor(40, 60, 25, 180)
            fmt.setBackground(bg_color)
            fmt.setFontWeight(QFont.Weight.Bold)
            cursor.setCharFormat(fmt)
            self._text_edit.setTextCursor(cursor)
            self._text_edit.ensureCursorVisible()
        except Exception:
            pass


def _make_clickable_label(text: str, on_click: Callable[[], None]) -> QLabel:
    """Create a clickable label that shows source code when clicked."""
    lbl = QLabel(f"  {text}")
    lbl.setStyleSheet(f"""
        QLabel {{
            color: {_accent()};
            font-size: 9px;
            padding: 0px;
        }}
        QLabel:hover {{
            color: #8abbff;
        }}
    """)
    lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    lbl.setToolTip("Click to view source code")
    lbl.mousePressEvent = lambda e: on_click()  # type: ignore
    return lbl


def _get_component_icon_pixmap(cls, size: int = 16) -> QPixmap:
    icon_name = getattr(cls, '_icon', None)
    if icon_name:
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'core', 'components', 'icons')
        icon_path = os.path.join(icons_dir, icon_name)
        if os.path.exists(icon_path):
            return QPixmap(icon_path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    gizmo_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gizmo_icons')
    icon_path = os.path.join(gizmo_dir, f'{cls.__name__}.png')
    if os.path.exists(icon_path):
        return QPixmap(icon_path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    r, g, b = getattr(cls, '_gizmo_icon_color', (140, 60, 200))
    label = getattr(cls, '_gizmo_icon_label', '?')
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    from PyQt6.QtGui import QPainter, QColor as QC, QFont as QF, QBrush as QB, QPen
    from PyQt6.QtCore import QRect
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QB(QC(r, g, b)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, 3, 3)
    if label:
        p.setPen(QC(255, 255, 255))
        f = QF("Segoe UI", size // 2, QF.Weight.Bold)
        p.setFont(f)
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, label[0].upper())
    p.end()
    return pix


class _FocusSpinBox(QDoubleSpinBox):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

class _DragLabel(QLabel):
    def __init__(self, text, color, spinbox):
        super().__init__(text)
        self._spinbox = spinbox
        self._dragging = False
        self._start_x = 0
        self._start_val = 0
        self.setFixedWidth(scale(14))
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setStyleSheet(f"color: {color}; font-weight: bold;")
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_x = event.globalPosition().x()
            self._start_val = self._spinbox.value()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
    def mouseMoveEvent(self, event):
        if self._dragging:
            screen = self.screen()
            global_x = event.globalPosition().x()
            global_y = event.globalPosition().y()
            dx = global_x - self._start_x
            if screen:
                geo = screen.geometry()
                margin = 2
                if global_x >= geo.right() - margin:
                    landing_x = geo.left() + margin + 5
                    self._start_x -= global_x - landing_x
                    QCursor.setPos(int(landing_x), int(global_y))
                elif global_x <= geo.left() + margin:
                    landing_x = geo.right() - margin - 5
                    self._start_x -= global_x - landing_x
                    QCursor.setPos(int(landing_x), int(global_y))
            modifiers = QApplication.keyboardModifiers()
            ctrl_down = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                factor = 0.001
            elif ctrl_down:
                factor = 0.1
            else:
                factor = 0.01
            new_val = self._start_val + dx * factor
            if not ctrl_down:
                try:
                    from core.engine import Engine
                    gizmo = Engine.instance().viewport.gizmo
                    if gizmo.snap_enabled and gizmo.snap_translate > 0:
                        snap = gizmo.snap_translate
                        new_val = round(new_val / snap) * snap
                except Exception:
                    pass
            self._spinbox.setValue(new_val)
            event.accept()
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            event.accept()

_FUSION_SPINBOX_STYLE = f"""
    QDoubleSpinBox, QSpinBox {{
        background: {_FUSION_BG_INPUT};
        color: {_FUSION_TEXT_BRIGHT};
        border: 1px solid {_FUSION_BORDER};
        border-radius: {_FUSION_INPUT_RADIUS};
        padding: 1px 2px 1px 4px;
        font-size: 11px;
        min-height: 20px;
        selection-background-color: {_accent()};
    }}
    QDoubleSpinBox:hover, QSpinBox:hover {{
        border-color: {_FUSION_BORDER_LIGHT};
    }}
    QDoubleSpinBox:focus, QSpinBox:focus {{
        border-color: {_accent()};
    }}
    QDoubleSpinBox::up-button, QSpinBox::up-button {{
        border: none;
        background: transparent;
        width: 12px;
        subcontrol-origin: border;
        subcontrol-position: top right;
    }}
    QDoubleSpinBox::down-button, QSpinBox::down-button {{
        border: none;
        background: transparent;
        width: 12px;
        subcontrol-origin: border;
        subcontrol-position: bottom right;
    }}
    QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {{
        width: 6px;
        height: 6px;
        border: none;
    }}
    QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {{
        width: 6px;
        height: 6px;
        border: none;
    }}
"""

def _make_spinbox(val: float, lo: float = -1e9, hi: float = 1e9, step: float = 0.1, decimals: int = 4) -> QDoubleSpinBox:
    sb = _FocusSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    sb.setValue(val)
    sb.setMinimumWidth(60)
    sb.setStyleSheet(_FUSION_SPINBOX_STYLE)
    return sb


def _make_color_swatch(rgb: Optional[list[float]], callback) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(*scale_xy(28, 22))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    _update_swatch(btn, rgb or [0.0, 0.0, 0.0])
    def _pick():
        cur = rgb or [0.0, 0.0, 0.0]
        c = QColorDialog.getColor(QColor(int(cur[0]*255), int(cur[1]*255), int(cur[2]*255)))
        if c.isValid():
            new_rgb = [c.red()/255.0, c.green()/255.0, c.blue()/255.0]
            callback(new_rgb)
            _update_swatch(btn, new_rgb)
    btn.clicked.connect(_pick)
    return btn

def _update_swatch(btn: QPushButton, rgb: list[float]):
    if rgb:
        btn.setStyleSheet(f"background: rgba({int(rgb[0]*255)},{int(rgb[1]*255)},{int(rgb[2]*255)},255); border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: {_FUSION_INPUT_RADIUS};")
    else:
        btn.setStyleSheet(f"background: {_FUSION_BG_INPUT}; border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: {_FUSION_INPUT_RADIUS};")

class _DropLabelMixin:
    _HIGHLIGHT_STYLE = f"background: {_FUSION_BG_HOVER}; border: 1px solid {_accent()}; border-radius: {_FUSION_INPUT_RADIUS}; padding: 2px 6px;"
    _NORMAL_STYLE = f"color: {_FUSION_TEXT}; background: {_FUSION_BG_INPUT}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; padding: 2px 6px;"

    def _highlight(self, on=True):
        if on:
            if not hasattr(self, '_cached_style'):
                self._cached_style = self.styleSheet() or self._NORMAL_STYLE
            self.setStyleSheet(self._HIGHLIGHT_STYLE)
        else:
            style = getattr(self, '_cached_style', self._NORMAL_STYLE)
            self.setStyleSheet(style)


class _ResourceDropLabel(QLabel, _DropLabelMixin):
    def __init__(self, on_drop, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_drop = on_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            self._highlight(True)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._highlight(False)
        path = None
        if event.mimeData().hasUrls():
            path = event.mimeData().urls()[0].toLocalFile()
        elif event.mimeData().hasText():
            path = event.mimeData().text().strip()
        if path and self._on_drop:
            self._on_drop(path)
        event.acceptProposedAction()


class _EntityDropLabel(QLabel, _DropLabelMixin):
    def __init__(self, on_drop, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_drop = on_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-zpe-entity"):
            event.setDropAction(Qt.DropAction.CopyAction)
            self._highlight(True)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-zpe-entity"):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._highlight(False)
        if event.mimeData().hasFormat("application/x-zpe-entity"):
            data = bytes(event.mimeData().data("application/x-zpe-entity")).decode("utf-8")
            eid = data.split(",")[0]
            if eid and self._on_drop:
                self._on_drop(eid)
        event.acceptProposedAction()


class EntityPickerDialog(QDialog):
    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Entity")
        self.setMinimumSize(300, 400)
        self.resize(320, 450)
        self._scene = scene
        self._selected_id: Optional[str] = None
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {_FUSION_BG};
            }}
            QLineEdit {{
                background: {_FUSION_BG_INPUT};
                color: {_FUSION_TEXT_BRIGHT};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 3px 6px;
                font-size: 11px;
                selection-background-color: {_accent()};
            }}
            QLineEdit:focus {{ border-color: {_accent()}; }}
            QListWidget {{
                background: {_FUSION_BG_CARD};
                color: {_FUSION_TEXT};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                font-size: 11px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 3px 6px;
                border-radius: 2px;
            }}
            QListWidget::item:selected {{
                background: {_FUSION_BG_HOVER};
                color: {_FUSION_TEXT_BRIGHT};
            }}
            QListWidget::item:hover {{
                background: {_FUSION_BG_HOVER};
            }}
            QPushButton {{
                color: {_FUSION_TEXT};
                background: {_FUSION_BG_INPUT};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 4px 16px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {_FUSION_BG_HOVER};
                color: {_FUSION_TEXT_BRIGHT};
            }}
            QPushButton:disabled {{
                color: {_FUSION_TEXT_DIM};
                background: {_FUSION_BG};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search entities...")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setSpacing(1)
        self._list.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        self._select_btn = QPushButton("Select")
        self._select_btn.setEnabled(False)
        self._select_btn.clicked.connect(self._accept_selection)
        btn_row.addWidget(self._select_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._list.itemSelectionChanged.connect(self._on_selection_changed)

    def _populate(self, filter_text: str = ""):
        self._list.clear()
        filter_lower = filter_text.lower()
        if not self._scene:
            return
        for e in self._scene.get_all_entities():
            if filter_text and filter_lower not in e.name.lower():
                continue
            item = QListWidgetItem(f"  {e.name}")
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            icon_cls = None
            for c in e.get_all_components():
                if getattr(type(c), '_show_gizmo_icon', True) and type(c).__name__ != "Transform":
                    icon_cls = type(c)
                    break
            if icon_cls:
                pix = _get_component_icon_pixmap(icon_cls, 16)
                item.setIcon(QIcon(pix))
            self._list.addItem(item)

    def _filter(self, text: str):
        self._populate(text)

    def _on_selection_changed(self):
        items = self._list.selectedItems()
        self._select_btn.setEnabled(len(items) > 0)

    def _accept_selection(self):
        items = self._list.selectedItems()
        if items:
            self._selected_id = items[0].data(Qt.ItemDataRole.UserRole)
            self.accept()

    def selected_id(self) -> Optional[str]:
        return self._selected_id


def _update_resource_icon(icon_lbl: QLabel, path: str, size: int):
    if path and os.path.exists(path):
        ext = os.path.splitext(path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tga"):
            pix = QPixmap(path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(pix)
            return
    icon_lbl.clear()
    icon_lbl.setText("")


def _make_resource_picker(path: str, filter_str: str, callback: Callable[[str], None]) -> QWidget:
    from editor.resource_picker import pick_resource
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    name = os.path.basename(path) if path else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    icon_lbl.setStyleSheet(f"border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 2px; background: {_FUSION_BG};")
    _update_resource_icon(icon_lbl, path, 20)
    layout.addWidget(icon_lbl)

    def _on_resource_drop(p: str):
        _update_display(p)
    name_lbl = _ResourceDropLabel(_on_resource_drop, name if name else "None")
    name_lbl.setStyleSheet(
        f"color: {_FUSION_TEXT}; background: {_FUSION_BG_INPUT}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; padding: 2px 6px;"
    )
    name_lbl.setMinimumHeight(22)
    name_lbl.setToolTip(path if path else "No resource selected")
    layout.addWidget(name_lbl, 1)

    def _update_display(p: str):
        new_name = os.path.basename(p) if p else ""
        name_lbl.setText(new_name if new_name else "None")
        name_lbl.setToolTip(p if p else "No resource selected")
        _update_resource_icon(icon_lbl, p, 20)
        clear_btn.setVisible(bool(p))
        callback(p)

    btn = QPushButton("\u25CB")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip("Pick Resource")
    btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 11px;
        background: {_FUSION_BG_INPUT}; font-size: 14px; }}
        QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
    """)
    def _pick():
        p = pick_resource(w, "Select Resource", filter_str, path)
        if p:
            _update_display(p)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)

    clear_btn = QPushButton("x")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    clear_btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: none; border-radius: {_FUSION_INPUT_RADIUS}; font-size: 10px; background: transparent; }}
        QPushButton:hover {{ color: {_FUSION_ACCENT_RED}; background: #3a1a1a; }}
    """)
    def _clear():
        _update_display("")
    clear_btn.clicked.connect(_clear)
    clear_btn.setVisible(bool(path))
    layout.addWidget(clear_btn)
    return w


def _make_gameobject_picker(entity_id: str, scene, callback: Callable[[str], None]) -> QWidget:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    target_entity = scene.get_entity(entity_id) if scene and entity_id else None
    name = target_entity.name if target_entity else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    icon_lbl.setStyleSheet(f"border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 2px; background: {_FUSION_BG};")
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if target_entity:
        for c in target_entity.get_all_components():
            if getattr(type(c), '_show_gizmo_icon', True) and type(c).__name__ != "Transform":
                pix = _get_component_icon_pixmap(type(c), 18)
                icon_lbl.setPixmap(pix)
                break
    layout.addWidget(icon_lbl)

    def _on_entity_drop(eid: str):
        _update_entity_display(eid)
    name_lbl = _EntityDropLabel(_on_entity_drop, name if name else "None")
    name_lbl.setStyleSheet(
        f"color: {_FUSION_TEXT}; background: {_FUSION_BG_INPUT}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; padding: 2px 6px;"
    )
    name_lbl.setMinimumHeight(22)
    name_lbl.setToolTip(entity_id if entity_id else "No entity selected")
    layout.addWidget(name_lbl, 1)

    def _update_entity_display(eid: str):
        nonlocal target_entity
        target_entity = scene.get_entity(eid) if scene and eid else None
        new_name = target_entity.name if target_entity else ""
        name_lbl.setText(new_name if new_name else "None")
        name_lbl.setToolTip(eid if eid else "No entity selected")
        icon_lbl.clear()
        if target_entity:
            for c in target_entity.get_all_components():
                if getattr(type(c), '_show_gizmo_icon', True) and type(c).__name__ != "Transform":
                    pix = _get_component_icon_pixmap(type(c), 18)
                    icon_lbl.setPixmap(pix)
                    break
        clear_btn.setVisible(bool(eid))
        callback(eid)

    btn = QPushButton("\u25CB")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip("Pick Entity")
    btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 11px;
        background: {_FUSION_BG_INPUT}; font-size: 14px; }}
        QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
    """)
    def _pick():
        dlg = EntityPickerDialog(scene, w)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            picked_id = dlg.selected_id()
            if picked_id is not None:
                _update_entity_display(picked_id)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)

    clear_btn = QPushButton("x")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    clear_btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: none; border-radius: {_FUSION_INPUT_RADIUS}; font-size: 10px; background: transparent; }}
        QPushButton:hover {{ color: {_FUSION_ACCENT_RED}; background: #3a1a1a; }}
    """)
    def _clear():
        _update_entity_display("")
    clear_btn.clicked.connect(_clear)
    clear_btn.setVisible(bool(entity_id))
    layout.addWidget(clear_btn)
    return w


def _make_resource_type_picker(path: str, resource_type: str, callback: Callable[[str], None]) -> QWidget:
    from editor.resource_picker import pick_resource
    from core.components.scripting.script_component import RESOURCE_TYPE_FILTERS
    filter_str = RESOURCE_TYPE_FILTERS.get(resource_type, "All Files (*)")
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    name = os.path.basename(path) if path else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    icon_lbl.setStyleSheet(f"border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 2px; background: {_FUSION_BG};")
    _update_resource_icon(icon_lbl, path, 20)
    layout.addWidget(icon_lbl)

    def _on_resource_drop(p: str):
        _update_display(p)
    name_lbl = _ResourceDropLabel(_on_resource_drop, name if name else f"None ({resource_type})")
    name_lbl.setStyleSheet(
        f"color: {_FUSION_TEXT}; background: {_FUSION_BG_INPUT}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; padding: 2px 6px;"
    )
    name_lbl.setMinimumHeight(22)
    name_lbl.setToolTip(path if path else f"No {resource_type} selected")
    layout.addWidget(name_lbl, 1)

    def _update_display(p: str):
        new_name = os.path.basename(p) if p else ""
        name_lbl.setText(new_name if new_name else f"None ({resource_type})")
        name_lbl.setToolTip(p if p else f"No {resource_type} selected")
        _update_resource_icon(icon_lbl, p, 20)
        clear_btn.setVisible(bool(p))
        callback(p)

    btn = QPushButton("\u25CB")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip(f"Pick {resource_type}")
    btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 11px;
        background: {_FUSION_BG_INPUT}; font-size: 14px; }}
        QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
    """)
    def _pick():
        p = pick_resource(w, f"Select {resource_type}", filter_str, path)
        if p:
            _update_display(p)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)

    clear_btn = QPushButton("x")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    clear_btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: none; border-radius: {_FUSION_INPUT_RADIUS}; font-size: 10px; background: transparent; }}
        QPushButton:hover {{ color: {_FUSION_ACCENT_RED}; background: #3a1a1a; }}
    """)
    def _clear():
        _update_display("")
    clear_btn.clicked.connect(_clear)
    clear_btn.setVisible(bool(path))
    layout.addWidget(clear_btn)
    return w


def _make_asset_picker(path: str, asset_type: str, callback: Callable[[str], None]) -> QWidget:
    from editor.resource_picker import pick_resource
    from core.components.scripting.script_component import RESOURCE_TYPE_FILTERS
    filter_str = RESOURCE_TYPE_FILTERS.get(asset_type, "All Files (*)")
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    name = os.path.basename(path) if path else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    icon_lbl.setStyleSheet(f"border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 2px; background: {_FUSION_BG};")
    _update_resource_icon(icon_lbl, path, 20)
    layout.addWidget(icon_lbl)

    def _on_asset_drop(p: str):
        _update_display(p)
    name_lbl = _ResourceDropLabel(_on_asset_drop, name if name else f"None ({asset_type})")
    name_lbl.setStyleSheet(
        f"color: {_FUSION_TEXT}; background: {_FUSION_BG_INPUT}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; padding: 2px 6px;"
    )
    name_lbl.setMinimumHeight(22)
    name_lbl.setToolTip(path if path else f"No {asset_type} selected")
    layout.addWidget(name_lbl, 1)

    def _update_display(p: str):
        new_name = os.path.basename(p) if p else ""
        name_lbl.setText(new_name if new_name else f"None ({asset_type})")
        name_lbl.setToolTip(p if p else f"No {asset_type} selected")
        _update_resource_icon(icon_lbl, p, 20)
        clear_btn.setVisible(bool(p))
        callback(p)

    btn = QPushButton("\u25CB")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip(f"Pick {asset_type}")
    btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 11px;
        background: {_FUSION_BG_INPUT}; font-size: 14px; }}
        QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
    """)
    def _pick():
        p = pick_resource(w, f"Select {asset_type}", filter_str, path)
        if p:
            _update_display(p)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)

    create_btn = QPushButton("+")
    create_btn.setFixedSize(*scale_xy(22, 22))
    create_btn.setToolTip(f"Create new {asset_type}")
    create_btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: 11px;
        background: {_FUSION_BG_INPUT}; font-size: 14px; }}
        QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: #4ec9b0; }}
    """)
    def _create():
        _create_asset_dialog(w, asset_type, _update_display)
    create_btn.clicked.connect(_create)
    layout.addWidget(create_btn)

    clear_btn = QPushButton("x")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    clear_btn.setStyleSheet(f"""
        QPushButton {{ color: {_FUSION_TEXT_DIM}; border: none; border-radius: {_FUSION_INPUT_RADIUS}; font-size: 10px; background: transparent; }}
        QPushButton:hover {{ color: {_FUSION_ACCENT_RED}; background: #3a1a1a; }}
    """)
    def _clear():
        _update_display("")
    clear_btn.clicked.connect(_clear)
    clear_btn.setVisible(bool(path))
    layout.addWidget(clear_btn)
    return w


def _create_asset_dialog(parent, asset_type: str, callback: Callable[[str], None]):
    from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from core.components.scripting.script_component import RESOURCE_TYPE_FILTERS
    project_root = getattr(parent, '_project_root', os.getcwd())
    name, ok = QInputDialog.getText(parent, f"New {asset_type}", f"Asset name:")
    if not ok or not name.strip():
        return
    fname = name.strip()
    exts = {"animclip": ".animclip", "animcontroller": ".animcontroller"}
    ext = exts.get(asset_type, ".asset")
    if not fname.endswith(ext):
        fname += ext
    default_path = os.path.join(project_root, "Assets", fname)
    path, _ = QFileDialog.getSaveFileName(parent, f"Save {asset_type}", default_path,
                                          RESOURCE_TYPE_FILTERS.get(asset_type, "All Files (*)"))
    if not path:
        return
    from core.components.animation.animation_clip import AnimationClip
    if asset_type == "animclip":
        clip = AnimationClip(name.strip())
        clip.save(path)
    elif asset_type == "animcontroller":
        from core.components.animation.animator_controller import AnimatorController
        ctrl = AnimatorController(name.strip())
        ctrl.save(path)
    callback(path)


_XYZ_COLORS = {"X": "#f44747", "Y": "#4ec9b0", "Z": "#5a9cf5"}


def _make_vec2_row(label: str, vec: Vec2, callback) -> tuple[QWidget, list[QDoubleSpinBox]]:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    lbl = QLabel(label)
    lbl.setFixedWidth(scale(80))
    layout.addWidget(lbl)
    spinboxes = []
    for val, comp_label in [(vec.x, "X"), (vec.y, "Y")]:
        lbl_c = QLabel(comp_label)
        lbl_c.setFixedWidth(scale(14))
        color = _XYZ_COLORS.get(comp_label, "#aaa")
        lbl_c.setStyleSheet(f"color: {color}; font-weight: bold;")
        sb = _make_spinbox(val)
        sb.valueChanged.connect(callback)
        layout.addWidget(lbl_c)
        layout.addWidget(sb)
        spinboxes.append(sb)
    return w, spinboxes


def _make_vec3_row(label: str, vec: Vec3, callback, reset_to: Optional[list] = None) -> tuple[QWidget, list[QDoubleSpinBox]]:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    lbl = QLabel(label)
    lbl.setFixedWidth(scale(80))
    layout.addWidget(lbl)
    spinboxes = []
    for val, comp_label in [(vec.x, "X"), (vec.y, "Y"), (vec.z, "Z")]:
        sb = _make_spinbox(val)
        sb.valueChanged.connect(callback)
        lbl_c = _DragLabel(comp_label, _XYZ_COLORS.get(comp_label, "#aaa"), sb)
        layout.addWidget(lbl_c)
        layout.addWidget(sb)
        spinboxes.append(sb)
    if reset_to is not None:
        btn = QPushButton()
        btn.setText("\u21ba")
        btn.setFixedSize(*scale_xy(18, 18))
        btn.setToolTip(f"Reset {label}")
        btn.setStyleSheet(f"""
            QPushButton {{ font-size: 12px; color: {_FUSION_TEXT_DIM}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; background: transparent; }}
            QPushButton:hover {{ color: {_accent()}; border-color: {_accent()}; background: {_FUSION_BG_HOVER}; }}
        """)
        def _reset():
            for sb, v in zip(spinboxes, reset_to):
                sb.setValue(v)
        btn.clicked.connect(_reset)
        layout.addWidget(btn)
    return w, spinboxes


def _get_component_source_path(comp_cls: type) -> str:
    import inspect
    try:
        file_path = inspect.getfile(comp_cls)
        rel = os.path.relpath(file_path, _PROJECT_ROOT)
        return rel.replace(os.sep, "/")
    except Exception:
        return ""


def _get_property_line_number(comp_cls: type, prop_name: str) -> int:
    import inspect
    try:
        lines, start_line = inspect.getsourcelines(comp_cls)
        for i, line in enumerate(lines):
            if prop_name in line and ("self." + prop_name) in line:
                return start_line + i
        for i, line in enumerate(lines):
            if f"self.{prop_name}" in line or f": {prop_name}" in line:
                return start_line + i
    except Exception:
        pass
    return 1


def _collapse_value(v):
    if hasattr(v, 'to_list'):
        return v.to_list()
    if hasattr(v, '__iter__') and not isinstance(v, (str, bytes, dict)):
        return list(v)
    return v


class ComponentWidget(QWidget):
    remove_requested = pyqtSignal(str, str)
    move_up_requested = pyqtSignal(str)
    move_down_requested = pyqtSignal(str)
    reorder_requested = pyqtSignal(str, str, str)

    def __init__(self, component, entity=None, selected_entities=None, parent=None, component_key: str = ""):
        super().__init__(parent)
        self._component = component
        self._entity = entity
        self._selected_entities = list(selected_entities if selected_entities else [])
        self._component_key = component_key
        self._updating = False
        self._collapsed = False

        self.setStyleSheet(f"""
            ComponentWidget {{
                background: {_FUSION_BG_CARD};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_CARD_RADIUS};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._header_bg_style = f"""
            #compHeader {{
                background-color: {_FUSION_BG_HEADER};
                border-top-left-radius: {_FUSION_CARD_RADIUS};
                border-top-right-radius: {_FUSION_CARD_RADIUS};
                border-bottom: 1px solid {_FUSION_BORDER};
            }}
        """
        self._header_widget = QWidget()
        self._header_widget.setObjectName("compHeader")
        self._header_widget.setStyleSheet(self._header_bg_style)
        header_layout = QHBoxLayout(self._header_widget)
        header_layout.setContentsMargins(6, 3, 6, 3)
        header_layout.setSpacing(4)

        self._collapse_btn = QPushButton("\u25bc")
        self._collapse_btn.setFixedSize(*scale_xy(14, 14))
        self._collapse_btn.setFlat(True)
        self._collapse_btn.setStyleSheet(f"""
            QPushButton {{ color: {_FUSION_TEXT_DIM}; font-size: 8px; border: none; background: transparent; }}
            QPushButton:hover {{ color: {_FUSION_TEXT_BRIGHT}; }}
        """)
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self._collapse_btn)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(*scale_xy(16, 16))
        comp_cls = type(component)
        pix = _get_component_icon_pixmap(comp_cls, 16)
        self._icon_label.setPixmap(pix)
        self._icon_label.setToolTip(comp_cls.__name__)
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self._icon_label)

        self._name_label = QLabel(type(component).__name__)
        self._name_label.setStyleSheet(f"color: {_FUSION_TEXT_BRIGHT}; font-size: 11px; font-weight: 600; background: transparent;")
        self._name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self._name_label, 1)

        self._drag_start_pos = None

        self._enabled_cb = QCheckBox()
        self._enabled_cb.setChecked(component.enabled)
        self._enabled_cb.toggled.connect(self._on_enabled_toggled)
        self._enabled_cb.setStyleSheet(f"background: transparent;")
        header_layout.addWidget(self._enabled_cb)

        self._move_up_btn = QPushButton("^")
        self._move_up_btn.setFixedSize(*scale_xy(16, 16))
        self._move_up_btn.setFlat(True)
        self._move_up_btn.setStyleSheet(f"""
            QPushButton {{ color: {_FUSION_TEXT_DIM}; font-size: 9px; font-weight: bold; border: none; background: transparent; }}
            QPushButton:hover {{ color: {_FUSION_TEXT_BRIGHT}; background: {_FUSION_BG_HOVER}; border-radius: 2px; }}
            QPushButton:disabled {{ color: #444; }}
        """)
        self._move_up_btn.clicked.connect(lambda: self.move_up_requested.emit(self._component_key))
        header_layout.addWidget(self._move_up_btn)

        self._move_down_btn = QPushButton("v")
        self._move_down_btn.setFixedSize(*scale_xy(16, 16))
        self._move_down_btn.setFlat(True)
        self._move_down_btn.setStyleSheet(f"""
            QPushButton {{ color: {_FUSION_TEXT_DIM}; font-size: 9px; font-weight: bold; border: none; background: transparent; }}
            QPushButton:hover {{ color: {_FUSION_TEXT_BRIGHT}; background: {_FUSION_BG_HOVER}; border-radius: 2px; }}
            QPushButton:disabled {{ color: #444; }}
        """)
        self._move_down_btn.clicked.connect(lambda: self.move_down_requested.emit(self._component_key))
        header_layout.addWidget(self._move_down_btn)

        self._header_widget.installEventFilter(self)
        main_layout.addWidget(self._header_widget)

        self._content_widget = QWidget()
        self._content_widget.setObjectName("compBody")
        self._content_widget.setStyleSheet(f"""
            #compBody {{
                background: {_FUSION_BG_CARD};
                border-bottom-left-radius: {_FUSION_CARD_RADIUS};
                border-bottom-right-radius: {_FUSION_CARD_RADIUS};
            }}
        """)
        self._layout = QVBoxLayout(self._content_widget)
        self._layout.setContentsMargins(8, 6, 8, 6)
        self._layout.setSpacing(3)
        main_layout.addWidget(self._content_widget)

        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._build_fields()
        self._update_appearance()

    def eventFilter(self, obj, event):
        if obj is self._header_widget:
            if event.type() == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_start_pos = event.position().toPoint()
                self._drag_started = False
            elif event.type() == event.Type.MouseMove and (event.buttons() & Qt.MouseButton.LeftButton):
                if self._drag_start_pos is not None and not self._drag_started:
                    delta = event.position().toPoint() - self._drag_start_pos
                    if delta.manhattanLength() >= QApplication.startDragDistance():
                        self._start_drag()
                return True
            elif event.type() == event.Type.MouseButtonRelease:
                self._drag_start_pos = None
                self._drag_started = False
        return super().eventFilter(obj, event)

    def _start_drag(self):
        self._drag_started = True
        comp_data = self._component.serialize()
        data = {
            "entity_id": self._entity.id if self._entity else "",
            "component_key": self._component_key,
            "component_type": type(self._component).__name__,
            "component_data": comp_data,
        }
        mime = QMimeData()
        mime.setData(_COMPONENT_MIME, json.dumps(data).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = self._header_widget.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(self._header_widget.mapFromGlobal(QCursor.pos()))
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        self._drag_start_pos = None
        self._drag_started = False

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._collapse_btn.setText("\u25b6" if self._collapsed else "\u25bc")
        self._content_widget.setVisible(not self._collapsed)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            raw = bytes(event.mimeData().data(_COMPONENT_MIME)).decode("utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                event.ignore()
                return
            dragged_key = data.get("component_key", "")
            target_key = self._component_key
            source_eid = data.get("entity_id", "")
            if dragged_key and target_key and source_eid == (self._entity.id if self._entity else ""):
                self.reorder_requested.emit(source_eid, dragged_key, target_key)
                event.acceptProposedAction()
                return
            event.ignore()
        else:
            super().dropEvent(event)

    def _undo_setter(self, prop_name):
        c = self._component
        def _set_and_sync(v):
            get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, getattr(c, prop_name), v))
            try:
                from core.engine import Engine
                collab = Engine.instance().collab_manager
                if collab and collab.connected and self._entity:
                    val = _collapse_value(v)
                    print(f"COLLAB SYNC: entity={self._entity.id}, key={self._component_key}, prop={prop_name}, val={val}")
                    collab.send_component_update(self._entity.id, self._component_key, prop_name, val)
                else:
                    print(f"COLLAB SKIP: collab={collab}, connected={collab.connected if collab else 'N/A'}, entity={self._entity}")
            except Exception as e:
                import traceback
                traceback.print_exc()
        return _set_and_sync

    def _undo_setter_all(self, comp_type, prop_name):
        entities = [e for e in self._selected_entities if e.has_component(comp_type)]
        if len(entities) <= 1:
            return self._undo_setter(prop_name)
        old_values = []
        for ent in entities:
            comp = ent.get_component(comp_type)
            if comp and hasattr(comp, prop_name):
                old_values.append(getattr(comp, prop_name))
            else:
                old_values.append(None)
        def _set_all(v):
            cmds = []
            for i, ent in enumerate(entities):
                comp = ent.get_component(comp_type)
                if comp and hasattr(comp, prop_name):
                    old_v = old_values[i]
                    if old_v is not None:
                        cmds.append(SetComponentCommand(ent, comp_type, prop_name, old_v, v))
            if cmds:
                get_history().execute(CompoundCommand(cmds, f"Set {prop_name} on {len(entities)} entities"))
        return _set_all

    def _undo_setter_int(self, prop_name):
        return self._undo_setter(prop_name)

    def _on_layer_mask_toggle(self, prop_name, bit, btn, layer_names, menu, all_act, nothing_act):
        mask = int(getattr(self._component, prop_name))
        if mask & (1 << bit):
            mask &= ~(1 << bit)
        else:
            mask |= 1 << bit
        setattr(self._component, prop_name, mask)
        self._update_layer_mask_text(btn, mask, layer_names)
        all_act.setChecked(mask == 0xFFFF)
        nothing_act.setChecked(mask == 0)

    def _on_layer_mask_set_all(self, prop_name, state, btn, layer_names, menu):
        mask = 0xFFFF if state else 0
        setattr(self._component, prop_name, mask)
        self._update_layer_mask_text(btn, mask, layer_names)
        for act in menu.actions():
            if act.isCheckable() and act.text() not in ("Everything", "Nothing"):
                act.setChecked(state)
            elif act.text() == "Everything":
                act.setChecked(state)
            elif act.text() == "Nothing":
                act.setChecked(not state)

    def _update_layer_mask_text(self, btn, mask, layer_names):
        if mask == 0:
            btn.setText("Nothing")
        elif mask == 0xFFFF:
            btn.setText("Everything")
        else:
            selected = []
            for i in range(MAX_LAYERS):
                if mask & (1 << i):
                    name = layer_names[i] if i < len(layer_names) else f"Layer{i}"
                    selected.append(name)
            if len(selected) <= 3:
                btn.setText(", ".join(selected))
            else:
                btn.setText(f"{', '.join(selected[:3])}... (+{len(selected)-3})")

    def _update_appearance(self):
        enabled = self._component.enabled
        disabled_border = f"1px solid {_FUSION_BORDER};"
        header_color = f"background-color: {_FUSION_BG_HEADER if enabled else '#222222'};"
        self._header_widget.setStyleSheet(
            f"#compHeader {{ {header_color} border-top-left-radius: {_FUSION_CARD_RADIUS}; border-top-right-radius: {_FUSION_CARD_RADIUS}; border-bottom: {disabled_border} }}"
        )
        name_color = _FUSION_TEXT_BRIGHT if enabled else _FUSION_TEXT_DISABLED
        self._name_label.setStyleSheet(f"color: {name_color}; font-size: 11px; font-weight: 600; background: transparent;")
        self._content_widget.setEnabled(enabled)

    def _on_enabled_toggled(self, checked: bool):
        old = not checked
        self._component.enabled = checked
        if checked: self._component.on_enable()
        else: self._component.on_disable()
        if self._entity:
            get_history().execute(SetComponentCommand(self._entity, type(self._component), "enabled", old, checked))
        self._update_appearance()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {_FUSION_BG_CARD};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 4px;
            }}
            QMenu::item {{
                color: {_FUSION_TEXT};
                padding: 4px 20px;
                border-radius: 2px;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background: {_FUSION_BG_HOVER};
                color: {_FUSION_TEXT_BRIGHT};
            }}
            QMenu::separator {{
                height: 1px;
                background: {_FUSION_BORDER};
                margin: 4px 8px;
            }}
        """)
        copy_comp = QAction("Copy Component", self)
        copy_comp.triggered.connect(self._copy_component)
        menu.addAction(copy_comp)
        copy_vals = QAction("Copy Values", self)
        copy_vals.triggered.connect(self._copy_values)
        menu.addAction(copy_vals)
        paste_vals = QAction("Paste Component Values", self)
        paste_vals.setEnabled(InspectorPanel._clipboard is not None)
        paste_vals.triggered.connect(self._paste_values)
        menu.addAction(paste_vals)
        menu.addSeparator()
        rem = QAction("Remove Component", self)
        rem.triggered.connect(lambda: self.remove_requested.emit(type(self._component).__name__, self._component_key))
        menu.addAction(rem)
        menu.exec(self.mapToGlobal(pos))

    def _copy_component(self):
        InspectorPanel._clipboard = {
            "mode": "component",
            "type": type(self._component).__name__,
            "data": self._component.serialize(),
        }

    def _copy_values(self):
        data = self._component.serialize()
        InspectorPanel._clipboard = {
            "mode": "values",
            "type": type(self._component).__name__,
            "data": data,
        }

    def _paste_values(self):
        if InspectorPanel._clipboard is None:
            return
        from core.ecs import ComponentRegistry
        cb = InspectorPanel._clipboard
        target_type_name = cb["type"]
        target_cls = ComponentRegistry.get(target_type_name)
        if not target_cls:
            return
        source_data = cb["data"]
        current_type_name = type(self._component).__name__
        if target_type_name != current_type_name:
            return
        cmds = []
        entities = [e for e in self._selected_entities if e.has_component(target_cls)]
        if not entities:
            entities = [self._entity] if self._entity else []
            if not entities:
                return
        for ent in entities:
            comp = ent.get_component(target_cls)
            if comp:
                for key, val in source_data.items():
                    if key in ("type", "_key", "enabled"):
                        continue
                    old_val = getattr(comp, key, None)
                    if old_val is not None:
                        setattr(comp, key, val)
                        cmds.append(SetComponentCommand(ent, target_cls, key, old_val, val))
        if cmds:
            get_history().execute(CompoundCommand(cmds, f"Paste {target_type_name}"))

    def _build_fields(self):
        comp = self._component
        ctype = type(comp).__name__
        if ctype == "Transform":
            self._build_transform()
        elif ctype == "ScriptComponent":
            self._build_script_fields(comp)
        else:
            self._toggle_checkboxes: dict[str, QCheckBox] = {}
            self._toggle_rows: dict[str, list[QWidget]] = {}
            fields = getattr(type(comp), "_inspector_fields", lambda: [])()
            for field in fields:
                self._build_field_from_meta(field)
            for toggle_name, cb in self._toggle_checkboxes.items():
                rows = self._toggle_rows.get(toggle_name, [])
                if rows:
                    cb.toggled.connect(lambda v, rs=rows: self._on_toggle_changed(v, rs))
                    for r in rows:
                        r.setVisible(cb.isChecked())

    def _on_toggle_changed(self, v: bool, rows: list[QWidget]):
        for r in rows:
            r.setVisible(v)

    def _add_field(self, label: str, widget: QWidget, prop_name: str = "", toggle_field: str = ""):
        row = QWidget()
        row.setStyleSheet(f"background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        lbl = QLabel(label)
        lbl.setFixedWidth(scale(100))
        lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
        rl.addWidget(lbl)
        rl.addWidget(widget, 1)
        if prop_name:
            comp_type = type(self._component).__name__
            src_path = _get_component_source_path(type(self._component))
            line_num = _get_property_line_number(type(self._component), prop_name)
            source_lbl = _make_clickable_label("src", lambda sp=src_path, ln=line_num: self._show_source(sp, ln, comp_type, prop_name))
            rl.addWidget(source_lbl)
        self._layout.addWidget(row)
        if toggle_field:
            self._toggle_rows.setdefault(toggle_field, []).append(row)

    def _build_field_from_meta(self, field):
        c = self._component
        prop_name = field.name

        if field.field_type.value == "header":
            header = QLabel(f"  {field.label}")
            header.setStyleSheet(f"""
                QLabel {{
                    color: {_accent()};
                    font-weight: 600;
                    font-size: 11px;
                    padding: 5px 0 3px 0;
                    border-bottom: 1px solid {_FUSION_BORDER};
                }}
            """)
            self._layout.addWidget(header)
            return

        value = getattr(c, prop_name)

        if field.field_type.value == "float":
            sb = _make_spinbox(value, field.min_val, field.max_val, field.step, field.decimals)
            comp_cls = type(c)
            sb.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
            self._add_field(field.label, sb, prop_name, field.toggle_field)

        elif field.field_type.value == "int":
            if field.readonly:
                lbl = QLabel(str(value))
                lbl.setStyleSheet(f"color: {_FUSION_TEXT_DIM}; padding: 4px 8px; font-size: 11px;")
                self._add_field(field.label, lbl)
            else:
                sb = QSpinBox()
                min_i = max(-2147483648, min(2147483647, int(field.min_val)))
                max_i = max(-2147483648, min(2147483647, int(field.max_val)))
                sb.setRange(min_i, max_i)
                sb.setValue(max(min_i, min(max_i, int(value))))
                sb.setMinimumWidth(60)
                sb.setStyleSheet(_FUSION_SPINBOX_STYLE)
                comp_cls = type(c)
                sb.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
                self._add_field(field.label, sb, prop_name, field.toggle_field)

        elif field.field_type.value == "slider":
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            scale = 1000.0
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(int(field.min_val * scale), int(field.max_val * scale))
            slider.setValue(int(value * scale))
            slider.setSingleStep(max(1, int(field.step * scale)))
            slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{
                    border: none;
                    height: 4px;
                    background: {_FUSION_BORDER};
                    border-radius: 2px;
                }}
                QSlider::handle:horizontal {{
                    background: {_accent()};
                    border: none;
                    width: 10px;
                    height: 10px;
                    margin: -3px 0;
                    border-radius: 5px;
                }}
                QSlider::handle:horizontal:hover {{
                    background: #7bb5ff;
                }}
                QSlider::sub-page:horizontal {{
                    background: {_accent()};
                    border-radius: 2px;
                }}
            """)
            sb = _make_spinbox(value, field.min_val, field.max_val, field.step, field.decimals)
            comp_cls = type(c)
            sb.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
            _updating = [False]
            def _on_slider(v):
                if _updating[0]: return
                _updating[0] = True
                sb.setValue(v / scale)
                _updating[0] = False
            def _on_spinbox(v):
                if _updating[0]: return
                _updating[0] = True
                slider.setValue(int(v * scale))
                _updating[0] = False
            slider.valueChanged.connect(_on_slider)
            sb.valueChanged.connect(_on_spinbox)
            rl.addWidget(slider, 1)
            rl.addWidget(sb)
            self._add_field(field.label, row, prop_name, field.toggle_field)

        elif field.field_type.value == "int_slider":
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            min_i = max(-2147483648, min(2147483647, int(field.min_val)))
            max_i = max(-2147483648, min(2147483647, int(field.max_val)))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(min_i, max_i)
            slider.setValue(max(min_i, min(max_i, int(value))))
            slider.setSingleStep(max(1, int(field.step)))
            slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{
                    border: none;
                    height: 4px;
                    background: {_FUSION_BORDER};
                    border-radius: 2px;
                }}
                QSlider::handle:horizontal {{
                    background: {_accent()};
                    border: none;
                    width: 10px;
                    height: 10px;
                    margin: -3px 0;
                    border-radius: 5px;
                }}
                QSlider::handle:horizontal:hover {{
                    background: #7bb5ff;
                }}
                QSlider::sub-page:horizontal {{
                    background: {_accent()};
                    border-radius: 2px;
                }}
            """)
            sb = QSpinBox()
            sb.setRange(min_i, max_i)
            sb.setValue(max(min_i, min(max_i, int(value))))
            sb.setMinimumWidth(50)
            sb.setStyleSheet(_FUSION_SPINBOX_STYLE)
            comp_cls = type(c)
            sb.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
            _updating_int = [False]
            def _on_slider_int(v):
                if _updating_int[0]: return
                _updating_int[0] = True
                sb.setValue(v)
                _updating_int[0] = False
            def _on_spinbox_int(v):
                if _updating_int[0]: return
                _updating_int[0] = True
                slider.setValue(v)
                _updating_int[0] = False
            slider.valueChanged.connect(_on_slider_int)
            sb.valueChanged.connect(_on_spinbox_int)
            rl.addWidget(slider, 1)
            rl.addWidget(sb)
            self._add_field(field.label, row, prop_name, field.toggle_field)

        elif field.field_type.value == "bool":
            cb = QCheckBox()
            cb.setChecked(value)
            cb.setStyleSheet(_checkbox_style())
            comp_cls = type(c)
            cb.toggled.connect(self._undo_setter_all(comp_cls, prop_name))
            self._add_field(field.label, cb, prop_name, field.toggle_field)
            self._toggle_checkboxes[prop_name] = cb

        elif field.field_type.value == "button":
            btn = QPushButton(field.label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {_FUSION_TEXT};
                    background: {_FUSION_BG_INPUT};
                    border: 1px solid {_FUSION_BORDER_LIGHT};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 3px 12px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
            """)
            def _on_click(*_):
                method = getattr(c, prop_name, None)
                if callable(method):
                    method()
            btn.clicked.connect(_on_click)
            self._add_field(field.label, btn, prop_name, field.toggle_field)

        elif field.field_type.value == "enum":
            cb = QComboBox()
            cb.setStyleSheet(f"""
                QComboBox {{
                    background: {_FUSION_BG_INPUT};
                    color: {_FUSION_TEXT_BRIGHT};
                    border: 1px solid {_FUSION_BORDER};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    min-height: 20px;
                }}
                QComboBox:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                QComboBox::drop-down {{
                    border: none;
                    width: 16px;
                }}
                QComboBox::down-arrow {{
                    width: 8px;
                    height: 8px;
                }}
                QComboBox QAbstractItemView {{
                    background: {_FUSION_BG_CARD};
                    color: {_FUSION_TEXT};
                    border: 1px solid {_FUSION_BORDER};
                    selection-background-color: {_FUSION_BG_HOVER};
                    selection-color: {_FUSION_TEXT_BRIGHT};
                }}
            """)
            enum_class = field.enum_class
            items = [e.value for e in enum_class]
            cb.addItems(items)
            current_val = value.value if hasattr(value, 'value') else str(value)
            idx = items.index(current_val) if current_val in items else 0
            cb.setCurrentIndex(idx)
            comp_cls = type(c)
            def _on_enum_change(t):
                entities = [e for e in self._selected_entities if e.has_component(comp_cls)]
                old_vals = []
                for ent in entities:
                    comp = ent.get_component(comp_cls)
                    if comp: old_vals.append(getattr(comp, prop_name))
                    else: old_vals.append(None)
                cmds = []
                for i, ent in enumerate(entities):
                    comp = ent.get_component(comp_cls)
                    if comp and old_vals[i] is not None:
                        new_val = enum_class(t)
                        cmds.append(SetComponentCommand(ent, comp_cls, prop_name, old_vals[i], new_val))
                if cmds: get_history().execute(CompoundCommand(cmds, f"Set {prop_name} on {len(entities)} entities"))
            cb.currentTextChanged.connect(_on_enum_change)
            self._add_field(field.label, cb, prop_name, field.toggle_field)

        elif field.field_type.value == "string":
            le = QLineEdit(str(value))
            le.setMinimumWidth(60)
            le.setStyleSheet(f"""
                QLineEdit {{
                    background: {_FUSION_BG_INPUT};
                    color: {_FUSION_TEXT_BRIGHT};
                    border: 1px solid {_FUSION_BORDER};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QLineEdit:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                QLineEdit:focus {{ border-color: {_accent()}; }}
            """)
            le.textChanged.connect(self._undo_setter(prop_name))
            self._add_field(field.label, le, prop_name, field.toggle_field)

        elif field.field_type.value == "textarea":
            te = QPlainTextEdit(str(value))
            te.setMinimumHeight(60)
            te.setStyleSheet(f"""
                QPlainTextEdit {{
                    background: {_FUSION_BG_INPUT};
                    color: {_FUSION_TEXT_BRIGHT};
                    border: 1px solid {_FUSION_BORDER};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QPlainTextEdit:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                QPlainTextEdit:focus {{ border-color: {_accent()}; }}
            """)
            _setter = self._undo_setter(prop_name)
            te.textChanged.connect(lambda: _setter(te.toPlainText()))
            self._add_field(field.label, te, prop_name, field.toggle_field)

        elif field.field_type.value == "resource_path":
            picker = _make_resource_picker(value, field.file_filter or "All Files (*.*)", lambda p: get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, getattr(c, prop_name), p)))
            self._add_field(field.label, picker, prop_name, field.toggle_field)

        elif field.field_type.value == "gameobject":
            scene = self._entity._scene if self._entity else None
            picker = _make_gameobject_picker(value or "", scene, lambda eid: get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, getattr(c, prop_name), eid or "")))
            self._add_field(field.label, picker, prop_name, field.toggle_field)

        elif field.field_type.value == "resource":
            picker = _make_resource_type_picker(value or "", field.resource_type or "mesh", lambda p: get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, getattr(c, prop_name), p)))
            self._add_field(field.label, picker, prop_name, field.toggle_field)

        elif field.field_type.value == "asset":
            picker = _make_asset_picker(value or "", field.resource_type or "animclip", lambda p: get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, getattr(c, prop_name), p)))
            self._add_field(field.label, picker, prop_name, field.toggle_field)

        elif field.field_type.value == "color":
            old_val = list(value) if value else [0.0, 0.0, 0.0]
            swatch = _make_color_swatch(value, lambda new_val: get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, old_val, list(new_val))))
            swatch.setFixedSize(*scale_xy(28, 22))
            self._add_field(field.label, swatch, prop_name, field.toggle_field)

        elif field.field_type.value == "curve":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            preview = CurvePreview()
            curve = Curve.from_list(value if value else [[0, 1], [1, 1]])
            preview.set_curve(curve)
            preview.setToolTip("Click to edit curve")
            rl.addWidget(preview, 1)
            edit_btn = QPushButton("Edit")
            rl.addWidget(edit_btn)
            def _open_editor(*, _prop_name=prop_name, _field=field):
                try:
                    current_data = getattr(c, _prop_name) or [[0, 1], [1, 1]]
                    edit_curve = Curve.from_list(current_data)
                    dlg = CurveEditorDialog(edit_curve, f"Edit {field.label}", self)
                    if dlg.exec():
                        new_curve = dlg.get_curve()
                        new_data = new_curve.to_list()
                        old_data = getattr(c, _prop_name)
                        setattr(c, _prop_name, new_data)
                        if self._entity:
                            get_history().execute(SetComponentCommand(self._entity, type(c), _prop_name, old_data, new_data))
                        preview.set_curve(new_curve)
                except Exception as e:
                    Logger.error(f"Curve editor error: {e}", e)
            edit_btn.clicked.connect(_open_editor)
            preview.clicked.connect(_open_editor)
            self._add_field(field.label, row, prop_name, field.toggle_field)

        elif field.field_type.value == "list":
            self._build_list_field_standalone(field, prop_name)

        elif field.field_type.value == "vec2":
            vec_val = getattr(c, prop_name)
            if isinstance(vec_val, Vec2):
                w, sbs = _make_vec2_row(field.label, vec_val, lambda: self._on_vec2_changed(prop_name, sbs))
                setattr(self, f"_sbs_{prop_name}", sbs)
                self._layout.addWidget(w)

        elif field.field_type.value == "vec3":
            vec_val = getattr(c, prop_name)
            if isinstance(vec_val, Vec3):
                w, sbs = _make_vec3_row(field.label, vec_val, lambda: self._on_vec3_changed(prop_name, sbs))
                setattr(self, f"_sbs_{prop_name}", sbs)
                self._layout.addWidget(w)

        elif field.field_type.value == "anchor":
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(4)
            lbl = QLabel("Anchor Preset")
            lbl.setStyleSheet(f"color: {_FUSION_TEXT_DIM}; font-size: 11px; background: transparent;")
            cl.addWidget(lbl)
            selector = AnchorPresetSelector()
            selector.set_anchor(value)
            def _on_anchor_change(v):
                setattr(c, prop_name, v)
                w = getattr(c, '_widget_ref', None)
                if w:
                    w._anchor = v
                    cr = getattr(w, '_canvas_ref', None)
                    if cr and hasattr(w, 'update_anchor'):
                        w.update_anchor(cr.width(), cr.height())
                        c.update_from_widget()
            selector.anchor_changed.connect(_on_anchor_change)
            cl.addWidget(selector)
            self._layout.addWidget(container)

        elif field.field_type.value == "layer":
            cfg = get_project_config(os.getcwd())
            layer_names = cfg.get("physics.layer_names", DEFAULT_LAYER_NAMES)
            cb = QComboBox()
            cb.setStyleSheet(f"""
                QComboBox {{
                    background: {_FUSION_BG_INPUT};
                    color: {_FUSION_TEXT_BRIGHT};
                    border: 1px solid {_FUSION_BORDER};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    min-height: 20px;
                }}
                QComboBox:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                QComboBox::drop-down {{ border: none; width: 16px; }}
                QComboBox::down-arrow {{ width: 8px; height: 8px; }}
                QComboBox QAbstractItemView {{
                    background: {_FUSION_BG_CARD};
                    color: {_FUSION_TEXT};
                    border: 1px solid {_FUSION_BORDER};
                    selection-background-color: {_FUSION_BG_HOVER};
                    selection-color: {_FUSION_TEXT_BRIGHT};
                }}
            """)
            cb.addItems(layer_names[:MAX_LAYERS])
            if 0 <= value < len(layer_names):
                cb.setCurrentIndex(int(value))
            comp_cls = type(c)
            cb.currentIndexChanged.connect(self._undo_setter_all(comp_cls, prop_name))
            self._add_field(field.label, cb, prop_name, field.toggle_field)

        elif field.field_type.value == "layer_mask":
            cfg = get_project_config(os.getcwd())
            layer_names = cfg.get("physics.layer_names", DEFAULT_LAYER_NAMES)
            mask_value = int(value)
            comp_cls = type(c)

            btn = QPushButton()
            btn.setObjectName("layerMaskBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ text-align: left; padding: 3px 8px; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; color: {_FUSION_TEXT}; font-size: 11px; background: {_FUSION_BG_INPUT}; }}
                QPushButton:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
            """)
            self._update_layer_mask_text(btn, mask_value, layer_names)

            menu = QMenu(btn)
            menu.setStyleSheet(f"""
                QMenu {{ background: {_FUSION_BG_CARD}; border: 1px solid {_FUSION_BORDER}; padding: 4px; }}
                QMenu::item {{ color: {_FUSION_TEXT}; padding: 4px 20px; }}
                QMenu::item:selected {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
                QMenu::indicator {{ width: 14px; height: 14px; }}
            """)

            all_act = menu.addAction("Everything")
            all_act.setCheckable(True)
            all_act.setChecked(mask_value == 0xFFFF)
            all_act.triggered.connect(lambda: self._on_layer_mask_set_all(prop_name, True, btn, layer_names, menu))

            nothing_act = menu.addAction("Nothing")
            nothing_act.setCheckable(True)
            nothing_act.setChecked(mask_value == 0)
            nothing_act.triggered.connect(lambda: self._on_layer_mask_set_all(prop_name, False, btn, layer_names, menu))

            menu.addSeparator()

            layer_actions = []
            for i in range(MAX_LAYERS):
                name = layer_names[i] if i < len(layer_names) else f"Layer{i}"
                act = menu.addAction(name)
                act.setCheckable(True)
                act.setChecked(bool(mask_value & (1 << i)))
                act.triggered.connect(lambda checked, bit=i: self._on_layer_mask_toggle(prop_name, bit, btn, layer_names, menu, all_act, nothing_act))
                layer_actions.append(act)

            btn.clicked.connect(lambda: menu.exec(btn.mapToGlobal(btn.rect().bottomLeft())))
            self._add_field(field.label, btn, prop_name, field.toggle_field)

    def _build_list_field_standalone(self, field, prop_name):
        c = self._component
        value = getattr(c, prop_name)
        if not isinstance(value, list):
            lbl = QLabel("Invalid list")
            self._layout.addWidget(lbl)
            return

        header_row = QWidget()
        rl_header = QHBoxLayout(header_row)
        rl_header.setContentsMargins(0, 0, 0, 0)
        rl_header.setSpacing(4)
        label = QLabel(field.label)
        label.setFixedWidth(scale(110))
        rl_header.addWidget(label)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(*scale_xy(20, 18))
        add_btn.setToolTip("Add item")
        add_btn.setStyleSheet(f"""
            QPushButton {{ color: {_FUSION_ACCENT_GREEN}; border: 1px solid #3a5a3a; background: {_FUSION_BG_INPUT}; font-weight: bold; font-size: 12px; padding: 0; }}
            QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
        """)
        add_btn.clicked.connect(lambda _, p=prop_name, comp=c: self._list_add_item(comp, p))
        rl_header.addWidget(add_btn)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        rl_header.addWidget(container, 1)
        self._layout.addWidget(header_row)

        element_fields = field.element_fields

        def rebuild_list():
            while layout.count():
                item = layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            current_value = getattr(c, prop_name) or []
            for idx, elem_data in enumerate(current_value):
                row = self._build_list_row_standalone(prop_name, idx, elem_data, element_fields)
                layout.addWidget(row)

        rebuild_list()
        setattr(self, f"_rebuild_{prop_name}", rebuild_list)

    def _build_list_row_standalone(self, prop_name, index, elem_data, element_fields):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(2, 1, 2, 1)
        rl.setSpacing(3)

        idx_label = QLabel(str(index))
        idx_label.setFixedWidth(scale(16))
        idx_label.setStyleSheet(f"color: {_FUSION_TEXT_DIM}; font-size: 9px;")
        rl.addWidget(idx_label)

        for ef in element_fields:
            val = elem_data.get(ef.name, None) if isinstance(elem_data, dict) else None
            widget = self._build_list_element_widget_standalone(prop_name, index, ef, val)
            if widget:
                rl.addWidget(widget, 1 if ef.field_type.value in ("gameobject", "string") else 0)

        remove_btn = QPushButton("-")
        remove_btn.setFixedSize(*scale_xy(18, 18))
        remove_btn.setToolTip("Remove item")
        remove_btn.setStyleSheet(f"""
            QPushButton {{ color: {_FUSION_ACCENT_RED}; border: 1px solid #5a2a2a; background: {_FUSION_BG_INPUT}; font-weight: bold; font-size: 12px; padding: 0; }}
            QPushButton:hover {{ color: {_FUSION_TEXT_BRIGHT}; background: {_FUSION_BG_HOVER}; }}
        """)
        remove_btn.clicked.connect(lambda _, i=index, p=prop_name, comp=self._component: self._list_remove_item(comp, p, i))
        rl.addWidget(remove_btn)

        return row

    def _build_list_element_widget_standalone(self, prop_name, index, ef, val):
        c = self._component

        if ef.field_type.value == "float":
            sb = QDoubleSpinBox()
            sb.setRange(ef.min_val, ef.max_val)
            sb.setSingleStep(ef.step)
            sb.setDecimals(ef.decimals)
            sb.setValue(val if val is not None else 0.0)
            sb.setMinimumWidth(50)
            sb.setStyleSheet(_FUSION_SPINBOX_STYLE)
            def on_change(v, idx=index, pn=prop_name, fn=ef.name):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = v
                    current[idx] = elem
                    setattr(c, pn, current)
            sb.valueChanged.connect(on_change)
            return sb

        elif ef.field_type.value == "int":
            sb = QSpinBox()
            sb.setRange(int(ef.min_val), int(ef.max_val))
            sb.setValue(val if val is not None else 0)
            sb.setMinimumWidth(40)
            sb.setStyleSheet(_FUSION_SPINBOX_STYLE)
            def on_change(v, idx=index, pn=prop_name, fn=ef.name):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = v
                    current[idx] = elem
                    setattr(c, pn, current)
            sb.valueChanged.connect(on_change)
            return sb

        elif ef.field_type.value == "bool":
            cb = QCheckBox()
            cb.setChecked(bool(val))
            cb.setStyleSheet(_checkbox_style())
            def on_toggle(v, idx=index, pn=prop_name, fn=ef.name):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = v
                    current[idx] = elem
                    setattr(c, pn, current)
            cb.toggled.connect(on_toggle)
            return cb

        elif ef.field_type.value == "gameobject":
            scene = self._entity._scene if self._entity else None
            entity_id = val or ""
            def on_entity(eid, idx=index, pn=prop_name, fn=ef.name):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = eid or None
                    current[idx] = elem
                    setattr(c, pn, current)
            picker = _make_gameobject_picker(entity_id, scene, on_entity)
            return picker

        elif ef.field_type.value == "string":
            le = QLineEdit(str(val) if val is not None else "")
            le.setStyleSheet(f"""
                QLineEdit {{
                    background: {_FUSION_BG_INPUT};
                    color: {_FUSION_TEXT_BRIGHT};
                    border: 1px solid {_FUSION_BORDER};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 1px 3px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QLineEdit:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                QLineEdit:focus {{ border-color: {_accent()}; }}
            """)
            def on_change(t, idx=index, pn=prop_name, fn=ef.name):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = t
                    current[idx] = elem
                    setattr(c, pn, current)
            le.textChanged.connect(on_change)
            return le

        elif ef.field_type.value == "enum":
            cb = QComboBox()
            cb.setStyleSheet(f"""
                QComboBox {{
                    background: {_FUSION_BG_INPUT};
                    color: {_FUSION_TEXT_BRIGHT};
                    border: 1px solid {_FUSION_BORDER};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 1px 3px;
                    font-size: 11px;
                    min-height: 18px;
                }}
                QComboBox:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                QComboBox::drop-down {{ border: none; width: 14px; }}
                QComboBox::down-arrow {{ width: 6px; height: 6px; }}
                QComboBox QAbstractItemView {{
                    background: {_FUSION_BG_CARD};
                    color: {_FUSION_TEXT};
                    border: 1px solid {_FUSION_BORDER};
                    selection-background-color: {_FUSION_BG_HOVER};
                    selection-color: {_FUSION_TEXT_BRIGHT};
                }}
            """)
            enum_class = ef.enum_class
            items = [e.value for e in enum_class]
            cb.addItems(items)
            current_val = val.value if hasattr(val, 'value') else str(val)
            idx2 = items.index(current_val) if current_val in items else 0
            cb.setCurrentIndex(idx2)
            def on_change(t, idx=index, pn=prop_name, fn=ef.name, ec=enum_class):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = ec(t)
                    current[idx] = elem
                    setattr(c, pn, current)
            cb.currentTextChanged.connect(on_change)
            return cb

        elif ef.field_type.value == "vec2":
            from core.math3d import Vec2
            vec_val = val if isinstance(val, Vec2) else (Vec2(*val) if isinstance(val, list) and len(val) >= 2 else Vec2(0, 0))
            w, sbs = _make_vec2_row("", vec_val, lambda: None)
            def on_change(idx=index, pn=prop_name, fn=ef.name, boxes=sbs):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = Vec2(boxes[0].value(), boxes[1].value())
                    current[idx] = elem
                    setattr(c, pn, current)
            for sb in sbs:
                sb.valueChanged.connect(on_change)
            return w

        elif ef.field_type.value == "vec3":
            from core.math3d import Vec3
            vec_val = val if isinstance(val, Vec3) else (Vec3(*val) if isinstance(val, list) and len(val) >= 3 else Vec3(0, 0, 0))
            w, sbs = _make_vec3_row("", vec_val, lambda: None)
            def on_change(idx=index, pn=prop_name, fn=ef.name, boxes=sbs):
                current = getattr(c, pn) or []
                if idx < len(current):
                    elem = dict(current[idx])
                    elem[fn] = Vec3(boxes[0].value(), boxes[1].value(), boxes[2].value())
                    current[idx] = elem
                    setattr(c, pn, current)
            for sb in sbs:
                sb.valueChanged.connect(on_change)
            return w

        return None

    def _list_add_item(self, component, prop_name):
        current = getattr(component, prop_name) or []
        new_elem = {}
        fields_meta = self._get_list_element_fields(prop_name)
        for ef in fields_meta:
            if ef.field_type.value == "float":
                new_elem[ef.name] = 0.0
            elif ef.field_type.value == "int":
                new_elem[ef.name] = 0
            elif ef.field_type.value == "bool":
                new_elem[ef.name] = False
            elif ef.field_type.value in ("gameobject",):
                new_elem[ef.name] = None
            elif ef.field_type.value == "string":
                new_elem[ef.name] = ""
            elif ef.field_type.value == "vec2":
                new_elem[ef.name] = Vec2(0, 0)
            elif ef.field_type.value == "vec3":
                new_elem[ef.name] = Vec3(0, 0, 0)
            else:
                new_elem[ef.name] = None
        current.append(new_elem)
        setattr(component, prop_name, list(current))
        rebuild_fn = getattr(self, f"_rebuild_{prop_name}", None)
        if rebuild_fn:
            rebuild_fn()

    def _list_remove_item(self, component, prop_name, index):
        current = getattr(component, prop_name) or []
        if 0 <= index < len(current):
            current.pop(index)
            setattr(component, prop_name, list(current))
        rebuild_fn = getattr(self, f"_rebuild_{prop_name}", None)
        if rebuild_fn:
            rebuild_fn()

    def _list_set_entity(self, component, prop_name, index, field_name, entity_id):
        current = getattr(component, prop_name) or []
        if 0 <= index < len(current):
            elem = dict(current[index])
            elem[field_name] = entity_id or None
            current[index] = elem
            setattr(component, prop_name, list(current))

    def _get_list_element_fields(self, prop_name):
        fields_meta = getattr(type(self._component), "_inspector_fields", lambda: [])()
        for f in fields_meta:
            if f.name == prop_name and f.field_type.value == "list":
                return f.element_fields
        return []

    def _on_vec2_changed(self, prop_name: str, spinboxes: list):
        if self._updating: return
        c = self._component
        old_val = getattr(c, prop_name)
        new_val = Vec2(spinboxes[0].value(), spinboxes[1].value())
        setattr(c, prop_name, new_val)
        if self._entity:
            get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, old_val, new_val))

    def refresh_vec2_field(self, prop_name: str):
        c = self._component
        sbs_key = f"_sbs_{prop_name}"
        if not hasattr(self, sbs_key): return
        sbs = getattr(self, sbs_key)
        val = getattr(c, prop_name)
        for sb, v in zip(sbs, [val.x, val.y]):
            sb.setValue(v)

    def _on_vec3_changed(self, prop_name: str, spinboxes: list):
        if self._updating: return
        c = self._component
        old_val = getattr(c, prop_name)
        new_val = Vec3(spinboxes[0].value(), spinboxes[1].value(), spinboxes[2].value())
        setattr(c, prop_name, new_val)
        if self._entity:
            get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, old_val, new_val))

    def refresh_vec3_field(self, prop_name: str):
        c = self._component
        sbs_key = f"_sbs_{prop_name}"
        if not hasattr(self, sbs_key): return
        sbs = getattr(self, sbs_key)
        val = getattr(c, prop_name)
        for sb, v in zip(sbs, [val.x, val.y, val.z]):
            sb.setValue(v)

    def _show_source(self, file_path: str, line_number: int, comp_type: str, prop_name: str):
        title = f"{comp_type}.{prop_name}"
        dlg = SourceViewerDialog(file_path, line_number, title, self)
        dlg.exec()

    def _build_script_fields(self, comp):
        for field in type(comp)._inspector_fields():
            self._build_field_from_meta(field)
        script_fields = comp.get_script_public_fields()
        if script_fields:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {_FUSION_BORDER}; margin: 4px 0;")
            self._layout.addWidget(sep)
        for field in script_fields:
            self._build_script_field_from_meta(field, comp)

    def _build_script_field_from_meta(self, field, comp):
        prop_name = field.name
        value = comp.get_field_value(prop_name)

        if field.field_type.value == "float":
            sb = _make_spinbox(value if value is not None else 0.0, field.min_val, field.max_val, field.step, field.decimals)
            def _on_float_changed(v, n=prop_name):
                old = comp.get_field_value(n)
                comp.set_field_value(n, v)
                if self._entity:
                    get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{n}", old, v))
            sb.valueChanged.connect(_on_float_changed)
            self._add_field(field.label, sb)

        elif field.field_type.value == "int":
            sb = QSpinBox()
            min_i = max(-2147483648, min(2147483647, int(field.min_val)))
            max_i = max(-2147483648, min(2147483647, int(field.max_val)))
            sb.setRange(min_i, max_i)
            sb.setValue(max(min_i, min(max_i, int(value if value is not None else 0))))
            sb.setMinimumWidth(60)
            sb.setStyleSheet(_FUSION_SPINBOX_STYLE)
            def _on_int_changed(v, n=prop_name):
                old = comp.get_field_value(n)
                comp.set_field_value(n, v)
                if self._entity:
                    get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{n}", old, v))
            sb.valueChanged.connect(_on_int_changed)
            self._add_field(field.label, sb)

        elif field.field_type.value == "bool":
            cb = QCheckBox()
            cb.setChecked(value if value is not None else False)
            cb.setStyleSheet(_checkbox_style())
            def _on_bool_changed(v, n=prop_name):
                old = comp.get_field_value(n)
                comp.set_field_value(n, v)
                if self._entity:
                    get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{n}", old, v))
            cb.toggled.connect(_on_bool_changed)
            self._add_field(field.label, cb)

        elif field.field_type.value == "string":
            le = QLineEdit(str(value) if value is not None else "")
            le.setMinimumWidth(60)
            le.setStyleSheet(f"""
                QLineEdit {{
                    background: {_FUSION_BG_INPUT};
                    color: {_FUSION_TEXT_BRIGHT};
                    border: 1px solid {_FUSION_BORDER};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QLineEdit:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                QLineEdit:focus {{ border-color: {_accent()}; }}
            """)
            def _on_str_changed(v, n=prop_name):
                old = comp.get_field_value(n)
                comp.set_field_value(n, v)
                if self._entity:
                    get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{n}", old, v))
            le.textChanged.connect(_on_str_changed)
            self._add_field(field.label, le)

        elif field.field_type.value == "vec2":
            from core.math3d import Vec2
            vec_val = value if isinstance(value, Vec2) else Vec2(0, 0)
            w, sbs = _make_vec2_row(field.label, vec_val, lambda: None)
            sbs_key = f"_sbs_{prop_name}"
            setattr(self, sbs_key, sbs)
            def _on_vec2_changed(n=prop_name, sbs_box=sbs):
                new_val = Vec2(sbs_box[0].value(), sbs_box[1].value())
                old = comp.get_field_value(n)
                comp.set_field_value(n, new_val)
                if self._entity:
                    get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{n}", old, new_val))
            for sb in sbs:
                sb.valueChanged.connect(_on_vec2_changed)
            self._layout.addWidget(w)

        elif field.field_type.value == "vec3":
            from core.math3d import Vec3
            vec_val = value if isinstance(value, Vec3) else Vec3(0, 0, 0)
            w, sbs = _make_vec3_row(field.label, vec_val, lambda: None)
            sbs_key = f"_sbs_{prop_name}"
            setattr(self, sbs_key, sbs)
            def _on_vec3_changed(n=prop_name, sbs_box=sbs):
                new_val = Vec3(sbs_box[0].value(), sbs_box[1].value(), sbs_box[2].value())
                old = comp.get_field_value(n)
                comp.set_field_value(n, new_val)
                if self._entity:
                    get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{n}", old, new_val))
            for sb in sbs:
                sb.valueChanged.connect(_on_vec3_changed)
            self._layout.addWidget(w)

        elif field.field_type.value == "gameobject":
            scene = self._entity._scene if self._entity else None
            picker = _make_gameobject_picker(value or "", scene, lambda v, n=prop_name: self._on_script_gameobject_changed(comp, n, v))
            self._add_field(field.label, picker)

        elif field.field_type.value == "resource":
            from core.components.scripting.script_component import RESOURCE_TYPE_FILTERS
            rtype = field.resource_type or "mesh"
            picker = _make_resource_type_picker(value or "", rtype, lambda v, n=prop_name: self._on_script_resource_changed(comp, n, v))
            self._add_field(field.label, picker)

        elif field.field_type.value == "asset":
            picker = _make_asset_picker(value or "", field.resource_type or "animclip", lambda v, n=prop_name: self._on_script_resource_changed(comp, n, v))
            self._add_field(field.label, picker)

        elif field.field_type.value == "enum":
            enum_class = field.enum_class
            if enum_class:
                items = [e.value for e in enum_class]
                cb = QComboBox()
                cb.setStyleSheet(f"""
                    QComboBox {{
                        background: {_FUSION_BG_INPUT};
                        color: {_FUSION_TEXT_BRIGHT};
                        border: 1px solid {_FUSION_BORDER};
                        border-radius: {_FUSION_INPUT_RADIUS};
                        padding: 2px 4px;
                        font-size: 11px;
                        min-height: 20px;
                    }}
                    QComboBox:hover {{ border-color: {_FUSION_BORDER_LIGHT}; }}
                    QComboBox::drop-down {{ border: none; width: 16px; }}
                    QComboBox::down-arrow {{ width: 8px; height: 8px; }}
                    QComboBox QAbstractItemView {{
                        background: {_FUSION_BG_CARD};
                        color: {_FUSION_TEXT};
                        border: 1px solid {_FUSION_BORDER};
                        selection-background-color: {_FUSION_BG_HOVER};
                        selection-color: {_FUSION_TEXT_BRIGHT};
                    }}
                """)
                cb.addItems(items)
                current_val = value if isinstance(value, str) else (value.value if hasattr(value, 'value') else '')
                idx = items.index(current_val) if current_val in items else 0
                cb.setCurrentIndex(idx)
                def _on_enum_changed(v, n=prop_name):
                    old = comp.get_field_value(n)
                    comp.set_field_value(n, v)
                    if self._entity:
                        get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{n}", old, v))
                cb.currentTextChanged.connect(_on_enum_changed)
                self._add_field(field.label, cb)

        elif field.field_type.value == "button":
            btn = QPushButton(field.label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {_FUSION_TEXT};
                    background: {_FUSION_BG_INPUT};
                    border: 1px solid {_FUSION_BORDER_LIGHT};
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 3px 12px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
            """)

            def _on_click(m=prop_name, c=comp):
                m = str(m)
                if not c._py_instance:
                    c._load_script()
                if c._py_instance and hasattr(c._py_instance, m):
                    try:
                        c._py_instance._entity = c._entity
                        getattr(c._py_instance, m)()
                    except Exception as e:
                        from core.logger import Logger
                        Logger.error(f"Script button '{m}' error: {e}")
            btn.clicked.connect(_on_click)
            self._add_field("", btn)

    def _on_script_gameobject_changed(self, comp, prop_name, value):
        old = comp.get_field_value(prop_name)
        comp.set_field_value(prop_name, value)
        if self._entity:
            get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{prop_name}", old, value))

    def _on_script_resource_changed(self, comp, prop_name, value):
        old = comp.get_field_value(prop_name)
        comp.set_field_value(prop_name, value)
        if self._entity:
            get_history().execute(SetComponentCommand(self._entity, type(comp), f"_script_{prop_name}", old, value))

    def _build_transform(self):
        c = self._component
        pos = c.local_position
        rot = c.local_euler_angles
        sc = c.local_scale
        pos_widget, self._pos_sbs = _make_vec3_row("Position", pos, self._on_transform_changed, reset_to=[0,0,0])
        self._layout.addWidget(pos_widget)
        rot_widget, self._rot_sbs = _make_vec3_row("Rotation", rot, self._on_transform_changed, reset_to=[0,0,0])
        self._layout.addWidget(rot_widget)
        sc_widget, self._sc_sbs = _make_vec3_row("Scale", sc, self._on_transform_changed, reset_to=[1,1,1])
        self._layout.addWidget(sc_widget)

    def _on_transform_changed(self):
        if self._updating: return
        self._updating = True
        c = self._component
        old_pos = Vec3(c.local_position.x, c.local_position.y, c.local_position.z)
        old_rot = Vec3(c.local_euler_angles.x, c.local_euler_angles.y, c.local_euler_angles.z)
        old_sc = Vec3(c.local_scale.x, c.local_scale.y, c.local_scale.z)
        new_pos = Vec3(self._pos_sbs[0].value(), self._pos_sbs[1].value(), self._pos_sbs[2].value())
        new_rot = Vec3(self._rot_sbs[0].value(), self._rot_sbs[1].value(), self._rot_sbs[2].value())
        new_sc = Vec3(self._sc_sbs[0].value(), self._sc_sbs[1].value(), self._sc_sbs[2].value())
        c.local_position = new_pos
        c.local_euler_angles = new_rot
        c.local_scale = new_sc
        self._updating = False
        if self._entity:
            from core.commands import CompoundCommand, SetComponentCommand, get_history
            from core.components import Transform
            cmds = [
                SetComponentCommand(self._entity, Transform, "local_position", old_pos, new_pos),
                SetComponentCommand(self._entity, Transform, "local_euler_angles", old_rot, new_rot),
                SetComponentCommand(self._entity, Transform, "local_scale", old_sc, new_sc),
            ]
            get_history().execute(CompoundCommand(cmds, "Transform Change"))
            try:
                from core.engine import Engine
                collab = Engine.instance().collab_manager
                if collab and collab.connected and self._entity:
                    from core.math3d import Vec3 as _Vec3
                    collab.send_component_update(self._entity.id, self._component_key, "local_position", _collapse_value(new_pos))
                    collab.send_component_update(self._entity.id, self._component_key, "local_euler_angles", _collapse_value(new_rot))
                    collab.send_component_update(self._entity.id, self._component_key, "local_scale", _collapse_value(new_sc))
            except Exception:
                pass

    def refresh_transform(self):
        if self._updating: return
        c = self._component
        if not hasattr(self, "_pos_sbs"): return
        self._updating = True
        pos = c.local_position
        rot = c.local_euler_angles
        sc = c.local_scale
        for sb, v in zip(self._pos_sbs, [pos.x, pos.y, pos.z]): sb.setValue(v)
        for sb, v in zip(self._rot_sbs, [rot.x, rot.y, rot.z]): sb.setValue(v)
        for sb, v in zip(self._sc_sbs, [sc.x, sc.y, sc.z]): sb.setValue(v)
        self._updating = False


class ComponentPickerDialog(QDialog):
    def __init__(self, entity, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Component")
        self.setMinimumSize(340, 420)
        self.resize(360, 480)
        self._entity = entity
        self._selected: Optional[dict] = None
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {_FUSION_BG};
            }}
            QLineEdit {{
                background: {_FUSION_BG_INPUT};
                color: {_FUSION_TEXT_BRIGHT};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 3px 6px;
                font-size: 11px;
                selection-background-color: {_accent()};
            }}
            QLineEdit:focus {{ border-color: {_accent()}; }}
            QListWidget {{
                background: {_FUSION_BG_CARD};
                color: {_FUSION_TEXT};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                font-size: 11px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 3px 6px;
                border-radius: 2px;
            }}
            QListWidget::item:selected {{
                background: {_FUSION_BG_HOVER};
                color: {_FUSION_TEXT_BRIGHT};
            }}
            QListWidget::item:hover {{
                background: {_FUSION_BG_HOVER};
            }}
            QPushButton {{
                color: {_FUSION_TEXT};
                background: {_FUSION_BG_INPUT};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 4px 16px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {_FUSION_BG_HOVER};
                color: {_FUSION_TEXT_BRIGHT};
            }}
            QPushButton:disabled {{
                color: {_FUSION_TEXT_DIM};
                background: {_FUSION_BG};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search components and scripts...")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setSpacing(1)
        self._list.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("Add")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._accept_selection)
        btn_row.addWidget(self._add_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._list.itemSelectionChanged.connect(self._on_selection_changed)

    def _get_available_scripts(self) -> list[dict]:
        from core.engine import Engine
        eng = Engine.instance()
        project_root = eng.project_root if eng is not None else _PROJECT_ROOT
        for candidate in (
            os.path.join(project_root, "assets", "scripts"),
            os.path.join(project_root, "scripts"),
        ):
            scripts_dir = os.path.normpath(candidate)
            if os.path.isdir(scripts_dir):
                break
        else:
            return []
        results = []
        for root, dirs, files in os.walk(scripts_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in sorted(files):
                if f.endswith(".py") and not f.startswith("__"):
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, scripts_dir)
                    results.append({"name": rel, "path": full, "type": "script"})
        return results

    def _populate(self, filter_text: str = ""):
        self._list.clear()
        from core.ecs import ComponentRegistry
        categories = {}
        for comp_name in ComponentRegistry.all():
            cats = ComponentRegistry.get_categories(comp_name)
            for cat in cats:
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(comp_name)
        all_registered = set(ComponentRegistry.all().keys())
        filter_lower = filter_text.lower()

        for cat in sorted(categories.keys()):
            cat_items = [c for c in categories[cat] if c in all_registered]
            if not cat_items:
                continue
            if filter_text:
                cat_items = [c for c in cat_items if filter_lower in c.lower()]
                if not cat_items:
                    continue
            header_item = QListWidgetItem(f"── {cat} ──")
            header_item.setFlags(header_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            header_item.setForeground(QColor(_FUSION_TEXT_DIM))
            self._list.addItem(header_item)
            for cname in cat_items:
                cls = ComponentRegistry.get(cname)
                can_multiple = getattr(cls, '_allow_multiple', False) if cls else False
                item = QListWidgetItem(f"  {cname}")
                item.setData(Qt.ItemDataRole.UserRole, {"type": "component", "name": cname})
                if not can_multiple and self._entity.has_component(cls):
                    item.setForeground(QColor(_FUSION_TEXT_DIM))
                    item.setToolTip("Already added")
                if cls:
                    pix = _get_component_icon_pixmap(cls, 16)
                    item.setIcon(QIcon(pix))
                self._list.addItem(item)

        scripts = self._get_available_scripts()
        if filter_text:
            scripts = [s for s in scripts if filter_lower in s["name"].lower()]
        if scripts:
            header_item = QListWidgetItem("── Scripts ──")
            header_item.setFlags(header_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            header_item.setForeground(QColor(_FUSION_TEXT_DIM))
            self._list.addItem(header_item)
            for s in scripts:
                item = QListWidgetItem(f"  {s['name']}")
                item.setData(Qt.ItemDataRole.UserRole, s)
                item.setToolTip(f"Add script: {s['name']}")
                self._list.addItem(item)

    def _filter(self, text: str):
        self._populate(text)

    def _on_selection_changed(self):
        items = self._list.selectedItems()
        if items:
            data = items[0].data(Qt.ItemDataRole.UserRole)
            self._add_btn.setEnabled(data is not None)
        else:
            self._add_btn.setEnabled(False)

    def _accept_selection(self):
        items = self._list.selectedItems()
        if items:
            data = items[0].data(Qt.ItemDataRole.UserRole)
            if data:
                self._selected = data
                self.accept()

    def selected_result(self) -> Optional[dict]:
        return self._selected


class InspectorPanel(QDockWidget):
    _clipboard = None

    def __init__(self, engine: Engine, parent=None):
        super().__init__("Inspector", parent)
        self._engine = engine
        self._entity: Optional[Entity] = None
        self._selected_entities: list = []
        self._comp_widgets: list[ComponentWidget] = []
        self._asset_widgets: list[QWidget] = []
        self._updating: bool = False
        self._locked: bool = False
        self._asset_path: Optional[str] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_transform)
        self._refresh_timer.start(100)
        self._animator_mode = False
        self._animator_state: Optional[AnimatorState] = None
        self._animator_transition: Optional[AnimatorTransition] = None
        self._animator_controller: Optional[AnimatorController] = None
        self._saved_entity: Optional[Entity] = None
        self._saved_entities: list[Entity] = []
        self._setup_ui()

    def load_config(self, config) -> None:
        refresh_interval = config.get("inspector.refresh_interval", 100)
        self._refresh_timer.setInterval(refresh_interval)

    def _setup_ui(self):
        outer = QWidget()
        outer.setStyleSheet(f"background: {_FUSION_BG};")
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._header_widget = QWidget()
        self._header_widget.setStyleSheet(f"background: {_FUSION_BG};")
        header_layout = QHBoxLayout(self._header_widget)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.setSpacing(4)
        self._lock_btn = QPushButton("\U0001F512")
        self._lock_btn.setFixedSize(*scale_xy(22, 22))
        self._lock_btn.setCheckable(True)
        self._lock_btn.setChecked(False)
        self._lock_btn.setToolTip("Lock Inspector")
        self._lock_btn.setStyleSheet(f"""
            QPushButton {{ color: {_FUSION_TEXT_DIM}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; font-size: 10px; background: transparent; }}
            QPushButton:hover {{ color: {_FUSION_TEXT_BRIGHT}; background: {_FUSION_BG_HOVER}; }}
            QPushButton:checked {{ color: {_FUSION_ACCENT_ORANGE}; border-color: {_FUSION_ACCENT_ORANGE}; }}
        """)
        self._lock_btn.toggled.connect(self._on_lock_toggled)
        header_layout.addWidget(self._lock_btn)
        self._active_cb = QCheckBox()
        self._active_cb.toggled.connect(self._on_active_changed)
        self._active_cb.setStyleSheet(f"background: transparent;")
        header_layout.addWidget(self._active_cb)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Entity name")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {_FUSION_BG};
                color: {_FUSION_TEXT_BRIGHT};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 2px 4px;
                font-size: 11px;
                selection-background-color: {_accent()};
            }}
            QLineEdit:focus {{ border-color: {_accent()}; }}
        """)
        self._name_edit.textChanged.connect(self._on_name_changed)
        header_layout.addWidget(self._name_edit, 1)
        self._tag_edit = QLineEdit()
        self._tag_edit.setPlaceholderText("Tag")
        self._tag_edit.setFixedWidth(scale(80))
        self._tag_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {_FUSION_BG};
                color: {_FUSION_TEXT_DIM};
                border: 1px solid {_FUSION_BORDER};
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 2px 4px;
                font-size: 10px;
            }}
            QLineEdit:focus {{ border-color: {_accent()}; color: {_FUSION_TEXT_BRIGHT}; }}
        """)
        self._tag_edit.textChanged.connect(self._on_tag_changed)
        header_layout.addWidget(self._tag_edit)
        layer_lbl = QLabel("Layer")
        layer_lbl.setStyleSheet(f"color: {_FUSION_TEXT_DIM}; font-size: 10px; background: transparent;")
        header_layout.addWidget(layer_lbl)
        self._layer_sb = QSpinBox()
        self._layer_sb.setRange(0, 31)
        self._layer_sb.setFixedWidth(scale(46))
        self._layer_sb.setStyleSheet(_FUSION_SPINBOX_STYLE)
        self._layer_sb.valueChanged.connect(self._on_layer_changed)
        header_layout.addWidget(self._layer_sb)
        outer_layout.addWidget(self._header_widget)

        self._prefab_bar_widget = QWidget()
        self._prefab_bar_widget.setStyleSheet(f"background: {_FUSION_BG};")
        prefab_bar_layout = QHBoxLayout(self._prefab_bar_widget)
        prefab_bar_layout.setContentsMargins(6, 2, 6, 2)
        self._prefab_label = QLabel()
        self._prefab_label.setStyleSheet(f"color: {_accent()}; font-weight: 600; font-size: 11px; background: transparent;")
        prefab_bar_layout.addWidget(self._prefab_label)
        self._override_label = QLabel()
        self._override_label.setStyleSheet(f"color: {_FUSION_ACCENT_ORANGE}; font-size: 10px; background: transparent;")
        prefab_bar_layout.addWidget(self._override_label)
        prefab_bar_layout.addStretch()
        _prefab_btn_style = f"""
            QPushButton {{
                color: {_FUSION_TEXT}; background: {_FUSION_BG_INPUT};
                border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS};
                padding: 2px 8px; font-size: 10px;
            }}
            QPushButton:hover {{ background: {_FUSION_BG_HOVER}; color: {_FUSION_TEXT_BRIGHT}; }}
        """
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setFixedHeight(scale(22))
        self._apply_btn.setStyleSheet(_prefab_btn_style)
        self._apply_btn.clicked.connect(self._on_apply_prefab)
        prefab_bar_layout.addWidget(self._apply_btn)
        self._revert_btn = QPushButton("Revert")
        self._revert_btn.setFixedHeight(scale(22))
        self._revert_btn.setStyleSheet(_prefab_btn_style)
        self._revert_btn.clicked.connect(self._on_revert_prefab)
        prefab_bar_layout.addWidget(self._revert_btn)
        self._select_prefab_btn = QPushButton("Select")
        self._select_prefab_btn.setFixedHeight(scale(22))
        self._select_prefab_btn.setStyleSheet(_prefab_btn_style)
        self._select_prefab_btn.clicked.connect(self._on_select_prefab_asset)
        prefab_bar_layout.addWidget(self._select_prefab_btn)
        outer_layout.addWidget(self._prefab_bar_widget)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_FUSION_BORDER};")
        outer_layout.addWidget(sep)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {_FUSION_BG}; }}
            QScrollBar:vertical {{
                background: {_FUSION_BG};
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {_FUSION_BORDER};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_FUSION_BORDER_LIGHT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        self._content_widget = QWidget()
        self._content_widget.setStyleSheet(f"background: {_FUSION_BG};")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content_widget)
        outer_layout.addWidget(self._scroll, 1)

        bottom = QWidget()
        bottom.setStyleSheet(f"background: {_FUSION_BG};")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(6, 4, 6, 6)
        self._add_comp_btn = QPushButton("+ Add Component")
        self._add_comp_btn.setFixedHeight(scale(24))
        self._add_comp_btn.setStyleSheet(f"""
            QPushButton {{
                color: {_FUSION_TEXT_BRIGHT};
                background: {_FUSION_BG_HEADER};
                border: 1px dashed {_FUSION_BORDER_LIGHT};
                border-radius: {_FUSION_CARD_RADIUS};
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {_FUSION_BG_HOVER};
                border-color: {_accent()};
                color: {_accent()};
            }}
        """)
        self._add_comp_btn.clicked.connect(self._show_add_component_menu)
        bottom_layout.addWidget(self._add_comp_btn)
        outer_layout.addWidget(bottom)

        self._prefab_bar_widget.setVisible(False)
        self._header_widget.setVisible(False)
        self._add_comp_btn.setVisible(False)
        self.setWidget(outer)

    def _on_lock_toggled(self, checked: bool):
        self._locked = checked
        self._lock_btn.setToolTip("Unlock Inspector" if checked else "Lock Inspector")

    def set_entity(self, entity: Optional[Entity]):
        if self._locked:
            return
        self._animator_mode = False
        self._animator_state = None
        self._animator_transition = None
        self._animator_controller = None
        self._entity = entity
        self._selected_entities = [entity] if entity else []
        self._asset_path = None
        self._rebuild()

    def set_selected_entities(self, entities: list):
        if self._locked:
            return
        self._animator_mode = False
        self._animator_state = None
        self._animator_transition = None
        self._animator_controller = None
        self._selected_entities = list(entities)
        self._entity = entities[0] if entities else None
        self._asset_path = None
        self._rebuild()

    def show_import_settings(self, path: str):
        self._entity = None
        self._asset_path = path
        self._rebuild()

    def show_animator_state(self, state: AnimatorState, controller: AnimatorController):
        self._saved_entity = self._entity
        self._saved_entities = list(self._selected_entities)
        self._entity = None
        self._asset_path = None
        self._animator_mode = True
        self._animator_state = state
        self._animator_transition = None
        self._animator_controller = controller
        self._rebuild()

    def show_animator_transition(self, trans: AnimatorTransition, controller: AnimatorController):
        self._saved_entity = self._entity
        self._saved_entities = list(self._selected_entities)
        self._entity = None
        self._asset_path = None
        self._animator_mode = True
        self._animator_transition = trans
        self._animator_state = None
        self._animator_controller = controller
        self._rebuild()

    def clear_animator_mode(self):
        if self._animator_mode:
            self._animator_mode = False
            self._animator_state = None
            self._animator_transition = None
            self._entity = self._saved_entity
            self._selected_entities = self._saved_entities
            self._animator_controller = None
            self._rebuild()

    def _add_asset_widget(self, w: QWidget):
        self._asset_widgets.append(w)
        self._content_layout.addWidget(w)

    def _build_import_settings(self):
        import os
        self._updating = True
        name = os.path.basename(self._asset_path)
        ext = os.path.splitext(name)[1].lower()
        title = QLabel(f"<b>{name}</b>")
        title.setStyleSheet(f"color: {_FUSION_TEXT_BRIGHT}; padding: 4px 0; font-size: 12px;")
        self._add_asset_widget(title)
        info = QLabel(f"Path: {self._asset_path}")
        info.setStyleSheet(f"color: {_FUSION_TEXT_DIM}; font-size: 10px;")
        info.setWordWrap(True)
        self._add_asset_widget(info)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_FUSION_BORDER};")
        self._add_asset_widget(sep)
        if ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
            self._build_mesh_import_settings()
        elif ext in (".png", ".jpg", ".jpeg", ".svg"):
            self._build_texture_import_settings()
        elif ext in (".wav", ".mp3", ".ogg"):
            self._build_audio_import_settings()
        elif ext == ".zpem" or ext == ".mat":
            self._build_material_editor()
        else:
            lbl = QLabel("No import settings for this file type.")
            lbl.setStyleSheet(f"color: {_FUSION_TEXT_DIM};")
            self._add_asset_widget(lbl)
        self._updating = False

    def _build_labeled_field(self, label: str, widget: QWidget):
        row = QWidget()
        row.setStyleSheet(f"background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 2, 0, 2)
        rl.setSpacing(4)
        lbl = QLabel(label)
        lbl.setFixedWidth(scale(120))
        lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
        rl.addWidget(lbl)
        rl.addWidget(widget)
        self._add_asset_widget(row)

    def _build_mesh_import_settings(self):
        import json, os
        from editor.model_preview import ModelPreviewWidget
        from core.asset_importer import load_obj_async, load_mesh_async

        preview = ModelPreviewWidget()
        preview.setFixedHeight(200)
        self._add_asset_widget(preview)

        def _on_mesh_loaded(data):
            if data is not None and len(data.vertices) >= 3 and len(data.indices) >= 3:
                preview.set_mesh(data.vertices, data.indices, normals=data.normals)

        ext = os.path.splitext(self._asset_path)[1].lower()
        if ext == ".obj":
            load_obj_async(self._asset_path, _on_mesh_loaded)
        else:
            load_mesh_async(self._asset_path, _on_mesh_loaded)

        from core.config import get_global_config
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings = json.load(f)
            except: pass
        scale_sb = QDoubleSpinBox()
        scale_sb.setRange(0.001, 1000.0)
        scale_sb.setSingleStep(0.1)
        scale_sb.setValue(settings.get("scale", 1.0))
        scale_sb.valueChanged.connect(lambda v: self._save_import_setting("scale", v))
        self._build_labeled_field("Scale Factor", scale_sb)
        pivot_cb = QCheckBox()
        pivot_cb.setChecked(settings.get("center_pivot", False))
        pivot_cb.toggled.connect(lambda v: self._save_import_setting("center_pivot", v))
        self._build_labeled_field("Center Pivot", pivot_cb)
        flip_uv_cb = QCheckBox()
        flip_uv_cb.setChecked(settings.get("flip_uvs", False))
        flip_uv_cb.toggled.connect(lambda v: self._save_import_setting("flip_uvs", v))
        self._build_labeled_field("Flip UVs", flip_uv_cb)
        smooth_sb = QDoubleSpinBox()
        smooth_sb.setRange(0.0, 180.0)
        smooth_sb.setSingleStep(1.0)
        smooth_sb.setDecimals(1)
        smooth_sb.setValue(settings.get("smooth_angle", 30.0))
        smooth_sb.valueChanged.connect(lambda v: self._save_import_setting("smooth_angle", v))
        self._build_labeled_field("Smooth Angle", smooth_sb)
        gen_nrm = QCheckBox()
        gen_nrm.setChecked(settings.get("gen_normals", True))
        gen_nrm.toggled.connect(lambda v: self._save_import_setting("gen_normals", v))
        self._build_labeled_field("Generate Normals", gen_nrm)
        gen_uv = QCheckBox()
        gen_uv.setChecked(settings.get("gen_uvs", True))
        gen_uv.toggled.connect(lambda v: self._save_import_setting("gen_uvs", v))
        self._build_labeled_field("Generate UVs", gen_uv)

    def _build_texture_import_settings(self):
        import json, os
        from core.texture_import_settings import DEFAULT_SETTINGS
        cache_path = self._asset_path + ".import"
        settings = dict(DEFAULT_SETTINGS)
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings.update(json.load(f))
            except: pass

        # Texture Type
        type_cb = QComboBox()
        type_cb.addItems(["albedo", "normal", "metallic", "roughness", "ao", "emission", "sprite"])
        type_cb.setCurrentText(settings.get("type", "albedo"))
        type_cb.currentTextChanged.connect(lambda v: self._save_import_setting("type", v))
        self._build_labeled_field("Texture Type", type_cb)

        # sRGB
        srgb = QCheckBox()
        srgb.setChecked(settings.get("srgb", True))
        srgb.toggled.connect(lambda v: self._save_import_setting("srgb", v))
        self._build_labeled_field("sRGB", srgb)

        # Filter Mode
        filter_cb = QComboBox()
        filter_cb.addItems(["point", "bilinear", "trilinear"])
        filter_cb.setCurrentText(settings.get("filter_mode", "trilinear"))
        filter_cb.currentTextChanged.connect(lambda v: self._save_import_setting("filter_mode", v))
        self._build_labeled_field("Filter Mode", filter_cb)

        # Anisotropic Filtering
        aniso_cb = QComboBox()
        aniso_cb.addItems(["1 (Off)", "2", "4", "8", "16"])
        aniso_val = settings.get("anisotropic", 1)
        aniso_cb.setCurrentIndex({1:0, 2:1, 4:2, 8:3, 16:4}.get(aniso_val, 0))
        def _on_aniso(v):
            mapping = [1, 2, 4, 8, 16]
            self._save_import_setting("anisotropic", mapping[aniso_cb.currentIndex()])
        aniso_cb.currentIndexChanged.connect(_on_aniso)
        self._build_labeled_field("Aniso Level", aniso_cb)

        # Max Texture Size
        max_sb = QSpinBox()
        max_sb.setRange(32, 8192)
        max_sb.setSingleStep(2)
        max_sb.setValue(settings.get("max_size", 2048))
        max_sb.valueChanged.connect(lambda v: self._save_import_setting("max_size", v))
        self._build_labeled_field("Max Size", max_sb)

        # Wrap Mode
        wrap_cb = QComboBox()
        wrap_cb.addItems(["clamp", "repeat", "mirrored_repeat"])
        wrap_cb.setCurrentText(settings.get("wrap_mode", "clamp"))
        wrap_cb.currentTextChanged.connect(lambda v: self._save_import_setting("wrap_mode", v))
        self._build_labeled_field("Wrap Mode", wrap_cb)

        # Compression
        comp_cb = QComboBox()
        comp_cb.addItems(["none", "low", "normal", "high"])
        comp_cb.setCurrentText(settings.get("compression", "none"))
        comp_cb.currentTextChanged.connect(lambda v: self._save_import_setting("compression", v))
        self._build_labeled_field("Compression", comp_cb)

    def _build_audio_import_settings(self):
        import json, os
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings = json.load(f)
            except: pass
        qual_sb = QSpinBox()
        qual_sb.setRange(0, 100)
        qual_sb.setValue(settings.get("quality", 80))
        qual_sb.valueChanged.connect(lambda v: self._save_import_setting("quality", v))
        self._build_labeled_field("Quality", qual_sb)
        stream_cb = QCheckBox()
        stream_cb.setChecked(settings.get("stream", False))
        stream_cb.toggled.connect(lambda v: self._save_import_setting("stream", v))
        self._build_labeled_field("Stream", stream_cb)

    def _save_import_setting(self, key: str, value):
        import json, os
        if not self._asset_path: return
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings = json.load(f)
            except: pass
        settings[key] = value
        try:
            with open(cache_path, "w") as f:
                json.dump(settings, f, indent=2)
        except: pass

    def _build_material_editor(self):
        from core.material import Material
        from editor.material_preview import MaterialPreviewWidget
        try:
            mat = Material.load(self._asset_path, self._engine.project_root if self._engine else "")
        except Exception:
            mat = None
        if mat is None:
            lbl = QLabel("Failed to load material.")
            lbl.setStyleSheet(f"color: {_FUSION_ACCENT_RED};")
            self._add_asset_widget(lbl)
            return
        props = mat.properties

        shader_props = mat._shader_properties

        # Preview widget only for materials with known previewable properties
        preview = MaterialPreviewWidget()
        preview.setFixedHeight(200)
        preview_vals = {}
        ac = props.get("albedo_color") or props.get("_BaseColor")
        if ac:
            preview_vals["albedo"] = ac[:3] if len(ac) >= 3 else [1.0, 1.0, 1.0]
        m = props.get("metallic") if "metallic" in props else props.get("_Metallic")
        if m is not None:
            preview_vals["metallic"] = m
        s = props.get("smoothness") if "smoothness" in props else props.get("_Smoothness")
        if s is not None:
            preview_vals["smoothness"] = s
        ec = props.get("emission_color") or props.get("_EmissionColor")
        if ec:
            preview_vals["emission"] = ec
        ei = props.get("emission_intensity") if "emission_intensity" in props else props.get("_EmissionIntensity")
        if ei is not None:
            preview_vals["emit_intensity"] = ei
        for tex_key in ("albedo_texture", "_BaseMap", "_BaseTex"):
            if tex_key in props and props[tex_key]:
                preview_vals["albedo_tex"] = props[tex_key]
                break
        if preview_vals:
            preview.set_properties(**preview_vals)
        self._add_asset_widget(preview)

        def _save():
            mat.save(self._asset_path, self._engine.project_root)

        def _update_preview():
            pv = {}
            ac = props.get("albedo_color") or props.get("_BaseColor")
            if ac:
                pv["albedo"] = ac[:3] if len(ac) >= 3 else [1.0, 1.0, 1.0]
            m = props.get("metallic") if "metallic" in props else props.get("_Metallic")
            if m is not None:
                pv["metallic"] = m
            s = props.get("smoothness") if "smoothness" in props else props.get("_Smoothness")
            if s is not None:
                pv["smoothness"] = s
            ec = props.get("emission_color") or props.get("_EmissionColor")
            if ec:
                pv["emission"] = ec
            ei = props.get("emission_intensity") if "emission_intensity" in props else props.get("_EmissionIntensity")
            if ei is not None:
                pv["emit_intensity"] = ei
            for tex_key in ("albedo_texture", "_BaseMap", "_BaseTex"):
                if tex_key in props and props[tex_key]:
                    pv["albedo_tex"] = props[tex_key]
                    break
            if pv:
                preview.set_properties(**pv)

        # Shader picker
        shader_row = QWidget()
        shader_rl = QHBoxLayout(shader_row)
        shader_rl.setContentsMargins(0, 2, 0, 2)
        shader_lbl = QLabel("Shader")
        shader_lbl.setFixedWidth(scale(120))
        shader_lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px;")
        shader_rl.addWidget(shader_lbl)
        def _on_shader_pick(p):
            mat.shader_path = p
            mat.load_shader_properties(p, self._engine.project_root)
            props.clear()
            for sp in mat._shader_properties:
                props[sp.name] = sp.default_value
            _save()
            self._rebuild()
        shader_picker = _make_resource_picker(mat.shader_path, "Shaders (*.shader *.vert *.frag)", _on_shader_pick)
        shader_rl.addWidget(shader_picker, 1)
        self._add_asset_widget(shader_row)

        # Build property widgets from shader properties
        if shader_props:
            # Group properties by category
            tex_props = [p for p in shader_props if p.prop_type in ("2D", "cube")]
            non_tex_props = [p for p in shader_props if p.prop_type not in ("2D", "cube")]

            for sp in non_tex_props:
                self._add_shader_property_widget(sp, props, _save, _update_preview)

            if tex_props:
                sep = QLabel("<b>Textures</b>")
                sep.setStyleSheet(f"color: {_FUSION_TEXT}; padding: 4px 0; font-size: 11px;")
                self._add_asset_widget(sep)
                for sp in tex_props:
                    self._add_shader_property_widget(sp, props, _save, _update_preview)
        else:
            # Fallback for materials without .shader properties: show known keys
            known_keys = {
                "albedo_color": {"label": "Albedo", "widget": "color"},
                "albedo_texture": {"label": "Albedo Map", "widget": "texture"},
                "metallic": {"label": "Metallic", "widget": "slider", "min": 0, "max": 1, "step": 0.01},
                "smoothness": {"label": "Smoothness", "widget": "slider", "min": 0, "max": 1, "step": 0.01},
                "emission_color": {"label": "Emission", "widget": "color"},
                "emission_intensity": {"label": "Emission Intensity", "widget": "slider", "min": 0, "max": 100, "step": 0.1},
                "normal_texture": {"label": "Normal Map", "widget": "texture"},
                "roughness_texture": {"label": "Roughness Map", "widget": "texture"},
            }
            tex_seen = False
            for key, cfg in known_keys.items():
                if cfg["widget"] == "texture" and not tex_seen:
                    sep = QLabel("<b>Textures</b>")
                    sep.setStyleSheet(f"color: {_FUSION_TEXT}; padding: 4px 0; font-size: 11px;")
                    self._add_asset_widget(sep)
                    tex_seen = True
                self._add_fallback_widget(key, cfg, props, _save, _update_preview)

        self._add_asset_widget(QLabel(""))

    def _add_shader_property_widget(self, sp, props, _save, _update_preview):
        """Build a widget for a ShaderProperty from a .shader file."""
        from editor.resource_picker import pick_resource
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor

        prop_type = sp.prop_type
        key = sp.name
        label = sp.display_name

        if prop_type in ("2D", "cube"):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            row.setStyleSheet("background: transparent;")
            lbl = QLabel(label)
            lbl.setFixedWidth(scale(120))
            lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
            rl.addWidget(lbl)
            def _on_pick(p):
                props[key] = p
                _save()
                _update_preview()
            picker = _make_resource_picker(props.get(key, ""), "Images (*.png *.jpg *.jpeg)", _on_pick)
            rl.addWidget(picker, 1)
            self._add_asset_widget(row)

        elif prop_type == "Color":
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl.setFixedWidth(scale(120))
            lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
            rl.addWidget(lbl)
            val = props.get(key, [1.0, 1.0, 1.0, 1.0])
            swatch = QPushButton()
            swatch.setFixedSize(*scale_xy(28, 22))
            r = int(val[0]*255) if len(val) > 0 else 255
            g = int(val[1]*255) if len(val) > 1 else 255
            b = int(val[2]*255) if len(val) > 2 else 255
            a = int(val[3]*255) if len(val) > 3 else 255
            swatch.setStyleSheet(f"background: rgba({r},{g},{b},{a}); border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: {_FUSION_INPUT_RADIUS};")
            def _pick_color(_key=key):
                cv = props.get(_key, [1,1,1,1])
                cr = int(cv[0]*255) if len(cv) > 0 else 255
                cg = int(cv[1]*255) if len(cv) > 1 else 255
                cb = int(cv[2]*255) if len(cv) > 2 else 255
                c = QColorDialog.getColor(QColor(cr, cg, cb))
                if c.isValid():
                    new_val = [c.red()/255.0, c.green()/255.0, c.blue()/255.0]
                    if len(cv) > 3:
                        new_val.append(float(cv[3]))
                    else:
                        new_val.append(1.0)
                    props[_key] = new_val
                    swatch.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},{int(new_val[3]*255)}); border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: {_FUSION_INPUT_RADIUS};")
                    _save()
                    _update_preview()
            swatch.clicked.connect(_pick_color)
            rl.addWidget(swatch)
            rl.addStretch()
            self._add_asset_widget(row)

        elif prop_type == "Range":
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl.setFixedWidth(scale(120))
            lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
            rl.addWidget(lbl)
            sb = QDoubleSpinBox()
            sb.setRange(sp.range_min, sp.range_max)
            sb.setSingleStep((sp.range_max - sp.range_min) / 100.0)
            sb.setValue(props.get(key, 0.0))
            def _on_change(v, _key=key):
                props[_key] = v
                _save()
                _update_preview()
            sb.valueChanged.connect(_on_change)
            rl.addWidget(sb, 1)
            self._add_asset_widget(row)

        elif prop_type in ("Float", "Int"):
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl.setFixedWidth(scale(120))
            lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
            rl.addWidget(lbl)
            if prop_type == "Int":
                sb = QSpinBox()
                sb.setRange(-999999, 999999)
            else:
                sb = QDoubleSpinBox()
                sb.setRange(-999999.0, 999999.0)
                sb.setSingleStep(0.1)
            sb.setValue(props.get(key, 0))
            def _on_change(v, _key=key):
                props[_key] = v
                _save()
                _update_preview()
            sb.valueChanged.connect(_on_change)
            rl.addWidget(sb, 1)
            self._add_asset_widget(row)

    def _add_fallback_widget(self, key, cfg, props, _save, _update_preview):
        """Build a widget for a known fallback property key."""
        from editor.resource_picker import pick_resource
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor

        label = cfg["label"]
        widget_type = cfg["widget"]

        if widget_type == "texture":
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl.setFixedWidth(scale(120))
            lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
            rl.addWidget(lbl)
            def _on_pick(p, _key=key):
                props[_key] = p
                _save()
                _update_preview()
            picker = _make_resource_picker(props.get(key, ""), "Images (*.png *.jpg *.jpeg)", _on_pick)
            rl.addWidget(picker, 1)
            self._add_asset_widget(row)

        elif widget_type == "color":
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl.setFixedWidth(scale(120))
            lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
            rl.addWidget(lbl)
            val = props.get(key, [1.0, 1.0, 1.0, 1.0])
            swatch = QPushButton()
            swatch.setFixedSize(*scale_xy(28, 22))
            r = int(val[0]*255) if len(val) > 0 else 255
            g = int(val[1]*255) if len(val) > 1 else 255
            b = int(val[2]*255) if len(val) > 2 else 255
            swatch.setStyleSheet(f"background: rgba({r},{g},{b},255); border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: {_FUSION_INPUT_RADIUS};")
            def _pick_color(_key=key):
                cv = props.get(_key, [1,1,1,1])
                cr = int(cv[0]*255) if len(cv) > 0 else 255
                cg = int(cv[1]*255) if len(cv) > 1 else 255
                cb = int(cv[2]*255) if len(cv) > 2 else 255
                c = QColorDialog.getColor(QColor(cr, cg, cb))
                if c.isValid():
                    new_val = [c.red()/255.0, c.green()/255.0, c.blue()/255.0]
                    if len(cv) > 3:
                        new_val.append(float(cv[3]))
                    else:
                        new_val.append(1.0)
                    props[_key] = new_val
                    swatch.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},255); border: 1px solid {_FUSION_BORDER_LIGHT}; border-radius: {_FUSION_INPUT_RADIUS};")
                    _save()
                    _update_preview()
            swatch.clicked.connect(_pick_color)
            rl.addWidget(swatch)
            rl.addStretch()
            self._add_asset_widget(row)

        elif widget_type == "slider":
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl.setFixedWidth(scale(120))
            lbl.setStyleSheet(f"color: {_FUSION_TEXT}; font-size: 11px; background: transparent;")
            rl.addWidget(lbl)
            sb = QDoubleSpinBox()
            sb.setRange(cfg.get("min", 0.0), cfg.get("max", 1.0))
            sb.setSingleStep(cfg.get("step", 0.01))
            sb.setValue(props.get(key, 0.0))
            def _on_change(v, _key=key):
                props[_key] = v
                _save()
                _update_preview()
            sb.valueChanged.connect(_on_change)
            rl.addWidget(sb, 1)
            self._add_asset_widget(row)

    def _build_animator_state_inspector(self, state: AnimatorState):
        self._build_section_title(f"State: {state.name}")
        name_edit = QLineEdit(state.name)
        name_edit.setStyleSheet(self._animator_input_style())
        name_edit.textChanged.connect(lambda t: self._on_animator_state_name_changed(state, t))
        self._content_layout.addWidget(QLabel("Name"))
        self._content_layout.addWidget(name_edit)
        speed_sb = QDoubleSpinBox()
        speed_sb.setRange(-100.0, 100.0)
        speed_sb.setValue(state.speed)
        speed_sb.valueChanged.connect(lambda v: setattr(state, 'speed', v))
        speed_sb.setStyleSheet(self._animator_input_style())
        self._content_layout.addWidget(QLabel("Speed"))
        self._content_layout.addWidget(speed_sb)
        tag_edit = QLineEdit(state.tag)
        tag_edit.setStyleSheet(self._animator_input_style())
        tag_edit.textChanged.connect(lambda t: setattr(state, 'tag', t))
        self._content_layout.addWidget(QLabel("Tag"))
        self._content_layout.addWidget(tag_edit)

    def _build_animator_transition_inspector(self, trans: AnimatorTransition):
        self._build_section_title("Transition")
        dur_sb = QDoubleSpinBox()
        dur_sb.setRange(0.0, 10.0)
        dur_sb.setSingleStep(0.05)
        dur_sb.setValue(trans.transition_duration)
        dur_sb.valueChanged.connect(lambda v: setattr(trans, 'transition_duration', v))
        dur_sb.setStyleSheet(self._animator_input_style())
        self._content_layout.addWidget(QLabel("Duration"))
        self._content_layout.addWidget(dur_sb)
        exit_sb = QDoubleSpinBox()
        exit_sb.setRange(0.0, 1.0)
        exit_sb.setSingleStep(0.05)
        exit_sb.setValue(trans.exit_time)
        exit_sb.valueChanged.connect(lambda v: setattr(trans, 'exit_time', v))
        exit_sb.setStyleSheet(self._animator_input_style())
        self._content_layout.addWidget(QLabel("Exit Time"))
        self._content_layout.addWidget(exit_sb)
        has_exit_cb = QCheckBox("Has Exit Time")
        has_exit_cb.setChecked(trans.has_exit_time)
        has_exit_cb.toggled.connect(lambda v: setattr(trans, 'has_exit_time', v))
        has_exit_cb.setStyleSheet("color: #ccc; font-size: 10px;")
        self._content_layout.addWidget(has_exit_cb)
        fixed_dur_cb = QCheckBox("Fixed Duration")
        fixed_dur_cb.setChecked(trans.has_fixed_duration)
        fixed_dur_cb.toggled.connect(lambda v: setattr(trans, 'has_fixed_duration', v))
        fixed_dur_cb.setStyleSheet("color: #ccc; font-size: 10px;")
        self._content_layout.addWidget(fixed_dur_cb)
        self._build_section_title("Conditions")
        for cond in trans.conditions:
            self._build_animator_condition_row(trans, cond)
        add_cond_btn = QPushButton("+ Add Condition")
        add_cond_btn.clicked.connect(lambda: self._add_animator_condition(trans))
        add_cond_btn.setStyleSheet(self._animator_btn_style())
        self._content_layout.addWidget(add_cond_btn)

    def _build_animator_condition_row(self, trans, cond):
        row = QHBoxLayout()
        param_combo = QComboBox()
        ctrl = self._animator_controller
        if ctrl:
            for p in ctrl.parameters:
                param_combo.addItem(p.name)
        param_combo.setCurrentText(cond.parameter)
        param_combo.textActivated.connect(lambda text, c=cond: setattr(c, 'parameter', text))
        param_combo.setStyleSheet(self._animator_input_style())
        row.addWidget(param_combo)
        mode_combo = QComboBox()
        modes = ["if", "if_not", "greater", "less", "equals", "not_equal"]
        mode_combo.addItems(modes)
        mode_combo.setCurrentText(cond.mode.value)
        mode_combo.textActivated.connect(lambda text, c=cond: setattr(c, 'mode', AnimatorConditionMode(text)))
        mode_combo.setStyleSheet(self._animator_input_style())
        row.addWidget(mode_combo)
        thresh_sb = QDoubleSpinBox()
        thresh_sb.setRange(-99999.0, 99999.0)
        thresh_sb.setValue(cond.threshold)
        thresh_sb.valueChanged.connect(lambda v, c=cond: setattr(c, 'threshold', v))
        thresh_sb.setStyleSheet(self._animator_input_style())
        row.addWidget(thresh_sb)
        del_btn = QPushButton("x")
        del_btn.setFixedSize(*scale_xy(20, 20))
        del_btn.clicked.connect(lambda: self._remove_animator_condition(trans, cond))
        del_btn.setStyleSheet("QPushButton { color: #c66; border: none; font-size: 10px; } QPushButton:hover { color: #f88; }")
        row.addWidget(del_btn)
        self._content_layout.addLayout(row)

    def _add_animator_condition(self, trans):
        trans.conditions.append(AnimatorCondition())
        self._rebuild()

    def _remove_animator_condition(self, trans, cond):
        if cond in trans.conditions:
            trans.conditions.remove(cond)
        self._rebuild()

    def _on_animator_state_name_changed(self, state, new_name):
        old_name = state.name
        state.name = new_name
        self._rebuild()

    def _build_section_title(self, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #aaa; font-size: 10px; font-weight: bold; padding: 4px 0;")
        self._content_layout.addWidget(lbl)

    def _animator_input_style(self) -> str:
        return f"background: {_FUSION_BG_INPUT}; color: {_FUSION_TEXT}; border: 1px solid {_FUSION_BORDER}; border-radius: {_FUSION_INPUT_RADIUS}; padding: 2px 4px; font-size: 10px;"

    def _animator_btn_style(self) -> str:
        return (f"QPushButton {{ background: #3a3a3a; color: {_FUSION_TEXT}; border: 1px solid #555; "
                f"border-radius: 3px; font-size: 10px; padding: 2px 8px; }} "
                f"QPushButton:hover {{ background: #4a4a4a; }}")

    def _rebuild(self):
        self._content_widget.setVisible(False)
        try:
            self._updating = True
            for w in self._comp_widgets:
                w.hide()
                w.deleteLater()
            self._comp_widgets.clear()
            while self._content_layout.count():
                item = self._content_layout.takeAt(0)
                if item and item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            self._asset_widgets.clear()
            stretch = self._content_layout.takeAt(self._content_layout.count() - 1)
            if self._animator_mode:
                self._header_widget.setVisible(False)
                self._add_comp_btn.setVisible(False)
                if self._animator_state:
                    self._build_animator_state_inspector(self._animator_state)
                elif self._animator_transition:
                    self._build_animator_transition_inspector(self._animator_transition)
                self._content_layout.addStretch()
                return
            if self._asset_path:
                self._header_widget.setVisible(False)
                self._add_comp_btn.setVisible(False)
                self._build_import_settings()
                self._content_layout.addStretch()
                return
            if not self._entity:
                self._header_widget.setVisible(False)
                self._add_comp_btn.setVisible(False)
                self._content_layout.addStretch()
                return
            self._header_widget.setVisible(True)
            self._add_comp_btn.setVisible(True)
            if self._entity.is_prefab_instance:
                from core.prefab import Prefab, PrefabLibrary
                prefab_path = PrefabLibrary.path_for_guid(self._entity._prefab_guid)
                overrides = Prefab.compute_all_overrides([self._entity])
                prefab_name = prefab_path.replace("\\", "/").split("/")[-1] if prefab_path else "Prefab"
                self._prefab_label.setText(f"Prefab: {prefab_name}")
                if overrides:
                    self._override_label.setText(f"({len(overrides)} override{'s' if len(overrides) != 1 else ''})")
                    self._override_label.setVisible(True)
                else:
                    self._override_label.setVisible(False)
                self._prefab_bar_widget.setVisible(True)
            else:
                self._prefab_bar_widget.setVisible(False)
            for i in range(self._header_widget.layout().count() - 1, -1, -1):
                item = self._header_widget.layout().itemAt(i)
                if item and item.widget() and item.widget().property("is_multi_label"):
                    item.widget().deleteLater()
            if len(self._selected_entities) > 1:
                multi_label = QLabel(f"({len(self._selected_entities)} selected)")
                multi_label.setProperty("is_multi_label", True)
                multi_label.setStyleSheet(f"color: {_accent()}; font-size: 11px; padding: 2px 0; background: transparent;")
                self._header_widget.layout().insertWidget(0, multi_label)
            self._active_cb.setChecked(self._entity.active)
            self._name_edit.setText(self._entity.name)
            tags = ", ".join(self._entity.tags)
            self._tag_edit.setText(tags)
            self._layer_sb.setValue(self._entity.layer)
            rev_map = {id(c): k for k, c in self._entity._components.items()}
            comps = self._entity.get_all_components()
            for idx, comp in enumerate(comps):
                try:
                    key = rev_map.get(id(comp), "")
                    cw = ComponentWidget(comp, self._entity, self._selected_entities, self._content_widget, component_key=key)
                    cw.remove_requested.connect(self._remove_component)
                    cw.move_up_requested.connect(self._move_component_up)
                    cw.move_down_requested.connect(self._move_component_down)
                    cw.reorder_requested.connect(self._on_reorder_component)
                    cw._move_up_btn.setEnabled(idx > 0)
                    cw._move_down_btn.setEnabled(idx < len(comps) - 1)
                    self._content_layout.addWidget(cw)
                    self._comp_widgets.append(cw)
                except Exception as e:
                    Logger.error(f"Inspector build error for {type(comp).__name__}: {e}", e)
            self._content_layout.addStretch()
        finally:
            self._updating = False
            self._content_widget.setVisible(True)

    def _refresh_transform(self):
        for cw in self._comp_widgets:
            ctype = type(cw._component).__name__
            if ctype == "Transform":
                try: cw.refresh_transform()
                except: pass
            else:
                fields = getattr(type(cw._component), "_inspector_fields", lambda: [])()
                for f in fields:
                    if f.field_type.value == "vec2":
                        try: cw.refresh_vec2_field(f.name)
                        except: pass
                    elif f.field_type.value == "vec3":
                        try: cw.refresh_vec3_field(f.name)
                        except: pass

    def _on_active_changed(self, checked: bool):
        if self._updating or not self._entity: return
        old = not checked
        self._entity.active = checked
        get_history().execute(SetComponentCommand(self._entity, type(self._entity), "active", old, checked))

    def _on_name_changed(self, text: str):
        if self._updating or not self._entity: return
        old = self._entity.name
        self._entity.name = text
        get_history().execute(SetComponentCommand(self._entity, type(self._entity), "name", old, text))
        if self._engine.scene: self._engine.scene.mark_dirty()

    def _on_tag_changed(self, text: str):
        if self._updating or not self._entity: return
        old = set(self._entity.tags)
        self._entity._tags = set(t.strip() for t in text.split(",") if t.strip())
        get_history().execute(SetComponentCommand(self._entity, type(self._entity), "tags", old, set(self._entity.tags)))

    def _on_layer_changed(self, val: int):
        if self._updating or not self._entity: return
        old = self._entity.layer
        self._entity.layer = val
        get_history().execute(SetComponentCommand(self._entity, type(self._entity), "layer", old, val))

    def _remove_component(self, comp_name: str, comp_key: str = ""):
        if not self._entity: return
        from core.ecs import ComponentRegistry
        from core.commands import RemoveComponentCommand
        cls = ComponentRegistry.get(comp_name)
        if cls:
            cmd = RemoveComponentCommand(self._entity, cls, component_key=comp_key)
            get_history().execute(cmd)
        self._rebuild()
        self._send_collab_component_remove(comp_key or comp_name)

    def _on_reorder_component(self, source_eid: str, dragged_key: str, target_key: str):
        if not self._entity or self._entity.id != source_eid:
            return
        keys = list(self._entity._components.keys())
        if dragged_key not in keys or target_key not in keys:
            return
        dragged_idx = keys.index(dragged_key)
        target_idx = keys.index(target_key)
        if dragged_idx == target_idx:
            return
        keys.remove(dragged_key)
        new_pos = keys.index(target_key)
        keys.insert(new_pos + 1 if dragged_idx < target_idx else new_pos, dragged_key)
        self._entity._components = {k: self._entity._components[k] for k in keys}
        self._rebuild()

    def _move_component_up(self, comp_key: str):
        if not self._entity: return
        self._entity.move_component(comp_key, -1)
        self._rebuild()

    def _move_component_down(self, comp_key: str):
        if not self._entity: return
        self._entity.move_component(comp_key, 1)
        self._rebuild()

    def _show_add_component_menu(self):
        if not self._entity: return
        dlg = ComponentPickerDialog(self._entity, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.selected_result()
            if result and result["type"] == "component":
                self._add_component(result["name"])
            elif result and result["type"] == "script":
                self._add_script_component(result["path"])

    def _send_collab_component_add(self, comp_name: str, added_key: str):
        if not self._entity or not hasattr(self, '_engine') or not self._engine:
            return
        collab = self._engine.collab_manager if hasattr(self._engine, 'collab_manager') else None
        if not collab or not collab.connected:
            return
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(comp_name)
        if not cls:
            return
        comp_key = added_key or next((k for k in self._entity._components if k == comp_name or k.startswith(comp_name + ".")), None)
        comp = self._entity._components.get(comp_key) if comp_key else None
        if not comp:
            return
        comp_data = comp.serialize() if hasattr(comp, 'serialize') else {}
        if not comp_data:
            comp_data = {}
            for attr in dir(comp):
                if attr.startswith('_'): continue
                v = getattr(comp, attr)
                if callable(v): continue
                comp_data[attr] = v
        collab.send_component_add(self._entity.id, comp_name, comp_data)

    def _send_collab_component_remove(self, comp_key: str):
        if not self._entity or not hasattr(self, '_engine') or not self._engine:
            return
        collab = self._engine.collab_manager if hasattr(self._engine, 'collab_manager') else None
        if not collab or not collab.connected:
            return
        collab.send_component_remove(self._entity.id, comp_key)

    def _add_component(self, comp_name: str):
        if not self._entity: return
        from core.ecs import ComponentRegistry
        from core.commands import AddComponentCommand
        cls = ComponentRegistry.get(comp_name)
        if cls:
            can_multiple = getattr(cls, '_allow_multiple', False)
            if not can_multiple and self._entity.has_component(cls):
                return
            cmd = AddComponentCommand(self._entity, cls)
            get_history().execute(cmd)
            self._rebuild()
            self._send_collab_component_add(comp_name, cmd._added_key)

    def _add_script_component(self, script_path: str):
        if not self._entity: return
        from core.components.scripting.script_component import ScriptComponent
        from core.commands import AddComponentCommand
        cmd = AddComponentCommand(self._entity, ScriptComponent)
        get_history().execute(cmd)
        found = self._entity.get_components(ScriptComponent)
        if found:
            import os
            root = self._engine.project_root
            try:
                rel = os.path.relpath(script_path, root)
                found[-1].script_path = rel.replace("\\", "/") if not rel.startswith("..") else os.path.abspath(script_path)
            except ValueError:
                found[-1].script_path = os.path.abspath(script_path)
            self._rebuild()
        self._send_collab_component_add("ScriptComponent", cmd._added_key)

    def _get_prefab_roots(self, entity) -> list:
        roots = []
        seen = set()
        def walk(e):
            if e.id in seen:
                return
            seen.add(e.id)
            if e.is_prefab_instance and e._prefab_guid == entity._prefab_guid:
                p = e._parent
                while p and p.is_prefab_instance and p._prefab_guid == e._prefab_guid:
                    p = p._parent
                if p is None or not p.is_prefab_instance or p._prefab_guid != e._prefab_guid:
                    roots.append(e)
            for c in e.children:
                walk(c)
        walk(entity)
        if not roots and entity.is_prefab_instance:
            roots = [entity]
        return roots

    def _on_apply_prefab(self):
        if not self._entity or not self._entity.is_prefab_instance:
            return
        from core.prefab import Prefab, PrefabLibrary
        from core.logger import Logger
        prefab_path = PrefabLibrary.path_for_guid(self._entity._prefab_guid)
        if not prefab_path:
            Logger.warning("Cannot find prefab asset for this instance.")
            return
        roots = self._get_prefab_roots(self._entity)
        all_entities = []
        def collect(e):
            all_entities.append(e)
            for c in e.children:
                collect(c)
        for r in roots:
            collect(r)
        current_data = {}
        for e in all_entities:
            current_data[e.id] = e.serialize()
        pref = Prefab(self._entity.name, self._entity._prefab_guid)
        pref.roots_data = [current_data[r.id] for r in roots]
        pref.save(prefab_path)
        PrefabLibrary.invalidate(prefab_path)
        self._rebuild()

    def _on_revert_prefab(self):
        if not self._entity or not self._entity.is_prefab_instance:
            return
        from core.commands import RevertPrefabInstanceCommand, get_history
        scene = self._engine.scene if hasattr(self._engine, 'scene') else None
        if not scene:
            return
        roots = self._get_prefab_roots(self._entity)
        cmd = RevertPrefabInstanceCommand(scene, roots)
        get_history().execute(cmd)
        self._rebuild()

    def _on_select_prefab_asset(self):
        if not self._entity or not self._entity.is_prefab_instance:
            return
        from core.prefab import PrefabLibrary
        prefab_path = PrefabLibrary.path_for_guid(self._entity._prefab_guid)
        if prefab_path:
            self.show_import_settings(prefab_path)
