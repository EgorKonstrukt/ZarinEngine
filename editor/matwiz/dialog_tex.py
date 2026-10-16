# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import editor.icons as qta
from PySide6.QtWidgets import QComboBox, QPushButton, QFileDialog, QTableWidgetItem, QAbstractItemView
from PySide6.QtCore import Qt
from core.config.editor_scale import scale_xy
from core.assets.matp import _parse_shader_file
from .naming import _guess_map_type


class _DialogTexturesMixin:
    def _on_add_textures(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Textures", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff *.webp *.hdr *.exr *.dds *.svg);;All Files (*)"
        )
        if files:
            self._add_texture_files(files)

    def _on_files_dropped(self, paths: list[str]):
        self._add_texture_files(paths)

    def _add_texture_files(self, files: list[str]):
        existing = set(self._get_texture_files())
        for f in files:
            if f in existing:
                continue
            existing.add(f)
            self._insert_texture_row(f)
        self._on_auto_map()
        self._refresh_preview()

    def _insert_texture_row(self, filepath: str):
        row = self._texture_table.rowCount()
        self._texture_table.insertRow(row)
        name_item = QTableWidgetItem(os.path.basename(filepath))
        name_item.setData(Qt.ItemDataRole.UserRole, filepath)
        name_item.setToolTip(filepath)
        self._texture_table.setItem(row, 0, name_item)
        combo = QComboBox()
        combo.addItem("Auto-detect", "")
        shader_path = self._get_current_shader_path()
        shader_props = self._get_texture_properties(shader_path)
        for prop_name, display in shader_props:
            combo.addItem(display, prop_name)
        combo.addItem("Custom...", "custom")
        combo.currentIndexChanged.connect(lambda _, r=row: self._on_map_changed(r))
        self._texture_table.setCellWidget(row, 1, combo)
        remove_btn = QPushButton(qta.icon("fa5s.times", color=chr(35) + "f44747"), "")
        remove_btn.setFixedSize(*scale_xy(22, 22))
        remove_btn.clicked.connect(lambda _, r=row: self._remove_texture_row(r))
        self._texture_table.setCellWidget(row, 2, remove_btn)

    def _remove_texture_row(self, row: int):
        if 0 <= row < self._texture_table.rowCount():
            self._texture_table.removeRow(row)
            self._refresh_preview()

    def _on_map_changed(self, row: int):
        self._refresh_preview()

    def _get_texture_properties(self, shader_path: str) -> list[tuple[str, str]]:
        if not shader_path:
            return []
        result = _parse_shader_file(shader_path)
        if not result:
            return []
        props = result[0]
        tex_props = [(p.name, p.display_name) for p in props if p.prop_type in ("2D", "cube")]
        return tex_props

    def _on_auto_map(self):
        shader_path = self._get_current_shader_path()
        shader_props = self._get_texture_properties(shader_path)
        prop_names = [p[0] for p in shader_props]
        used = set()
        for row in range(self._texture_table.rowCount()):
            name_item = self._texture_table.item(row, 0)
            combo = self._texture_table.cellWidget(row, 1)
            if not name_item or not isinstance(combo, QComboBox):
                continue
            filepath = name_item.data(Qt.ItemDataRole.UserRole) or name_item.text()
            filename = os.path.basename(filepath)
            guessed = _guess_map_type(filename)
            if guessed and guessed in prop_names and guessed not in used:
                for i in range(combo.count()):
                    if combo.itemData(i) == guessed:
                        combo.setCurrentIndex(i)
                        used.add(guessed)
                        break
            else:
                combo.setCurrentIndex(0)
        self._refresh_preview()

    def _on_clear_textures(self):
        self._texture_table.setRowCount(0)
        self._assignments.clear()
        self._refresh_preview()
