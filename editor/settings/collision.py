# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget
from core.config.editor_scale import scale
from core.physics.collision_layers import DEFAULT_LAYER_NAMES, MAX_LAYERS
from editor.settings.widgets import SECTION_DESCRIPTIONS

def build_file_assoc_page(self, prefix: str) -> QWidget:
    from editor.file_associations import register, unregister, status
    from editor.constants import EXTENSIONS
    import os
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    container = QWidget()
    outer_layout = QVBoxLayout(container)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)
    header_text = "File Associations"
    desc_text = SECTION_DESCRIPTIONS.get(prefix, "")
    if desc_text:
        header_text += f"  \u2014  {desc_text}"
    hlabel = QLabel(header_text)
    hlabel.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px 16px;")
    outer_layout.addWidget(hlabel)
    info_label = QLabel("Register Zarin Engine file extensions with Windows Explorer.\n" "This allows opening .zpes and .zpep files by double-clicking.")
    info_label.setWordWrap(True)
    info_label.setStyleSheet("padding: 4px 16px 8px 16px; color: #aaa;")
    outer_layout.addWidget(info_label)
    status_group = QWidget()
    status_layout = QVBoxLayout(status_group)
    status_layout.setContentsMargins(16, 8, 16, 8)
    status_layout.setSpacing(4)
    self._assoc_status_labels = {}
    for ext, info in EXTENSIONS.items():
        row = QHBoxLayout()
        lbl = QLabel(f"{ext}  \u2014  {info['description']}")
        lbl.setStyleSheet("font-size: 13px;")
        status_lbl = QLabel("unknown")
        status_lbl.setStyleSheet("color: gray; font-weight: bold;")
        self._assoc_status_labels[ext] = status_lbl
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(status_lbl)
        status_layout.addLayout(row)
    outer_layout.addWidget(status_group)
    btn_group = QWidget()
    btn_layout = QHBoxLayout(btn_group)
    btn_layout.setContentsMargins(16, 8, 16, 8)
    btn_layout.setSpacing(12)
    register_btn = QPushButton("Register File Associations")
    register_btn.setFixedHeight(scale(32))
    register_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 4px 16px; }")
    register_btn.clicked.connect(self._on_register_assoc)
    btn_layout.addWidget(register_btn)
    unregister_btn = QPushButton("Unregister File Associations")
    unregister_btn.setFixedHeight(scale(32))
    unregister_btn.setStyleSheet("QPushButton { padding: 4px 16px; }")
    unregister_btn.clicked.connect(self._on_unregister_assoc)
    btn_layout.addWidget(unregister_btn)
    btn_layout.addStretch()
    outer_layout.addWidget(btn_group)
    self._assoc_refresh_btn = QPushButton("Refresh Status")
    self._assoc_refresh_btn.setFixedWidth(scale(120))
    self._assoc_refresh_btn.clicked.connect(self._refresh_assoc_status)
    br_layout = QHBoxLayout()
    br_layout.setContentsMargins(16, 4, 16, 12)
    br_layout.addWidget(self._assoc_refresh_btn)
    br_layout.addStretch()
    outer_layout.addLayout(br_layout)
    outer_layout.addStretch()
    scroll.setWidget(container)
    self._refresh_assoc_status()
    return scroll
def refresh_assoc_status(self):
    from editor.file_associations import status
    try:
        st = status()
    except Exception:
        st = {}
    for ext, lbl in self._assoc_status_labels.items():
        registered = st.get(ext, False)
        if registered:
            lbl.setText("Registered")
            lbl.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            lbl.setText("Not registered")
            lbl.setStyleSheet("color: #f44336; font-weight: bold;")
def on_register_assoc(self):
    from editor.file_associations import register
    import os
    svg_path = os.path.join(os.path.dirname(__file__), "..", "zarin_icon.svg")
    svg_path = os.path.abspath(svg_path)
    if not os.path.exists(svg_path):
        svg_path = os.path.join(os.path.dirname(__file__), "..", "assets", "zarin_icon.svg")
        svg_path = os.path.abspath(svg_path)
    if not os.path.exists(svg_path):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "Error", "zarin_icon.svg not found")
        return
    result = register(svg_path)
    self._refresh_assoc_status()
    from PySide6.QtWidgets import QMessageBox
    if result:
        QMessageBox.information(self, "Success", f"Registered: {', '.join(result)}")
    else:
        QMessageBox.warning(self, "Error", "Failed to register file associations")
def on_unregister_assoc(self):
    from editor.file_associations import unregister
    result = unregister()
    self._refresh_assoc_status()
    from PySide6.QtWidgets import QMessageBox
    if result:
        QMessageBox.information(self, "Success", f"Unregistered: {', '.join(result)}")
def add_collision_layers_editor(self, parent_layout):
    layer_names = self._config.get("physics.layer_names", list(DEFAULT_LAYER_NAMES))
    collision_matrix = self._config.get("physics.collision_matrix", [0xFFFF] * MAX_LAYERS)
    gb_layers = QGroupBox("Collision Layers")
    gl = QGridLayout(gb_layers)
    gl.setSpacing(4)
    self._layer_edits = []
    for i in range(MAX_LAYERS):
        name = layer_names[i] if i < len(layer_names) else DEFAULT_LAYER_NAMES[i]
        lbl = QLabel(f"{i}:")
        lbl.setFixedWidth(scale(24))
        le = QLineEdit(name)
        le.setFixedWidth(scale(160))
        le.textChanged.connect(lambda _, idx=i: self._on_layer_name_changed(idx))
        self._layer_edits.append(le)
        gl.addWidget(lbl, i, 0)
        gl.addWidget(le, i, 1)
    parent_layout.addWidget(gb_layers)
    gb_matrix = QGroupBox("Collision Matrix")
    gb_layout = QVBoxLayout(gb_matrix)
    open_btn = QPushButton("Edit Collision Matrix...")
    open_btn.clicked.connect(lambda: self._open_collision_matrix_dialog())
    gb_layout.addWidget(open_btn)
    parent_layout.addWidget(gb_matrix)
def on_layer_name_changed(self, idx):
    names = [le.text() for le in self._layer_edits]
    self._config.set("physics.layer_names", names, notify=True)
    self._config.save()
def open_collision_matrix_dialog(self):
    layer_names = self._config.get("physics.layer_names", list(DEFAULT_LAYER_NAMES))
    collision_matrix = list(self._config.get("physics.collision_matrix", [0xFFFF] * MAX_LAYERS))
    dialog = CollisionMatrixDialog(layer_names, collision_matrix, self)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        self._config.set("physics.collision_matrix", dialog.get_matrix(), notify=True)
        self._config.save()


class CollisionMatrixDialog(QDialog):
    def __init__(self, layer_names, matrix, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Collision Matrix")
        self.setMinimumSize(600, 500)
        self._matrix = list(matrix)
        self._layer_names = list(layer_names)
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(2)
        info = QLabel("Check which layers collide with each other:")
        info.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(info)
        self._checks = []
        for i in range(MAX_LAYERS):
            lbl = QLabel(f"{i}:{layer_names[i] if i < len(layer_names) else ''}")
            lbl.setFixedWidth(scale(140))
            grid.addWidget(lbl, i + 1, 0)
            lbl_top = QLabel(str(i))
            lbl_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_top.setFixedWidth(scale(24))
            grid.addWidget(lbl_top, 0, i + 1)
            row_checks = []
            for j in range(MAX_LAYERS):
                chk = QCheckBox()
                chk.setChecked(bool(self._matrix[i] & (1 << j)))
                chk.stateChanged.connect(lambda _, ri=i, cj=j: self._on_toggle(ri, cj))
                chk.setFixedWidth(scale(24))
                grid.addWidget(chk, i + 1, j + 1, Qt.AlignmentFlag.AlignCenter)
                row_checks.append(chk)
            self._checks.append(row_checks)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
    def _on_toggle(self, i, j):
        chk = self._checks[i][j]
        if chk.isChecked():
            self._matrix[i] |= 1 << j
        else:
            self._matrix[i] &= ~(1 << j)
    def get_matrix(self):
        return self._matrix
