# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""
Build Settings dialog вЂ” Unity-style scene list and plugin management.
Allows configuring which scenes and plugins are included in the build.
"""
from __future__ import annotations
import os
import editor.icons as qta
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QFileDialog, QMessageBox, QAbstractItemView,
    QGroupBox, QCheckBox, QScrollArea, QWidget, QLineEdit, QSpinBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from core.config.build_settings import BuildSettings
from core.foundation.logger import Logger


class BuildSettingsDialog(QDialog):
    build_settings_changed = Signal()

    def __init__(self, project_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Build Settings")
        self.setMinimumSize(540, 600)
        self._project_root = project_root
        self._settings = BuildSettings.instance() or BuildSettings()
        self._settings.load(os.path.join(project_root, "BuildSettings.json"))
        self._setup_ui()
        self._refresh_scene_list()
        self._refresh_plugin_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # в”Ђв”Ђ Scenes section в”Ђв”Ђ
        header = QLabel("Scenes In Build")
        header.setFont(QFont("", 12, QFont.Weight.Bold))
        layout.addWidget(header)

        info = QLabel("Drag to reorder. First scene is loaded on startup.")
        info.setStyleSheet("color: #888;")
        layout.addWidget(info)

        self._scene_list = QListWidget()
        self._scene_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._scene_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._scene_list.model().rowsMoved.connect(self._on_reorder)
        layout.addWidget(self._scene_list)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton(qta.icon("fa5s.plus", color="#9ccc65"), " Add Scene")
        self._add_btn.clicked.connect(self._add_scene)
        btn_layout.addWidget(self._add_btn)
        self._remove_btn = QPushButton(qta.icon("fa5s.minus", color="#e74c3c"), " Remove")
        self._remove_btn.clicked.connect(self._remove_scene)
        btn_layout.addWidget(self._remove_btn)
        btn_layout.addStretch()
        self._up_btn = QPushButton("в–І")
        self._up_btn.setFixedWidth(30)
        self._up_btn.clicked.connect(self._move_up)
        btn_layout.addWidget(self._up_btn)
        self._down_btn = QPushButton("в–ј")
        self._down_btn.setFixedWidth(30)
        self._down_btn.clicked.connect(self._move_down)
        btn_layout.addWidget(self._down_btn)
        layout.addLayout(btn_layout)

        # в”Ђв”Ђ Plugins section в”Ђв”Ђ
        plugin_header = QLabel("Plugins In Build")
        plugin_header.setFont(QFont("", 12, QFont.Weight.Bold))
        layout.addWidget(plugin_header)

        plugin_info = QLabel("Check plugins to include. Unchecked plugins are excluded from the build.")
        plugin_info.setStyleSheet("color: #888;")
        layout.addWidget(plugin_info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._plugin_container = QWidget()
        self._plugin_layout = QVBoxLayout(self._plugin_container)
        self._plugin_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._plugin_container)
        layout.addWidget(scroll)

        player_group = QGroupBox("Player Settings")
        player_layout = QVBoxLayout()
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Game title:"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Zarin Player")
        title_row.addWidget(self._title_edit)
        title_row.addWidget(QLabel("Version:"))
        self._version_edit = QLineEdit()
        self._version_edit.setMaximumWidth(90)
        title_row.addWidget(self._version_edit)
        player_layout.addLayout(title_row)
        icon_row = QHBoxLayout()
        icon_row.addWidget(QLabel("Icon:"))
        self._icon_edit = QLineEdit()
        self._icon_edit.setPlaceholderText("zarin_logo.svg (default)")
        icon_row.addWidget(self._icon_edit)
        icon_btn = QPushButton("Browse...")
        icon_btn.clicked.connect(self._browse_icon)
        icon_row.addWidget(icon_btn)
        player_layout.addLayout(icon_row)
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Window:"))
        self._width_spin = QSpinBox()
        self._width_spin.setRange(320, 7680)
        self._width_spin.setSuffix(" px")
        size_row.addWidget(self._width_spin)
        size_row.addWidget(QLabel("x"))
        self._height_spin = QSpinBox()
        self._height_spin.setRange(240, 4320)
        self._height_spin.setSuffix(" px")
        size_row.addWidget(self._height_spin)
        size_row.addStretch()
        player_layout.addLayout(size_row)
        self._splash_check = QCheckBox("Show splash screen")
        player_layout.addWidget(self._splash_check)
        self._fullscreen_check = QCheckBox("Start fullscreen")
        player_layout.addWidget(self._fullscreen_check)
        self._fps_check = QCheckBox("Show FPS in title (updates twice a second)")
        player_layout.addWidget(self._fps_check)
        self._debug_check = QCheckBox("Enable debug overlay on Shift+F3")
        player_layout.addWidget(self._debug_check)
        player_group.setLayout(player_layout)
        layout.addWidget(player_group)
        self._load_player_options()

        # в”Ђв”Ђ Build Options в”Ђв”Ђ
        options_group = QGroupBox("Build Options")
        options_layout = QVBoxLayout()
        self._strip_check = QCheckBox("Strip unused assets (scan scenes for references)")
        self._strip_check.setChecked(self._settings._build_options.get("strip_unused_assets", True))
        options_layout.addWidget(self._strip_check)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # в”Ђв”Ђ Bottom buttons в”Ђв”Ђ
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_and_close)
        bottom_layout.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)
        layout.addLayout(bottom_layout)

    def _load_player_options(self):
        try:
            get = self._settings.player_option
        except Exception:
            return
        try:
            self._title_edit.setText(str(get("game_title", "") or ""))
            self._icon_edit.setText(str(get("icon", "") or ""))
            self._version_edit.setText(str(get("version", "1.0.0") or "1.0.0"))
            self._width_spin.setValue(int(get("window_width", 1280) or 1280))
            self._height_spin.setValue(int(get("window_height", 720) or 720))
            self._splash_check.setChecked(bool(get("show_splash", True)))
            self._fullscreen_check.setChecked(bool(get("fullscreen", False)))
            self._fps_check.setChecked(bool(get("show_fps_in_title", False)))
            self._debug_check.setChecked(bool(get("debug_shift_f3", True)))
        except Exception:
            pass

    def _refresh_scene_list(self):
        self._scene_list.clear()
        scenes = self._settings.scenes
        for i, scene in enumerate(scenes):
            item = QListWidgetItem()
            name = Path(scene).stem
            text = f"  {scene}"
            if i == 0:
                text += "  (Startup)"
            item.setText(text)
            item.setData(Qt.ItemDataRole.UserRole, scene)
            self._scene_list.addItem(item)

    def _add_scene(self):
        scenes_dir = os.path.join(self._project_root, "scenes")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Scenes", scenes_dir,
            "Zarin Scenes (*.zpes);;All Files (*)"
        )
        if files:
            for f in files:
                rel = os.path.relpath(f, self._project_root)
                self._settings.add_scene(rel)
            self._refresh_scene_list()

    def _remove_scene(self):
        item = self._scene_list.currentItem()
        if item:
            scene = item.data(Qt.ItemDataRole.UserRole)
            self._settings.remove_scene(scene)
            self._refresh_scene_list()

    def _move_up(self):
        row = self._scene_list.currentRow()
        if row > 0:
            self._settings.move_scene(row, row - 1)
            self._refresh_scene_list()
            self._scene_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._scene_list.currentRow()
        if row < self._scene_list.count() - 1:
            self._settings.move_scene(row, row + 1)
            self._refresh_scene_list()
            self._scene_list.setCurrentRow(row + 1)

    def _refresh_plugin_list(self):
        # Clear existing checkboxes
        while self._plugin_layout.count():
            w = self._plugin_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        selected = set(self._settings.build_plugins)
        self._plugin_checkboxes = {}
        plugins_dir = os.path.join(self._project_root, "plugins")

        # Scan plugins/ root
        if os.path.isdir(plugins_dir):
            for fname in sorted(os.listdir(plugins_dir)):
                fpath = os.path.join(plugins_dir, fname)
                if fname.endswith(".py") and not fname.startswith("_"):
                    name = fname[:-3]
                    self._add_plugin_checkbox(name, f"plugins/{fname}", selected)
                elif os.path.isdir(fpath) and not fname.startswith("_"):
                    init_path = os.path.join(fpath, "__init__.py")
                    if os.path.isfile(init_path):
                        # Package-style plugin (e.g. plugins/user/bsp_import_plugin)
                        self._add_package_plugins(fpath, fname, selected)

        self._plugin_layout.addStretch()

    def _add_plugin_checkbox(self, name: str, label: str, selected: set):
        cb = QCheckBox(name)
        if name in selected:
            cb.setChecked(True)
        cb.setToolTip(label)
        self._plugin_checkboxes[name] = cb
        self._plugin_layout.addWidget(cb)

    def _add_package_plugins(self, pkg_dir: str, prefix: str, selected: set):
        self._add_plugin_checkbox(prefix, f"plugins/{prefix}/__init__.py", selected)
        for fname in sorted(os.listdir(pkg_dir)):
            if fname.endswith(".py") and not fname.startswith("_"):
                name = prefix + "." + fname[:-3]
                self._add_plugin_checkbox(name, f"plugins/{prefix}/{fname}", selected)

    def _on_reorder(self):
        """Handle drag-drop reorder."""
        scenes = []
        for i in range(self._scene_list.count()):
            item = self._scene_list.item(i)
            scenes.append(item.data(Qt.ItemDataRole.UserRole))
        self._settings.set_scenes(scenes)

    def _browse_icon(self):
        try:
            start = self._project_root
            picked, _ = QFileDialog.getOpenFileName(
                self, "Game Icon", start,
                "Images (*.svg *.png *.ico *.bmp *.jpg);;All Files (*)"
            )
        except Exception:
            return
        if picked:
            try:
                self._icon_edit.setText(os.path.relpath(picked, self._project_root))
            except Exception:
                self._icon_edit.setText(picked)

    def _save_and_close(self):
        self._settings._build_options["strip_unused_assets"] = self._strip_check.isChecked()
        selected = [name for name, cb in self._plugin_checkboxes.items() if cb.isChecked()]
        self._settings.set_plugins(selected)
        try:
            self._settings.set_player_option("game_title", self._title_edit.text().strip())
            self._settings.set_player_option("icon", self._icon_edit.text().strip())
            self._settings.set_player_option("version", self._version_edit.text().strip() or "1.0.0")
            self._settings.set_player_option("window_width", int(self._width_spin.value()))
            self._settings.set_player_option("window_height", int(self._height_spin.value()))
            self._settings.set_player_option("show_splash", bool(self._splash_check.isChecked()))
            self._settings.set_player_option("fullscreen", bool(self._fullscreen_check.isChecked()))
            self._settings.set_player_option("show_fps_in_title", bool(self._fps_check.isChecked()))
            self._settings.set_player_option("debug_shift_f3", bool(self._debug_check.isChecked()))
        except Exception:
            pass
        save_path = os.path.join(self._project_root, "BuildSettings.json")
        self._settings.save(save_path)
        self.build_settings_changed.emit()
        self.accept()
