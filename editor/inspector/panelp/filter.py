# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QDoubleSpinBox, QSpinBox, QCheckBox, QSizePolicy
from editor.inspector.helpersp import make_resource_picker
from editor.inspector.panelp.util import _smart_label_width

class InspectorFilterMixin:
    def _on_search_changed(self, text: str):
        for cw in self._comp_widgets:
            try:
                cw.set_filter(text)
            except Exception:
                pass

    def _add_shader_property_widget(self, sp, props, _save, _update_preview):
        from editor.picker import pick_resource
        from PyQt6.QtGui import QColor
        prop_type = sp.prop_type
        key = sp.name
        label = sp.display_name
        if prop_type in ("2D", "cube"):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            def _on_pick(p):
                try:
                    props[key] = p
                except Exception:
                    pass
                try:
                    _save()
                except Exception:
                    pass
                try:
                    _update_preview()
                except Exception:
                    pass
            tex_legacy = {
                "_BaseMap": "albedo_texture",
                "_NormalMap": "normal_texture",
                "_RoughnessMap": "roughness_texture",
                "_OcclusionMap": "occlusion_texture",
                "_EmissionMap": "emission_texture",
            }
            current = props.get(key) or props.get(tex_legacy.get(key, ""))
            picker = make_resource_picker(current, "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff *.webp *.hdr *.exr *.dds *.svg)", _on_pick)
            rl.addWidget(picker, 1)
            self._add_asset_widget(row)
        elif prop_type == "Color":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            from editor.color import ColorLineEdit
            try:
                _cc = props.get(key, [1.0, 1.0, 1.0, 1.0])
                if not isinstance(_cc, (list, tuple)) or len(_cc) < 3:
                    _cc = [1.0, 1.0, 1.0, 1.0]
            except Exception:
                _cc = [1.0, 1.0, 1.0, 1.0]
            cl = ColorLineEdit(_cc)
            def _on_color(_, _key=key):
                try:
                    props[_key] = cl.get_color_rgba()
                except Exception:
                    pass
                try:
                    _save()
                except Exception:
                    pass
                try:
                    _update_preview()
                except Exception:
                    pass
            cl.colorChanged.connect(_on_color)
            rl.addWidget(cl, 1)
            self._add_asset_widget(row)
        elif prop_type == "Range":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            sb = QDoubleSpinBox()
            try:
                lo = float(sp.range_min)
                hi = float(sp.range_max)
            except Exception:
                lo, hi = 0.0, 1.0
            try:
                if not (lo <= hi):
                    lo, hi = hi, lo
                if lo == hi:
                    hi = lo + 1.0
                sb.setRange(lo, hi)
            except Exception:
                try:
                    sb.setRange(0.0, 1.0)
                    lo, hi = 0.0, 1.0
                except Exception:
                    pass
            try:
                step = (hi - lo) / 100.0
                if not step or step <= 0.0:
                    step = 0.01
                sb.setSingleStep(float(step))
            except Exception:
                try:
                    sb.setSingleStep(0.01)
                except Exception:
                    pass
            raw = props.get(key, 0.0)
            try:
                sb.setValue(float(raw))
            except (ValueError, TypeError):
                try:
                    sb.setValue(float(sp.default_value) if isinstance(sp.default_value, (int, float)) else 0.0)
                except Exception:
                    sb.setValue(0.0)
            except Exception:
                try:
                    sb.setValue(0.0)
                except Exception:
                    pass
            def _on_change(v, _key=key):
                try:
                    props[_key] = v
                except Exception:
                    pass
                try:
                    _save()
                except Exception:
                    pass
                try:
                    _update_preview()
                except Exception:
                    pass
            sb.valueChanged.connect(_on_change)
            rl.addWidget(sb, 1)
            self._add_asset_widget(row)
        elif prop_type in ("Float", "Int"):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            if prop_type == "Int":
                sb = QSpinBox()
                sb.setRange(-999999, 999999)
            else:
                sb = QDoubleSpinBox()
                sb.setRange(-999999.0, 999999.0)
                sb.setSingleStep(0.1)
            raw_val = props.get(key, 0)
            try:
                sb.setValue(int(raw_val) if prop_type == "Int" else float(raw_val))
            except (ValueError, TypeError):
                try:
                    sb.setValue(0 if prop_type == "Int" else 0.0)
                except Exception:
                    pass
            except Exception:
                try:
                    sb.setValue(0 if prop_type == "Int" else 0.0)
                except Exception:
                    pass
            def _on_change(v, _key=key):
                try:
                    props[_key] = v
                except Exception:
                    pass
                try:
                    _save()
                except Exception:
                    pass
                try:
                    _update_preview()
                except Exception:
                    pass
            sb.valueChanged.connect(_on_change)
            rl.addWidget(sb, 1)
            self._add_asset_widget(row)
        elif prop_type == "Gradient":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            from editor.gradient import GradientLineEdit
            try:
                _gv = props.get(key, None)
                _valid = False
                if isinstance(_gv, (list, tuple)) and len(_gv) >= 2:
                    _valid = True
                    for _s in _gv:
                        try:
                            if not isinstance(_s, (list, tuple)) or len(_s) != 2:
                                _valid = False
                                break
                            float(_s[0])
                            _c = _s[1]
                            if not isinstance(_c, (list, tuple)) or len(_c) < 3:
                                _valid = False
                                break
                            for _cc in _c[:4]:
                                float(_cc)
                        except Exception:
                            _valid = False
                            break
                if not _valid:
                    _gv = None
            except Exception:
                _gv = None
            gle = GradientLineEdit(_gv)
            def _on_gradient(_, _key=key):
                try:
                    props[_key] = gle.get_stops()
                except Exception:
                    pass
                try:
                    _save()
                except Exception:
                    pass
                try:
                    _update_preview()
                except Exception:
                    pass
            gle.gradientChanged.connect(_on_gradient)
            rl.addWidget(gle, 1)
            self._add_asset_widget(row)

    def _add_fallback_widget(self, key, cfg, props, _save, _update_preview):
        from editor.picker import pick_resource
        from PyQt6.QtGui import QColor
        label = cfg["label"]
        widget_type = cfg["widget"]
        if widget_type == "texture":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            def _on_pick(p, _key=key):
                props[_key] = p
                _save()
                _update_preview()
            tex_candidates = {
                "albedo_texture": ("albedo_texture", "_BaseMap", "_MainTex", "diffuseMap", "_BaseTex"),
                "normal_texture": ("normal_texture", "_NormalMap"),
                "roughness_texture": ("roughness_texture", "_RoughnessMap"),
            }
            current = ""
            for cand in tex_candidates.get(key, (key,)):
                if props.get(cand):
                    current = props[cand]
                    break
            picker = make_resource_picker(current, "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff *.webp *.hdr *.exr *.dds *.svg)", _on_pick)
            rl.addWidget(picker, 1)
            self._add_asset_widget(row)
        elif widget_type == "color":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            from editor.color import ColorLineEdit
            cl = ColorLineEdit(props.get(key, [1.0, 1.0, 1.0, 1.0]))
            def _on_color(_, _key=key):
                props[_key] = cl.get_color_rgba()
                _save()
                _update_preview()
            cl.colorChanged.connect(_on_color)
            rl.addWidget(cl, 1)
            self._add_asset_widget(row)
        elif widget_type == "slider":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            sb = QDoubleSpinBox()
            sb.setRange(cfg.get("min", 0.0), cfg.get("max", 1.0))
            sb.setSingleStep(cfg.get("step", 0.01))
            raw = props.get(key, 0.0)
            try:
                sb.setValue(float(raw))
            except (ValueError, TypeError):
                sb.setValue(cfg.get("min", 0.0))
            def _on_change(v, _key=key):
                props[_key] = v
                _save()
                _update_preview()
            sb.valueChanged.connect(_on_change)
            rl.addWidget(sb, 1)
            self._add_asset_widget(row)
        elif widget_type == "toggle":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            from PyQt6.QtWidgets import QCheckBox
            cb = QCheckBox()
            cb.setChecked(bool(props.get(key, False)))
            def _on_toggle(v, _key=key):
                props[_key] = bool(v)
                _save()
                _update_preview()
            cb.toggled.connect(_on_toggle)
            rl.addWidget(cb, 1)
            self._add_asset_widget(row)
        elif widget_type == "gradient":
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            lbl = QLabel(label)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            from editor.gradient import GradientLineEdit
            gle = GradientLineEdit(props.get(key, None))
            def _on_gradient(_, _key=key):
                props[_key] = gle.get_stops()
                _save()
                _update_preview()
            gle.gradientChanged.connect(_on_gradient)
            rl.addWidget(gle, 1)
            self._add_asset_widget(row)

    def _build_section_title(self, text: str):
        lbl = QLabel(text)
        self._content_layout.addWidget(lbl)

    def _animator_input_style(self) -> str:
        return ""

    def _animator_btn_style(self) -> str:
        return ""

    def get_filter_text(self):
        try:
            return self._search_edit.text()
        except Exception:
            return ""
    def clear_filter(self):
        try:
            self._search_edit.clear()
        except Exception:
            pass
        return True
    def apply_filter(self, text: str):
        for cw in self._comp_widgets:
            try:
                cw.set_filter(text)
            except Exception:
                pass
        return True
