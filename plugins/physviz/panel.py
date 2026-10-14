# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
try:
    from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QWidget = object
    QVBoxLayout = object
    QHBoxLayout = object
    QLabel = object
    QCheckBox = object
    QDoubleSpinBox = object
    QSpinBox = object
    QPushButton = object
if _HAS_QT:
    class _PhysicsVisualisationPanel(QWidget):
        def __init__(self, plugin, parent=None):
            super().__init__(parent)
            self._plugin = plugin
            layout = QVBoxLayout(self)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(4)
            s = plugin.settings
            self._cb_enabled = QCheckBox("Enabled")
            self._cb_enabled.setChecked(bool(s["enabled"]))
            self._cb_enabled.toggled.connect(lambda v: self._set("enabled", bool(v)))
            layout.addWidget(self._cb_enabled)
            self._cb_velocity = QCheckBox("Velocity")
            self._cb_velocity.setChecked(bool(s["show_velocity"]))
            self._cb_velocity.toggled.connect(lambda v: self._set("show_velocity", bool(v)))
            layout.addWidget(self._cb_velocity)
            self._cb_acceleration = QCheckBox("Acceleration")
            self._cb_acceleration.setChecked(bool(s["show_acceleration"]))
            self._cb_acceleration.toggled.connect(lambda v: self._set("show_acceleration", bool(v)))
            layout.addWidget(self._cb_acceleration)
            self._cb_moment = QCheckBox("Moment")
            self._cb_moment.setChecked(bool(s["show_moment"]))
            self._cb_moment.toggled.connect(lambda v: self._set("show_moment", bool(v)))
            layout.addWidget(self._cb_moment)
            self._cb_selected = QCheckBox("Only selected")
            self._cb_selected.setChecked(bool(s["only_selected"]))
            self._cb_selected.toggled.connect(lambda v: self._set("only_selected", bool(v)))
            layout.addWidget(self._cb_selected)
            self._cb_labels = QCheckBox("Value labels")
            self._cb_labels.setChecked(bool(s["show_labels"]))
            self._cb_labels.toggled.connect(lambda v: self._set("show_labels", bool(v)))
            layout.addWidget(self._cb_labels)
            self._cb_editor = QCheckBox("Show in editor")
            self._cb_editor.setChecked(bool(s["show_editor"]))
            self._cb_editor.toggled.connect(lambda v: self._set("show_editor", bool(v)))
            layout.addWidget(self._cb_editor)
            self._cb_runtime = QCheckBox("Show in play mode")
            self._cb_runtime.setChecked(bool(s["show_runtime"]))
            self._cb_runtime.toggled.connect(lambda v: self._set("show_runtime", bool(v)))
            layout.addWidget(self._cb_runtime)
            self._cb_contacts = QCheckBox("Contacts")
            self._cb_contacts.setChecked(bool(s["show_contacts"]))
            self._cb_contacts.toggled.connect(lambda v: self._set("show_contacts", bool(v)))
            layout.addWidget(self._cb_contacts)
            self._cb_joints = QCheckBox("Joints")
            self._cb_joints.setChecked(bool(s["show_joints"]))
            self._cb_joints.toggled.connect(lambda v: self._set("show_joints", bool(v)))
            layout.addWidget(self._cb_joints)
            self._cb_colliders = QCheckBox("Colliders")
            self._cb_colliders.setChecked(bool(s["show_colliders"]))
            self._cb_colliders.toggled.connect(lambda v: self._set("show_colliders", bool(v)))
            layout.addWidget(self._cb_colliders)
            self._make_scale_row(layout, "Velocity scale", float(s["velocity_scale"]), "velocity_scale")
            self._make_scale_row(layout, "Acceleration scale", float(s["acceleration_scale"]), "acceleration_scale")
            self._make_scale_row(layout, "Moment scale", float(s["moment_scale"]), "moment_scale")
            self._make_scale_row(layout, "Max length", float(s["max_length"]), "max_length")
            self._make_scale_row(layout, "Min magnitude", float(s["min_magnitude"]), "min_magnitude")
            self._make_contact_row(layout, "Contact normal", float(s["contact_normal_length"]), "contact_normal_length")
            self._make_smooth_row(layout, "Smoothing", float(s["smooth"]), "smooth")
            self._make_scale_row(layout, "Accel spike limit", float(s["accel_spike"]), "accel_spike")
            self._make_scale_row(layout, "Moment spike limit", float(s["moment_spike"]), "moment_spike")
            self._make_int_row(layout, "Label cap", int(s["label_cap"]), "label_cap")
            btn = QPushButton("Clear")
            btn.clicked.connect(self._on_clear)
            layout.addWidget(btn)
            layout.addStretch(1)
        def _set(self, key, value):
            try:
                self._plugin.configure({key: value})
            except Exception:
                pass
        def _on_clear(self):
            try:
                self._plugin.clear()
            except Exception:
                pass
        def _make_scale_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QDoubleSpinBox()
            box.setRange(0.001, 5000.0)
            box.setDecimals(3)
            box.setSingleStep(0.05)
            box.setValue(max(0.001, value))
            box.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box
        def _make_smooth_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QDoubleSpinBox()
            box.setRange(0.02, 0.98)
            box.setDecimals(2)
            box.setSingleStep(0.05)
            box.setValue(min(0.98, max(0.02, value)))
            box.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box
        def _make_contact_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QDoubleSpinBox()
            box.setRange(0.05, 3.0)
            box.setDecimals(2)
            box.setSingleStep(0.05)
            box.setValue(min(3.0, max(0.05, value)))
            box.valueChanged.connect(lambda v, k=key: self._set(k, float(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box
        def _make_int_row(self, layout, title, value, key):
            row = QHBoxLayout()
            row.setSpacing(4)
            label = QLabel(title)
            row.addWidget(label)
            row.addStretch(1)
            box = QSpinBox()
            box.setRange(0, 500)
            box.setSingleStep(4)
            box.setValue(max(0, value))
            box.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
            row.addWidget(box)
            layout.addLayout(row)
            return box
