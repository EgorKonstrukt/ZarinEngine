# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
import json
import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QDoubleSpinBox, QSpinBox, QComboBox, QFrame, QSizePolicy
from PyQt6.QtCore import QTimer
import editor.icons as qta
from core.config.editor_scale import scale
from editor.inspector.constants import _accent
from editor.inspector.helpersp import make_resource_picker
from editor.inspector.panelp.util import _smart_label_width

class InspectorSectionsMixin:
    def _build_import_settings(self):
        self._updating = True
        name = os.path.basename(self._asset_path)
        ext = os.path.splitext(name)[1].lower()
        title = QLabel(f"<b>{name}</b>")
        self._add_asset_widget(title)
        info = QLabel(f"Path: {self._asset_path}")
        info.setWordWrap(True)
        self._add_asset_widget(info)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        self._add_asset_widget(sep)
        if ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
            self._build_mesh_import_settings()
        elif ext in (".png", ".jpg", ".jpeg", ".svg"):
            self._build_texture_import_settings()
        elif ext in (".wav", ".mp3", ".ogg", ".flac"):
            self._build_audio_import_settings()
        elif ext == ".zpem" or ext == ".mat":
            self._build_material_editor()
        elif ext == ".zphysmat":
            self._build_physic_material_editor()
        else:
            lbl = QLabel("No import settings for this file type.")
            self._add_asset_widget(lbl)
        self._updating = False

    def _build_labeled_field(self, label: str, widget: QWidget):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 2, 0, 2)
        rl.setSpacing(4)
        lbl = QLabel(label)
        lbl_min = _smart_label_width(lbl)
        lbl.setMinimumWidth(lbl_min)
        lbl.setMaximumWidth(int(lbl_min * 1.8))
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        rl.addWidget(lbl, 0)
        rl.addWidget(widget, 1)
        self._add_asset_widget(row)

    def _build_mesh_import_settings(self):
        from editor.model_preview import ModelPreviewWidget
        preview = ModelPreviewWidget()
        preview.setFixedHeight(200)
        self._add_asset_widget(preview)
        self._mesh_preview = preview
        from PyQt6.QtCore import QTimer
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as _f:
                    settings = json.load(_f)
            except Exception:
                pass
        scale_sb = QDoubleSpinBox()
        scale_sb.setRange(0.001, 1000.0)
        scale_sb.setSingleStep(0.1)
        scale_sb.setValue(settings.get("scale", 1.0))
        scale_sb.valueChanged.connect(lambda v: (self._save_import_setting("scale", v),
                                                 self._schedule_preview_reload()))
        self._build_labeled_field("Scale Factor", scale_sb)
        pivot_cb = QCheckBox()
        pivot_cb.setChecked(settings.get("center_pivot", False))
        pivot_cb.toggled.connect(lambda v: (self._save_import_setting("center_pivot", v),
                                            self._schedule_preview_reload()))
        self._build_labeled_field("Center Pivot", pivot_cb)
        flip_uv_cb = QCheckBox()
        flip_uv_cb.setChecked(settings.get("flip_uvs", True))
        flip_uv_cb.toggled.connect(lambda v: (self._save_import_setting("flip_uvs", v),
                                              self._schedule_preview_reload()))
        self._build_labeled_field("Flip UVs", flip_uv_cb)
        smooth_sb = QDoubleSpinBox()
        smooth_sb.setRange(0.0, 180.0)
        smooth_sb.setSingleStep(1.0)
        smooth_sb.setDecimals(1)
        smooth_sb.setValue(settings.get("smooth_angle", 30.0))
        smooth_sb.valueChanged.connect(lambda v: (self._save_import_setting("smooth_angle", v),
                                                  self._schedule_preview_reload()))
        self._build_labeled_field("Smooth Angle", smooth_sb)
        gen_nrm = QCheckBox()
        gen_nrm.setChecked(settings.get("gen_normals", True))
        gen_nrm.toggled.connect(lambda v: (self._save_import_setting("gen_normals", v),
                                           self._schedule_preview_reload()))
        self._build_labeled_field("Generate Normals", gen_nrm)
        gen_uv = QCheckBox()
        gen_uv.setChecked(settings.get("gen_uvs", True))
        gen_uv.toggled.connect(lambda v: (self._save_import_setting("gen_uvs", v),
                                          self._schedule_preview_reload()))
        self._build_labeled_field("Generate UVs", gen_uv)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        self._add_asset_widget(sep2)
        self._build_material_wizard_section(settings)
        self._reload_mesh_preview()

    def _schedule_preview_reload(self):
        from PyQt6.QtCore import QTimer
        timer = getattr(self, "_import_preview_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._reload_mesh_preview)
            self._import_preview_timer = timer
        timer.start(150)

    def _reload_mesh_preview(self):
        preview = getattr(self, "_mesh_preview", None)
        if preview is None:
            return
        from core.assets.importer import load_obj_async, load_mesh_async
        import numpy as np
        from PyQt6.QtCore import QTimer
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as _f:
                    settings = json.load(_f)
            except Exception:
                pass

        def _on_mesh_loaded(data):
            if data is not None and len(data.vertices) >= 3 and len(data.indices) >= 3:
                s = settings.get("scale", 1.0)
                verts = data.vertices.reshape(-1, 3).astype(np.float32) * s
                QTimer.singleShot(0, lambda v=verts, i=data.indices, n=data.normals: preview.set_mesh(v, i, normals=n))
                sub_names = getattr(data, "sub_mesh_names", [])
                old_names = settings.get("sub_mesh_names", [])
                if sub_names and sub_names != old_names:
                    self._save_submesh_names(sub_names)
                    QTimer.singleShot(0, self._rebuild)
        ext = os.path.splitext(self._asset_path)[1].lower()
        if ext == ".obj":
            load_obj_async(self._asset_path, _on_mesh_loaded)
        else:
            load_mesh_async(self._asset_path, _on_mesh_loaded)

    def _save_submesh_names(self, names: list[str]):
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as _f:
                    settings = json.load(_f)
            except Exception:
                pass
        settings["sub_mesh_names"] = names
        existing = settings.get("materials", [])
        if len(existing) < len(names):
            while len(existing) < len(names):
                existing.append("")
            settings["materials"] = existing
        try:
            with open(cache_path, "w") as _f:
                json.dump(settings, _f, indent=2)
        except Exception:
            pass

    def _get_submesh_names(self) -> list[str]:
        cache_path = self._asset_path + ".import"
        if not os.path.exists(cache_path):
            return []
        try:
            with open(cache_path) as _f:
                settings = json.load(_f)
            return settings.get("sub_mesh_names", [])
        except Exception:
            return []

    def _build_material_wizard_section(self, import_settings: dict):
        from editor.matwiz import MaterialWizardDialog
        mat_group = QLabel("<b>Materials</b>")
        self._add_asset_widget(mat_group)
        assigned = import_settings.get("materials", [])
        sub_names = import_settings.get("sub_mesh_names", [])
        if not sub_names:
            sub_names = [f"SubMesh {i}" for i in range(len(assigned))] if assigned else []
        if assigned:
            for i, mp in enumerate(assigned):
                row = QWidget()
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 2, 0, 2)
                rl.setSpacing(4)
                slot_name = sub_names[i] if i < len(sub_names) else f"Slot {i}"
                lbl = QLabel(slot_name)
                lbl.setMinimumWidth(90)
                lbl.setMaximumWidth(130)
                lbl.setStyleSheet("font-size: 11px;")
                lbl.setToolTip(f"Submesh: {slot_name}")
                rl.addWidget(lbl)
                from editor.inspector.helpersp import make_resource_picker
                def _on_mat_pick(p, idx=i):
                    self._save_import_material(idx, p)
                picker = make_resource_picker(mp, "Materials (*.mat *.zpem)", _on_mat_pick)
                rl.addWidget(picker, 1)
                self._add_asset_widget(row)
        elif not sub_names:
            info = QLabel("Load a mesh to auto-detect submesh material slots.")
            info.setStyleSheet("color: " + chr(35) + "888; font-size: 11px;")
            self._add_asset_widget(info)
        wizard_btn = QPushButton(qta.icon("fa5s.magic", color=chr(35) + "5a9cf5"), " Material Wizard...")
        wizard_btn.setToolTip("Open Material Wizard to auto-create materials from textures")
        wizard_btn.clicked.connect(self._open_material_wizard)
        self._add_asset_widget(wizard_btn)

    def _open_material_wizard(self):
        from editor.matwiz import MaterialWizardDialog
        project_root = self._engine.project_root if self._engine else os.getcwd()
        sub_names = self._get_submesh_names()
        dlg = MaterialWizardDialog(project_root, self, submesh_names=sub_names)
        dlg.materials_created.connect(self._on_materials_created)
        dlg.exec()

    def _on_materials_created(self, paths: list[str]):
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings = json.load(f)
            except Exception:
                pass
        sub_names = settings.get("sub_mesh_names", [])
        mats = settings.get("materials", [])
        if sub_names:
            while len(mats) < len(sub_names):
                mats.append("")
            for p in paths:
                basename = os.path.splitext(os.path.basename(p))[0]
                try:
                    rel = os.path.relpath(p, self._engine.project_root if self._engine else os.getcwd())
                except ValueError:
                    rel = p
                rel = rel.replace("\\", "/")
                matched = False
                for i, sn in enumerate(sub_names):
                    if sn and sn.lower() == basename.lower():
                        mats[i] = rel
                        matched = True
                        break
                if not matched:
                    for i in range(len(mats)):
                        if not mats[i]:
                            mats[i] = rel
                            break
                    else:
                        mats.append(rel)
        else:
            existing = mats
            for p in paths:
                try:
                    rel = os.path.relpath(p, self._engine.project_root if self._engine else os.getcwd())
                except ValueError:
                    rel = p
                existing.append(rel.replace("\\", "/"))
            mats = existing
        settings["materials"] = mats
        try:
            with open(cache_path, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass
        self._rebuild()

    def _save_import_material(self, index: int, path: str):
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings = json.load(f)
            except Exception:
                pass
        mats = settings.get("materials", [])
        while len(mats) <= index:
            mats.append("")
        mats[index] = self._relativize_asset_path(path)
        settings["materials"] = mats
        try:
            with open(cache_path, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception:
            pass

    def _build_texture_import_settings(self):
        from core.assets.texture_import_settings import DEFAULT_SETTINGS
        cache_path = self._asset_path + ".import"
        settings = dict(DEFAULT_SETTINGS)
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings.update(json.load(f))
            except Exception: pass
        type_cb = QComboBox()
        type_cb.addItems(["albedo", "normal", "metallic", "roughness", "ao", "emission", "sprite"])
        type_cb.setCurrentText(settings.get("type", "albedo"))
        type_cb.currentTextChanged.connect(lambda v: self._save_import_setting("type", v))
        self._build_labeled_field("Texture Type", type_cb)
        srgb = QCheckBox()
        srgb.setChecked(settings.get("srgb", True))
        srgb.toggled.connect(lambda v: self._save_import_setting("srgb", v))
        self._build_labeled_field("sRGB", srgb)
        filter_cb = QComboBox()
        filter_cb.addItems(["point", "bilinear", "trilinear"])
        filter_cb.setCurrentText(settings.get("filter_mode", "trilinear"))
        filter_cb.currentTextChanged.connect(lambda v: self._save_import_setting("filter_mode", v))
        self._build_labeled_field("Filter Mode", filter_cb)
        aniso_cb = QComboBox()
        aniso_cb.addItems(["1 (Off)", "2", "4", "8", "16"])
        aniso_val = settings.get("anisotropic", 1)
        aniso_cb.setCurrentIndex({1:0, 2:1, 4:2, 8:3, 16:4}.get(aniso_val, 0))
        def _on_aniso(v):
            mapping = [1, 2, 4, 8, 16]
            self._save_import_setting("anisotropic", mapping[aniso_cb.currentIndex()])
        aniso_cb.currentIndexChanged.connect(_on_aniso)
        self._build_labeled_field("Aniso Level", aniso_cb)
        max_sb = QSpinBox()
        max_sb.setRange(32, 8192)
        max_sb.setSingleStep(2)
        max_sb.setValue(settings.get("max_size", 2048))
        max_sb.valueChanged.connect(lambda v: self._save_import_setting("max_size", v))
        self._build_labeled_field("Max Size", max_sb)
        wrap_cb = QComboBox()
        wrap_cb.addItems(["clamp", "repeat", "mirrored_repeat"])
        wrap_cb.setCurrentText(settings.get("wrap_mode", "clamp"))
        wrap_cb.currentTextChanged.connect(lambda v: self._save_import_setting("wrap_mode", v))
        self._build_labeled_field("Wrap Mode", wrap_cb)
        comp_cb = QComboBox()
        comp_cb.addItems(["none", "low", "normal", "high"])
        comp_cb.setCurrentText(settings.get("compression", "none"))
        comp_cb.currentTextChanged.connect(lambda v: self._save_import_setting("compression", v))
        self._build_labeled_field("Compression", comp_cb)

    def _build_audio_import_settings(self):
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings = json.load(f)
            except Exception: pass
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
        if not self._asset_path: return
        cache_path = self._asset_path + ".import"
        settings = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    settings = json.load(f)
            except Exception: pass
        settings[key] = value
        try:
            with open(cache_path, "w") as f:
                json.dump(settings, f, indent=2)
        except Exception: pass
        ext = os.path.splitext(self._asset_path)[1].lower()
        if ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
            if getattr(self, "_mesh_preview", None) is not None:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, self._reload_mesh_preview)

    def _refresh_transform(self):
        for cw in self._comp_widgets:
            ctype = type(cw._component).__name__
            if ctype == "Transform":
                try: cw.refresh_transform()
                except Exception: pass
            else:
                fields = getattr(type(cw._component), "_inspector_fields", lambda: [])()
                for f in fields:
                    if f.field_type.value == "vec2":
                        try: cw.refresh_vec2_field(f.name)
                        except Exception: pass
                    elif f.field_type.value == "vec3":
                        try: cw.refresh_vec3_field(f.name)
                        except Exception: pass
                    elif f.field_type.value == "vec4":
                        try: cw.refresh_vec4_field(f.name)
                        except Exception: pass
                    elif f.field_type.value in ("vec2_slider", "vec3_slider"):
                        try: cw.refresh_vec2_field(f.name) if f.field_type.value == "vec2_slider" else cw.refresh_vec3_field(f.name)
                        except Exception: pass
                try:
                    live = cw._component.live_inspector_fields()
                except Exception:
                    live = ()
                if live:
                    for _ln in live:
                        try: cw.refresh_scalar_field(_ln)
                        except Exception: pass

    def _on_select_prefab_asset(self):
        if not self._entity or not self._entity.is_prefab_instance:
            return
        from core.ecs.prefabp import PrefabLibrary
        prefab_path = PrefabLibrary.path_for_guid(self._entity._prefab_guid)
        if prefab_path:
            self.show_import_settings(prefab_path)

    def _on_open_prefab_editor(self):
        if not self._entity or not self._entity.is_prefab_instance:
            return
        from core.ecs.prefabp import PrefabLibrary
        prefab_path = PrefabLibrary.path_for_guid(self._entity._prefab_guid)
        if prefab_path:
            self.open_prefab_editor.emit(prefab_path)


