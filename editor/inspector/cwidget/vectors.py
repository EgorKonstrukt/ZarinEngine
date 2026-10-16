# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
from PySide6.QtWidgets import QWidget, QSpinBox, QDoubleSpinBox, QSlider, QDialog, QPushButton
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag, QCursor
from core.maths.math3d import Vec2, Vec3, Vec4
from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history
from core.physics.collision_layers import MAX_LAYERS
from editor.inspector.constants import _COMPONENT_MIME, _FUSION_INPUT_RADIUS
from editor.inspector.helpersp import collapse_value, make_vec2_row, make_vec3_row, make_vec4_row, make_vec2_slider_row, make_vec3_slider_row
class VectorsMixin:
    def _undo_setter(self, prop_name):
        return self._undo_setter_all(type(self._component), prop_name)
    def _undo_setter_all(self, comp_type, prop_name):
        entities = [e for e in self._selected_entities if e.has_component(comp_type)]
        if len(entities) <= 1:
            ent = self._entity
            c = self._component
            def _set_single(v):
                old = getattr(c, prop_name) if hasattr(c, prop_name) else None
                try:
                    setattr(c, prop_name, v)
                except Exception:
                    pass
                get_history().execute(SetComponentCommand(ent, comp_type, prop_name, old, v))
                try:
                    from core.engine.eng import Engine
                    collab = Engine.instance().collab_manager
                    if collab and collab.connected and ent:
                        val = collapse_value(v)
                        collab.send_component_update(ent.id, self._component_key, prop_name, val)
                except Exception:
                    pass
            return _set_single
        def _set_all(v):
            cmds = []
            for ent in entities:
                comp = ent.get_component(comp_type)
                if comp and hasattr(comp, prop_name):
                    old_v = getattr(comp, prop_name)
                    try:
                        setattr(comp, prop_name, v)
                    except Exception:
                        continue
                    cmds.append(SetComponentCommand(ent, comp_type, prop_name, old_v, v))
                    try:
                        from core.engine.eng import Engine
                        collab = Engine.instance().collab_manager
                        if collab and collab.connected:
                            collab.send_component_update(ent.id, self._component_key if ent is self._entity else comp_type.__name__, prop_name, collapse_value(v))
                    except Exception:
                        pass
            if cmds:
                get_history().execute(CompoundCommand(cmds, f"Set {prop_name} on {len(entities)} entities"))
        return _set_all
    def _undo_setter_int(self, prop_name):
        return self._undo_setter_all(type(self._component), prop_name)
    def _set_vec_multi(self, prop_name, idx, new_val):
        comp_type = type(self._component)
        entities = [e for e in self._selected_entities if e.has_component(comp_type)]
        if len(entities) <= 1:
            c = self._component
            vec = getattr(c, prop_name, None)
            if vec is None:
                return
            if isinstance(vec, (list, tuple)):
                lst = list(vec)
                if idx < len(lst):
                    lst[idx] = new_val
                    setattr(c, prop_name, type(vec)(lst) if isinstance(vec, tuple) else lst)
            elif hasattr(vec, 'x'):
                vals = [vec.x, vec.y, vec.z, vec.w] if hasattr(vec, 'w') else ([vec.x, vec.y] if hasattr(vec, 'y') else [vec.x])
                vals[idx] = new_val
                if len(vals) == 2:
                    setattr(c, prop_name, Vec2(*vals))
                elif len(vals) == 3:
                    setattr(c, prop_name, Vec3(*vals))
                elif len(vals) == 4:
                    setattr(c, prop_name, Vec4(*vals))
            return
        cmds = []
        for ent in entities:
            comp = ent.get_component(comp_type)
            if not comp or not hasattr(comp, prop_name):
                continue
            vec = getattr(comp, prop_name, None)
            if vec is None:
                continue
            old = vec
            if isinstance(vec, (list, tuple)):
                lst = list(vec)
                if idx < len(lst):
                    lst[idx] = new_val
                    new_vec = type(vec)(lst) if isinstance(vec, tuple) else lst
                else:
                    continue
            elif hasattr(vec, 'x'):
                if hasattr(vec, 'w'):
                    vals = [vec.x, vec.y, vec.z, vec.w]
                    vals[idx] = new_val
                    new_vec = Vec4(*vals)
                elif hasattr(vec, 'z'):
                    vals = [vec.x, vec.y, vec.z]
                    vals[idx] = new_val
                    new_vec = Vec3(*vals)
                else:
                    vals = [vec.x, vec.y]
                    vals[idx] = new_val
                    new_vec = Vec2(*vals)
            else:
                continue
            try:
                setattr(comp, prop_name, new_vec)
            except Exception:
                continue
            cmds.append(SetComponentCommand(ent, comp_type, prop_name, old, new_vec))
        if cmds:
            get_history().execute(CompoundCommand(cmds, f"Set {prop_name}[{idx}] on {len(cmds)} entities"))
    def _on_layer_mask_toggle(self, prop_name, bit, btn, layer_names, menu, all_act, nothing_act):
        comp_type = type(self._component)
        entities = [e for e in self._selected_entities if e.has_component(comp_type)]
        if len(entities) <= 1:
            mask = int(getattr(self._component, prop_name))
            if mask & (1 << bit):
                mask &= ~(1 << bit)
            else:
                mask |= 1 << bit
            self._undo_setter_all(comp_type, prop_name)(mask)
            self._update_layer_mask_text(btn, mask, layer_names)
            all_act.setChecked(mask == 0xFFFF)
            nothing_act.setChecked(mask == 0)
            return
        first_mask = int(getattr(self._component, prop_name))
        new_mask = first_mask & ~(1 << bit) if (first_mask & (1 << bit)) else first_mask | (1 << bit)
        cmds = []
        for ent in entities:
            comp = ent.get_component(comp_type)
            if comp:
                old = int(getattr(comp, prop_name))
                cur = old & ~(1 << bit) if (old & (1 << bit)) else old | (1 << bit)
                try:
                    setattr(comp, prop_name, cur)
                except Exception:
                    continue
                cmds.append(SetComponentCommand(ent, comp_type, prop_name, old, cur))
        if cmds:
            get_history().execute(CompoundCommand(cmds, f"Toggle layer {bit} on {len(cmds)} entities"))
        self._update_layer_mask_text(btn, new_mask, layer_names)
        all_act.setChecked(new_mask == 0xFFFF)
        nothing_act.setChecked(new_mask == 0)
    def _on_layer_mask_set_all(self, prop_name, state, btn, layer_names, menu):
        comp_type = type(self._component)
        entities = [e for e in self._selected_entities if e.has_component(comp_type)]
        mask = 0xFFFF if state else 0
        if len(entities) <= 1:
            self._undo_setter_all(comp_type, prop_name)(mask)
            self._update_layer_mask_text(btn, mask, layer_names)
            for act in menu.actions():
                if act.isCheckable() and act.text() not in ("Everything", "Nothing"):
                    act.setChecked(state)
                elif act.text() == "Everything":
                    act.setChecked(state)
                elif act.text() == "Nothing":
                    act.setChecked(not state)
            return
        cmds = []
        for ent in entities:
            comp = ent.get_component(comp_type)
            if comp:
                old = int(getattr(comp, prop_name))
                try:
                    setattr(comp, prop_name, mask)
                except Exception:
                    continue
                cmds.append(SetComponentCommand(ent, comp_type, prop_name, old, mask))
        if cmds:
            get_history().execute(CompoundCommand(cmds, f"Set layer mask x{len(cmds)}"))
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
    def _on_vec2_changed(self, prop_name: str, spinboxes: list):
        self._updating = True
        self._updating = False
    def refresh_vec2_field(self, prop_name: str):
        pass
    def _on_vec3_changed(self, prop_name: str, spinboxes: list):
        self._updating = True
        self._updating = False
    def _on_vec4_changed(self, prop_name: str, spinboxes: list):
        self._updating = True
        self._updating = False
    def refresh_vec4_field(self, prop_name: str):
        pass
    def _on_gradient_changed(self, comp, prop_name, stops):
        pass
    def refresh_vec3_field(self, prop_name: str):
        pass
    def refresh_scalar_field(self, prop_name: str):
        if self._updating:
            return
        c = self._component
        try:
            value = getattr(c, prop_name)
        except Exception:
            return
        if isinstance(value, bool):
            return
        self._updating = True
        try:
            for r in self._field_rows:
                try:
                    if r.get("prop_name", "") != prop_name:
                        continue
                except Exception:
                    continue
                cell = r.get("field_widget")
                child = getattr(cell, "_field_child", None) if cell is not None else None
                if child is None:
                    continue
                targets = []
                try:
                    if isinstance(child, (QSpinBox, QDoubleSpinBox, QSlider)):
                        targets.append(child)
                    elif isinstance(child, QWidget):
                        for w in child.findChildren(QSpinBox):
                            targets.append(w)
                        for w in child.findChildren(QDoubleSpinBox):
                            targets.append(w)
                        for w in child.findChildren(QSlider):
                            targets.append(w)
                except Exception:
                    continue
                for w in targets:
                    try:
                        if w.hasFocus():
                            continue
                        try:
                            le = w.lineEdit()
                        except Exception:
                            le = None
                        if le is not None:
                            try:
                                if le.hasFocus():
                                    continue
                            except Exception:
                                pass
                        if isinstance(w, (QSpinBox, QSlider)):
                            w.blockSignals(True)
                            try:
                                w.setValue(int(value))
                            finally:
                                w.blockSignals(False)
                        else:
                            w.blockSignals(True)
                            try:
                                w.setValue(float(value))
                            finally:
                                w.blockSignals(False)
                    except Exception:
                        try:
                            w.blockSignals(False)
                        except Exception:
                            pass
                        continue
        finally:
            self._updating = False
    def refresh_split_gradient_fields(self):
        c = self._component
        for r in self._field_rows:
            fm = r.get("field_meta")
            if fm is None or fm.field_type.value != "split_gradient":
                continue
            pn = r.get("prop_name", "")
            if not pn or not hasattr(c, pn):
                continue
            cell = r.get("field_widget")
            child = getattr(cell, "_field_child", None) if cell is not None else None
            if child is not None and hasattr(child, "setValue"):
                child.blockSignals(True)
                try:
                    child.setValue(list(getattr(c, pn)) if getattr(c, pn) else [])
                except Exception:
                    pass
                child.blockSignals(False)
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
    def _build_vec2_field(self, field, prop_name, value):
        w, sbs = make_vec2_row(field.label, value if value is not None else Vec2(0.0, 0.0), lambda: None)
        for i, sb in enumerate(sbs):
            sb.valueChanged.connect(lambda v, idx=i, pn=prop_name: self._set_vec_multi(pn, idx, v))
        self._target_layout().addWidget(w)
    def _build_vec3_field(self, field, prop_name, value):
        w, sbs = make_vec3_row(field.label, value if value is not None else Vec3(0.0, 0.0, 0.0), lambda: None)
        for i, sb in enumerate(sbs):
            sb.valueChanged.connect(lambda v, idx=i, pn=prop_name: self._set_vec_multi(pn, idx, v))
        self._target_layout().addWidget(w)
    def _build_vec4_field(self, field, prop_name, value):
        w, sbs = make_vec4_row(field.label, value if value is not None else Vec4(0.0, 0.0, 0.0, 0.0), lambda: None)
        for i, sb in enumerate(sbs):
            sb.valueChanged.connect(lambda v, idx=i, pn=prop_name: self._set_vec_multi(pn, idx, v))
        self._target_layout().addWidget(w)
    def _build_vec2_slider_field(self, field, prop_name, value):
        w, sbs = make_vec2_slider_row(field.label, value, lambda: None, field.min_val, field.max_val)
        for i, sb in enumerate(sbs):
            sb.valueChanged.connect(lambda v, idx=i, pn=prop_name: self._set_vec_multi(pn, idx, v))
        self._target_layout().addWidget(w)
    def _build_vec3_slider_field(self, field, prop_name, value):
        w, sbs = make_vec3_slider_row(field.label, value, lambda: None, field.min_val, field.max_val)
        for i, sb in enumerate(sbs):
            sb.valueChanged.connect(lambda v, idx=i, pn=prop_name: self._set_vec_multi(pn, idx, v))
        self._target_layout().addWidget(w)
    def _build_gradient_field(self, field, prop_name, c, value):
        grad_preview = QPushButton()
        grad_preview.setFixedHeight(22)
        grad_preview.setMinimumWidth(120)
        grad_preview.setToolTip("Click to edit gradient")
        def _paint_gradient(btn, grad_data=value):
            if not grad_data:
                return
            if isinstance(grad_data, dict):
                alpha_keys = grad_data.get("alpha_keys", [])
                color_keys = grad_data.get("color_keys", [])
                alpha_map = {k[0]: k[1] for k in alpha_keys}
                color_map = {k[0]: list(k[1]) for k in color_keys}
                positions = sorted(set(list(alpha_map.keys()) + list(color_map.keys())))
                grad_data = []
                for p in positions:
                    cc = color_map.get(p, [1, 1, 1])
                    a = alpha_map.get(p, 1.0)
                    grad_data.append((p, [cc[0], cc[1], cc[2], a]))
            stops = []
            for pos, rgba in grad_data:
                r, g, b, a = (int(cc * 255) for cc in rgba[:4])
                stops.append((pos, f"rgba({r},{g},{b},{a})"))
            if stops:
                css = ", ".join(f"stop:{p} {cc}" for p, cc in stops)
                btn.setStyleSheet(
                    f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, {css}); "
                    f"border-radius: {_FUSION_INPUT_RADIUS}; border: 1px solid; }}"
                )
        _paint_gradient(grad_preview)
        def _open_gradient_editor():
            from editor.gradient import GradientEditorDialog
            editor_stops = value
            if isinstance(value, dict):
                alpha_keys = value.get("alpha_keys", [])
                color_keys = value.get("color_keys", [])
                alpha_map = {k[0]: k[1] for k in alpha_keys}
                color_map = {k[0]: list(k[1]) for k in color_keys}
                positions = sorted(set(list(alpha_map.keys()) + list(color_map.keys())))
                editor_stops = []
                for p in positions:
                    cc = color_map.get(p, [1, 1, 1])
                    a = alpha_map.get(p, 1.0)
                    editor_stops.append((p, [cc[0], cc[1], cc[2], a]))
            dlg = GradientEditorDialog(editor_stops, "Edit Gradient", self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_gradient = dlg.get_stops()
                if isinstance(value, dict):
                    alpha_keys = []
                    color_keys = []
                    for p, rgba in new_gradient:
                        color_keys.append([p, [rgba[0], rgba[1], rgba[2]]])
                        alpha_keys.append([p, rgba[3]])
                    new_gradient = {"alpha_keys": alpha_keys, "color_keys": color_keys}
                setattr(c, prop_name, new_gradient)
                _paint_gradient(grad_preview, new_gradient)
                get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, value, new_gradient))
        grad_preview.clicked.connect(_open_gradient_editor)
        self._add_field(field.label, grad_preview, prop_name, field.toggle_field)
    def _build_split_gradient_field(self, field, prop_name, c, value):
        from editor.split_gradient_widget import SplitGradientWidget
        max_val = field.max_val if field.max_val > -1e15 else 1.0
        decimals = field.decimals if field.decimals >= 0 else 1
        sgw = SplitGradientWidget(value=list(value) if value else [], max_value=max_val, decimals=decimals)
        comp_cls = type(c)
        sgw.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
        self._add_field(field.label, sgw, prop_name, field.toggle_field)
