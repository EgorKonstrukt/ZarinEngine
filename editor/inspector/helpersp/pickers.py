# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from typing import Callable
import qtawesome as qta
from PyQt6.QtWidgets import QLabel, QWidget, QHBoxLayout, QPushButton, QDialog
from PyQt6.QtCore import Qt
from core.config.editor_scale import scale_xy
from editor.inspector.widgets import _ResourceDropLabel, _EntityDropLabel, EntityPickerDialog
from editor.hover import attach_resource_hover, attach_entity_hover
from editor.inspector.helpersp.navigation import _NavFilter, _navigate_resource, _flash_resource, _navigate_entity, _flash_entity
from editor.inspector.helpersp.vectors import update_resource_icon, _is_path_valid, _ERROR_STYLE, _EMPTY_STYLE, _style_picker_btn, get_component_icon_pixmap, _create_asset_dialog

def make_resource_picker(path: str, filter_str: str, callback: Callable[[str], None]) -> QWidget:
    from editor.picker import pick_resource
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    name = os.path.basename(path) if path else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    layout.addWidget(icon_lbl)
    def _on_resource_drop(p: str):
        _update_display(p)
    name_lbl = _ResourceDropLabel(_on_resource_drop, name if name else "None")
    name_lbl.setMinimumHeight(22)
    name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    name_lbl.installEventFilter(_NavFilter(lambda: _flash_resource(name_lbl), lambda: _navigate_resource(name_lbl), name_lbl))
    layout.addWidget(name_lbl, 1)
    _hover_state = {"path": path}
    def _apply_state(p: str):
        _hover_state["path"] = p
        name_lbl.setText(os.path.basename(p) if p else "None")
        name_lbl.setToolTip(p if p else "No resource selected")
        if _is_path_valid(p):
            name_lbl.setStyleSheet(name_lbl._BASE_STYLE)
            update_resource_icon(icon_lbl, p, 20)
        elif p:
            name_lbl.setStyleSheet(_ERROR_STYLE)
            icon_lbl.setPixmap(qta.icon("fa5s.exclamation-triangle", color=chr(35) + "e74c3c").pixmap(20, 20))
        else:
            name_lbl.setStyleSheet(_EMPTY_STYLE)
            update_resource_icon(icon_lbl, p, 20)
    def _update_display(p: str):
        _apply_state(p)
        clear_btn.setVisible(bool(p))
        callback(p)
    _apply_state(path)
    btn = QPushButton(qta.icon("fa5s.folder-open", color=chr(35) + "d4d4d4"), "")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip("Pick Resource")
    _style_picker_btn(btn)
    def _pick():
        p = pick_resource(w, "Select Resource", filter_str, path)
        if p:
            _update_display(p)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)
    clear_btn = QPushButton(qta.icon("fa5s.times", color=chr(35) + "d4d4d4"), "")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    _style_picker_btn(clear_btn)
    def _clear():
        _update_display("")
    clear_btn.clicked.connect(_clear)
    layout.addWidget(clear_btn)
    clear_btn.setVisible(bool(path))
    try:
        attach_resource_hover(name_lbl, lambda: _hover_state.get("path") or None)
        attach_resource_hover(icon_lbl, lambda: _hover_state.get("path") or None)
    except Exception:
        pass
    return w

def make_gameobject_picker(entity_id: str, scene, callback: Callable[[str], None]) -> QWidget:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    target_entity = scene.get_entity(entity_id) if scene and entity_id else None
    name = target_entity.name if target_entity else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if target_entity:
        for c in target_entity.get_all_components():
            if getattr(type(c), '_show_gizmo_icon', True) and type(c).__name__ != "Transform":
                pix = get_component_icon_pixmap(type(c), 18)
                icon_lbl.setPixmap(pix)
                break
    layout.addWidget(icon_lbl)
    def _on_entity_drop(eid: str):
        _update_entity_display(eid)
    name_lbl = _EntityDropLabel(_on_entity_drop, name if name else "None")
    name_lbl.setMinimumHeight(22)
    name_lbl.setToolTip(entity_id if entity_id else "No entity selected")
    name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    name_lbl.installEventFilter(_NavFilter(lambda: _flash_entity(name_lbl), lambda: _navigate_entity(name_lbl), name_lbl))
    layout.addWidget(name_lbl, 1)
    _hover_holder = {"eid": entity_id}
    def _update_entity_display(eid: str):
        nonlocal target_entity
        _hover_holder["eid"] = eid
        target_entity = scene.get_entity(eid) if scene and eid else None
        new_name = target_entity.name if target_entity else ""
        name_lbl.setText(new_name if new_name else "None")
        name_lbl.setToolTip(eid if eid else "No entity selected")
        icon_lbl.clear()
        if target_entity:
            for c in target_entity.get_all_components():
                if getattr(type(c), '_show_gizmo_icon', True) and type(c).__name__ != "Transform":
                    pix = get_component_icon_pixmap(type(c), 18)
                    icon_lbl.setPixmap(pix)
                    break
            name_lbl.setStyleSheet(name_lbl._BASE_STYLE)
        elif eid:
            name_lbl.setStyleSheet(_ERROR_STYLE)
        else:
            name_lbl.setStyleSheet(_EMPTY_STYLE)
        clear_btn.setVisible(bool(eid))
        callback(eid)
    btn = QPushButton(qta.icon("fa5s.crosshairs", color=chr(35) + "d4d4d4"), "")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip("Pick Entity")
    _style_picker_btn(btn)
    def _pick():
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QCursor
        dlg = EntityPickerDialog(scene, None)
        dlg.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        dw, dh = dlg.width(), dlg.height()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() - dw // 2
        y = cursor_pos.y() + 4
        if y + dh > screen.bottom():
            y = cursor_pos.y() - dh - 4
        if y < screen.top():
            y = screen.top()
        if x + dw > screen.right():
            x = screen.right() - dw
        if x < screen.left():
            x = screen.left()
        dlg.move(x, y)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            picked_id = dlg.selected_id()
            if picked_id is not None:
                _update_entity_display(picked_id)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)
    clear_btn = QPushButton(qta.icon("fa5s.times", color=chr(35) + "d4d4d4"), "")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    _style_picker_btn(clear_btn)
    def _clear():
        _update_entity_display("")
    clear_btn.clicked.connect(_clear)
    layout.addWidget(clear_btn)
    clear_btn.setVisible(bool(entity_id))
    try:
        def _resolve_entity():
            try:
                eid = _hover_holder.get("eid") or ""
                if scene is not None and eid:
                    return scene.get_entity(eid)
            except Exception:
                return None
            return None
        attach_entity_hover(name_lbl, _resolve_entity)
        attach_entity_hover(icon_lbl, _resolve_entity)
    except Exception:
        pass
    return w

def make_resource_type_picker(path: str, resource_type: str, callback: Callable[[str], None]) -> QWidget:
    from editor.picker import pick_resource
    from core.components.scripting.scriptc import RESOURCE_TYPE_FILTERS
    filter_str = RESOURCE_TYPE_FILTERS.get(resource_type, "All Files (*)")
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    name = os.path.basename(path) if path else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    update_resource_icon(icon_lbl, path, 20)
    layout.addWidget(icon_lbl)
    def _on_resource_drop(p: str):
        _update_display(p)
    name_lbl = _ResourceDropLabel(_on_resource_drop, name if name else f"None ({resource_type})")
    name_lbl.setMinimumHeight(22)
    name_lbl.setToolTip(path if path else f"No {resource_type} selected")
    name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    name_lbl.installEventFilter(_NavFilter(lambda: _flash_resource(name_lbl), lambda: _navigate_resource(name_lbl), name_lbl))
    layout.addWidget(name_lbl, 1)
    _hover_state_rt = {"path": path}
    def _update_display(p: str):
        _hover_state_rt["path"] = p
        new_name = os.path.basename(p) if p else ""
        name_lbl.setText(new_name if new_name else f"None ({resource_type})")
        name_lbl.setToolTip(p if p else f"No {resource_type} selected")
        update_resource_icon(icon_lbl, p, 20)
        if p:
            if _is_path_valid(p):
                name_lbl.setStyleSheet(name_lbl._BASE_STYLE)
            else:
                name_lbl.setStyleSheet(_ERROR_STYLE)
                icon_lbl.setPixmap(qta.icon("fa5s.exclamation-triangle", color=chr(35) + "e74c3c").pixmap(20, 20))
        else:
            name_lbl.setStyleSheet(_EMPTY_STYLE)
        clear_btn.setVisible(bool(p))
        callback(p)
    btn = QPushButton(qta.icon("fa5s.folder-open", color=chr(35) + "d4d4d4"), "")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip(f"Pick {resource_type}")
    _style_picker_btn(btn)
    def _pick():
        p = pick_resource(w, f"Select {resource_type}", filter_str, path)
        if p:
            _update_display(p)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)
    clear_btn = QPushButton(qta.icon("fa5s.times", color=chr(35) + "d4d4d4"), "")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    _style_picker_btn(clear_btn)
    def _clear():
        _update_display("")
    clear_btn.clicked.connect(_clear)
    layout.addWidget(clear_btn)
    clear_btn.setVisible(bool(path))
    try:
        attach_resource_hover(name_lbl, lambda: _hover_state_rt.get("path") or None)
        attach_resource_hover(icon_lbl, lambda: _hover_state_rt.get("path") or None)
    except Exception:
        pass
    return w

def make_asset_picker(path: str, asset_type: str, callback: Callable[[str], None]) -> QWidget:
    from editor.picker import pick_resource
    from core.components.scripting.scriptc import RESOURCE_TYPE_FILTERS
    filter_str = RESOURCE_TYPE_FILTERS.get(asset_type, "All Files (*)")
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    name = os.path.basename(path) if path else ""
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(*scale_xy(20, 20))
    update_resource_icon(icon_lbl, path, 20)
    layout.addWidget(icon_lbl)
    def _on_asset_drop(p: str):
        _update_display(p)
    name_lbl = _ResourceDropLabel(_on_asset_drop, name if name else f"None ({asset_type})")
    name_lbl.setMinimumHeight(22)
    name_lbl.setToolTip(path if path else f"No {asset_type} selected")
    name_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    name_lbl.installEventFilter(_NavFilter(lambda: _flash_resource(name_lbl), lambda: _navigate_resource(name_lbl), name_lbl))
    layout.addWidget(name_lbl, 1)
    _hover_state_ap = {"path": path}
    def _update_display(p: str):
        _hover_state_ap["path"] = p
        new_name = os.path.basename(p) if p else ""
        name_lbl.setText(new_name if new_name else f"None ({asset_type})")
        name_lbl.setToolTip(p if p else f"No {asset_type} selected")
        update_resource_icon(icon_lbl, p, 20)
        if p:
            if _is_path_valid(p):
                name_lbl.setStyleSheet(name_lbl._BASE_STYLE)
            else:
                name_lbl.setStyleSheet(_ERROR_STYLE)
                icon_lbl.setPixmap(qta.icon("fa5s.exclamation-triangle", color=chr(35) + "e74c3c").pixmap(20, 20))
        else:
            name_lbl.setStyleSheet(_EMPTY_STYLE)
        clear_btn.setVisible(bool(p))
        callback(p)
    btn = QPushButton(qta.icon("fa5s.folder-open", color=chr(35) + "d4d4d4"), "")
    btn.setFixedSize(*scale_xy(22, 22))
    btn.setToolTip(f"Pick {asset_type}")
    _style_picker_btn(btn)
    def _pick():
        p = pick_resource(w, f"Select {asset_type}", filter_str, path)
        if p:
            _update_display(p)
    btn.clicked.connect(_pick)
    layout.addWidget(btn)
    create_btn = QPushButton(qta.icon("fa5s.plus", color=chr(35) + "9ccc65"), "")
    create_btn.setFixedSize(*scale_xy(22, 22))
    create_btn.setToolTip(f"Create new {asset_type}")
    _style_picker_btn(create_btn)
    def _create():
        _create_asset_dialog(w, asset_type, _update_display)
    create_btn.clicked.connect(_create)
    layout.addWidget(create_btn)
    clear_btn = QPushButton(qta.icon("fa5s.times", color=chr(35) + "d4d4d4"), "")
    clear_btn.setFixedSize(*scale_xy(20, 20))
    clear_btn.setToolTip("Clear")
    _style_picker_btn(clear_btn)
    def _clear():
        _update_display("")
    clear_btn.clicked.connect(_clear)
    layout.addWidget(clear_btn)
    clear_btn.setVisible(bool(path))
    try:
        attach_resource_hover(name_lbl, lambda: _hover_state_ap.get("path") or None)
        attach_resource_hover(icon_lbl, lambda: _hover_state_ap.get("path") or None)
    except Exception:
        pass
    return w
