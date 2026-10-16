# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import editor.icons as qta
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QHeaderView, QAbstractItemView,
    QGroupBox, QWidget, QSizePolicy, QCheckBox, QLineEdit,
)
from PySide6.QtCore import Qt
from core.config.editor_scale import scale_xy
from .drop_list import _TextureDropList
from .shaders import _extract_shader_name


class _DialogUiMixin:
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        shader_group = QGroupBox("Shader")
        sg_layout = QVBoxLayout(shader_group)
        sg_layout.setContentsMargins(8, 12, 8, 8)
        sg_layout.setSpacing(4)
        shader_row = QHBoxLayout()
        shader_lbl = QLabel("Shader:")
        shader_lbl.setMinimumWidth(70)
        shader_row.addWidget(shader_lbl)
        self._shader_combo = QComboBox()
        self._shader_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._shader_combo.currentIndexChanged.connect(self._on_shader_changed)
        shader_row.addWidget(self._shader_combo, 1)
        sg_layout.addLayout(shader_row)
        layout.addWidget(shader_group)
        tex_group = QGroupBox("Textures")
        tg_layout = QVBoxLayout(tex_group)
        tg_layout.setContentsMargins(8, 12, 8, 8)
        tg_layout.setSpacing(4)
        btn_row = QHBoxLayout()
        add_btn = QPushButton(qta.icon("fa5s.plus", color=chr(35) + "9ccc65"), " Add Textures")
        add_btn.clicked.connect(self._on_add_textures)
        btn_row.addWidget(add_btn)
        auto_btn = QPushButton(qta.icon("fa5s.magic", color=chr(35) + "5a9cf5"), " Auto-Map")
        auto_btn.setToolTip("Automatically map textures based on filenames")
        auto_btn.clicked.connect(self._on_auto_map)
        btn_row.addWidget(auto_btn)
        clear_btn = QPushButton(qta.icon("fa5s.trash", color=chr(35) + "f44747"), " Clear All")
        clear_btn.clicked.connect(self._on_clear_textures)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        tg_layout.addLayout(btn_row)
        self._texture_table = QTableWidget()
        self._texture_table.setColumnCount(3)
        self._texture_table.setHorizontalHeaderLabels(["Texture", "Maps To", ""])
        self._texture_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._texture_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._texture_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._texture_table.setColumnWidth(2, 30)
        self._texture_table.verticalHeader().setVisible(False)
        self._texture_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._texture_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._texture_table.setMinimumHeight(180)
        tg_layout.addWidget(self._texture_table)
        drop_label = QLabel("Drag & drop texture files here")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_label.setStyleSheet("color: " + chr(35) + "888; font-size: 11px; padding: 4px;")
        tg_layout.addWidget(drop_label)
        layout.addWidget(tex_group, 1)
        if self._submesh_names:
            sub_group = QGroupBox("Submeshes")
            sg2_layout = QVBoxLayout(sub_group)
            sg2_layout.setContentsMargins(8, 12, 8, 8)
            sg2_layout.setSpacing(2)
            for sn in self._submesh_names:
                row = QLabel(f"  {sn}")
                row.setStyleSheet("font-size: 11px; color: " + chr(35) + "aaa;")
                sg2_layout.addWidget(row)
            layout.addWidget(sub_group)
        output_group = QGroupBox("Output")
        og_layout = QVBoxLayout(output_group)
        og_layout.setContentsMargins(8, 12, 8, 8)
        og_layout.setSpacing(4)
        name_row = QHBoxLayout()
        name_lbl = QLabel("Name Pattern:")
        name_lbl.setMinimumWidth(100)
        name_row.addWidget(name_lbl)
        self._name_edit = QLineEdit("{material_name}")
        self._name_edit.setPlaceholderText("{material_name}")
        self._name_edit.setToolTip(
            "Variables: {material_name}, {shader_name}, {texture_name}"
        )
        name_row.addWidget(self._name_edit, 1)
        og_layout.addLayout(name_row)
        dir_row = QHBoxLayout()
        dir_lbl = QLabel("Output Folder:")
        dir_lbl.setMinimumWidth(100)
        dir_row.addWidget(dir_lbl)
        self._dir_edit = QLineEdit("")
        self._dir_edit.setPlaceholderText("Materials/ (relative to project)")
        dir_row.addWidget(self._dir_edit, 1)
        dir_browse = QPushButton(qta.icon("fa5s.folder-open", color=chr(35) + "d4d4d4"), "")
        dir_browse.setFixedSize(*scale_xy(22, 22))
        dir_browse.clicked.connect(self._on_browse_output_dir)
        dir_row.addWidget(dir_browse)
        og_layout.addLayout(dir_row)
        create_per_mesh_cb = QCheckBox("Create one material per submesh")
        create_per_mesh_cb.setChecked(True)
        create_per_mesh_cb.setToolTip(
            "When enabled, creates a separate material for each texture group.\n"
            "When disabled, creates a single material with all textures combined."
        )
        self._per_mesh_cb = create_per_mesh_cb
        og_layout.addWidget(create_per_mesh_cb)
        layout.addWidget(output_group)
        preview_group = QGroupBox("Preview")
        pg_layout = QVBoxLayout(preview_group)
        pg_layout.setContentsMargins(8, 12, 8, 8)
        self._preview_label = QLabel()
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet("font-size: 11px; color: " + chr(35) + "aaa;")
        self._preview_label.setMinimumHeight(60)
        pg_layout.addWidget(self._preview_label)
        layout.addWidget(preview_group)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        create_btn = QPushButton(qta.icon("fa5s.check", color=chr(35) + "9ccc65"), " Create Materials")
        create_btn.setStyleSheet(
            "QPushButton { background: " + chr(35) + "2d5a2d; border: 1px solid " + chr(35) + "4ec9b0; "
            "border-radius: 4px; padding: 6px 16px; font-weight: bold; color: " + chr(35) + "4ec9b0; }"
            "QPushButton:hover { background: " + chr(35) + "3a7a3a; }"
        )
        create_btn.clicked.connect(self._on_create)
        bottom_row.addWidget(create_btn)
        layout.addLayout(bottom_row)
        self._drop_list = _TextureDropList()
        self._drop_list.files_dropped.connect(self._on_files_dropped)
        self._drop_list.hide()

    def _populate_shaders(self):
        self._shader_combo.clear()
        self._shader_combo.addItem("-- Select Shader --", "")
        for name, path in self._shader_data:
            display = _extract_shader_name(path)
            self._shader_combo.addItem(f"{display}  ({name})", path)
        if len(self._shader_data) == 1:
            self._shader_combo.setCurrentIndex(1)

    def _on_shader_changed(self, index: int):
        if index <= 0:
            return
        self._on_auto_map()

    def _get_current_shader_path(self) -> str:
        idx = self._shader_combo.currentIndex()
        if idx <= 0:
            return ""
        return self._shader_combo.currentData()

    def _get_texture_files(self) -> list[str]:
        paths = []
        for row in range(self._texture_table.rowCount()):
            item = self._texture_table.item(row, 0)
            if item:
                paths.append(item.data(Qt.ItemDataRole.UserRole) or item.text())
        return paths
