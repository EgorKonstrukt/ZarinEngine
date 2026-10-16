# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import random
from typing import Optional, TYPE_CHECKING
from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from core.config.editor_scale import scale
from core.foundation.cmd import AddComponentCommand, get_history
from core.components.rendering.terrain import Terrain
from core.components.physics.terrain_collider import TerrainCollider
from core.components.transform.tr import Transform
from core.foundation.logger import Logger
from editor.panels.terrain.graph_widget import _TerrainNodeGraphWidget
if TYPE_CHECKING:
    from core.ecs import Entity
    from core.engine.eng import Engine


class TerrainPanel(QDockWidget):
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Terrain Editor", parent)
        self._engine = engine
        self._entity: Optional[Entity] = None
        self._terrain: Optional[Terrain] = None
        self._live = False
        self.setObjectName("TerrainEditorDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setMinimumSize(scale(680), scale(420))
        root = QWidget()
        self.setWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        action_bar = QHBoxLayout()
        create_btn = QPushButton("Create Terrain")
        create_btn.setToolTip("Create a new terrain on the selected object")
        create_btn.clicked.connect(self._on_create)
        action_bar.addWidget(create_btn)
        add_col_btn = QPushButton("Add Collider")
        add_col_btn.setToolTip("Add a TerrainCollider to the current terrain")
        add_col_btn.clicked.connect(self._on_add_collider)
        action_bar.addWidget(add_col_btn)
        random_btn = QPushButton("Randomize Seed")
        random_btn.clicked.connect(self._on_randomize)
        action_bar.addWidget(random_btn)
        layout.addLayout(action_bar)
        self._graph_widget = _TerrainNodeGraphWidget(self)
        layout.addWidget(self._graph_widget)

    @property
    def _graph(self):
        return self._graph_widget._graph if self._graph_widget else None

    @property
    def _res_spin(self):
        return self._graph_widget._res_spin if self._graph_widget else None

    @property
    def _world_spin(self):
        return self._graph_widget._world_spin if self._graph_widget else None

    def set_collaboration_manager(self, mgr):
        if self._graph_widget:
            self._graph_widget.set_collaboration_manager(mgr)

    def set_live(self, enabled: bool):
        self._live = enabled
        if enabled and (self._terrain is not None or self._find_or_create_terrain()):
            self._on_generate()

    def load_graph(self, path: str):
        if self._graph_widget:
            self._graph_widget._open_graph(path)
        if self._live and (self._terrain is not None or self._find_or_create_terrain()):
            self._on_generate()

    def _find_or_create_terrain(self):
        if self._terrain is not None:
            return True
        if not self._engine or not self._engine.scene:
            return False
        scene = self._engine.scene
        for e in scene.get_all_entities():
            tc = e.get_component(Terrain)
            if tc is not None:
                self._entity = e
                self._terrain = tc
                Logger.info("TerrainGraph: auto-selected terrain entity '{}'".format(getattr(e, '_name', '?')))
                return True
        return False

    def _on_generate(self):
        if self._graph is None:
            Logger.info("TerrainGraph: no graph, skipping generate")
            return
        if self._terrain is None:
            if not self._find_or_create_terrain():
                Logger.info("TerrainGraph: no terrain component in scene, skipping generate")
                return
        nodes = self._graph.all_nodes()
        if not nodes:
            Logger.info("TerrainGraph: graph has no nodes")
            return
        from editor.terrain_graph.code_generator import generate_shader
        from editor.terrain_graph.gpu_runner import run_shader
        res = int(self._res_spin.value()) if self._res_spin else 512
        seed = random.randint(0, 100000)
        source, uniforms, height_scale = generate_shader(self._graph, res)
        if not source:
            Logger.warning("TerrainGraph: code generator returned empty (need Height Output node connected)")
            return
        hf = run_shader(source, res, uniforms)
        if hf is None:
            Logger.warning("TerrainGraph: GPU shader execution failed (check GLSL)")
            return
        Logger.info(f"TerrainGraph: generated {hf.shape[0]}x{hf.shape[1]} heightfield, hscale={height_scale:.1f}")
        self._apply_heightfield(hf, height_scale)

    def _apply_heightfield(self, hf, height_scale=1.0):
        if self._terrain is None:
            return
        ws = float(self._world_spin.value()) if self._world_spin else 1000.0
        self._terrain.world_size = ws
        from core.terrain.terrain_generator import get_generator
        mesh = get_generator().mesh_from_heightfield(hf, ws)
        if mesh is None:
            Logger.warning("TerrainGraph: mesh_from_heightfield returned None")
            return
        self._terrain.set_heightfield(hf, mesh)
        tc = self._entity.get_component(TerrainCollider) if self._entity else None
        if tc is not None:
            tc.set_height_data(hf)
            tc.resolution = hf.shape[0]
            tc.size = self._terrain_size_vec(height_scale)
            tc.height_scale = height_scale
        if self._engine and self._engine.scene:
            self._engine.scene._render_version += 1
        self._collab_sync_terrain()

    def _collab_sync_terrain(self):
        mgr = getattr(self._engine, "collab_manager", None)
        if not mgr or not mgr.connected or not self._entity or not self._terrain:
            return
        eid = self._entity.id
        data = {
            "world_size": self._terrain.world_size,
            "graph_path": self._graph_widget._graph_path if self._graph_widget else "",
        }
        mgr.send_component_sync(eid, "Terrain", data)
        tc = self._entity.get_component(TerrainCollider)
        if tc is not None:
            cd = tc.serialize()
            cd.pop("height_data", None)
            mgr.send_component_sync(eid, "TerrainCollider", cd)

    def _terrain_size_vec(self, height_scale=1.0):
        from core.maths.math3d import Vec3
        ws = float(self._world_spin.value()) if self._world_spin else 1000.0
        return Vec3(ws, height_scale, ws)

    def set_entity(self, entity: Optional[Entity]):
        self._entity = entity
        self._terrain = None
        if entity is None:
            return
        comp = entity.get_component(Terrain)
        self._terrain = comp

    def _on_create(self):
        entity = self._get_selected_entity()
        created_entity = False
        if entity is None:
            scene = self._engine.scene
            if not scene:
                return
            entity = scene.create_entity("Terrain")
            entity.add_component(Transform())
            created_entity = True
        if entity.get_component(Terrain) is None:
            terrain = Terrain()
            entity.add_component(terrain)
            self._terrain = terrain
        else:
            self._terrain = entity.get_component(Terrain)
        self.set_entity(entity)
        self._prompt_save_graph()
        self._collab_sync_create(entity, created_entity)
        if self._live:
            self._on_generate()

    def _collab_sync_create(self, entity, created_entity: bool):
        mgr = getattr(self._engine, "collab_manager", None)
        if not mgr or not mgr.connected:
            return
        if created_entity:
            mgr.send_entity_create(entity.serialize())
        else:
            terrain = entity.get_component(Terrain)
            if terrain is not None:
                data = terrain.serialize()
                data.pop("heightfield", None)
                mgr.send_component_add(entity.id, "Terrain", data)

    def _prompt_save_graph(self):
        if self._graph is None:
            return
        nodes = self._graph.all_nodes()
        if not nodes:
            return
        gw = self._graph_widget
        if gw._graph_path:
            gw._do_save(gw._graph_path)
        else:
            gw._save_graph_as()

    def _on_add_collider(self):
        entity = self._get_selected_entity()
        if entity is None and self._entity is not None:
            entity = self._entity
        if entity is None:
            return
        if entity.get_component(Terrain) is None:
            Logger.warning("Terrain Editor: select a terrain object first")
            return
        added_now = False
        if entity.get_component(TerrainCollider) is None:
            history = get_history()
            if history is not None:
                history.execute(AddComponentCommand(entity, TerrainCollider()))
            else:
                entity.add_component(TerrainCollider())
            added_now = True
        tc = entity.get_component(TerrainCollider)
        if tc is not None:
            hs = 1.0
            if self._terrain and self._terrain.heightfield is not None:
                hs = self._terrain.height_scale
            tc.size = self._terrain_size_vec(hs)
            tc.height_scale = hs
            tc.resolution = int(self._res_spin.value()) if self._res_spin else 256
            self._collab_sync_collider(entity, tc, added_now)

    def _collab_sync_collider(self, entity, tc, added_now: bool):
        mgr = getattr(self._engine, "collab_manager", None)
        if not mgr or not mgr.connected:
            return
        eid = entity.id
        if added_now:
            mgr.send_component_add(eid, "TerrainCollider", tc.serialize())
        else:
            cd = tc.serialize()
            cd.pop("height_data", None)
            mgr.send_component_sync(eid, "TerrainCollider", cd)

    def _on_randomize(self):
        if self._graph is None:
            return
        for n in self._graph.all_nodes():
            params = getattr(n, '_PARAMS', {})
            if 'seed' in params:
                n.seed = float(random.randint(0, 100000))
        if self._terrain is not None:
            self._on_generate()

    def _get_selected_entity(self) -> Optional[Entity]:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if not eng:
            return None
        vp = getattr(eng, 'viewport', None)
        if not vp:
            return None
        sel = getattr(vp, '_selected_entities', None)
        if sel and len(sel) > 0:
            return sel[0]
        return None
