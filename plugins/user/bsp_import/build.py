# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import io
import json
import hashlib
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QGroupBox, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QDialogButtonBox
from PIL import Image
from .parse import BSPFile
def _generate_texture_png(tex_name: str, size: int = 128) -> bytes:
    h = hashlib.md5(tex_name.encode()).digest()
    r_base = (h[0] + 64) % 192 + 32
    g_base = (h[1] + 64) % 192 + 32
    b_base = (h[2] + 64) % 192 + 32
    img = Image.new('RGBA', (size, size))
    pixels = []
    check = 16
    for y in range(size):
        for x in range(size):
            cx = (x // check) % 2
            cy = (y // check) % 2
            is_light = (cx ^ cy) == 0
            if is_light:
                r = min(255, r_base + 30)
                g = min(255, g_base + 30)
                b = min(255, b_base + 30)
            else:
                r = max(0, r_base - 20)
                g = max(0, g_base - 20)
                b = max(0, b_base - 20)
            pixels.append((r, g, b, 255))
    img.putdata(pixels)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()
class ImportSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BSP Import Settings")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        geo_group = QGroupBox("Geometry", self)
        geo_layout = QFormLayout(geo_group)
        self.merge_cb = QCheckBox("Merge faces by material", self)
        self.merge_cb.setChecked(True)
        geo_layout.addRow(self.merge_cb)
        self.center_cb = QCheckBox("Center pivot on each group", self)
        self.center_cb.setChecked(True)
        geo_layout.addRow(self.center_cb)
        self.scale_sb = QDoubleSpinBox(self)
        self.scale_sb.setRange(0.001, 1000.0)
        self.scale_sb.setValue(1.0)
        self.scale_sb.setSingleStep(0.1)
        self.scale_sb.setDecimals(4)
        geo_layout.addRow("Scale factor:", self.scale_sb)
        layout.addWidget(geo_group)
        coord_group = QGroupBox("Coordinate System", self)
        coord_layout = QFormLayout(coord_group)
        self.coord_cb = QComboBox(self)
        self.coord_cb.addItems([
            "Source (Z-up) -> ZarPy (Y-up)",
            "Keep Source (Z-up)",
        ])
        coord_layout.addRow("Conversion:", self.coord_cb)
        layout.addWidget(coord_group)
        tex_group = QGroupBox("Textures", self)
        tex_layout = QFormLayout(tex_group)
        self.gen_tex_cb = QCheckBox("Generate procedural textures", self)
        self.gen_tex_cb.setChecked(True)
        tex_layout.addRow(self.gen_tex_cb)
        self.tex_size_sb = QSpinBox(self)
        self.tex_size_sb.setRange(16, 1024)
        self.tex_size_sb.setValue(128)
        self.tex_size_sb.setSingleStep(32)
        tex_layout.addRow("Texture size (px):", self.tex_size_sb)
        layout.addWidget(tex_group)
        adv_group = QGroupBox("Advanced", self)
        adv_layout = QFormLayout(adv_group)
        self.import_brush_cb = QCheckBox("Import brush entity models", self)
        adv_layout.addRow(self.import_brush_cb)
        self.import_ents_cb = QCheckBox("Import entity keyvalues", self)
        adv_layout.addRow(self.import_ents_cb)
        layout.addWidget(adv_group)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        layout.addWidget(buttons)
    def get_settings(self) -> dict:
        return {
            'merge_by_material': self.merge_cb.isChecked(),
            'center_pivot': self.center_cb.isChecked(),
            'scale': self.scale_sb.value(),
            'convert_coords': self.coord_cb.currentIndex() == 0,
            'generate_textures': self.gen_tex_cb.isChecked(),
            'texture_size': self.tex_size_sb.value(),
            'import_brush_entities': self.import_brush_cb.isChecked(),
            'import_entity_data': self.import_ents_cb.isChecked(),
        }
class BSPImportWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    def __init__(self, path: str, settings: dict,
                 project_root: str, materials_dir: str):
        super().__init__()
        self._path = path
        self._settings = settings
        self._project_root = project_root
        self._materials_dir = materials_dir
        self._cancelled = False
    def cancel(self):
        self._cancelled = True
    def run(self):
        try:
            self.progress.emit(0, "Parsing BSP file...")
            bsp = BSPFile(self._path)
            if self._cancelled:
                return
            self.progress.emit(15, f"Extracting {len(bsp.faces)} faces...")
            groups = bsp.extract_mesh_groups(self._settings, self._on_sub_progress)
            if self._cancelled or not groups:
                self.progress.emit(100, "Cancelled")
                return
            gen_tex = self._settings.get('generate_textures', True)
            tex_size = self._settings.get('texture_size', 128)
            self.progress.emit(65, f"Generating {len(groups)} textures...")
            saved_textures = {}
            for i, group in enumerate(groups):
                if self._cancelled:
                    return
                tex_name = group['name']
                pct = 65 + int((i / len(groups)) * 20)
                self.progress.emit(pct, f"Generating texture: {tex_name}")
                if gen_tex:
                    png = _generate_texture_png(tex_name, tex_size)
                    tex_path = os.path.normpath(
                        os.path.join(self._materials_dir, f"{tex_name}.png"))
                    with open(tex_path, 'wb') as f:
                        f.write(png)
                    saved_textures[tex_name] = tex_path
            self.progress.emit(86, "Saving material files...")
            saved_materials = {}
            saved_materials_abs = {}
            os.makedirs(self._materials_dir, exist_ok=True)
            for i, group in enumerate(groups):
                if self._cancelled:
                    return
                tex_name = group['name']
                pct = 86 + int((i / len(groups)) * 4)
                self.progress.emit(pct, f"Saving material: {tex_name}")
                tex_path = saved_textures.get(tex_name, "")
                mat_path = os.path.normpath(
                    os.path.join(self._materials_dir, f"{tex_name}.mat"))
                if not os.path.exists(mat_path) and tex_path:
                    rel_tex = os.path.relpath(tex_path, self._project_root).replace("\\", "/")
                    mat_data = {
                        "name": tex_name,
                        "shader_path": "",
                        "properties": {
                            "albedo_texture": rel_tex,
                            "use_albedo_tex": 1,
                        }
                    }
                    with open(mat_path, 'w', encoding='utf-8') as f:
                        json.dump(mat_data, f, indent=2)
                saved_materials_abs[tex_name] = mat_path
                saved_materials[tex_name] = os.path.relpath(
                    mat_path, self._project_root).replace("\\", "/")
                group['_material_abs'] = mat_path
            self.progress.emit(90, "Preparing scene data...")
            bsp_name = os.path.splitext(os.path.basename(bsp.path))[0]
            result = dict(
                bsp_name=bsp_name,
                groups=groups,
                saved_materials=saved_materials,
                saved_materials_abs=saved_materials_abs,
                face_count=len(bsp.faces),
                center_pivot=self._settings.get('center_pivot', True),
            )
            self.progress.emit(100, "Done")
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
    def _on_sub_progress(self, pct: int, msg: str):
        if not self._cancelled:
            self.progress.emit(pct, msg)
