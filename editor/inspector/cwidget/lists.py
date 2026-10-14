# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QSpinBox, QComboBox, QLineEdit, QSizePolicy, QMenu
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import qtawesome as qta
from core.config.editor_scale import scale_xy
from core.maths.math3d import Vec3
from core.physics.collision_layers import MAX_LAYERS, DEFAULT_LAYER_NAMES
from core.config.config import get_project_config
from editor.inspector.constants import _FUSION_INPUT_RADIUS, _accent, _window_text
from editor.inspector.helpers import make_spinbox, make_gameobject_picker, make_resource_picker, make_resource_type_picker, make_vec3_row
class ListsMixin:
    def _build_list_field_standalone(self, field, prop_name):
        c = self._component
        self._list_submesh_names = self._get_submesh_names()
        old = getattr(self, "_list_container", None)
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(2)
        lbl = QLabel(field.label)
        hl.addWidget(lbl)
        add_btn = QPushButton("+")
        add_btn.setFixedSize(*scale_xy(18, 18))
        add_btn.setStyleSheet(f"""
            QPushButton {{ color: {_accent()}; font-size: 10px; background: transparent; border: none; }}
        """)
        add_btn.clicked.connect(lambda: self._list_add_item(c, prop_name))
        hl.addStretch()
        hl.addWidget(add_btn)
        cl.addWidget(header)
        self._list_container = container
        def rebuild_list():
            for i in reversed(range(cl.count())):
                w = cl.itemAt(i).widget()
                if w is not header and w is not None:
                    w.deleteLater()
            items = getattr(c, prop_name, [])
            element_fields = self._get_list_element_fields(prop_name)
            for idx, elem in enumerate(items):
                row = self._build_list_row_standalone(prop_name, idx, elem, element_fields)
                cl.addWidget(row)
        rebuild_list()
        self._target_layout().addWidget(container)
    def _list_item_label(self, prop_name, index):
        if type(self._component).__name__ == "MeshRenderer" and prop_name == "materials":
            names = getattr(self, "_list_submesh_names", None)
            if names is None:
                names = self._get_submesh_names()
            if names and len(names) > 1:
                return names[index] if (index < len(names) and names[index]) else f"Submesh {index}"
        if type(self._component).__name__ == "BlendShapes" and prop_name == "shapes":
            try:
                items = getattr(self._component, "shapes", [])
                if 0 <= index < len(items):
                    label = str(items[index].get("name", ""))
                    if label:
                        return label
            except Exception:
                pass
            return f"Shape {index}"
        return ""
    def _list_min_length(self, prop_name):
        if type(self._component).__name__ == "MeshRenderer" and prop_name == "materials":
            names = getattr(self, "_list_submesh_names", None)
            if names is None:
                names = self._get_submesh_names()
            if names and len(names) > 1:
                return len(names)
        return 0
    def _get_submesh_names(self):
        if self._entity is None:
            return []
        try:
            from core.components.rendering.renderers.mesh_filter import MeshFilter
            from core.engine.engine import Engine
            eng = Engine.instance()
            r = getattr(eng, '_renderer', None)
            if r is None:
                vp = getattr(eng, 'viewport', None)
                r = getattr(vp, '_renderer', None)
            if r is None or r._mesh_loader is None:
                return []
            mf = self._entity.get_component(MeshFilter)
            if mf is None:
                return []
            key = mf.mesh_path
            if not key:
                return []
            meshes = r._mesh_loader._meshes
            mesh = meshes.get(key)
            if mesh is None:
                prefix = key + "|"
                for k, v in meshes.items():
                    if k.startswith(prefix):
                        mesh = v
                        break
            if mesh is not None:
                names = getattr(mesh, 'sub_mesh_names', None)
                if names:
                    return list(names)
        except Exception:
            pass
        return []
    def _build_list_row_standalone(self, prop_name, index, elem_data, element_fields):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)
        remove_btn = QPushButton("\u2212")
        remove_btn.setFixedSize(*scale_xy(16, 16))
        remove_btn.setStyleSheet(f"""
            QPushButton {{ color: {_window_text()}; font-size: 10px; background: transparent; border: none; }}
        """)
        remove_btn.clicked.connect(lambda: self._list_remove_item(self._component, prop_name, index))
        rl.addWidget(remove_btn)
        item_label = self._list_item_label(prop_name, index)
        if item_label:
            lbl = QLabel(item_label)
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
        elem_widget = QWidget()
        el = QHBoxLayout(elem_widget)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(2)
        for ef in element_fields:
            w = self._build_list_element_widget_standalone(prop_name, index, ef, elem_data)
            if w:
                el.addWidget(w)
        rl.addWidget(elem_widget, 1)
        return row
    def _build_list_element_widget_standalone(self, prop_name, index, ef, val):
        if ef.field_type.value == "float":
            sb = make_spinbox(val.get(ef.name, 0.0) if isinstance(val, dict) else 0.0)
            sb.setStyleSheet(f"""
                QDoubleSpinBox {{
                    background: palette(base); color: palette(text);
                    border: 1px solid palette(mid); border-radius: 2px; padding: 2px;
                }}
            """)
            def on_change(v, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = v
                    setattr(self._component, pn, items)
            sb.valueChanged.connect(on_change)
            return sb
        elif ef.field_type.value == "int":
            sb = QSpinBox()
            sb.setRange(-9223372036854775808, 9223372036854775807)
            sb.setValue(val.get(ef.name, 0) if isinstance(val, dict) else 0)
            sb.setStyleSheet(f"""
                QSpinBox {{
                    background: palette(base); color: palette(text);
                    border: 1px solid palette(mid); border-radius: 2px; padding: 2px;
                }}
            """)
            def on_change(v, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = v
                    setattr(self._component, pn, items)
            sb.valueChanged.connect(on_change)
            return sb
        elif ef.field_type.value == "bool":
            cb = QCheckBox()
            cb.setChecked(val.get(ef.name, False) if isinstance(val, dict) else False)
            cb.setStyleSheet("background: transparent;")
            def on_toggle(v, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = v
                    setattr(self._component, pn, items)
            cb.toggled.connect(on_toggle)
            return cb
        elif ef.field_type.value == "gameobject":
            from core.engine.engine import Engine
            scene = Engine.instance().scene
            eid = val.get(ef.name, "") if isinstance(val, dict) else ""
            def on_entity(eid, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = eid
                    setattr(self._component, pn, items)
            return make_gameobject_picker(eid, scene, on_entity)
        elif ef.field_type.value == "enum":
            raw = val.get(ef.name, "") if isinstance(val, dict) else ""
            options, enum_cls, current = self._enum_spec(ef, raw)
            combo = QComboBox()
            for opt in options:
                combo.addItem(opt)
            try: combo.setCurrentText(current)
            except Exception: pass
            def on_change(t, idx=index, pn=prop_name, fn=ef.name):
                nv = self._enum_value(enum_cls, t)
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = nv
                    setattr(self._component, pn, items)
            combo.currentTextChanged.connect(on_change)
            return combo
        elif ef.field_type.value == "resource" or ef.field_type.value == "resource_path":
            path = val.get(ef.name, "") if isinstance(val, dict) else ""
            filter_str = ef.file_filter or "All Files (*)"
            def on_change(t, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = t
                    setattr(self._component, pn, items)
            return make_resource_picker(path, filter_str, on_change)
        elif ef.field_type.value == "resource_type":
            path = val.get(ef.name, "") if isinstance(val, dict) else ""
            rt = ef.resource_type or ""
            def on_change(t, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = t
                    setattr(self._component, pn, items)
            return make_resource_type_picker(path, rt, on_change)
        elif ef.field_type.value == "string" or ef.field_type.value == "text":
            te = QLineEdit()
            te.setText(str(val.get(ef.name, "")) if isinstance(val, dict) else "")
            te.setStyleSheet(f"""
                QLineEdit {{
                    background: palette(base); color: palette(text);
                    border: 1px solid palette(mid); border-radius: 2px; padding: 2px 4px; font-size: 11px;
                }}
            """)
            def on_change(t, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = t
                    setattr(self._component, pn, items)
            te.textChanged.connect(on_change)
            return te
        elif ef.field_type.value == "vec3":
            val_vec = val.get(ef.name, Vec3(0, 0, 0)) if isinstance(val, dict) else Vec3(0, 0, 0)
            w, sbs = make_vec3_row(ef.label or "", val_vec, lambda: None)
            def on_change(_, idx=index, pn=prop_name, fn=ef.name, boxes=sbs):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = Vec3(boxes[0].value(), boxes[1].value(), boxes[2].value())
                    setattr(self._component, pn, items)
            for sb in sbs:
                sb.valueChanged.connect(on_change)
            return w
        elif ef.field_type.value == "color":
            from editor.color_picker import ColorLineEdit
            rgb = val.get(ef.name, [1, 1, 1]) if isinstance(val, dict) else [1, 1, 1]
            initial = QColor.fromRgbF(*rgb[:3])
            color_edit = ColorLineEdit(initial)
            color_edit.setFixedSize(*scale_xy(60, 20))
            def on_change(col, idx=index, pn=prop_name, fn=ef.name):
                items = list(getattr(self._component, pn))
                if idx < len(items) and isinstance(items[idx], dict):
                    items[idx][fn] = [col.redF(), col.greenF(), col.blueF()]
                    setattr(self._component, pn, items)
            color_edit.colorChanged.connect(on_change)
            return color_edit
        return None
    def _list_add_item(self, component, prop_name):
        items = list(getattr(component, prop_name, []))
        items.append({})
        setattr(component, prop_name, items)
        self._build_list_field_standalone(
            [f for f in getattr(type(component), "_inspector_fields", lambda: [])() if f.name == prop_name][0],
            prop_name
        )
    def _list_remove_item(self, component, prop_name, index):
        items = list(getattr(component, prop_name, []))
        if 0 <= index < len(items):
            items.pop(index)
            setattr(component, prop_name, items)
        self._build_list_field_standalone(
            [f for f in getattr(type(component), "_inspector_fields", lambda: [])() if f.name == prop_name][0],
            prop_name
        )
    def _list_set_entity(self, component, prop_name, index, field_name, entity_id):
        items = list(getattr(component, prop_name, []))
        if index < len(items) and isinstance(items[index], dict):
            items[index][field_name] = entity_id
            setattr(component, prop_name, items)
    def _get_list_element_fields(self, prop_name):
        from core.components.inspector_meta import InspectorField
        fields = getattr(type(self._component), "_inspector_fields", lambda: [])()
        for f in fields:
            if f.name == prop_name:
                return f.element_fields or []
        return []
    def _build_layer_mask_field(self, field, prop_name):
        btn = QPushButton("Everything")
        btn.setStyleSheet(f"""
                QPushButton {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 6px;
                    font-size: 10px;
                    text-align: left;
                }}
            """)
        btn.setMinimumHeight(22)
        from core.engine.engine import Engine
        cfg = get_project_config(Engine.instance().project_root)
        layer_names = cfg.get("physics.layer_names", DEFAULT_LAYER_NAMES) if cfg else DEFAULT_LAYER_NAMES
        menu = QMenu(self)
        all_act = menu.addAction("Everything")
        all_act.setCheckable(True)
        all_act.setChecked(True)
        all_act.triggered.connect(lambda checked: self._on_layer_mask_set_all(prop_name, checked, btn, layer_names, menu))
        nothing_act = menu.addAction("Nothing")
        nothing_act.setCheckable(True)
        nothing_act.triggered.connect(lambda checked: self._on_layer_mask_set_all(prop_name, not checked, btn, layer_names, menu))
        menu.addSeparator()
        for i in range(MAX_LAYERS):
            name = layer_names[i] if i < len(layer_names) else f"Layer{i}"
            act = menu.addAction(name)
            act.setCheckable(True)
            mask = int(getattr(self._component, prop_name))
            act.setChecked(bool(mask & (1 << i)))
            act.triggered.connect(lambda checked, b=i, b0=btn, lm=layer_names, m=menu, al=all_act, nt=nothing_act: self._on_layer_mask_toggle(prop_name, b, b0, lm, m, al, nt))
        _mask = int(getattr(self._component, prop_name))
        self._update_layer_mask_text(btn, _mask, layer_names)
        self._add_field(field.label, btn, prop_name, field.toggle_field)
    def _build_layer_field(self, field, prop_name, c, value):
        sb = QSpinBox()
        sb.setRange(0, 31)
        sb.setValue(int(value) if value is not None else 0)
        sb.setMinimumWidth(60)
        comp_cls = type(c)
        sb.valueChanged.connect(self._undo_setter_all(comp_cls, prop_name))
        self._add_field(field.label, sb, prop_name, field.toggle_field)
