# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QDoubleSpinBox, QComboBox, QCheckBox, QSizePolicy
from core.config.editor_scale import scale
from editor.inspector.constants import _FUSION_ACCENT_RED, _accent
from editor.inspector.helpersp import make_resource_picker
from editor.inspector.panelp.util import _smart_label_width
from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history

class InspectorClipboardMixin:
    _clipboard = None
    def _build_material_editor(self):
        from core.assets.matp import Material, MaterialLibrary
        from editor.material_preview import MaterialPreviewWidget
        eng = self._engine
        root = eng.project_root if eng else ""
        if root and not os.path.isabs(self._asset_path):
            abs_path = os.path.normpath(os.path.join(root, self._asset_path))
        else:
            abs_path = os.path.normpath(self._asset_path)
        mat = MaterialLibrary._materials.get(abs_path)
        if mat is None:
            try:
                mat = Material.load(self._asset_path, root)
            except Exception:
                mat = None
        if mat is None:
            lbl = QLabel("Failed to load material.")
            lbl.setStyleSheet(f"color: {_FUSION_ACCENT_RED};")
            self._add_asset_widget(lbl)
            return
        props = mat.properties
        shader_props = mat._shader_properties
        preview = MaterialPreviewWidget()
        preview.setFixedHeight(200)
        preview_vals = {}
        ac = props.get("albedo_color") or props.get("_BaseColor")
        try:
            if isinstance(ac, (list, tuple)) and len(ac) >= 3:
                preview_vals["albedo"] = list(ac[:4])
        except Exception:
            pass
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
            try:
                mat.save(self._asset_path, self._engine.project_root if self._engine else root)
            except Exception:
                pass
        def _update_preview():
            try:
                try:
                    from PyQt6 import sip as _sip
                    if _sip.isdeleted(preview):
                        return
                except Exception:
                    try:
                        import sip as _sip2
                        if _sip2.isdeleted(preview):
                            return
                    except Exception:
                        pass
                pv = {}
                ac = props.get("albedo_color") or props.get("_BaseColor")
                if ac is not None:
                    try:
                        if isinstance(ac, (list, tuple)) and len(ac) >= 3:
                            pv["albedo"] = list(ac[:4])
                    except Exception:
                        pass
                m = props.get("metallic") if "metallic" in props else props.get("_Metallic")
                if isinstance(m, (int, float)):
                    pv["metallic"] = float(m)
                s = props.get("smoothness") if "smoothness" in props else props.get("_Smoothness")
                if isinstance(s, (int, float)):
                    pv["smoothness"] = float(s)
                ec = props.get("emission_color") or props.get("_EmissionColor")
                if ec is not None:
                    try:
                        if isinstance(ec, (list, tuple)) and len(ec) >= 3:
                            pv["emission"] = list(ec[:3])
                    except Exception:
                        pass
                ei = props.get("emission_intensity") if "emission_intensity" in props else props.get("_EmissionIntensity")
                if isinstance(ei, (int, float)):
                    pv["emit_intensity"] = float(ei)
                for tex_key in ("albedo_texture", "_BaseMap", "_BaseTex"):
                    try:
                        v = props.get(tex_key)
                        if isinstance(v, str) and v:
                            pv["albedo_tex"] = v
                            break
                    except Exception:
                        continue
                if pv:
                    preview.set_properties(**pv)
            except Exception:
                pass
        shader_row = QWidget()
        shader_rl = QHBoxLayout(shader_row)
        shader_rl.setContentsMargins(0, 2, 0, 2)
        shader_lbl = QLabel("Shader")
        shader_lbl_min = _smart_label_width(shader_lbl)
        shader_lbl.setMinimumWidth(shader_lbl_min)
        shader_lbl.setMaximumWidth(int(shader_lbl_min * 1.8))
        shader_lbl.setWordWrap(True)
        shader_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        shader_rl.addWidget(shader_lbl, 0)
        def _store_shader(p: str) -> str:
            if p and os.path.isabs(p):
                try:
                    from core.assets.matp import _project_root as _eng_root
                    norm = os.path.normpath(p)
                    eng = os.path.normpath(_eng_root())
                    if norm == eng or norm.startswith(eng + os.sep):
                        return os.path.relpath(norm, eng).replace("\\", "/")
                    root = self._engine.project_root if self._engine else os.getcwd()
                    if root:
                        proj = os.path.normpath(os.path.abspath(root))
                        if norm == proj or norm.startswith(proj + os.sep):
                            return os.path.relpath(norm, proj).replace("\\", "/")
                except Exception:
                    pass
            return p
        def _on_shader_pick(p):
            try:
                if not p:
                    return
                p = _store_shader(p)
                if p == mat.shader_path:
                    return
                proj_root = self._engine.project_root if self._engine else root
                mat.shader_path = p
                try:
                    mat.load_shader_properties(p, proj_root)
                except Exception:
                    try:
                        mat._shader_properties = []
                    except Exception:
                        pass
                try:
                    props.clear()
                except Exception:
                    pass
                try:
                    for sp in list(mat._shader_properties):
                        try:
                            props[sp.name] = sp.default_value
                        except Exception:
                            continue
                except Exception:
                    pass
                try:
                    _save()
                except Exception:
                    pass
                try:
                    self._rebuild()
                except Exception:
                    pass
            except Exception:
                pass
        shader_picker = make_resource_picker(mat.shader_path, "Shaders (*.shader *.vert *.frag *.glsl *.hlsl *.compute)", _on_shader_pick)
        shader_rl.addWidget(shader_picker, 1)
        self._add_asset_widget(shader_row)
        if shader_props:
            tex_props = [p for p in shader_props if p.prop_type in ("2D", "cube")]
            non_tex_props = [p for p in shader_props if p.prop_type not in ("2D", "cube")]
            for sp in non_tex_props:
                self._add_shader_property_widget(sp, props, _save, _update_preview)
            if tex_props:
                sep = QLabel("<b>Textures</b>")
                self._add_asset_widget(sep)
                for sp in tex_props:
                    self._add_shader_property_widget(sp, props, _save, _update_preview)
        else:
            known_keys = {
                "_BaseColor": {"label": "Albedo", "widget": "color"},
                "albedo_texture": {"label": "Albedo Map", "widget": "texture"},
                "_Metallic": {"label": "Metallic", "widget": "slider", "min": 0, "max": 1, "step": 0.01},
                "_Smoothness": {"label": "Smoothness", "widget": "slider", "min": 0, "max": 1, "step": 0.01},
                "_EmissionColor": {"label": "Emission", "widget": "color"},
                "_EmissionIntensity": {"label": "Emission Intensity", "widget": "slider", "min": 0, "max": 100, "step": 0.1},
                "normal_texture": {"label": "Normal Map", "widget": "texture"},
                "roughness_texture": {"label": "Roughness Map", "widget": "texture"},
                "double_sided": {"label": "Double Sided", "widget": "toggle"},
            }
            tex_seen = False
            for key, cfg in known_keys.items():
                if cfg["widget"] == "texture" and not tex_seen:
                    sep = QLabel("<b>Textures</b>")
                    self._add_asset_widget(sep)
                    tex_seen = True
                self._add_fallback_widget(key, cfg, props, _save, _update_preview)
        self._add_asset_widget(QLabel(""))

    def _build_physic_material_editor(self):
        from core.assets.physics_material import PhysicsMaterial, PhysicCombineMode
        eng = self._engine
        root = eng.project_root if eng else ""
        if root and not os.path.isabs(self._asset_path):
            abs_path = os.path.normpath(os.path.join(root, self._asset_path))
        else:
            abs_path = os.path.normpath(self._asset_path)
        mat = PhysicsMaterial.load(self._asset_path, root)
        if mat is None:
            lbl = QLabel("Failed to load physic material.")
            lbl.setStyleSheet(f"color: {_FUSION_ACCENT_RED};")
            self._add_asset_widget(lbl)
            return

        def _save():
            mat.save(self._asset_path, root)

        def _make_row(label_text: str, widget: QWidget) -> QWidget:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(4)
            lbl = QLabel(label_text)
            lbl_min = _smart_label_width(lbl)
            lbl.setMinimumWidth(lbl_min)
            lbl.setMaximumWidth(int(lbl_min * 1.8))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            rl.addWidget(lbl, 0)
            rl.addWidget(widget, 1)
            return row

        df_sb = QDoubleSpinBox()
        df_sb.setRange(0.0, 1.0)
        df_sb.setSingleStep(0.01)
        df_sb.setDecimals(3)
        df_sb.setValue(mat.dynamic_friction)
        def _on_df(v, _m=mat):
            _m.dynamic_friction = v; _save()
        df_sb.valueChanged.connect(_on_df)
        self._add_asset_widget(_make_row("Dynamic Friction", df_sb))

        sf_sb = QDoubleSpinBox()
        sf_sb.setRange(0.0, 1.0)
        sf_sb.setSingleStep(0.01)
        sf_sb.setDecimals(3)
        sf_sb.setValue(mat.static_friction)
        def _on_sf(v, _m=mat):
            _m.static_friction = v; _save()
        sf_sb.valueChanged.connect(_on_sf)
        self._add_asset_widget(_make_row("Static Friction", sf_sb))

        b_sb = QDoubleSpinBox()
        b_sb.setRange(0.0, 1.0)
        b_sb.setSingleStep(0.01)
        b_sb.setDecimals(3)
        b_sb.setValue(mat.bounciness)
        def _on_b(v, _m=mat):
            _m.bounciness = v; _save()
        b_sb.valueChanged.connect(_on_b)
        self._add_asset_widget(_make_row("Bounciness", b_sb))

        fc_cb = QComboBox()
        for mode in PhysicCombineMode:
            fc_cb.addItem(mode.label, mode.value)
        idx = next((i for i, m in enumerate(PhysicCombineMode) if m == mat.friction_combine), 0)
        fc_cb.setCurrentIndex(idx)
        def _on_fc(idx, _m=mat, _cb=fc_cb):
            _m.friction_combine = PhysicCombineMode(_cb.currentData()); _save()
        fc_cb.currentIndexChanged.connect(_on_fc)
        self._add_asset_widget(_make_row("Friction Combine", fc_cb))

        bc_cb = QComboBox()
        for mode in PhysicCombineMode:
            bc_cb.addItem(mode.label, mode.value)
        idx = next((i for i, m in enumerate(PhysicCombineMode) if m == mat.bounce_combine), 0)
        bc_cb.setCurrentIndex(idx)
        def _on_bc(idx, _m=mat, _cb=bc_cb):
            _m.bounce_combine = PhysicCombineMode(_cb.currentData()); _save()
        bc_cb.currentIndexChanged.connect(_on_bc)
        self._add_asset_widget(_make_row("Bounce Combine", bc_cb))

    def _relativize_asset_path(self, path: str) -> str:
        if not path:
            return ""
        root = self._engine.project_root if self._engine else os.getcwd()
        try:
            return os.path.relpath(path, root).replace("\\", "/")
        except ValueError:
            return path

    def copy_component(self, comp_name: str, comp_key: str = ""):
        ent = self._entity
        if ent is None:
            return None
        target = comp_key or comp_name
        comp = None
        try:
            comp = ent._components.get(target, None)
        except Exception:
            comp = None
        if comp is None:
            try:
                for k, c in ent._components.items():
                    if k == comp_name or k.startswith(comp_name + "."):
                        comp = c
                        target = k
                        break
            except Exception:
                return None
        if comp is None:
            return None
        try:
            data = comp.serialize() if hasattr(comp, "serialize") else {}
        except Exception:
            data = {}
        type(self)._clipboard = {"mode": "component", "type": type(comp).__name__, "key": target, "data": data}
        return type(self)._clipboard
    def paste_component_values(self):
        cb = type(self)._clipboard
        if cb is None:
            return False
        try:
            target_type = cb.get("type", "")
            source = cb.get("data", {})
        except Exception:
            return False
        if not target_type or not source:
            return False
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(target_type)
        if cls is None:
            return False
        ents = list(self._selected_entities) if self._selected_entities else ([self._entity] if self._entity else [])
        cmds = []
        for ent in ents:
            try:
                comp = ent.get_component(cls)
            except Exception:
                continue
            if comp is None:
                continue
            for k, v in source.items():
                if k in ("type", "_key", "enabled"):
                    continue
                try:
                    old = getattr(comp, k, None)
                except Exception:
                    continue
                if old is None:
                    continue
                try:
                    setattr(comp, k, v)
                except Exception:
                    continue
                cmds.append(SetComponentCommand(ent, cls, k, old, v))
        if not cmds:
            return False
        if len(cmds) == 1:
            get_history().execute(cmds[0])
        else:
            get_history().execute(CompoundCommand(cmds, "Paste " + target_type))
        try:
            self._rebuild()
        except Exception:
            pass
        return True
    def clear_clipboard(self):
        type(self)._clipboard = None
        return True
