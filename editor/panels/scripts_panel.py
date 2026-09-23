# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from typing import TYPE_CHECKING
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout,
                              QToolBar, QToolButton, QLabel, QFileDialog,
                              QMessageBox, QSplitter, QSizePolicy)
from PyQt6.QtCore import Qt, QSize
from core.config.editor_scale import scale
from editor.panels.node_palette import NodePalette
if TYPE_CHECKING:
    from core.engine.engine import Engine

_DARK_STYLE = ""

class _ShaderGraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._graph = None
        self._view = None
        self._node_classes = {}
        self._current_file = None
        self._place_index = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setStyleSheet(f"""
        """)

        self._new_btn = QToolButton()
        self._new_btn.setText("+ New")
        self._new_btn.clicked.connect(self._new_shader)
        toolbar.addWidget(self._new_btn)

        self._open_btn = QToolButton()
        self._open_btn.setText("Open")
        self._open_btn.clicked.connect(self._open_shader)
        toolbar.addWidget(self._open_btn)

        self._save_btn = QToolButton()
        self._save_btn.setText("Save")
        self._save_btn.clicked.connect(self._save_shader)
        toolbar.addWidget(self._save_btn)

        self._save_as_btn = QToolButton()
        self._save_as_btn.setText("Save As")
        self._save_as_btn.clicked.connect(self._save_shader_as)
        toolbar.addWidget(self._save_as_btn)

        toolbar.addSeparator()

        self._compile_btn = QToolButton()
        self._compile_btn.setText("Generate Code")
        self._compile_btn.clicked.connect(self._generate_and_preview)
        toolbar.addWidget(self._compile_btn)

        self._file_label = QLabel("  No file")
        toolbar.addWidget(self._file_label)

        layout.addWidget(toolbar)

        self._create_graph_view()
        self._node_palette = self._create_node_palette()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._node_palette)
        self._view.setMinimumWidth(scale(320))
        self._view.setMinimumHeight(scale(200))
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self._view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([scale(190), scale(600)])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        layout.addWidget(splitter, 1)

    def _create_node_palette(self):
        from editor.shader_graph.nodes import ALL_NODES
        node_map: dict[str, object] = {}
        for cls in ALL_NODES:
            name = cls.NODE_NAME if hasattr(cls, 'NODE_NAME') else cls.__name__
            node_map[name] = cls
        self._node_classes = node_map
        categories: dict[str, list[tuple]] = {
            "Input": [
                ("Vertex Position", "Vertex Position", "Add Vertex Position node"),
                ("UV", "UV", "Add UV node"),
                ("Normal", "Normal", "Add Normal node"),
                ("Time", "Time", "Add Time node"),
                ("Color", "Color", "Add Color node"),
                ("Float", "Float", "Add Float node"),
            ],
            "Math": [
                ("Add", "Add", "Add Add node"),
                ("Multiply", "Multiply", "Add Multiply node"),
                ("Subtract", "Subtract", "Add Subtract node"),
                ("Lerp", "Lerp", "Add Lerp node"),
                ("Dot Product", "Dot Product", "Add Dot Product node"),
                ("Clamp", "Clamp", "Add Clamp node"),
                ("Step", "Step", "Add Step node"),
                ("Fresnel", "Fresnel", "Add Fresnel node"),
            ],
            "Vector": [
                ("Normalize", "Normalize", "Add Normalize node"),
            ],
            "Texture": [
                ("Texture 2D", "Texture 2D", "Add Texture 2D node"),
            ],
            "Output": [
                ("Vertex Output", "Vertex Output", "Add Vertex Output node"),
                ("Fragment Output", "Fragment Output", "Add Fragment Output node"),
            ],
        }
        palette = NodePalette(parent=self, title="Node Palette", placeholder="Search nodes...", categories=categories)
        palette.node_chosen.connect(self._add_node)
        return palette

    def _create_graph_view(self):
        from editor.NodeGraphQt import NodeGraph
        from editor.shader_graph.nodes import ALL_NODES
        if not getattr(self, '_node_classes', None):
            node_map: dict[str, object] = {}
            for cls in ALL_NODES:
                name = cls.NODE_NAME if hasattr(cls, 'NODE_NAME') else cls.__name__
                node_map[name] = cls
            self._node_classes = node_map
        self._graph = NodeGraph()
        self._graph.register_nodes([cls for cls in self._node_classes.values()])
        viewer = self._graph.viewer()
        self._view = viewer

    def _resolve_node_class(self, key: str):
        if key in self._node_classes:
            return self._node_classes[key]
        norm = str(key).lower().replace(" ", "").replace("_", "")
        for name, cls in self._node_classes.items():
            if str(name).lower().replace(" ", "").replace("_", "") == norm:
                return cls
        for name, cls in self._node_classes.items():
            cn = type(cls).__name__ if not isinstance(cls, type) else cls.__name__
            if norm in cn.lower().replace("_", ""):
                return cls
        return None

    def _next_node_pos(self):
        try:
            center = self._view.mapToScene(self._view.viewport().rect().center())
            cx = float(center.x())
            cy = float(center.y())
        except Exception:
            cx = 0.0
            cy = 0.0
        idx = getattr(self, '_place_index', 0)
        step = (idx % 8) * 36.0
        self._place_index = idx + 1
        return [cx + step - 126.0, cy + step - 126.0]

    def _add_node(self, key):
        cls = self._resolve_node_class(key)
        if cls is None:
            return
        node = cls()
        pos = self._next_node_pos()
        self._graph.add_node(node, pos=pos)
        try:
            self._graph.clear_selection()
            node.set_selected(True)
        except Exception:
            pass

    def _new_shader(self):
        self._graph.clear()
        self._current_file = None
        self._file_label.setText("  Untitled Shader")
        self._add_node('Vertex Output')
        self._add_node('Fragment Output')

    def _open_shader(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Shader", "",
            "Shader Files (*.shader);;All Files (*)")
        if path:
            self._load_shader_file(path)

    def _load_shader_file(self, path: str):
        self._current_file = path
        self._file_label.setText(f"  {os.path.basename(path)}")
        self._graph.clear()
        self._add_node('Vertex Output')
        self._add_node('Fragment Output')
        vo = None
        fo = None
        for n in self._graph.all_nodes():
            cn = type(n).__name__
            if 'VertexOutput' in cn:
                vo = n
                vo.set_pos(-200, 0)
            elif 'FragmentOutput' in cn:
                fo = n
                fo.set_pos(200, 0)

    def _save_shader(self):
        if self._current_file:
            self._compile_and_save(self._current_file)
        else:
            self._save_shader_as()

    def _save_shader_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Shader", "",
            "Shader Files (*.shader)")
        if path:
            if not path.endswith('.shader'):
                path += '.shader'
            self._current_file = path
            self._file_label.setText(f"  {os.path.basename(path)}")
            self._compile_and_save(path)

    def _compile_and_save(self, path: str):
        from editor.shader_graph.code_generator import generate_shader_code
        code = generate_shader_code(self._graph, self._get_shader_name(path))
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(code)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save:\n{e}")

    def _get_shader_name(self, path: str):
        basename = os.path.splitext(os.path.basename(path))[0]
        return f"Zarin/{basename}"

    def _generate_and_preview(self):
        from PyQt6.QtWidgets import QPlainTextEdit
        from editor.shader_graph.code_generator import generate_shader_code
        code = generate_shader_code(self._graph, "Preview/Shader")
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(code)
        preview.resize(700, 500)
        preview.setWindowTitle("Generated Shader Code")
        preview.setStyleSheet(f"""
            QPlainTextEdit {{ background: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace; font-size: 12px; }}
        """)
        preview.show()

class ScriptsPanel(QDockWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Shaders", parent)
        self._engine = engine
        self.setStyleSheet(_DARK_STYLE)
        self.setObjectName("ShadersDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setMinimumSize(scale(680), scale(420))
        self._shader_widget = _ShaderGraphWidget()
        self.setWidget(self._shader_widget)
