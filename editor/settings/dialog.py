# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Any, Optional
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget
from core.config.config import Config
from core.config.editor_scale import scale
from editor.settings.collision import add_collision_layers_editor, build_file_assoc_page, on_layer_name_changed, on_register_assoc, on_unregister_assoc, open_collision_matrix_dialog, refresh_assoc_status
from editor.settings.widgets import FIELD_TOOLTIPS, SECTION_DESCRIPTIONS, SECTION_ICONS, SliderSpinBox, _FIELD_RANGES
try:
    import editor.icons as qta
except ImportError:
    qta = None

class SettingsDialog(QDialog):
    config_changed = pyqtSignal(str, object)
    def __init__(self, title: str, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(title)
        self.setMinimumSize(800, 520)
        self.resize(900, 580)
        self._field_resets: dict[str, tuple[QPushButton, Any]] = {}
        self._field_widgets: dict[str, QWidget] = {}
        self._config.on_changed(self._on_config_changed)
        self._setup_ui()
        if self._list_widget.count() > 0:
            self._list_widget.setCurrentRow(0)
    def _on_config_changed(self, key: str, value: Any):
        self.config_changed.emit(key, value)
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        title_label = QLabel(self.windowTitle())
        title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search settings...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(200)
        self._search_edit.textChanged.connect(self._on_search)
        header_layout.addWidget(self._search_edit)
        main_layout.addWidget(header)
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self._list_widget = QListWidget()
        self._list_widget.setFixedWidth(scale(180))
        self._list_widget.setFrameShape(QFrame.Shape.StyledPanel)
        self._list_widget.currentRowChanged.connect(self._on_list_row_changed)
        self._list_widget.installEventFilter(self)
        sections = [(k, v) for k, v in self._config.to_dict().items() if isinstance(v, dict)]
        sections.sort(key=lambda x: x[0])
        self._sections = [s[0] for s in sections]
        self._pages: dict[str, QWidget] = {}
        self._stack = QStackedWidget()
        for section, values in sections:
            icon_name = SECTION_ICONS.get(section)
            item = QListWidgetItem()
            if icon_name is not None and qta is not None:
                item.setIcon(qta.icon(icon_name, color="#d4d4d4"))
            item.setText(section.replace("_", " ").title())
            self._list_widget.addItem(item)
            scroll = self._build_page(section, values)
            self._pages[section] = scroll
            self._stack.addWidget(scroll)
        content_layout.addWidget(self._list_widget)
        content_layout.addWidget(self._stack, 1)
        main_layout.addWidget(content, 1)
        bottom_bar = QWidget()
        bar_layout = QHBoxLayout(bottom_bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        restore_btn = QPushButton("Restore Defaults")
        restore_btn.clicked.connect(self._on_restore)
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(scale(80))
        close_btn.clicked.connect(self.close)
        bar_layout.addWidget(restore_btn)
        bar_layout.addStretch()
        bar_layout.addWidget(close_btn)
        main_layout.addWidget(bottom_bar)
    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._list_widget and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            row = self._list_widget.currentRow()
            if delta > 0 and row > 0:
                self._list_widget.setCurrentRow(row - 1)
            elif delta < 0 and row < self._list_widget.count() - 1:
                self._list_widget.setCurrentRow(row + 1)
            return True
        return super().eventFilter(obj, event)
    def _on_list_row_changed(self, row: int):
        if 0 <= row < len(self._sections):
            self._stack.setCurrentIndex(row)
    def _on_search(self, text: str):
        text = text.lower().strip()
        for i in range(self._stack.count()):
            self._stack.widget(i).setVisible(True)
        for i, section in enumerate(self._sections):
            item = self._list_widget.item(i)
            if not text:
                item.setHidden(False)
                self._pages[section].setVisible(True)
            else:
                matches = text in section.lower() or text in SECTION_DESCRIPTIONS.get(section, "").lower()
                matches = matches or any(text in k.lower() or text in FIELD_TOOLTIPS.get(f"{section}.{k}", "").lower() for k in self._config.to_dict().get(section, {}) if not isinstance(self._config.to_dict().get(section, {})[k], dict))
                item.setHidden(not matches)
                self._pages[section].setVisible(matches)
    def _build_page(self, prefix: str, data: dict) -> QWidget:
        if prefix == "file_assoc":
            return self._build_file_assoc_page(prefix)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        header_text = prefix.replace("_", " ").title()
        desc_text = SECTION_DESCRIPTIONS.get(prefix, "")
        if desc_text:
            header_text += f"  \u2014  {desc_text}"
        hlabel = QLabel(header_text)
        hlabel.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px 16px;")
        outer_layout.addWidget(hlabel)
        form_container = QWidget()
        form = QFormLayout(form_container)
        form.setContentsMargins(16, 8, 16, 8)
        form.setSpacing(6)
        keys = sorted(data.keys())
        for key in keys:
            value = data[key]
            full_key = f"{prefix}.{key}"
            if isinstance(value, dict):
                continue
            widget = self._create_widget(full_key, value)
            if widget:
                label_text = key.replace("_", " ").title()
                restart = self._config.is_restart_key(full_key)
                if restart:
                    label_text += " [restart]"
                label = QLabel(label_text)
                tooltip = FIELD_TOOLTIPS.get(full_key, "")
                if restart:
                    label.setStyleSheet("color: orange;")
                    label.setToolTip("Restart required" + ("\n" + tooltip if tooltip else ""))
                if tooltip:
                    label.setToolTip(tooltip)
                    widget.setToolTip(tooltip)
                default_val = self._config._defaults.get(prefix, {}).get(key)
                self._field_widgets[full_key] = widget
                if default_val is not None and not isinstance(default_val, dict):
                    row_widget = QWidget()
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(4)
                    row_layout.addWidget(widget, 1)
                    reset_btn = QPushButton()
                    reset_btn.setIcon(qta.icon("fa5s.undo", color="#888") if qta else QIcon())
                    reset_btn.setFixedSize(scale(20), scale(20))
                    reset_btn.setToolTip("Reset to default")
                    reset_btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 3px; }")
                    reset_btn.clicked.connect(lambda _, k=full_key: self._reset_field(k))
                    row_layout.addWidget(reset_btn)
                    self._field_resets[full_key] = (reset_btn, default_val)
                    self._update_reset_btn(full_key)
                    form.addRow(label, row_widget)
                else:
                    form.addRow(label, widget)
        outer_layout.addWidget(form_container)
        if prefix == "physics":
            self._add_collision_layers_editor(outer_layout)
        outer_layout.addStretch()
        scroll.setWidget(container)
        return scroll
    def _build_file_assoc_page(self, prefix: str) -> QWidget:
        return build_file_assoc_page(self, prefix)
    def _refresh_assoc_status(self):
        return refresh_assoc_status(self)
    def _on_register_assoc(self):
        return on_register_assoc(self)
    def _on_unregister_assoc(self):
        return on_unregister_assoc(self)
    def _create_widget(self, key: str, value) -> Optional[QWidget]:
        if key == "input.control_scheme":
            cb = QComboBox()
            cb.addItems(["fps", "tps"])
            cb.setCurrentText(self._config.get(key, "fps"))
            cb.currentTextChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            return cb
        if key == "physics.simulation_mode":
            container = QWidget()
            vl = QVBoxLayout(container)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(2)
            cb = QComboBox()
            cb.addItems(["single", "multi_threaded", "per_layer_process"])
            cb.setCurrentText(self._config.get(key, value))
            cb.currentTextChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            vl.addWidget(cb)
            info = QLabel("single = всё в основном потоке, отладка\n" "multi_threaded = один отдельный процесс, стандарт\n" "per_layer_process = свой процесс на каждый слой коллизии, для безумных симуляций")
            info.setStyleSheet("color: #888; font-size: 11px; padding-left: 4px;")
            info.setWordWrap(True)
            vl.addWidget(info)
            return container
        if key == "audio.distance_model":
            cb = QComboBox()
            cb.addItems(["none", "inverse_distance", "inverse_distance_clamped", "linear_distance", "linear_distance_clamped", "exponent_distance", "exponent_distance_clamped"])
            cb.setCurrentText(self._config.get(key, "inverse_distance_clamped"))
            cb.currentTextChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            return cb
        if key == "rendering.bvh_build_mode":
            cb = QComboBox()
            cb.addItems(["fast", "accurate"])
            cb.setCurrentText(self._config.get(key, "fast"))
            cb.currentTextChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            return cb
        if key == "audio.device_name":
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            le = QLineEdit(self._config.get(key, ""))
            le.setPlaceholderText("System default")
            le.setFixedWidth(220)
            le.textChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            hl.addWidget(le)
            from core.audio.sys import AudioSystem
            devices = AudioSystem.get_available_devices()
            if devices:
                detect_btn = QPushButton("Detect")
                detect_btn.setFixedWidth(scale(56))
                def _detect(_checked=False, _btn=detect_btn, edit=le, k=key):
                    from core.audio.sys import AudioSystem
                    devs = AudioSystem.get_available_devices()
                    if devs:
                        current = edit.text()
                        if current and current in devs:
                            idx = devs.index(current)
                        else:
                            idx = 0
                        from PyQt6.QtWidgets import QInputDialog
                        item, ok = QInputDialog.getItem(_btn, "Audio Devices", "Select device:", devs, idx, False)
                        if ok:
                            edit.setText(item)
                            self._on_value_changed(k, item)
                detect_btn.clicked.connect(_detect)
                hl.addWidget(detect_btn)
            return container
        if key == "editor.thumb_cache_mode":
            cb = QComboBox()
            cb.addItems(["metadata", "content"])
            cb.setCurrentText(self._config.get(key, "metadata"))
            cb.currentTextChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            return cb
        if key == "rendering.play_viewport_throttle":
            cb = QComboBox()
            cb.addItems(["editor", "game", "off"])
            cb.setCurrentText(self._config.get(key, "editor"))
            cb.currentTextChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            return cb
        if key == "physics.solver":
            from physics_solvers.registry import SOLVERS, choices, normalize
            container = QWidget()
            vl = QVBoxLayout(container)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(2)
            cb = QComboBox()
            for solver_key in choices():
                cb.addItem(SOLVERS[solver_key]["title"], solver_key)
            current = normalize(self._config.get(key, value))
            idx = cb.findData(current)
            if idx >= 0:
                cb.setCurrentIndex(idx)
            cb.currentIndexChanged.connect(lambda i, k=key, c=cb: self._on_value_changed(k, c.itemData(i)))
            vl.addWidget(cb)
            info = QLabel("Culverin (Jolt Physics) = default, fast and recommended\n" "PyBullet (Bullet Physics) = needs 'pip install pybullet'\n" "PhysX (NVIDIA) = needs 'pip install ovphysx'")
            info.setStyleSheet("color: #888; font-size: 11px; padding-left: 4px;")
            info.setWordWrap(True)
            vl.addWidget(info)
            return container
        if isinstance(value, list):
            if len(value) in (3, 4) and all(isinstance(v, (int, float)) for v in value):
                from editor.color import ColorLineEdit
                current = self._config.get(key, value)
                cl = ColorLineEdit(current)
                cl.colorChanged.connect(lambda _, k=key, w=cl: self._on_value_changed(k, w.get_color_rgba()))
                return cl
            return None
        if isinstance(value, bool):
            cb = QCheckBox()
            cb.setChecked(self._config.get(key, value))
            cb.toggled.connect(lambda checked, k=key: self._on_value_changed(k, checked))
            return cb
        elif isinstance(value, (int, float)):
            val = self._config.get(key, value)
            slider_range = _FIELD_RANGES.get(key)
            is_float = isinstance(value, float)
            w = SliderSpinBox(key, val, is_float, slider_range)
            w.valueChanged.connect(lambda v, k=key: self._on_value_changed(k, v))
            return w
        elif isinstance(value, str):
            le = QLineEdit(self._config.get(key, value))
            le.setFixedWidth(220)
            le.textChanged.connect(lambda t, k=key: self._on_value_changed(k, t))
            return le
        return None
    def _add_collision_layers_editor(self, parent_layout):
        return add_collision_layers_editor(self, parent_layout)
    def _on_layer_name_changed(self, idx):
        return on_layer_name_changed(self, idx)
    def _open_collision_matrix_dialog(self):
        return open_collision_matrix_dialog(self)
    def _on_value_changed(self, key: str, value):
        self._config.set(key, value, notify=True)
        self._config.save()
        self._update_reset_btn(key)
    def _update_reset_btn(self, key: str):
        if key not in self._field_resets:
            return
        btn, default_val = self._field_resets[key]
        current = self._config.get(key)
        btn.setVisible(current != default_val)
    def _reset_field(self, key: str):
        if key not in self._field_resets:
            return
        _, default_val = self._field_resets[key]
        self._config.reset(key)
        self._config.save()
        self._config._notify(key, default_val)
        self._update_reset_btn(key)
        widget = self._field_widgets.get(key)
        if widget is None:
            return
        if hasattr(widget, 'setValue'):
            widget.setValue(default_val if isinstance(default_val, (int, float)) else 0)
        elif hasattr(widget, 'setCurrentText'):
            widget.setCurrentText(str(default_val))
        elif hasattr(widget, 'setChecked'):
            widget.setChecked(bool(default_val))
        elif hasattr(widget, 'setText'):
            widget.setText(str(default_val))
        elif hasattr(widget, 'set_color'):
            widget.set_color(default_val)
    def _on_restore(self):
        row = self._list_widget.currentRow()
        if row < 0 or row >= len(self._sections):
            return
        section = self._sections[row]
        prefix = section + "."
        for k in [k for k in self._field_resets if k.startswith(prefix)]:
            self._field_resets.pop(k, None)
            self._field_widgets.pop(k, None)
        self._config.reset(section)
        self._config.save()
        old = self._pages[section]
        self._stack.removeWidget(old)
        old.deleteLater()
        values = self._config.to_dict().get(section, {})
        scroll = self._build_page(section, values)
        self._pages[section] = scroll
        self._stack.insertWidget(row, scroll)
        self._stack.setCurrentIndex(row)
