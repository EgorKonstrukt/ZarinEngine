# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QToolBar, QToolButton, QLabel, QDoubleSpinBox, QSpinBox, QPlainTextEdit, QFileDialog, QSplitter, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, QSize
from core.config.editor_scale import scale
from editor.panels.node_palette import NodePalette
from core.foundation.logger import Logger


class _TerrainNodeGraphWidget(QWidget):
    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._panel = panel
        self._graph = None
        self._view = None
        self._node_classes = {}
        self._graph_path = ""
        self._loading = False
        self._collab_bridge = None
        self._place_index = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        save_btn = QToolButton()
        save_btn.setText("Save")
        save_btn.setToolTip("Save graph to .zterr file")
        save_btn.clicked.connect(lambda: self._save_graph())
        toolbar.addWidget(save_btn)
        save_as_btn = QToolButton()
        save_as_btn.setText("Save As")
        save_as_btn.clicked.connect(lambda: self._save_graph_as())
        toolbar.addWidget(save_as_btn)
        open_btn = QToolButton()
        open_btn.setText("Open")
        open_btn.setToolTip("Open .zterr graph file")
        open_btn.clicked.connect(lambda: self._open_graph())
        toolbar.addWidget(open_btn)
        toolbar.addSeparator()
        new_btn = QToolButton()
        new_btn.setText("+ New")
        new_btn.clicked.connect(self._new_graph)
        toolbar.addWidget(new_btn)
        delete_btn = QToolButton()
        delete_btn.setText("Delete")
        delete_btn.setToolTip("Delete selected nodes (Del)")
        delete_btn.clicked.connect(self._delete_selected)
        toolbar.addWidget(delete_btn)
        toolbar.addSeparator()
        preview_btn = QToolButton()
        preview_btn.setText("Preview")
        preview_btn.clicked.connect(self._on_preview)
        toolbar.addWidget(preview_btn)
        self._live_btn = QToolButton()
        self._live_btn.setText("Live")
        self._live_btn.setCheckable(True)
        self._live_btn.toggled.connect(self._on_live_toggle)
        toolbar.addWidget(self._live_btn)
        toolbar.addSeparator()
        res_label = QLabel("Res:")
        toolbar.addWidget(res_label)
        self._res_spin = QSpinBox()
        self._res_spin.setRange(32, 2048)
        self._res_spin.setSingleStep(16)
        self._res_spin.setValue(512)
        self._res_spin.setMaximumWidth(80)
        toolbar.addWidget(self._res_spin)
        world_label = QLabel("World:")
        toolbar.addWidget(world_label)
        self._world_spin = QDoubleSpinBox()
        self._world_spin.setRange(10.0, 100000.0)
        self._world_spin.setSingleStep(10.0)
        self._world_spin.setDecimals(1)
        self._world_spin.setValue(1000.0)
        self._world_spin.setMaximumWidth(100)
        toolbar.addWidget(self._world_spin)
        self._shader_preview_btn = QToolButton()
        self._shader_preview_btn.setText("View GLSL")
        self._shader_preview_btn.clicked.connect(self._show_shader_code)
        toolbar.addWidget(self._shader_preview_btn)
        layout.addWidget(toolbar)
        self._create_graph_view()
        self._node_palette = self._create_node_palette()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._node_palette)
        viewer = self._graph.viewer()
        self._view = viewer
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
        self._graph.node_created.connect(self._on_graph_changed)
        self._graph.nodes_deleted.connect(self._on_graph_changed)
        self._graph.port_connected.connect(self._on_graph_changed)
        self._graph.port_disconnected.connect(self._on_graph_changed)
        self._graph.property_changed.connect(self._on_graph_changed)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(600)
        self._preview_timer.timeout.connect(self._do_update_previews)
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(800)
        self._live_timer.timeout.connect(self._do_live_generate)
        self._preview_busy = False
        self._live_busy = False
        self._view.installEventFilter(self)
        self._collab_bridge = None

    def set_collaboration_manager(self, mgr):
        if self._collab_bridge is None:
            from editor.terrain_graph.collab_bridge import TerrainGraphCollabBridge
            self._collab_bridge = TerrainGraphCollabBridge(self, mgr)
        else:
            self._collab_bridge.set_collaboration_manager(mgr)

    def eventFilter(self, obj, event):
        if obj is self._view and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Delete:
                self._delete_selected()
                return True
        return super().eventFilter(obj, event)

    def _create_node_palette(self):
        from editor.terrain_graph.nodesp import ALL_NODES
        node_map = {}
        for cls in ALL_NODES:
            name = cls.NODE_NAME if hasattr(cls, 'NODE_NAME') else cls.__name__
            node_map[name] = cls
        self._node_classes = node_map
        categories: dict[str, list[tuple]] = {}
        for cls in ALL_NODES:
            name = cls.NODE_NAME if hasattr(cls, 'NODE_NAME') else cls.__name__
            nt = getattr(cls, 'NODE_TYPE', 'value')
            cat = nt.replace("_", " ").title()
            if cat not in categories:
                categories[cat] = []
            categories[cat].append((name, name, f"Add {name} node"))
        order = ["Generator", "Uv Modifier", "Modifier", "Math", "Output"]
        ordered: dict[str, list[tuple]] = {}
        for cat in order:
            if cat in categories:
                ordered[cat] = sorted(categories.pop(cat), key=lambda e: e[0].lower())
        for cat in sorted(categories.keys()):
            ordered[cat] = sorted(categories[cat], key=lambda e: e[0].lower())
        palette = NodePalette(parent=self, title="Node Palette", placeholder="Search nodes...", categories=ordered)
        palette.node_chosen.connect(self._add_node)
        return palette

    def _create_graph_view(self):
        from editor.NodeGraphQt import NodeGraph
        from editor.terrain_graph.nodesp import ALL_NODES
        self._graph = NodeGraph()
        self._graph.register_nodes(ALL_NODES)

    def _add_node(self, key):
        target = None
        for cls in self._node_classes.values():
            cls_name = getattr(cls, 'NODE_NAME', cls.__name__)
            if cls_name == key:
                target = cls
                break
        if target is None:
            return
        node = target()
        pos = self._next_node_pos()
        self._graph.add_node(node, pos=pos)
        try:
            self._graph.clear_selection()
            node.set_selected(True)
        except Exception:
            pass

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

    def _delete_selected(self):
        selected = self._graph.selected_nodes()
        if not selected:
            return
        self._graph.delete_nodes(selected)

    def _new_graph(self):
        self._graph.clear()
        self._graph_path = ""
        self._update_title()

    def _update_title(self):
        name = os.path.splitext(os.path.basename(self._graph_path))[0] if self._graph_path else "untitled"
        self._panel.setWindowTitle(f"Terrain Editor — {name}")

    def _save_graph(self):
        if self._graph_path:
            self._do_save(self._graph_path)
        else:
            self._save_graph_as()

    def _save_graph_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Terrain Graph", self._graph_path or "",
            "Terrain Graphs (*.zterr)")
        if not path:
            return
        if not path.endswith(".zterr"):
            path += ".zterr"
        self._do_save(path)
        self._graph_path = path
        self._update_title()
        if self._panel._terrain is not None:
            self._panel._terrain.graph_path = path

    def _do_save(self, path):
        from editor.terrain_graph.graph_serializer import save_graph
        if save_graph(self._graph, path):
            Logger.info(f"TerrainGraph: saved to {path}")
        else:
            Logger.warning(f"TerrainGraph: failed to save to {path}")

    def _open_graph(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open Terrain Graph", "",
                "Terrain Graphs (*.zterr)")
            if not path:
                return
        self._loading = True
        from editor.terrain_graph.graph_serializer import load_graph
        ok = load_graph(self._graph, path)
        self._loading = False
        if ok:
            self._graph_path = path
            self._update_title()
            Logger.info(f"TerrainGraph: loaded from {path}")
            if self._panel._terrain is not None:
                self._panel._terrain.graph_path = path
        else:
            Logger.warning(f"TerrainGraph: failed to load from {path}")

    def _on_graph_changed(self, *args):
        if self._loading:
            return
        if self._panel._live:
            self._live_timer.start()
        self._preview_timer.start()

    def _do_live_generate(self):
        if self._live_busy:
            self._live_timer.start()
            return
        self._live_busy = True
        try:
            if self._panel._terrain is not None or self._panel._find_or_create_terrain():
                self._panel._on_generate()
        finally:
            self._live_busy = False

    def _on_preview(self):
        self._panel._on_generate()
        self._do_update_previews()

    def _do_update_previews(self):
        if self._preview_busy:
            return
        self._preview_busy = True
        try:
            from editor.terrain_graph.node_preview import update_all_previews
            update_all_previews(self._graph, resolution=48)
        except Exception as e:
            Logger.warning(f"TerrainGraph: preview update failed: {e}")
        finally:
            self._preview_busy = False

    def _on_live_toggle(self, enabled):
        self._panel.set_live(enabled)

    def _show_shader_code(self):
        from editor.terrain_graph.code_generator import generate_shader
        res = self._res_spin.value()
        source, uniforms, height_scale = generate_shader(self._graph, res)
        if not source:
            Logger.warning("TerrainGraph: empty graph, cannot generate shader")
            return
        self._preview_window = QPlainTextEdit()
        self._preview_window.setReadOnly(True)
        self._preview_window.setPlainText(source)
        self._preview_window.resize(700, 500)
        self._preview_window.setWindowTitle("Generated Terrain Compute Shader")
        self._preview_window.setStyleSheet("QPlainTextEdit { background: rgb(30, 30, 30); color: rgb(212, 212, 212); font-family: Consolas, monospace; font-size: 12px; }")
        self._preview_window.show()
