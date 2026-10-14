# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QCheckBox, QSpinBox, QGroupBox, QFormLayout
from PyQt6.QtCore import Qt
from core.config.editor_scale import scale_xy
from core.foundation.commands import SetComponentCommand, get_history
from editor.inspector.helpers import make_spinbox, make_clickable_label, get_component_source_path, get_property_line_number, make_resource_picker, make_gameobject_picker, make_resource_type_picker, make_asset_picker
class FieldsMixin:
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
        self._wire_validation()
    def _on_toggle_changed(self, v: bool, rows: list[QWidget]):
        for r in rows:
            r.setVisible(v)
    def _on_group_toggled(self, gform: QFormLayout, visible: bool):
        for i in range(gform.count()):
            item = gform.itemAt(i)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setVisible(visible)
    def _resolve_default(self, prop_name: str, suggested):
        if suggested is not None:
            return suggested
        f = self._current_field
        if f is not None and f.field_type.value in ("float", "int", "slider", "int_slider"):
            return 0
        if f is not None and f.field_type.value == "bool":
            return False
        if f is not None and f.field_type.value in ("string", "text", "textarea", "keybinding"):
            return ""
        return None
    def _reset_to_default(self, prop_name: str, suggested=None):
        default = self._resolve_default(prop_name, suggested)
        if default is None:
            return
        c = self._component
        old = getattr(c, prop_name, None)
        setattr(c, prop_name, default)
        get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, old, default))
        self._rebuild_fields()
    def _validate_field(self, prop_name: str, widget: QWidget, value):
        f = self._current_field
        bad = False
        if f is not None and f.field_type.value in ("float", "int", "slider", "int_slider"):
            try:
                if value is None or (isinstance(value, float) and value != value):
                    bad = True
                elif hasattr(f, "min_val") and f.min_val > -1e15 and value < f.min_val:
                    bad = True
                elif hasattr(f, "max_val") and f.max_val < 1e15 and value > f.max_val:
                    bad = True
            except Exception:
                pass
        if bad:
            widget.setStyleSheet("border: 1px solid #f44747; border-radius: 2px;")
            widget.setToolTip("Value out of range or invalid")
        else:
            widget.setStyleSheet("")
            widget.setToolTip("")
    def _wire_validation(self):
        from PyQt6.QtWidgets import QAbstractSpinBox, QSlider
        for row in self._field_rows:
            f = row.get("field_meta")
            if f is None or f.field_type.value not in ("float", "int", "slider", "int_slider"):
                continue
            w = row["field_widget"]
            target = w._field_child if hasattr(w, "_field_child") else w
            prop = row["prop_name"]
            if isinstance(target, QAbstractSpinBox):
                target.valueChanged.connect(lambda v, p=prop, tw=target: self._validate_field(p, tw, v))
            elif isinstance(target, QSlider):
                target.valueChanged.connect(lambda v, p=prop, tw=target: self._validate_field(p, tw, v))
    def _sync_int_field_values(self):
        c = self._component
        for r in self._field_rows:
            pn = r.get("prop_name", "")
            if not pn or not hasattr(c, pn):
                continue
            cell = r.get("field_widget")
            if cell is None:
                continue
            child = getattr(cell, "_field_child", None)
            if isinstance(child, QSpinBox):
                child.blockSignals(True)
                child.setValue(getattr(c, pn, child.value()))
                child.blockSignals(False)
    def _make_field_cell(self, widget: QWidget, prop_name: str, field_meta=None):
        cell = QWidget()
        fl = QHBoxLayout(cell)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(4)
        fl.addWidget(widget, 1)
        cell._field_child = widget
        if prop_name and field_meta is not None and field_meta.default_value is not None:
            reset_btn = QPushButton("\u21ba")
            reset_btn.setFixedSize(*scale_xy(18, 18))
            reset_btn.setToolTip("Reset to default")
            reset_btn.setStyleSheet("QPushButton { color: #bbb; background: transparent; border: 1px solid #444; border-radius: 3px; font-size: 10px; } QPushButton:hover { color: #fff; border-color: #777; }")
            reset_btn.clicked.connect(lambda _, pn=prop_name, dv=field_meta.default_value: self._reset_to_default(pn, dv))
            fl.addWidget(reset_btn)
            cell._reset_btn = reset_btn
        if prop_name:
            comp_type = type(self._component).__name__
            src_path = get_component_source_path(type(self._component))
            line_num = get_property_line_number(type(self._component), prop_name)
            source_lbl = make_clickable_label("src", lambda sp=src_path, ln=line_num: self._show_source(sp, ln, comp_type, prop_name))
            fl.addWidget(source_lbl)
        return cell
    def _add_field(self, label: str, widget: QWidget, prop_name: str = "", toggle_field: str = "", field_meta=None):
        if field_meta is None:
            field_meta = getattr(self, "_current_field", None)
        target = self._target_layout()
        lbl = QLabel(label)
        lbl.setWordWrap(True)
        if prop_name:
            lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            lbl.customContextMenuRequested.connect(lambda pos, pn=prop_name: self._show_field_context_menu(pos, pn))
        if field_meta is not None and field_meta.description:
            lbl.setToolTip(field_meta.description)
        if prop_name and prop_name in self._overridden_props:
            lbl.setStyleSheet("color: #e0a93b; font-weight: 600;")
        if prop_name and len(self._selected_entities) > 1:
            try:
                first_seen = False
                first_val = None
                mixed = False
                comp_type = type(self._component)
                for e in self._selected_entities:
                    comp = e.get_component(comp_type)
                    if comp is not None and hasattr(comp, prop_name):
                        cur = getattr(comp, prop_name)
                        if not first_seen:
                            first_val = cur
                            first_seen = True
                        elif cur != first_val:
                            mixed = True
                            break
                if mixed:
                    base_tip = field_meta.description if field_meta is not None and field_meta.description else ""
                    lbl.setToolTip((base_tip + "\n" if base_tip else "") + "Mixed values across selection")
                    style = lbl.styleSheet() or ""
                    if prop_name not in self._overridden_props:
                        lbl.setStyleSheet(style + " color: #7fb0ff;")
            except Exception:
                pass
        cell = self._make_field_cell(widget, prop_name, field_meta) if (prop_name or field_meta is not None) else None
        if label:
            target.addRow(lbl, cell if cell is not None else widget)
        else:
            target.addRow(cell if cell is not None else widget)
        self._field_rows.append({
            "label": label,
            "label_widget": lbl,
            "field_widget": cell if cell is not None else widget,
            "prop_name": prop_name,
            "field_meta": field_meta,
            "toggle_field": toggle_field,
        })
        if toggle_field:
            self._toggle_rows.setdefault(toggle_field, []).append(cell if cell is not None else widget)
    def _enum_spec(self, field, value):
        options = list(field.enum_options or [])
        enum_cls = field.enum_class
        if not options and enum_cls is not None:
            options = [e.name for e in enum_cls]
        current = ""
        if value is not None:
            if enum_cls is not None and isinstance(value, enum_cls):
                current = value.name
            elif enum_cls is not None and isinstance(value, str):
                if value in enum_cls.__members__:
                    current = enum_cls[value].name
                else:
                    for e in enum_cls:
                        if e.value == value:
                            current = e.name
                            break
                    else:
                        current = value
            else:
                current = str(value)
        return options, enum_cls, current
    def _enum_value(self, enum_cls, text):
        return enum_cls[text] if enum_cls is not None else text
    def _build_field_from_meta(self, field):
        c = self._component
        self._current_field = field
        prop_name = field.name
        if field.field_type.value == "header":
            group = QGroupBox(field.label)
            group.setObjectName("inspectorGroup")
            group.setCheckable(True)
            group.setChecked(True)
            group.setStyleSheet(
                "QGroupBox#inspectorGroup { color: #ccc; border: 1px solid #3a3a3a; "
                "border-radius: 4px; margin-top: 10px; padding-top: 16px; font-size: 11px; "
                "font-weight: 600; background: rgba(255,255,255,0.02); } "
                "QGroupBox#inspectorGroup::title { subcontrol-origin: margin; left: 8px; "
                "padding: 0 4px; } "
                "QGroupBox#inspectorGroup::indicator { width: 10px; height: 10px; }"
            )
            gform = QFormLayout(group)
            gform.setContentsMargins(8, 4, 8, 6)
            gform.setSpacing(3)
            gform.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            gform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            gform.setHorizontalSpacing(8)
            group.toggled.connect(lambda v, gf=gform: self._on_group_toggled(gf, v))
            self._group_form = gform
            self._layout.addWidget(group)
            return
        value = getattr(c, prop_name)
        if field.field_type.value == "float":
            sb = make_spinbox(value, field.min_val, field.max_val, field.step, field.decimals)
            comp_cls = type(c)
            sb.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
            self._add_field(field.label, sb, prop_name, field.toggle_field)
        elif field.field_type.value == "int":
            self._build_int_field(field, prop_name, c, value)
        elif field.field_type.value == "slider":
            self._build_slider_field(field, prop_name, c, value)
        elif field.field_type.value == "int_slider":
            self._build_int_slider_field(field, prop_name, c, value)
        elif field.field_type.value == "bool":
            cb = QCheckBox()
            cb.setChecked(value)
            comp_cls = type(c)
            cb.toggled.connect(self._undo_setter_all(comp_cls, prop_name))
            self._add_field(field.label, cb, prop_name, field.toggle_field)
            self._toggle_checkboxes[prop_name] = cb
        elif field.field_type.value == "button":
            btn = QPushButton(field.label)
            def _on_button():
                fn = getattr(c, prop_name, None)
                if callable(fn):
                    fn()
                self._sync_int_field_values()
            btn.clicked.connect(_on_button)
            self._add_field("", btn)
        elif field.field_type.value == "color":
            self._build_color_field(field, prop_name, c, value)
        elif field.field_type.value == "enum":
            self._build_enum_field(field, prop_name, c, value)
        elif field.field_type.value == "resource":
            pw = make_resource_picker(value, field.file_filter or "All Files (*)", self._undo_setter_all(type(c), prop_name))
            self._add_field(field.label, pw, prop_name, field.toggle_field)
        elif field.field_type.value == "gameobject":
            from core.engine.engine import Engine
            scene = Engine.instance().scene
            gw = make_gameobject_picker(value, scene, self._undo_setter_all(type(c), prop_name))
            self._add_field(field.label, gw, prop_name, field.toggle_field)
        elif field.field_type.value == "resource_type":
            pw = make_resource_type_picker(value, field.resource_type or "", self._undo_setter_all(type(c), prop_name))
            self._add_field(field.label, pw, prop_name, field.toggle_field)
        elif field.field_type.value == "asset":
            pw = make_asset_picker(value, field.resource_type or "", self._undo_setter_all(type(c), prop_name))
            self._add_field(field.label, pw, prop_name, field.toggle_field)
        elif field.field_type.value == "curve":
            self._build_curve_field(field, prop_name, c, value)
        elif field.field_type.value == "anchor":
            self._build_anchor_field(field, prop_name, c, value)
        elif field.field_type.value == "text":
            self._build_text_field(field, prop_name, c, value)
        elif field.field_type.value == "vec2":
            self._build_vec2_field(field, prop_name, value)
        elif field.field_type.value == "vec3":
            self._build_vec3_field(field, prop_name, value)
        elif field.field_type.value == "list":
            self._build_list_field_standalone(field, prop_name)
        elif field.field_type.value == "layer_mask":
            self._build_layer_mask_field(field, prop_name)
        elif field.field_type.value == "vec4":
            self._build_vec4_field(field, prop_name, value)
        elif field.field_type.value == "keybinding":
            self._build_keybinding_field(field, prop_name, c, value)
        elif field.field_type.value == "vec2_slider":
            self._build_vec2_slider_field(field, prop_name, value)
        elif field.field_type.value == "vec3_slider":
            self._build_vec3_slider_field(field, prop_name, value)
        elif field.field_type.value == "gradient":
            self._build_gradient_field(field, prop_name, c, value)
        elif field.field_type.value == "split_gradient":
            self._build_split_gradient_field(field, prop_name, c, value)
        elif field.field_type.value == "resource_path":
            pw = make_resource_picker(value, field.file_filter or "All Files (*)", self._undo_setter(prop_name))
            self._add_field(field.label, pw, prop_name, field.toggle_field)
        elif field.field_type.value == "string":
            self._build_string_field(field, prop_name, c, value)
        elif field.field_type.value == "textarea":
            self._build_textarea_field(field, prop_name, c, value)
        elif field.field_type.value == "layer":
            self._build_layer_field(field, prop_name, c, value)
