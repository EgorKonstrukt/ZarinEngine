# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional
import editor.icons as qta
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QSplitter, QDialog,
    QDoubleSpinBox, QComboBox, QMenu,
)
from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QMouseEvent, QWheelEvent,
    QKeyEvent, QPainterPath, QFontMetrics, QPalette,
)
from core.foundation.curve import Curve, CurveKey, TangentMode
from core.components.animation.animation_clip import AnimationClip
from core.config.editor_scale import scale, scale_xy
from core.components.properties import read_prop, to_float
from editor.inspector.entity_property_picker import EntityPropertyDialog

from editor.panels.anim.panel import TimelineRuler, Dopesheet, CurveEditorWidget
from editor.panels.anim.panel import _FPS, _TIMELINE_HEIGHT, _KEYFRAME_SIZE, _ROW_HEIGHT, _LEFT_PANEL_WIDTH, _LABEL_WIDTH

class AnimationPanel(QDockWidget):
    def __init__(self, engine, main_window):
        super().__init__("Animation", main_window)
        self._engine = engine
        self._main_window = main_window
        self._clip: Optional[AnimationClip] = None
        self._clip_path: str = ""
        self._entity: Optional[object] = None
        self._is_playing: bool = False
        self._current_time: float = 0.0
        self._pixels_per_second: float = 100.0
        self._selected_property: Optional[str] = None
        self._dirty: bool = False
        self.setObjectName("AnimationDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setMinimumSize(300, 200)
        self._build_ui()
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._tick)

    def _build_ui(self):
        central = QWidget()
        self.setWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_toolbar())
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._timeline_ruler = TimelineRuler()
        self._timeline_ruler.scrubbed.connect(self._on_scrub)
        self._dopesheet = Dopesheet()
        self._dopesheet.key_selected.connect(self._on_key_selected)
        self._dopesheet.keys_modified.connect(self._mark_dirty)
        self._dopesheet.property_clicked.connect(self._on_property_clicked)
        self._dopesheet.remove_requested.connect(self._on_remove_requested)
        self._curve_editor = CurveEditorWidget()
        self._curve_editor.curve_changed.connect(self._mark_dirty)
        timeline_widget = QWidget()
        tl_layout = QVBoxLayout(timeline_widget)
        tl_layout.setContentsMargins(0, 0, 0, 0)
        tl_layout.setSpacing(0)
        tl_layout.addWidget(self._timeline_ruler)
        tl_layout.addWidget(self._dopesheet, 1)
        splitter.addWidget(timeline_widget)
        splitter.addWidget(self._curve_editor)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)
        self._update_ui()

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self._play_btn = QPushButton(qta.icon("fa5s.play", color=chr(35) + "d4d4d4"), "")
        self._play_btn.setFixedSize(*scale_xy(26, 22))
        self._play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self._play_btn)
        self._stop_btn = QPushButton(qta.icon("fa5s.stop", color=chr(35) + "d4d4d4"), "")
        self._stop_btn.setFixedSize(*scale_xy(26, 22))
        self._stop_btn.clicked.connect(self._stop_playback)
        layout.addWidget(self._stop_btn)
        self._record_btn = QPushButton(qta.icon("fa5s.dot-circle", color=chr(35) + "ff4444"), "")
        self._record_btn.setFixedSize(*scale_xy(26, 22))
        layout.addWidget(self._record_btn)
        self._key_btn = QPushButton(qta.icon("fa5s.key", color=chr(35) + "d4d4d4"), "")
        self._key_btn.setFixedSize(*scale_xy(26, 22))
        self._key_btn.setToolTip("Add Keyframe")
        self._key_btn.clicked.connect(self._add_keyframe)
        layout.addWidget(self._key_btn)
        self._time_spin = QDoubleSpinBox()
        self._time_spin.setRange(0.0, 99999.0)
        self._time_spin.setSingleStep(0.01)
        self._time_spin.setDecimals(2)
        self._time_spin.setValue(0.0)
        self._time_spin.valueChanged.connect(self._on_spin_time)
        self._time_spin.setFixedWidth(scale(70))
        self._time_spin.setStyleSheet("border: 1px solid; border-radius: 3px; padding: 1px 4px;")
        layout.addWidget(self._time_spin)
        self._add_prop_btn = QPushButton(qta.icon("fa5s.plus", color=chr(35) + "9ccc65"), " Add Property")
        self._add_prop_btn.setFixedHeight(scale(22))
        self._add_prop_btn.clicked.connect(self._add_property)
        layout.addWidget(self._add_prop_btn)
        self._clip_combo = QComboBox()
        self._clip_combo.setMinimumWidth(150)
        self._clip_combo.setStyleSheet("border: 1px solid; border-radius: 3px; padding: 1px 4px;")
        layout.addWidget(self._clip_combo)
        layout.addStretch()
        return tb

    def _btn_style(self) -> str:
        return ""


    def set_entity(self, entity):
        self._entity = entity
        if entity:
            anim = entity.get_component_by_name("Animation")
            if anim and anim.clip:
                self.load_clip_from_path(anim.clip)
                return
        self.load_clip_from_path("")

    def load_clip_from_path(self, path: str):
        if self._dirty and self._clip and self._clip_path:
            self._clip.save(self._clip_path)
            self._dirty = False
        self._clip_path = path
        if path:
            clip = AnimationClip.load(path)
            self.load_clip(clip)
        else:
            self.load_clip(None)

    def load_clip(self, clip: Optional[AnimationClip]):
        if self._dirty and self._clip and self._clip_path:
            self._clip.save(self._clip_path)
            self._dirty = False
        self._clip = clip
        self._current_time = 0.0
        self._timeline_ruler.set_clip(clip)
        self._dopesheet.set_clip(clip)
        self._curve_editor.set_curve("", None)
        self._selected_property = None
        self._dopesheet.set_selected_property(None)
        self._update_property_list()
        self._update_ui()
        self._timeline_ruler.set_time(0.0)
        self._dopesheet.set_time(0.0)
        self._time_spin.setValue(0.0)

    def _update_property_list(self):
        self._dopesheet.update()

    def _mark_dirty(self):
        self._dirty = True

    def _add_property(self):
        if not self._clip or not self._entity:
            return
        entity_id = self._entity.id
        dlg = EntityPropertyDialog(self._engine.scene, entity_id, "", self, locked=True)
        dlg.setWindowTitle(f"Add Property — {self._entity.name}")
        if dlg.exec_near_cursor() == QDialog.DialogCode.Accepted:
            path = dlg.result_property()
            if path:
                self._on_add_property(path)

    def _on_add_property(self, path: str):
        if self._clip:
            self._clip.add_curve(path)
            self._mark_dirty()
            self._update_property_list()

    def _on_property_clicked(self, path: str):
        self._selected_property = path
        if self._clip and path in self._clip.curves:
            self._curve_editor.set_curve(path, self._clip.curves[path])
            self._dopesheet.set_selected_property(path)

    def _on_remove_requested(self, path: str):
        if self._clip:
            self._clip.remove_curve(path)
            self._mark_dirty()
            self._update_property_list()
            if self._selected_property == path:
                self._selected_property = None
                self._curve_editor.set_curve("", None)

    def _on_key_selected(self, path, key):
        if self._clip and path in self._clip.curves:
            self._selected_property = path
            self._dopesheet.set_selected_property(path)
            self._curve_editor.set_curve(path, self._clip.curves[path])

    def _apply_preview(self, t: float):
        if not self._clip or not self._entity:
            return
        try:
            from core.components.animation.animation_component import (
                _as_quat,
                _resolve_bone_path,
            )
            from core.components.properties import write_prop
            for bone_path, prop, val in self._clip.evaluate_all(t):
                target = _resolve_bone_path(self._entity, bone_path)
                write_prop(target, prop, val)
            for bone_path, prop, quat in self._clip.evaluate_rotations_all(t):
                target = _resolve_bone_path(self._entity, bone_path)
                write_prop(target, prop, _as_quat(quat))
        except Exception:
            pass

    def _on_scrub(self, t: float):
        self._current_time = t
        self._apply_preview(t)
        self._time_spin.blockSignals(True)
        self._time_spin.setValue(t)
        self._time_spin.blockSignals(False)
        self._dopesheet.set_time(t)

    def _on_spin_time(self, t: float):
        self._current_time = t
        self._apply_preview(t)
        self._timeline_ruler.set_time(t)
        self._dopesheet.set_time(t)

    def _toggle_play(self):
        if self._is_playing:
            self._is_playing = False
            self._play_btn.setIcon(qta.icon("fa5s.play", color=chr(35) + "d4d4d4"))
            self._play_timer.stop()
        else:
            self._is_playing = True
            self._play_btn.setIcon(qta.icon("fa5s.pause", color=chr(35) + "d4d4d4"))
            self._play_timer.start(int(1000 / _FPS))

    def _stop_playback(self):
        self._is_playing = False
        self._play_btn.setIcon(qta.icon("fa5s.play", color=chr(35) + "d4d4d4"))
        self._play_timer.stop()
        self._current_time = 0.0
        self._timeline_ruler.set_time(0.0)
        self._dopesheet.set_time(0.0)
        self._time_spin.setValue(0.0)
        self._apply_preview(0.0)

    def _tick(self):
        if not self._clip:
            return
        dt = 1.0 / _FPS
        self._current_time += dt
        if self._current_time >= self._clip.length:
            if self._clip.loop:
                self._current_time %= self._clip.length
            else:
                self._current_time = self._clip.length
                self._toggle_play()
        self._timeline_ruler.set_time(self._current_time)
        self._dopesheet.set_time(self._current_time)
        self._apply_preview(self._current_time)
        self._time_spin.blockSignals(True)
        self._time_spin.setValue(self._current_time)
        self._time_spin.blockSignals(False)

    def _add_keyframe(self):
        if not self._clip or not self._selected_property:
            return
        curve = self._clip.add_curve(self._selected_property)
        val = to_float(read_prop(self._entity, self._selected_property))
        curve.add_key(self._current_time, val if val is not None else 0.0)
        self._mark_dirty()
        self._update_property_list()
        self._curve_editor.set_curve(self._selected_property, curve)

    def _update_ui(self):
        has_clip = self._clip is not None
        self._play_btn.setEnabled(has_clip)
        self._stop_btn.setEnabled(has_clip)
        self._key_btn.setEnabled(has_clip)
        self._add_prop_btn.setEnabled(has_clip)

    def load_config(self, config):
        pass

