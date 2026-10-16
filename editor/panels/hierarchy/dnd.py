# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
import time
import os
from typing import Optional, TYPE_CHECKING
import editor.icons as qta
from PySide6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QMenu, QLineEdit, QLabel, QInputDialog, QAbstractItemView, QStyledItemDelegate, QApplication, QHeaderView)
from PySide6.QtCore import Qt, Signal, QTimer, QMimeData
from PySide6.QtGui import QKeySequence, QAction, QDrag, QColor, QKeyEvent, QBrush, QPixmap, QIcon
from editor.inspector.helpersp import _flash_overlay
from core.config.editor_scale import scale, scale_xy
if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.engine.eng import Engine
class HierarchyDndMixin:
    def _on_reparent(self, dragged_eid: str, target_eid: Optional[str]):
        if not self._scene:
            return
        dragged = self._scene.get_entity(dragged_eid)
        if not dragged:
            return
        if target_eid is not None:
            target = self._scene.get_entity(target_eid)
            if not target:
                return
            if dragged == target:
                return
            if self._is_ancestor(dragged, target):
                return
            dragged.set_parent(target)
        else:
            dragged.set_parent(None)
        self._scene.mark_dirty()
        self._refresh()
        if self._selected_entity:
            self._restore_selection(self._selected_entity.id)
    def _on_component_drop(self, target_eid: str, data: dict, is_copy: bool):
        if not self._scene:
            return
        target_entity = self._scene.get_entity(target_eid)
        if not target_entity:
            return
        source_entity = self._scene.get_entity(data.get("entity_id", ""))
        if not source_entity:
            return
        if not is_copy and source_entity == target_entity:
            return
        comp_type_name = data.get("component_type", "")
        component_key = data.get("component_key", "")
        comp_data = data.get("component_data", {})
        if not comp_type_name or not comp_data:
            return
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(comp_type_name)
        if not cls:
            return
        can_multiple = getattr(cls, '_allow_multiple', False)
        from core.foundation.cmd import MoveComponentCommand, CopyComponentCommand, CompoundCommand, get_history
        if is_copy:
            eid_set = {target_eid}
            for item in self._tree.selectedItems():
                eid = item.data(0, Qt.ItemDataRole.UserRole)
                if eid:
                    eid_set.add(eid)
            targets = []
            for eid in eid_set:
                e = self._scene.get_entity(eid)
                if e and e != source_entity:
                    if not can_multiple and e.has_component(cls):
                        continue
                    targets.append(e)
            if not targets:
                return
            cmds = [CopyComponentCommand(e, cls, comp_data, source_key=component_key) for e in targets]
            get_history().execute(CompoundCommand(cmds, f"Copy {comp_type_name} to {len(targets)} entities"))
        else:
            if not can_multiple and target_entity.has_component(cls):
                return
            get_history().execute(MoveComponentCommand(source_entity, target_entity, component_key, cls, comp_data))
        self._scene.mark_dirty()
        self.refresh()
        mw = self.parent()
        inspector = getattr(mw, '_inspector', None)
        if inspector:
            inspector._rebuild()
    def _is_ancestor(self, potential_ancestor: Entity, entity: Entity) -> bool:
        current = entity.parent
        while current:
            if current == potential_ancestor:
                return True
            current = current.parent
        return False
    def _on_copy(self):
        if not self._scene:
            return
        items = self._tree.selectedItems()
        if not items:
            return
        import copy
        selected = []
        for item in items:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            if eid:
                e = self._scene.get_entity(eid)
                if e:
                    selected.append(e)
        if not selected:
            return
        seen = set()
        to_serialize = []
        for e in selected:
            if e.id in seen:
                continue
            stack = [(e, True)]
            while stack:
                current, is_top = stack.pop()
                if current.id in seen:
                    continue
                seen.add(current.id)
                to_serialize.append((current, is_top))
                for child in current.children:
                    stack.append((child, False))
        clipboard = []
        for e, is_top in to_serialize:
            data = e.serialize()
            if is_top:
                data["parent"] = None
            if is_top:
                t = e.transform
                if t:
                    world_pos, world_rot, world_scale = t.world_matrix.decompose()
                    for comp_data in data.get("components", []):
                        if comp_data.get("_key") == "Transform":
                            comp_data["local_position"] = world_pos.to_list()
                            comp_data["local_rotation"] = world_rot.to_list()
                            comp_data["local_scale"] = world_scale.to_list()
                            break
            clipboard.append(data)
        mw = self.parent()
        viewport = getattr(mw, '_viewport', None)
        if viewport:
            viewport._entity_clipboard = clipboard
    def _on_paste(self):
        mw = self.parent()
        viewport = getattr(mw, '_viewport', None)
        if viewport:
            viewport._paste_entities()
    def _duplicate_entity(self, entity: Entity):
        if not self._scene:
            return
        new_e = self._scene.duplicate_entity(entity)
        self._collab_sync_create(new_e)
        self._refresh()
        self._selected_entity = new_e
        self.entity_selected.emit(new_e)
        item = self._find_item(new_e.id, self._tree.invisibleRootItem())
        if item:
            self._tree.setCurrentItem(item)
    def _delete_entity(self, entity: Entity):
        if not self._scene:
            return
        if entity.locked or entity.system:
            return
        from core.foundation.cmd import DeleteEntityCommand, get_history
        was_selected = (self._selected_entity == entity)
        self._collab_sync_delete(entity.id)
        cmd = DeleteEntityCommand(self._scene, entity.id)
        get_history().execute(cmd)
        if was_selected:
            self._selected_entity = None
            self.entity_selected.emit(None)
        self._refresh()
    def _delete_entities_by_ids(self, eids: list):
        if not self._scene:
            return
        for eid in eids:
            entity = self._scene.get_entity(eid)
            if entity:
                self._delete_entity(entity)
    def _delete_entity_by_id(self, eid: str):
        if not self._scene:
            return
        entity = self._scene.get_entity(eid)
        if entity:
            self._delete_entity(entity)
    def _toggle_active(self, entity: Entity):
        entity.active = not entity.active
        if self._scene:
            self._scene.mark_dirty()
        self._refresh()
        if self._selected_entity:
            self._restore_selection(self._selected_entity.id)
    def _toggle_lock(self, entity: Entity):
        entity.locked = not entity.locked
        if self._scene:
            self._scene.mark_dirty()
        self._refresh()
        if self._selected_entity:
            self._restore_selection(self._selected_entity.id)
    def _toggle_embed(self, entity: Entity, checked: bool):
        entity.embed_resources = checked
        if self._scene:
            self._scene.mark_dirty()
        self._refresh()
        if self._selected_entity:
            self._restore_selection(self._selected_entity.id)
    def _toggle_active_by_ids(self, eids: list):
        if not self._scene:
            return
        changed = False
        for eid in eids:
            entity = self._scene.get_entity(eid)
            if entity:
                entity.active = not entity.active
                changed = True
        if changed:
            self._scene.mark_dirty()
            self._refresh()
    def _toggle_active_selected(self):
        items = self._tree.selectedItems()
        if not items or not self._scene:
            return
        eids = []
        for item in items:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            if eid:
                eids.append(eid)
        self._toggle_active_by_ids(eids)
    def _find_item(self, eid: str, parent_item) -> Optional[QTreeWidgetItem]:
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == eid:
                return child
            found = self._find_item(eid, child)
            if found:
                return found
        return None
    def _restore_selection(self, eid: str):
        item = self._find_item(eid, self._tree.invisibleRootItem())
        if item:
            self._tree.setCurrentItem(item)
    def _frame_selected(self):
        try:
            ent = self._selected_entity
            if ent is None:
                items = self._tree.selectedItems()
                if items:
                    eid = items[0].data(0, Qt.ItemDataRole.UserRole)
                    if eid and self._scene:
                        ent = self._scene.get_entity(eid)
            if ent is None:
                return
            vp = getattr(self._engine, 'viewport', None)
            if vp is None or getattr(vp, '_cam', None) is None:
                return
            t = ent.transform
            if t is None:
                return
            try:
                from editor.entframe import compute_entity_frame
                renderer = getattr(vp, '_renderer', None)
                if renderer is None:
                    try:
                        renderer = vp.renderer
                    except Exception:
                        renderer = None
                center, radius = compute_entity_frame(ent, renderer)
                vp._cam.frame_bounds(center, radius)
            except Exception:
                try:
                    vp._cam.frame_bounds(t.position)
                except Exception:
                    pass
        except Exception:
            pass
    def _on_selection_changed(self):
        items = self._tree.selectedItems()
        if not items or not self._scene:
            if self._selected_entity:
                self._selected_entity = None
                self.entity_selected.emit(None)
            return
        if len(items) == 1:
            eid = items[0].data(0, Qt.ItemDataRole.UserRole)
            if not eid:
                return
            entity = self._scene.get_entity(eid)
            if entity and entity != self._selected_entity:
                self._selected_entity = entity
                self.entity_selected.emit(entity)
        else:
            entities = []
            for item in items:
                eid = item.data(0, Qt.ItemDataRole.UserRole)
                if eid:
                    entity = self._scene.get_entity(eid)
                    if entity:
                        entities.append(entity)
            if entities:
                self._selected_entity = entities[0]
                self.entities_selected.emit(entities)
    def set_selected_entity(self, entity: Optional[Entity]):
        self._tree.blockSignals(True)
        self._selected_entity = entity
        if entity:
            self._restore_selection(entity.id)
        else:
            self._tree.clearSelection()
        self._tree.blockSignals(False)
    def set_selected_entities(self, entities: list):
        self._tree.blockSignals(True)
        self._tree.clearSelection()
        if entities:
            pending = set()
            for entity in entities:
                if entity is not None:
                    try:
                        pending.add(entity.id)
                    except Exception:
                        pass
            if pending:
                stack = [self._tree.invisibleRootItem()]
                while stack and pending:
                    parent = stack.pop()
                    n = parent.childCount()
                    for i in range(n):
                        child = parent.child(i)
                        try:
                            eid = child.data(0, Qt.ItemDataRole.UserRole)
                        except Exception:
                            eid = None
                        if eid and eid in pending:
                            child.setSelected(True)
                            pending.discard(eid)
                            if not pending:
                                break
                        if child.childCount() > 0:
                            stack.append(child)
                    if not pending:
                        break
        self._tree.blockSignals(False)
        if entities:
            self._selected_entity = entities[0]
    def reveal_entity(self, eid: str):
        entity = self._scene.get_entity(eid) if self._scene else None
        if not entity:
            return
        self._tree.blockSignals(True)
        self._selected_entity = entity
        item = self._find_item(eid, self._tree.invisibleRootItem())
        if item:
            self._tree.setCurrentItem(item)
        self._tree.blockSignals(False)
        if item:
            self._tree.scrollToItem(item)
            self._flash_item(item)
        self.entity_selected.emit(entity)
    def flash_entity(self, eid: str):
        item = self._find_item(eid, self._tree.invisibleRootItem())
        if item:
            self._tree.scrollToItem(item)
            self._flash_item(item)
