# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from typing import Optional, Callable
import qtawesome as qta
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QPushButton, QDoubleSpinBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from core.config.editor_scale import scale, scale_xy
from editor.inspector.constants import _XYZ_COLORS, _accent
from editor.inspector.widgets import _FocusSpinBox, _DragLabel
from core.maths.math3d import Vec2, Vec3, Vec4
from editor.inspector.helpersp.navigation import _PROJECT_ROOT

_PICKER_BTN_STYLE = """
    QPushButton {
        background: transparent; border: 1px solid palette(mid);
        border-radius: 3px; padding: 0px; font-size: 10px;
    }
    QPushButton:hover { background: palette(light); border-color: palette(highlight); }
    QPushButton:pressed { background: palette(dark); }
"""

def _style_picker_btn(btn):
    btn.setStyleSheet(_PICKER_BTN_STYLE)

_SPIN_MIN = -9223372036854775808.0
_SPIN_MAX = 9223372036854775807.0

def make_spinbox(val: float, lo: float = _SPIN_MIN, hi: float = _SPIN_MAX, step: float = 0.1, decimals: int = 4) -> QDoubleSpinBox:
    sb = _FocusSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    sb.setValue(val)
    sb.setMinimumWidth(60)
    return sb

def make_clickable_label(text: str, on_click: Callable[[], None]) -> QLabel:
    lbl = QLabel(f"  {text}")
    lbl.setStyleSheet(f"""
        QLabel {{
            color: {_accent()};
            font-size: 9px;
            padding: 0px;
        }}
    """)
    lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    lbl.setToolTip("Click to view source code")
    lbl.mousePressEvent = lambda e: on_click()
    return lbl

def get_component_icon_pixmap(cls, size: int = 16) -> QPixmap:
    icon_name = getattr(cls, '_icon', None)
    if icon_name:
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'core', 'components', 'icons')
        icon_path = os.path.join(icons_dir, icon_name)
        if os.path.exists(icon_path):
            return QPixmap(icon_path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    gizmo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'gizmo_icons')
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

def update_resource_icon(icon_lbl: QLabel, path: str, size: int):
    if path and os.path.exists(path):
        ext = os.path.splitext(path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tga"):
            pix = QPixmap(path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(pix)
            return
    icon_lbl.clear()
    icon_lbl.setText("")

_COMMON_EXT = (".fbx", ".obj", ".stl", ".gltf", ".glb", ".usdz",
               ".png", ".jpg", ".jpeg", ".bmp", ".tga",
               ".wav", ".mp3", ".ogg", ".flac",
               ".py",
               ".mat",
               ".zphysmat",
               ".shader", ".vert", ".frag")

def _is_path_valid(p: str) -> bool:
    if not p:
        return False
    p = os.path.normpath(p)
    if os.path.exists(p):
        return True
    for ext in _COMMON_EXT:
        if os.path.exists(p + ext):
            return True
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng and eng.project_root:
            root = eng.project_root
            for ext in ("",) + _COMMON_EXT:
                if os.path.exists(os.path.normpath(os.path.join(root, p + ext))):
                    return True
    except Exception:
        pass
    return False

_ERROR_STYLE = """
    QLabel {
        background: ~3d1a1a; color: ~f44747;
        border: 1px solid ~f44747; border-radius: 2px;
        padding: 2px 4px; font-size: 11px;
    }
""".replace("~", chr(35))

_EMPTY_STYLE = """
    QLabel {
        background: ~3d3410; color: ~e0c040;
        border: 1px solid ~b89320; border-radius: 2px;
        padding: 2px 4px; font-size: 11px;
    }
""".replace("~", chr(35))

def _create_asset_dialog(parent, asset_type: str, callback: Callable[[str], None]):
    from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from core.components.scripting.scriptc import RESOURCE_TYPE_FILTERS
    project_root = getattr(parent, '_project_root', os.getcwd())
    name, ok = QInputDialog.getText(parent, f"New {asset_type}", f"Asset name:")
    if not ok or not name.strip():
        return
    fname = name.strip()
    exts = {"animclip": ".animclip", "animcontroller": ".animcontroller", "physicmaterial": ".zphysmat"}
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
    elif asset_type == "physicmaterial":
        from core.assets.physics_material import PhysicsMaterial
        mat = PhysicsMaterial(name.strip())
        mat.save(path)
    callback(path)

def make_vec2_row(label: str, vec: Vec2, callback) -> tuple[QWidget, list[QDoubleSpinBox]]:
    comps = [vec.x, vec.y] if hasattr(vec, "x") else [vec[0], vec[1]]
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    lbl = QLabel(label)
    lbl.setWordWrap(True)
    layout.addWidget(lbl)
    spinboxes = []
    for val, comp_label in zip(comps, ["X", "Y"]):
        lbl_c = QLabel(comp_label)
        lbl_c.setFixedWidth(scale(14))
        color = _XYZ_COLORS.get(comp_label, chr(35) + "aaa")
        lbl_c.setStyleSheet(f"color: {color}; font-weight: bold;")
        sb = make_spinbox(val)
        sb.valueChanged.connect(callback)
        layout.addWidget(lbl_c)
        layout.addWidget(sb)
        spinboxes.append(sb)
    return w, spinboxes

def make_vec3_row(label: str, vec: Vec3, callback, reset_to: Optional[list] = None) -> tuple[QWidget, list[QDoubleSpinBox]]:
    comps = [vec.x, vec.y, vec.z] if hasattr(vec, "x") else list(vec[:3])
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    lbl = QLabel(label)
    lbl.setWordWrap(True)
    layout.addWidget(lbl)
    spinboxes = []
    for val, comp_label in zip(comps, ["X", "Y", "Z"]):
        sb = make_spinbox(val)
        sb.valueChanged.connect(callback)
        lbl_c = _DragLabel(comp_label, _XYZ_COLORS.get(comp_label, chr(35) + "aaa"), sb)
        layout.addWidget(lbl_c)
        layout.addWidget(sb)
        spinboxes.append(sb)
    if reset_to is not None:
        btn = QPushButton(qta.icon("fa5s.undo-alt", color=chr(35) + "d4d4d4"), "")
        btn.setFixedSize(*scale_xy(18, 18))
        btn.setToolTip(f"Reset {label}")
        def _reset():
            for sb, v in zip(spinboxes, reset_to):
                sb.setValue(v)
        btn.clicked.connect(_reset)
        layout.addWidget(btn)
    return w, spinboxes

def make_vec4_row(label: str, vec: Vec4, callback) -> tuple[QWidget, list[QDoubleSpinBox]]:
    comps = [vec.x, vec.y, vec.z, vec.w] if hasattr(vec, "x") else list(vec[:4])
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    lbl = QLabel(label)
    lbl.setWordWrap(True)
    layout.addWidget(lbl)
    spinboxes = []
    for val, comp_label in zip(comps, ["X", "Y", "Z", "W"]):
        sb = make_spinbox(val)
        sb.valueChanged.connect(callback)
        lbl_c = _DragLabel(comp_label, _XYZ_COLORS.get(comp_label, chr(35) + "aaa"), sb)
        layout.addWidget(lbl_c)
        layout.addWidget(sb)
        spinboxes.append(sb)
    return w, spinboxes

def make_vec2_slider_row(label: str, vec: Vec2, callback, lo=0.0, hi=1.0) -> tuple[QWidget, list[QDoubleSpinBox]]:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    if label:
        lbl = QLabel(label)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
    spinboxes = []
    comps = [vec.x, vec.y] if hasattr(vec, "x") else [vec[0], vec[1]]
    for val, comp_label in zip(comps, ["X", "Y"]):
        lbl_c = _DragLabel(comp_label, _XYZ_COLORS.get(comp_label, chr(35) + "aaa"), None)
        layout.addWidget(lbl_c)
        sb = make_spinbox(val, lo, hi, (hi - lo) / 100.0)
        sb.setMinimumWidth(60)
        lbl_c._spinbox = sb
        sb.valueChanged.connect(callback)
        layout.addWidget(sb)
        spinboxes.append(sb)
    return w, spinboxes

def make_vec3_slider_row(label: str, vec: Vec3, callback, lo=0.0, hi=1.0) -> tuple[QWidget, list[QDoubleSpinBox]]:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    if label:
        lbl = QLabel(label)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
    spinboxes = []
    comps = [vec.x, vec.y, vec.z] if hasattr(vec, "x") else list(vec[:3])
    for val, comp_label in zip(comps, ["X", "Y", "Z"]):
        lbl_c = _DragLabel(comp_label, _XYZ_COLORS.get(comp_label, chr(35) + "aaa"), None)
        layout.addWidget(lbl_c)
        sb = make_spinbox(val, lo, hi, (hi - lo) / 100.0)
        sb.setMinimumWidth(60)
        lbl_c._spinbox = sb
        sb.valueChanged.connect(callback)
        layout.addWidget(sb)
        spinboxes.append(sb)
    return w, spinboxes

_SOURCE_PATH_CACHE: dict[type, str] = {}
_LINE_NUM_CACHE: dict[tuple, int] = {}

def get_component_source_path(comp_cls: type) -> str:
    cached = _SOURCE_PATH_CACHE.get(comp_cls)
    if cached is not None:
        return cached
    import inspect
    result = ""
    try:
        file_path = inspect.getfile(comp_cls)
        rel = os.path.relpath(file_path, _PROJECT_ROOT)
        result = rel.replace(os.sep, "/")
    except Exception:
        pass
    _SOURCE_PATH_CACHE[comp_cls] = result
    return result

def get_property_line_number(comp_cls: type, prop_name: str) -> int:
    key = (comp_cls, prop_name)
    cached = _LINE_NUM_CACHE.get(key)
    if cached is not None:
        return cached
    import inspect
    result = 1
    try:
        lines, start_line = inspect.getsourcelines(comp_cls)
        for i, line in enumerate(lines):
            if prop_name in line and ("self." + prop_name) in line:
                result = start_line + i
                break
        else:
            for i, line in enumerate(lines):
                if f"self.{prop_name}" in line or f": {prop_name}" in line:
                    result = start_line + i
                    break
    except Exception:
        pass
    _LINE_NUM_CACHE[key] = result
    return result

def collapse_value(v):
    if hasattr(v, 'to_list'):
        return v.to_list()
    if hasattr(v, '__iter__') and not isinstance(v, (str, bytes, dict)):
        return list(v)
    return v
