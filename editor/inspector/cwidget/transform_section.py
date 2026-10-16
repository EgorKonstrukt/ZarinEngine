# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QCheckBox, QSpinBox, QSlider, QComboBox, QSizePolicy, QDialog
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from core.config.editor_scale import scale
from core.maths.math3d import Vec3, Vec4
from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history
from core.foundation.curve import Curve
from editor.curve import CurvePreview, CurveEditorDialog
from core.gui.wid import AnchorPresetSelector
from editor.inspector.helpersp import make_spinbox, make_vec3_row
class TransformMixin:
    def _build_transform(self):
        tr = self._component
        w_pos, sbs_pos = make_vec3_row("Position", tr.local_position,
            lambda v: self._update_transform_from_spinboxes("local_position", sbs_pos),
            reset_to=[0.0, 0.0, 0.0])
        self._tr_pos_sbs = sbs_pos
        self._target_layout().addWidget(w_pos)
        w_rot, sbs_rot = make_vec3_row("Rotation", tr.local_euler_angles,
            lambda v: self._update_transform_from_spinboxes("local_euler_angles", sbs_rot),
            reset_to=[0.0, 0.0, 0.0])
        self._tr_rot_sbs = sbs_rot
        self._target_layout().addWidget(w_rot)
        w_scale, sbs_scale = make_vec3_row("Scale", tr.local_scale,
            lambda v: self._update_transform_from_spinboxes("local_scale", sbs_scale),
            reset_to=[1.0, 1.0, 1.0])
        self._tr_scale_sbs = sbs_scale
        self._target_layout().addWidget(w_scale)
    def _update_transform_from_spinboxes(self, attr, sbs):
        if self._updating: return
        comp_type = type(self._component)
        new = Vec3(sbs[0].value(), sbs[1].value(), sbs[2].value())
        entities = [e for e in self._selected_entities if e.has_component(comp_type)]
        if len(entities) <= 1:
            tr = self._component
            old = getattr(tr, attr)
            get_history().execute(SetComponentCommand(self._entity, comp_type, attr, old, new))
        else:
            cmds = []
            for ent in entities:
                comp = ent.get_component(comp_type)
                if comp:
                    old = getattr(comp, attr)
                    try:
                        setattr(comp, attr, Vec3(new.x, new.y, new.z))
                    except Exception:
                        continue
                    cmds.append(SetComponentCommand(ent, comp_type, attr, old, Vec3(new.x, new.y, new.z)))
            if len(cmds) == 1:
                get_history().execute(cmds[0])
            elif cmds:
                get_history().execute(CompoundCommand(cmds, f"Set {attr} x{len(cmds)}"))
        self._redraw_viewport()
    def refresh_transform(self):
        if self._updating: return
        tr = self._component
        pos = tr.local_position
        rot = tr.local_euler_angles
        scl = tr.local_scale
        self._updating = True
        try:
            self._set_transform_sb(self._tr_pos_sbs, pos.x, pos.y, pos.z)
            self._set_transform_sb(self._tr_rot_sbs, rot.x, rot.y, rot.z)
            self._set_transform_sb(self._tr_scale_sbs, scl.x, scl.y, scl.z)
        finally:
            self._updating = False
    @staticmethod
    def _set_transform_sb(sbs, x, y, z):
        for sb, val in zip(sbs, (x, y, z)):
            if sb is None:
                continue
            if sb.hasFocus() or (sb.lineEdit() is not None and sb.lineEdit().hasFocus()):
                continue
            sb.setValue(float(val))
    def _build_int_field(self, field, prop_name, c, value):
        if field.readonly:
            lbl = QLabel(str(value))
            self._add_field(field.label, lbl)
            return
        sb = QSpinBox()
        min_i = max(-9223372036854775808, min(9223372036854775807, int(field.min_val)))
        max_i = max(-9223372036854775808, min(9223372036854775807, int(field.max_val)))
        natural_min = min_i
        natural_max = max_i
        if field.on_set and hasattr(c, field.on_set):
            min_i = max(-9223372036854775808, min_i - 1)
            max_i = min(9223372036854775807, max_i + 1)
        sb.setRange(min_i, max_i)
        sb.setValue(max(natural_min, min(natural_max, int(value))))
        sb.setMinimumWidth(60)
        comp_cls = type(c)
        if field.on_set and hasattr(c, field.on_set):
            def _on_int_value(v, n=prop_name, m=field.on_set, nmn=natural_min, nmx=natural_max):
                if nmn <= v <= nmx:
                    self._undo_setter_all(comp_cls, n)(v)
                else:
                    fn = getattr(c, m, None)
                    if callable(fn) and fn(n, v):
                        self._sync_int_field_values()
                        self.refresh_split_gradient_fields()
            sb.valueChanged.connect(_on_int_value)
        else:
            _setter = self._undo_setter_all(comp_cls, prop_name)
            def _on_int_plain(v, s=_setter):
                s(v)
                self.refresh_split_gradient_fields()
            sb.valueChanged.connect(_on_int_plain)
        self._add_field(field.label, sb, prop_name, field.toggle_field)
    def _build_slider_field(self, field, prop_name, c, value):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        _slider_scale = 1000.0
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(field.min_val * _slider_scale), int(field.max_val * _slider_scale))
        slider.setValue(int(value * _slider_scale))
        slider.setSingleStep(max(1, int(field.step * _slider_scale)))
        sb = make_spinbox(value, field.min_val, field.max_val, field.step, field.decimals)
        comp_cls = type(c)
        sb.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
        _updating = [False]
        _slider_scale_val = _slider_scale
        def _on_slider(v):
            if _updating[0]: return
            _updating[0] = True
            sb.setValue(v / _slider_scale_val)
            _updating[0] = False
        def _on_spinbox(v):
            if _updating[0]: return
            _updating[0] = True
            slider.setValue(int(v * _slider_scale_val))
            _updating[0] = False
        slider.valueChanged.connect(_on_slider)
        sb.valueChanged.connect(_on_spinbox)
        rl.addWidget(slider, 1)
        rl.addWidget(sb)
        self._add_field(field.label, row, prop_name, field.toggle_field)
    def _build_int_slider_field(self, field, prop_name, c, value):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        min_i = max(-9223372036854775808, min(9223372036854775807, int(field.min_val)))
        max_i = max(-9223372036854775808, min(9223372036854775807, int(field.max_val)))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_i, max_i)
        slider.setValue(max(min_i, min(max_i, int(value))))
        slider.setSingleStep(max(1, int(field.step)))
        sb = QSpinBox()
        sb.setRange(min_i, max_i)
        sb.setValue(max(min_i, min(max_i, int(value))))
        sb.setMinimumWidth(50)
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
    def _build_color_field(self, field, prop_name, c, value):
        from editor.color import ColorLineEdit
        initial = None
        if isinstance(value, (list, tuple)):
            initial = QColor.fromRgbF(*value[:4])
        elif isinstance(value, Vec3):
            initial = QColor.fromRgbF(value.x, value.y, value.z)
        elif isinstance(value, Vec4):
            initial = QColor.fromRgbF(value.x, value.y, value.z, value.w)
        elif isinstance(value, QColor):
            initial = value
        color_edit = ColorLineEdit(initial)
        comp_cls = type(c)
        def _on_color_changed(col, _pn=prop_name, _cls=comp_cls):
            entities = [e for e in self._selected_entities if e.has_component(_cls)] or ([self._entity] if self._entity else [])
            cmds = []
            for ent in entities:
                comp = ent.get_component(_cls)
                if not comp or not hasattr(comp, _pn):
                    continue
                old_val = getattr(comp, _pn)
                rgb = [col.redF(), col.greenF(), col.blueF()]
                if isinstance(old_val, Vec4):
                    rgb.append(col.alphaF())
                if isinstance(old_val, Vec3):
                    new_val = Vec3(*rgb)
                elif isinstance(old_val, Vec4):
                    new_val = Vec4(*rgb)
                elif isinstance(old_val, list):
                    new_val = list(rgb)
                elif isinstance(old_val, tuple):
                    new_val = tuple(rgb)
                elif isinstance(old_val, QColor):
                    new_val = col
                else:
                    new_val = rgb
                try:
                    setattr(comp, _pn, new_val)
                except Exception:
                    continue
                cmds.append(SetComponentCommand(ent, _cls, _pn, old_val, new_val))
            if len(cmds) == 1:
                get_history().execute(cmds[0])
            elif cmds:
                get_history().execute(CompoundCommand(cmds, f"Set {_pn} x{len(cmds)}"))
        color_edit.colorChanged.connect(_on_color_changed)
        self._add_field(field.label, color_edit, prop_name, field.toggle_field)
    def _build_enum_field(self, field, prop_name, c, value):
        options, enum_cls, current = self._enum_spec(field, value)
        combo = QComboBox()
        for opt in options:
            combo.addItem(opt)
        try:
            combo.setCurrentText(current)
        except Exception:
            pass
        comp_cls = type(c)
        def _on_enum_change(t, _cls=comp_cls, _pn=prop_name):
            nv = self._enum_value(enum_cls, t)
            entities = [e for e in self._selected_entities if e.has_component(_cls)] or ([self._entity] if self._entity else [])
            cmds = []
            for ent in entities:
                comp = ent.get_component(_cls)
                if comp and hasattr(comp, _pn):
                    old = getattr(comp, _pn)
                    try:
                        setattr(comp, _pn, nv)
                    except Exception:
                        continue
                    cmds.append(SetComponentCommand(ent, _cls, _pn, old, nv))
            if len(cmds) == 1:
                get_history().execute(cmds[0])
            elif cmds:
                get_history().execute(CompoundCommand(cmds, f"Set {_pn} x{len(cmds)}"))
        combo.currentTextChanged.connect(_on_enum_change)
        self._add_field(field.label, combo, prop_name, field.toggle_field)
    def _build_curve_field(self, field, prop_name, c, value):
        preview = CurvePreview()
        preview.setMinimumHeight(scale(56))
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if isinstance(value, Curve):
            preview.set_curve(value)
        def _open_editor(*, _prop_name=prop_name, _field=field):
            dlg = CurveEditorDialog(getattr(c, _prop_name, None), _field.label, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                preview.set_curve(getattr(c, _prop_name, None))
        preview.mousePressEvent = lambda ev, pe=_open_editor: pe() if ev.button() == Qt.MouseButton.LeftButton else None
        self._add_field(field.label, preview, prop_name, field.toggle_field)
    def _build_anchor_field(self, field, prop_name, c, value):
        ctrl = AnchorPresetSelector()
        if hasattr(c, prop_name):
            current = getattr(c, prop_name)
            if isinstance(current, int):
                ctrl.set_anchor(current)
        comp_cls = type(c)
        def _on_anchor_change(v, _cls=comp_cls, _pn=prop_name):
            entities = [e for e in self._selected_entities if e.has_component(_cls)] or ([self._entity] if self._entity else [])
            cmds = []
            for ent in entities:
                comp = ent.get_component(_cls)
                if comp and hasattr(comp, _pn):
                    old = getattr(comp, _pn)
                    try:
                        setattr(comp, _pn, v)
                    except Exception:
                        continue
                    cmds.append(SetComponentCommand(ent, _cls, _pn, old, v))
            if len(cmds) == 1:
                get_history().execute(cmds[0])
            elif cmds:
                get_history().execute(CompoundCommand(cmds, f"Set {_pn} x{len(cmds)}"))
        ctrl.anchor_changed.connect(_on_anchor_change)
        self._add_field(field.label, ctrl, prop_name, field.toggle_field)
