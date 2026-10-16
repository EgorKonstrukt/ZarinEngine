# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QGroupBox, QScrollArea, QSlider
from PySide6.QtCore import Qt
from core.components.mesh_editor import ProBuilderMesh, SelectionMode, get_primitive_names
from core.config.editor_scale import scale
from editor.panels.meshedit.widgets import _STYLE_GROUP, _STYLE_LABEL, _make_btn, _make_spin
from editor.panels.meshedit.ops import _MeshOpsMixin
if TYPE_CHECKING:
    from core.ecs import Entity
    from core.engine.eng import Engine


class MeshEditorPanel(_MeshOpsMixin, QDockWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Mesh Editor", parent)
        self._engine = engine
        self._entity: Optional[Entity] = None
        self._mesh_comp: Optional[ProBuilderMesh] = None
        self._updating = False
        self.setObjectName("MeshEditorDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)
        root = QWidget()
        self.setWidget(root)
        self._layout = QVBoxLayout(root)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(2)
        scroll.setWidget(scroll_content)
        self._layout.addWidget(scroll)
        self._build_primitive_section()
        self._build_tools_section()
        self._build_selection_section()
        self._build_transform_section()
        self._build_info_section()
        self._scroll_layout.addStretch()
        self._update_mesh_ui(False)

    def _add_group(self, title: str, store_as: str = "") -> QVBoxLayout:
        gb = QGroupBox(title)
        gb.setStyleSheet(_STYLE_GROUP)
        layout = QVBoxLayout(gb)
        layout.setContentsMargins(6, 12, 6, 6)
        layout.setSpacing(3)
        self._scroll_layout.addWidget(gb)
        if store_as:
            setattr(self, store_as, gb)
        return layout

    def _build_primitive_section(self):
        layout = self._add_group("New Shape")
        row1 = QHBoxLayout()
        row1.setSpacing(3)
        self._primitive_combo = QComboBox()
        for name in get_primitive_names():
            self._primitive_combo.addItem(name)
        self._primitive_combo.setStyleSheet("border: 1px solid; padding: 2px 4px;")
        row1.addWidget(self._primitive_combo, 1)
        create_btn = _make_btn("Create", "Create primitive as new mesh", accent=True)
        create_btn.clicked.connect(self._on_create_primitive)
        row1.addWidget(create_btn)
        layout.addLayout(row1)
        size_row = QHBoxLayout()
        size_row.setSpacing(3)
        size_row.addWidget(QLabel("Size"))
        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setRange(1, 100)
        self._size_slider.setValue(50)
        self._size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._size_label = QLabel("1.0")
        self._size_label.setFixedWidth(scale(28))
        self._size_label.setStyleSheet("")
        self._size_slider.valueChanged.connect(lambda v: self._size_label.setText(f"{v/50:.1f}"))
        size_row.addWidget(self._size_slider)
        size_row.addWidget(self._size_label)
        layout.addLayout(size_row)
        detail_row = QHBoxLayout()
        detail_row.setSpacing(3)
        detail_row.addWidget(QLabel("Detail"))
        self._detail_slider = QSlider(Qt.Orientation.Horizontal)
        self._detail_slider.setRange(1, 100)
        self._detail_slider.setValue(50)
        self._detail_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._detail_label = QLabel("32")
        self._detail_label.setFixedWidth(scale(28))
        self._detail_label.setStyleSheet("")
        self._detail_slider.valueChanged.connect(lambda v: self._detail_label.setText(f"{max(4, v*32//50)}"))
        detail_row.addWidget(self._detail_slider)
        detail_row.addWidget(self._detail_label)
        layout.addLayout(detail_row)

    def _build_tools_section(self):
        layout = self._add_group("Tools", "_tools_group")
        r1 = QHBoxLayout()
        r1.setSpacing(3)
        extrude_btn = _make_btn("Extrude", "Extrude selected faces")
        extrude_btn.clicked.connect(self._on_extrude)
        r1.addWidget(extrude_btn)
        self._extrude_dist = _make_spin(0.25, -10, 10, 0.05, 3)
        r1.addWidget(self._extrude_dist)
        layout.addLayout(r1)
        r2 = QHBoxLayout()
        r2.setSpacing(3)
        bevel_btn = _make_btn("Bevel", "Bevel selected edges")
        bevel_btn.clicked.connect(self._on_bevel)
        r2.addWidget(bevel_btn)
        self._bevel_amount = _make_spin(0.1, 0.001, 5, 0.01, 3)
        r2.addWidget(self._bevel_amount)
        layout.addLayout(r2)
        r3 = QHBoxLayout()
        r3.setSpacing(3)
        subd_btn = _make_btn("Subdivide", "Subdivide selected faces")
        subd_btn.clicked.connect(self._on_subdivide)
        r3.addWidget(subd_btn)
        layout.addLayout(r3)
        r4 = QHBoxLayout()
        r4.setSpacing(3)
        weld_btn = _make_btn("Weld Verts", "Merge vertices within threshold")
        weld_btn.clicked.connect(self._on_weld)
        r4.addWidget(weld_btn)
        self._weld_thresh = _make_spin(0.001, 0.0001, 1, 0.001, 4)
        r4.addWidget(self._weld_thresh)
        layout.addLayout(r4)
        r5 = QHBoxLayout()
        r5.setSpacing(3)
        flip_btn = _make_btn("Flip Normals", "Flip normals of selected faces")
        flip_btn.clicked.connect(self._on_flip)
        r5.addWidget(flip_btn)
        layout.addLayout(r5)
        r6 = QHBoxLayout()
        r6.setSpacing(3)
        collapse_btn = _make_btn("Collapse Edges", "Collapse selected edges to midpoint")
        collapse_btn.clicked.connect(self._on_collapse)
        r6.addWidget(collapse_btn)
        layout.addLayout(r6)
        r7 = QHBoxLayout()
        r7.setSpacing(3)
        bridge_btn = _make_btn("Bridge Edges", "Bridge two selected edges")
        bridge_btn.clicked.connect(self._on_bridge)
        r7.addWidget(bridge_btn)
        layout.addLayout(r7)
        r8 = QHBoxLayout()
        r8.setSpacing(3)
        optimize_btn = _make_btn("Optimize", "Remove degenerate faces and weld coincident verts")
        optimize_btn.clicked.connect(self._on_optimize)
        r8.addWidget(optimize_btn)
        layout.addLayout(r8)

    def _build_selection_section(self):
        layout = self._add_group("Selection", "_sel_group")
        r = QHBoxLayout()
        r.setSpacing(3)
        self._sel_obj = _make_btn("Object", "Object selection mode")
        self._sel_obj.clicked.connect(lambda: self._set_sel_mode(SelectionMode.OBJECT))
        r.addWidget(self._sel_obj)
        self._sel_vert = _make_btn("Vertex", "Vertex selection mode")
        self._sel_vert.clicked.connect(lambda: self._set_sel_mode(SelectionMode.VERTEX))
        r.addWidget(self._sel_vert)
        self._sel_edge = _make_btn("Edge", "Edge selection mode")
        self._sel_edge.clicked.connect(lambda: self._set_sel_mode(SelectionMode.EDGE))
        r.addWidget(self._sel_edge)
        self._sel_face = _make_btn("Face", "Face selection mode")
        self._sel_face.clicked.connect(lambda: self._set_sel_mode(SelectionMode.FACE))
        r.addWidget(self._sel_face)
        layout.addLayout(r)
        clear_sel = _make_btn("Clear Selection", "Deselect all")
        clear_sel.clicked.connect(self._on_clear_selection)
        layout.addWidget(clear_sel)

    def _build_transform_section(self):
        layout = self._add_group("Transform Tools", "_xform_group")
        r1 = QHBoxLayout()
        r1.setSpacing(3)
        center_btn = _make_btn("Center Pivot", "Center pivot to geometry")
        center_btn.clicked.connect(self._on_center_pivot)
        r1.addWidget(center_btn)
        layout.addLayout(r1)

    def _build_info_section(self):
        layout = self._add_group("Mesh Info", "_info_group")
        self._vert_label = QLabel("Verts: 0")
        self._vert_label.setStyleSheet(_STYLE_LABEL)
        layout.addWidget(self._vert_label)
        self._tri_label = QLabel("Tris: 0")
        self._tri_label.setStyleSheet(_STYLE_LABEL)
        layout.addWidget(self._tri_label)
        self._edge_label = QLabel("Edges: 0")
        self._edge_label.setStyleSheet(_STYLE_LABEL)
        layout.addWidget(self._edge_label)
        smooth_row = QHBoxLayout()
        smooth_row.setSpacing(3)
        smooth_row.addWidget(QLabel("Smooth Angle"))
        self._smooth_angle = QSlider(Qt.Orientation.Horizontal)
        self._smooth_angle.setRange(0, 180)
        self._smooth_angle.setValue(45)
        self._smooth_angle.valueChanged.connect(self._on_smooth_changed)
        smooth_row.addWidget(self._smooth_angle)
        self._smooth_label = QLabel("45")
        self._smooth_label.setFixedWidth(scale(24))
        self._smooth_label.setStyleSheet("")
        smooth_row.addWidget(self._smooth_label)
        layout.addLayout(smooth_row)

    def _update_mesh_ui(self, enabled: bool):
        for w in [self._tools_group, self._sel_group, self._xform_group, self._info_group]:
            w.setEnabled(enabled)

    def set_entity(self, entity: Optional[Entity]):
        self._entity = entity
        if entity is None:
            self._mesh_comp = None
            self._update_mesh_ui(False)
            self._update_info()
            return
        comp = entity.get_component(ProBuilderMesh)
        self._mesh_comp = comp
        if comp is None:
            self._update_mesh_ui(False)
        else:
            self._update_mesh_ui(True)
            self._update_info()
            self._update_sel_buttons()
