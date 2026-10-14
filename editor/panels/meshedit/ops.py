# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from core.components.mesh_editor import (ProBuilderMesh, SelectionMode, create_primitive,
    extrude_faces, bevel_edges, subdivide_faces, weld_vertices,
    flip_normals, collapse_edges, bridge_edges, smart_optimize)
from core.components.rendering.renderers.mesh_filter import MeshFilter
from core.components.rendering.renderers.mesh_renderer import MeshRenderer
from core.foundation.logger import Logger
from editor.panels.meshedit.widgets import _STYLE_BTN, _STYLE_BTN_ACCENT
if TYPE_CHECKING:
    from core.ecs import Entity


class _MeshOpsMixin:
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

    def _on_create_primitive(self):
        name = self._primitive_combo.currentText()
        size_norm = self._size_slider.value() / 50.0
        detail_norm = max(4, self._detail_slider.value() * 32 // 50)
        entity = self._get_selected_entity()
        if entity is None:
            from core.ecs import Entity as EcsEntity
            scene = self._engine.scene
            if not scene:
                return
            entity = scene.create_entity(f"{name}")
            from core.components.transform.tr import Transform
            entity.add_component(Transform())
        pb: ProBuilderMesh = entity.get_component(ProBuilderMesh)
        if pb is None:
            pb = ProBuilderMesh()
            entity.add_component(pb)
        if name == "Box":
            s = size_norm * 0.5
            positions, indices = create_primitive(name, width=s, height=s, depth=s)
        elif name == "Sphere":
            positions, indices = create_primitive(name, radius=size_norm * 0.5, segments=detail_norm)
        elif name == "Cylinder":
            positions, indices = create_primitive(name, radius=size_norm * 0.25, height=size_norm * 0.5, segments=detail_norm)
        elif name == "Plane":
            positions, indices = create_primitive(name, width=size_norm, depth=size_norm)
        elif name == "Torus":
            positions, indices = create_primitive(name, major_radius=size_norm * 0.3, minor_radius=size_norm * 0.08,
                                                   major_segments=detail_norm, minor_segments=max(6, detail_norm // 2))
        elif name == "Cone":
            positions, indices = create_primitive(name, radius=size_norm * 0.25, height=size_norm * 0.5, segments=detail_norm)
        elif name == "Pipe":
            positions, indices = create_primitive(name, radius=size_norm * 0.3, thickness=size_norm * 0.06,
                                                   height=size_norm * 0.5, segments=detail_norm)
        elif name == "Stairs":
            positions, indices = create_primitive(name, width=size_norm * 0.8, height=size_norm * 0.5,
                                                   depth=size_norm, steps=max(2, detail_norm))
        else:
            positions, indices = create_primitive(name)
        pb.set_mesh_data(positions, indices)
        pb._gpu_dirty = True
        mf = entity.get_component(MeshFilter)
        if mf is None:
            mf = MeshFilter()
            entity.add_component(mf)
            mr = MeshRenderer()
            entity.add_component(mr)
        mf.mesh_name = f"ProBuilder_{entity.id[:6]}"
        mf.mesh_path = ""
        mr.materials[0]["path"] = "assets/materials/ProBuilderPrototype.mat"
        self._mesh_comp = pb
        self._update_info()
        if self._engine.scene:
            self._engine.scene._render_version += 1

    def _set_sel_mode(self, mode: SelectionMode):
        if self._mesh_comp is None:
            return
        self._mesh_comp.selection_mode = mode
        self._mesh_comp.clear_selection()
        self._update_sel_buttons()

    def _update_sel_buttons(self):
        if self._mesh_comp is None:
            return
        mode = self._mesh_comp.selection_mode
        for btn, m in [(self._sel_obj, SelectionMode.OBJECT),
                        (self._sel_vert, SelectionMode.VERTEX),
                        (self._sel_edge, SelectionMode.EDGE),
                        (self._sel_face, SelectionMode.FACE)]:
            if m == mode:
                btn.setStyleSheet(_STYLE_BTN_ACCENT)
            else:
                btn.setStyleSheet(_STYLE_BTN)

    def _update_info(self):
        if self._mesh_comp is None:
            self._vert_label.setText("Verts: 0")
            self._tri_label.setText("Tris: 0")
            self._edge_label.setText("Edges: 0")
            return
        self._vert_label.setText(f"Verts: {self._mesh_comp.vertex_count}")
        self._tri_label.setText(f"Tris: {self._mesh_comp.triangle_count}")
        self._edge_label.setText(f"Edges: {self._mesh_comp.edge_count}")
        self._smooth_angle.setValue(int(self._mesh_comp.smooth_angle))
        self._smooth_label.setText(str(int(self._mesh_comp.smooth_angle)))

    def _on_extrude(self):
        if self._mesh_comp is None:
            return
        if self._mesh_comp.selection_mode != SelectionMode.FACE or not self._mesh_comp.selected_faces:
            Logger.warning("Mesh Editor: Select faces in Face mode to extrude")
            return
        dist = self._extrude_dist.value()
        extrude_faces(self._mesh_comp, self._mesh_comp.selected_faces, dist)
        self._sync_to_renderer()
        self._update_info()

    def _on_bevel(self):
        if self._mesh_comp is None:
            return
        if self._mesh_comp.selection_mode != SelectionMode.EDGE or not self._mesh_comp.selected_edges:
            Logger.warning("Mesh Editor: Select edges in Edge mode to bevel")
            return
        amount = self._bevel_amount.value()
        bevel_edges(self._mesh_comp, self._mesh_comp.selected_edges, amount)
        self._sync_to_renderer()
        self._update_info()

    def _on_subdivide(self):
        if self._mesh_comp is None:
            return
        faces = self._mesh_comp.selected_faces if self._mesh_comp.selection_mode == SelectionMode.FACE and self._mesh_comp.selected_faces else None
        if faces is None:
            faces = set(range(self._mesh_comp.triangle_count))
        subdivide_faces(self._mesh_comp, faces)
        self._sync_to_renderer()
        self._update_info()

    def _on_weld(self):
        if self._mesh_comp is None:
            return
        thresh = self._weld_thresh.value()
        weld_vertices(self._mesh_comp, thresh)
        self._sync_to_renderer()
        self._update_info()

    def _on_flip(self):
        if self._mesh_comp is None:
            return
        faces = self._mesh_comp.selected_faces if self._mesh_comp.selection_mode == SelectionMode.FACE and self._mesh_comp.selected_faces else None
        flip_normals(self._mesh_comp, faces)
        self._sync_to_renderer()
        self._update_info()

    def _on_collapse(self):
        if self._mesh_comp is None:
            return
        if self._mesh_comp.selection_mode != SelectionMode.EDGE or not self._mesh_comp.selected_edges:
            Logger.warning("Mesh Editor: Select edges in Edge mode to collapse")
            return
        collapse_edges(self._mesh_comp, self._mesh_comp.selected_edges)
        self._sync_to_renderer()
        self._update_info()

    def _on_bridge(self):
        if self._mesh_comp is None:
            return
        if self._mesh_comp.selection_mode != SelectionMode.EDGE or len(self._mesh_comp.selected_edges) < 2:
            Logger.warning("Mesh Editor: Select at least 2 edges in Edge mode to bridge")
            return
        edges = sorted(self._mesh_comp.selected_edges, key=lambda x: (x[0], x[1]))
        bridge_edges(self._mesh_comp, edges[0], edges[1])
        self._sync_to_renderer()
        self._update_info()

    def _on_optimize(self):
        if self._mesh_comp is None:
            return
        smart_optimize(self._mesh_comp)
        self._sync_to_renderer()
        self._update_info()

    def _on_center_pivot(self):
        if self._mesh_comp is None:
            return
        pos = self._mesh_comp.positions
        if pos.size == 0:
            return
        center = pos.mean(axis=0)
        pos[:] = pos - center
        self._mesh_comp.rebuild_normals()
        self._sync_to_renderer()
        self._update_info()
        self._mesh_comp.rebuild_normals()
        self._sync_to_renderer()

    def _on_clear_selection(self):
        if self._mesh_comp is None:
            return
        self._mesh_comp.clear_selection()

    def _on_smooth_changed(self, val: int):
        if self._mesh_comp is None or self._updating:
            return
        self._smooth_label.setText(str(val))
        self._mesh_comp.smooth_angle = float(val)
        self._mesh_comp.rebuild_normals()
        self._sync_to_renderer()

    def _sync_to_renderer(self):
        if self._mesh_comp is None:
            return
        self._mesh_comp._gpu_dirty = True
        if self._engine and self._engine.scene:
            self._engine.scene._render_version += 1
