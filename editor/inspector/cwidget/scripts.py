# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QCheckBox, QSpinBox, QSlider, QComboBox, QDialog, QLineEdit, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from core.config.editor_scale import scale
from core.maths.math3d import Vec2, Vec3, Vec4
from core.foundation.logger import Logger
from core.foundation.curve import Curve
from editor.inspector.constants import _FUSION_INPUT_RADIUS, _accent
from editor.inspector.helpersp import make_spinbox, make_vec2_row, make_vec3_row, make_vec4_row
class ScriptsMixin:
    def _build_script_fields(self, comp):
        self._build_script_ref_row(comp)
        try:
            fields = comp.get_script_public_fields()
        except Exception:
            fields = []
        for field in fields or []:
            self._build_script_field_from_meta(field, comp)
    def _build_script_ref_row(self, comp):
        try:
            display = comp.get_script_display_name() if hasattr(comp, "get_script_display_name") else (comp.script_path or "")
        except Exception:
            display = ""
        if not display:
            display = "(none)"
        try:
            abs_path = comp.get_script_abs_path() if hasattr(comp, "get_script_abs_path") else (comp.script_path or "")
        except Exception:
            abs_path = ""
        missing = bool(comp.script_path) and not (abs_path and os.path.exists(abs_path))
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        name_btn = QPushButton(display if not missing else ("Missing: " + display))
        name_btn.setToolTip(comp.script_path or "")
        name_btn.setStyleSheet(f"""
            QPushButton {{
                border-radius: {_FUSION_INPUT_RADIUS};
                padding: 2px 6px; font-size: 11px; text-align: left;
            }}
        """)
        name_btn.setEnabled(bool(comp.script_path) and not missing)
        name_btn.clicked.connect(lambda _c=False, cc=comp: self._reveal_script_in_project(cc))
        open_btn = QPushButton("...")
        open_btn.setToolTip("Open script in Script Editor")
        open_btn.setFixedWidth(28)
        open_btn.setEnabled(bool(comp.script_path) and not missing)
        open_btn.clicked.connect(lambda _c=False, cc=comp: self._open_script_in_editor(cc))
        rl.addWidget(name_btn, 1)
        rl.addWidget(open_btn)
        self._add_field("Script", row)
    def _script_editor_path(self, comp) -> str:
        try:
            if hasattr(comp, "get_script_abs_path"):
                return comp.get_script_abs_path() or ""
        except Exception:
            pass
        return getattr(comp, "script_path", "") or ""
    def _reveal_script_in_project(self, comp):
        path = self._script_editor_path(comp)
        if not path:
            return
        try:
            mw = self.window()
            proj = getattr(mw, "_project", None)
            reveal = getattr(proj, "reveal_resource", None)
            if callable(reveal):
                reveal(path)
                return
            flash = getattr(proj, "flash_resource", None)
            if callable(flash):
                flash(path)
                return
        except Exception:
            pass
        self._open_script_in_editor(comp)
    def _open_script_in_editor(self, comp):
        path = self._script_editor_path(comp)
        if not path:
            return
        try:
            mw = self.window()
            se = getattr(mw, "_script_editor", None)
            if se is None:
                return
            opener = getattr(se, "open_script", None)
            if not callable(opener):
                widget = getattr(se, "_script_widget", None)
                opener = getattr(widget, "open_script", None)
            if callable(opener):
                opener(path)
            try:
                se.show()
                se.raise_()
            except Exception:
                pass
        except Exception as e:
            try:
                Logger.warning(f"Cannot open script '{path}': {e}")
            except Exception:
                pass
    def _build_script_field_from_meta(self, field, comp):
        prop_name = field.name
        self._current_field = field
        value = comp.get_field_value(prop_name)
        if field.field_type.value == "float":
            sb = make_spinbox(value if isinstance(value, (int, float)) else 0.0)
            def _on_float_changed(v, n=prop_name):
                comp.set_field_value(n, v)
            sb.valueChanged.connect(_on_float_changed)
            self._add_field(field.label or prop_name, sb)
        elif field.field_type.value == "int":
            sb = QSpinBox()
            sb.setRange(-9223372036854775808, 9223372036854775807)
            sb.setValue(int(value) if isinstance(value, (int, float)) else 0)
            def _on_int_changed(v, n=prop_name):
                comp.set_field_value(n, v)
            sb.valueChanged.connect(_on_int_changed)
            self._add_field(field.label or prop_name, sb)
        elif field.field_type.value == "slider":
            try:
                lo, hi = float(field.min_val), float(field.max_val)
            except Exception:
                lo, hi = 0.0, 1.0
            if hi <= lo:
                hi = lo + 1.0
            try:
                step = float(field.step) or 0.01
            except Exception:
                step = 0.01
            try:
                cur = float(value)
            except Exception:
                cur = lo
            cur = max(lo, min(hi, cur))
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            slider_scale = 1000.0
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(int(lo * slider_scale), int(hi * slider_scale))
            slider.setValue(int(cur * slider_scale))
            slider.setSingleStep(max(1, int(step * slider_scale)))
            sb = make_spinbox(cur, lo, hi, step, 4)
            _updating = [False]
            def _on_slider(v, n=prop_name, sc=slider_scale):
                if _updating[0]:
                    return
                _updating[0] = True
                try:
                    comp.set_field_value(n, v / sc)
                    sb.setValue(v / sc)
                finally:
                    _updating[0] = False
            def _on_spinbox(v, n=prop_name, sc=slider_scale):
                if _updating[0]:
                    return
                _updating[0] = True
                try:
                    comp.set_field_value(n, v)
                    slider.setValue(int(v * sc))
                finally:
                    _updating[0] = False
            slider.valueChanged.connect(_on_slider)
            sb.valueChanged.connect(_on_spinbox)
            rl.addWidget(slider, 1)
            rl.addWidget(sb)
            self._add_field(field.label or prop_name, row)
        elif field.field_type.value == "int_slider":
            try:
                min_i = max(-9223372036854775808, min(9223372036854775807, int(field.min_val)))
                max_i = max(-9223372036854775808, min(9223372036854775807, int(field.max_val)))
            except Exception:
                min_i, max_i = 0, 100
            if max_i <= min_i:
                max_i = min_i + 1
            try:
                step_i = max(1, int(field.step))
            except Exception:
                step_i = 1
            try:
                cur_i = int(value)
            except Exception:
                cur_i = min_i
            cur_i = max(min_i, min(max_i, cur_i))
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(min_i, max_i)
            slider.setValue(cur_i)
            slider.setSingleStep(step_i)
            sb = QSpinBox()
            sb.setRange(min_i, max_i)
            sb.setValue(cur_i)
            sb.setMinimumWidth(60)
            _updating_int = [False]
            def _on_slider_int(v, n=prop_name):
                if _updating_int[0]:
                    return
                _updating_int[0] = True
                try:
                    comp.set_field_value(n, v)
                    sb.setValue(v)
                finally:
                    _updating_int[0] = False
            def _on_spinbox_int(v, n=prop_name):
                if _updating_int[0]:
                    return
                _updating_int[0] = True
                try:
                    comp.set_field_value(n, v)
                    slider.setValue(v)
                finally:
                    _updating_int[0] = False
            slider.valueChanged.connect(_on_slider_int)
            sb.valueChanged.connect(_on_spinbox_int)
            rl.addWidget(slider, 1)
            rl.addWidget(sb)
            self._add_field(field.label or prop_name, row)
        elif field.field_type.value == "bool":
            cb = QCheckBox()
            cb.setChecked(bool(value))
            def _on_bool_changed(v, n=prop_name):
                comp.set_field_value(n, v)
            cb.toggled.connect(_on_bool_changed)
            self._add_field(field.label or prop_name, cb)
        elif field.field_type.value in ("string", "str"):
            te = QLineEdit()
            te.setText(str(value or ""))
            te.setStyleSheet(f"""
                QLineEdit {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QLineEdit:focus {{ border-color: {_accent()}; }}
            """)
            def _on_str_changed(v, n=prop_name):
                comp.set_field_value(n, v)
            te.textChanged.connect(_on_str_changed)
            self._add_field(field.label or prop_name, te)
        elif field.field_type.value == "vec2":
            v = value if isinstance(value, Vec2) else Vec2()
            w, sbs = make_vec2_row(field.label or "", v, lambda: None)
            def _on_vec2_changed(n=prop_name, sbs_box=sbs):
                comp.set_field_value(n, Vec2(sbs_box[0].value(), sbs_box[1].value()))
            for sb in sbs:
                sb.valueChanged.connect(_on_vec2_changed)
            self._target_layout().addWidget(w)
        elif field.field_type.value == "vec3":
            v = value if isinstance(value, Vec3) else Vec3()
            w, sbs = make_vec3_row(field.label or "", v, lambda: None)
            def _on_vec3_changed(n=prop_name, sbs_box=sbs):
                comp.set_field_value(n, Vec3(sbs_box[0].value(), sbs_box[1].value(), sbs_box[2].value()))
            for sb in sbs:
                sb.valueChanged.connect(_on_vec3_changed)
            self._target_layout().addWidget(w)
        elif field.field_type.value == "vec4":
            v = value if isinstance(value, Vec4) else Vec4(0.0, 0.0, 0.0, 0.0)
            w, sbs = make_vec4_row(field.label or "", v, lambda: None)
            def _on_vec4_changed(n=prop_name, sbs_box=sbs):
                comp.set_field_value(n, Vec4(sbs_box[0].value(), sbs_box[1].value(), sbs_box[2].value(), sbs_box[3].value()))
            for sb in sbs:
                sb.valueChanged.connect(_on_vec4_changed)
            self._target_layout().addWidget(w)
        elif field.field_type.value == "enum":
            options, enum_cls, current = self._enum_spec(field, value)
            combo = QComboBox()
            for opt in options:
                combo.addItem(opt)
            try: combo.setCurrentText(current)
            except Exception: pass
            def _on_enum_changed(v, n=prop_name):
                nv = self._enum_value(enum_cls, v)
                comp.set_field_value(n, nv)
            combo.currentTextChanged.connect(_on_enum_changed)
            self._add_field(field.label or prop_name, combo)
        elif field.field_type.value == "gameobject":
            btn = QPushButton(str(value or "") or f"Pick {field.label}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 6px; font-size: 10px; text-align: left;
                }}
            """)
            def _on_click_go(m=prop_name, cc=comp):
                from editor.inspector.widgets import pick_entity
                eid = pick_entity(self, cc.get_field_value(m) or "")
                if eid:
                    cc.set_field_value(m, eid)
                    btn.setText(str(eid))
            btn.clicked.connect(_on_click_go)
            self._add_field(field.label or prop_name, btn)
        elif field.field_type.value == "resource":
            filter_str = field.file_filter or ""
            btn = QPushButton(str(value or "") or f"Pick {field.label}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 6px; font-size: 10px; text-align: left;
                }}
            """)
            def _on_click_r(m=prop_name, cc=comp, fs=filter_str):
                from editor.picker import pick_resource
                p = pick_resource(self, "Select Resource", fs, cc.get_field_value(m) or "")
                if p:
                    cc.set_field_value(m, p)
                    btn.setText(str(p))
            btn.clicked.connect(_on_click_r)
            self._add_field(field.label or prop_name, btn)
        elif field.field_type.value == "resource_type":
            from core.components.scripting.scriptc import RESOURCE_TYPE_FILTERS
            filter_str = RESOURCE_TYPE_FILTERS.get(field.resource_type, "")
            btn = QPushButton(str(value or "") or f"Pick {field.label}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 6px; font-size: 10px; text-align: left;
                }}
            """)
            def _on_click_rt(m=prop_name, cc=comp, fs=filter_str):
                from editor.picker import pick_resource
                p = pick_resource(self, "Select Resource", fs, cc.get_field_value(m) or "")
                if p:
                    cc.set_field_value(m, p)
                    btn.setText(str(p))
            btn.clicked.connect(_on_click_rt)
            self._add_field(field.label or prop_name, btn)
        elif field.field_type.value == "curve":
            from editor.curve import CurvePreview, CurveEditorDialog
            preview = CurvePreview()
            preview.setMinimumHeight(scale(56))
            preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cv = comp.get_field_value(prop_name)
            if isinstance(cv, Curve):
                preview.set_curve(cv)
            def _open_curve_editor(_pn=prop_name, _preview=preview, _label=field.label):
                cur = comp.get_field_value(_pn)
                edit_curve = cur.copy() if isinstance(cur, Curve) else Curve()
                dlg = CurveEditorDialog(edit_curve, _label, self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    comp.set_field_value(_pn, dlg.get_curve())
                    _preview.set_curve(dlg.get_curve())
            preview.mousePressEvent = lambda ev, pe=_open_curve_editor: pe() if ev.button() == Qt.MouseButton.LeftButton else None
            self._add_field(field.label or prop_name, preview)
        elif field.field_type.value == "button":
            btn = QPushButton(field.label or prop_name)
            def _on_script_button(_checked=False, mn=prop_name, cc=comp):
                try:
                    if getattr(cc, "_py_instance", None) is None:
                        try:
                            cc._load_script()
                        except Exception:
                            pass
                    inst = getattr(cc, "_py_instance", None)
                    fn = getattr(inst, mn, None)
                    if callable(fn):
                        fn()
                    else:
                        Logger.warning(f"Script button '{mn}' has no callable method")
                except Exception as e:
                    try:
                        Logger.error(f"Script button '{mn}' error: {e}")
                    except Exception:
                        pass
            btn.clicked.connect(_on_script_button)
            self._add_field("", btn)
    def _on_script_gameobject_changed(self, comp, prop_name, value):
        pass
    def _on_script_resource_changed(self, comp, prop_name, value):
        pass
