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
import qtawesome as qta
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QMenu, QLineEdit, QLabel, QInputDialog, QAbstractItemView, QStyledItemDelegate, QApplication, QHeaderView)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData
from PyQt6.QtGui import QKeySequence, QAction, QDrag, QColor, QKeyEvent, QBrush, QPixmap, QIcon
from editor.inspector.helpersp import _flash_overlay
from core.config.editor_scale import scale, scale_xy
if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.engine.eng import Engine
class HierarchyMenuMixin:
    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        menu = QMenu(self)
        if item:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            entity = self._scene.get_entity(eid) if self._scene and eid else None
            if entity:
                rename_act = QAction("Rename\tF2", self)
                rename_act.triggered.connect(lambda: self._tree.editItem(item, 0))
                menu.addAction(rename_act)
                dup_act = QAction("Duplicate\tCtrl+D", self)
                dup_act.triggered.connect(lambda: self._duplicate_entity(entity))
                menu.addAction(dup_act)
                create_child_act = QAction("Create Child...", self)
                create_child_act.triggered.connect(lambda: self._show_add_dialog(entity))
                menu.addAction(create_child_act)
                child_menu = menu.addMenu("Create Child")
                self._add_create_menu_entries(child_menu, entity)
                menu.addSeparator()
                if entity.is_prefab_instance:
                    from core.ecs.prefabp import Prefab, PrefabLibrary
                    prefab_path = PrefabLibrary.path_for_guid(entity._prefab_guid)
                    apply_act = QAction("Apply", self)
                    apply_act.triggered.connect(lambda: self._apply_prefab(entity))
                    menu.addAction(apply_act)
                    revert_act = QAction("Revert", self)
                    revert_act.triggered.connect(lambda: self._revert_prefab(entity))
                    menu.addAction(revert_act)
                    if prefab_path:
                        select_act = QAction("Select Prefab Asset", self)
                        select_act.triggered.connect(
                            lambda: self._select_prefab_asset.emit(prefab_path))
                        menu.addAction(select_act)
                        open_edit_act = QAction("Open in Prefab Editor", self)
                        open_edit_act.triggered.connect(
                            lambda: self.open_prefab_editor.emit(prefab_path))
                        menu.addAction(open_edit_act)
                    unpack_act = QAction("Unpack", self)
                    unpack_act.triggered.connect(lambda: self._unpack_prefab(entity))
                    menu.addAction(unpack_act)
                    menu.addSeparator()
                set_active = QAction("Toggle Active", self)
                set_active.triggered.connect(lambda: self._toggle_active(entity))
                menu.addAction(set_active)
                lock_act = QAction("Toggle Lock", self)
                lock_act.setCheckable(True)
                lock_act.setChecked(entity.locked)
                lock_act.triggered.connect(lambda: self._toggle_lock(entity))
                menu.addAction(lock_act)
                embed_act = QAction("Embed Resources on Save", self)
                embed_act.setCheckable(True)
                embed_act.setChecked(entity.embed_resources)
                embed_act.triggered.connect(lambda checked=False, e=entity: self._toggle_embed(e, checked))
                menu.addAction(embed_act)
                menu.addSeparator()
                save_pref_act = QAction("Save as Prefab...", self)
                save_pref_act.triggered.connect(lambda: self._save_prefab(entity))
                menu.addAction(save_pref_act)
                menu.addSeparator()
                del_act = QAction("Delete", self)
                del_act.triggered.connect(lambda: self._delete_entity(entity))
                menu.addAction(del_act)
                menu.addSeparator()
                add_menu = menu.addMenu("Add Entity")
                self._add_create_menu_entries(add_menu, None)
                menu.addSeparator()
                add_child_dialog = QAction("Add Entity...", self)
                add_child_dialog.triggered.connect(lambda: self._show_add_dialog(None))
                menu.addAction(add_child_dialog)
        else:
            add_dialog_act = QAction("Add Entity...", self)
            add_dialog_act.triggered.connect(lambda: self._show_add_dialog(None))
            menu.addAction(add_dialog_act)
            self._add_create_menu_entries(menu, None)
        menu.exec(self._tree.mapToGlobal(pos))
    def _add_create_menu_entries(self, menu: QMenu, parent_entity=None):
        from editor.panels.add_entity_menu import populate_add_menu
        populate_add_menu(
            menu,
            on_system=lambda mp, p=parent_entity: self._create_system_prefab(mp, p),
            on_asset=lambda ap, p=parent_entity: self._create_prefab_asset(ap, p),
            on_search=lambda p=parent_entity: self._show_add_dialog(p),
        )
    def _show_add_dialog(self, parent_entity=None, pos=None):
        from editor.panels.add_entity_menu import AddEntityDialog
        title = "Add Entity"
        try:
            if parent_entity is not None:
                title = f"Add Child to '{parent_entity.name}'"
        except Exception:
            pass
        dlg = AddEntityDialog(self, title)
        if pos is not None:
            try:
                from PyQt6.QtWidgets import QApplication
                screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
                geo = screen.availableGeometry()
                x = min(max(pos.x(), geo.left()), max(geo.left(), geo.right() - dlg.width()))
                y = min(max(pos.y(), geo.top()), max(geo.top(), geo.bottom() - dlg.height()))
                dlg.move(x, y)
            except Exception:
                pass
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        if dlg.selected_menu_path:
            self._create_system_prefab(dlg.selected_menu_path, parent_entity)
        elif dlg.selected_asset_path:
            self._create_prefab_asset(dlg.selected_asset_path, parent_entity)
    def _show_create_menu(self):
        pos = None
        try:
            btn = self.sender() or self._add_btn
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
        except Exception:
            pos = None
        self._show_add_dialog(None, pos)
    def _collab_sync_create(self, entity):
        mgr = getattr(self._engine, "collab_manager", None)
        if mgr and mgr.connected:
            mgr.send_entity_create(entity.serialize())
    def _collab_sync_delete(self, entity_id: str):
        mgr = getattr(self._engine, "collab_manager", None)
        if mgr and mgr.connected:
            mgr.send_entity_delete(entity_id)
    def _finish_created_entities(self, entities, edit_first: bool = False):
        entities = [e for e in (entities or []) if e is not None]
        self._refresh()
        for e in entities:
            self._collab_sync_create(e)
        if entities:
            first = entities[0]
            self._selected_entity = first
            self.entity_selected.emit(first)
            item = self._find_item(first.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)
                if edit_first:
                    self._tree.editItem(item, 0)
        return entities
    def _create_system_prefab(self, menu_path: str, parent=None):
        if not self._scene:
            return []
        from core.foundation.cmd import CreateSystemPrefabCommand, get_history
        parent_id = parent.id if parent is not None else None
        cmd = CreateSystemPrefabCommand(self._scene, menu_path, parent_id)
        get_history().execute(cmd)
        entities = [self._scene.get_entity(eid) for eid in cmd._spawned_ids]
        entities = [e for e in entities if e]
        edit = str(menu_path).strip().lower() in ("create empty",)
        return self._finish_created_entities(entities, edit_first=edit)
    def _create_prefab_asset(self, asset_path: str, parent=None):
        if not self._scene:
            return []
        from core.ecs.prefabp import PrefabLibrary
        from core.foundation.cmd import InstantiatePrefabCommand, get_history
        prefab = PrefabLibrary.load(asset_path)
        if not prefab:
            return []
        parent_entity = parent
        cmd = InstantiatePrefabCommand(self._scene, prefab, self._engine._component_registry, parent_entity)
        get_history().execute(cmd)
        entities = [self._scene.get_entity(eid) for eid in cmd._spawned_ids]
        entities = [e for e in entities if e]
        return self._finish_created_entities(entities)
    def _create_entity(self):
        return self._create_system_prefab("Create Empty", None)
    def _create_child(self, parent: Entity):
        entities = self._create_system_prefab("Create Empty", parent)
        return entities[0] if entities else None
    def _create_primitive(self, mesh_name: str):
        lookup = {"cube": "3D Object/Cube", "sphere": "3D Object/Sphere", "plane": "3D Object/Plane"}
        menu_path = lookup.get(str(mesh_name).lower(), f"3D Object/{str(mesh_name).capitalize()}")
        return self._create_system_prefab(menu_path, None)
    def _create_probuilder_primitive(self, name: str):
        return self._create_system_prefab(f"3D Object/ProBuilder/{name}", None)
    def _create_light(self, ltype: str):
        lookup = {
            "sun": "Light/Sun",
            "directional": "Light/Directional Light",
            "point": "Light/Point Light",
            "spot": "Light/Spot Light",
            "area": "Light/Area Light",
        }
        return self._create_system_prefab(lookup.get(str(ltype).lower(), "Light/Point Light"), None)
    def _create_camera(self):
        return self._create_system_prefab("Camera", None)
    def _create_from_component(self, name: str, comp_cls_name: str, extra_setup=None):
        if not self._scene:
            return
        from core.prefabs.registry import get_system_prefabs
        for entry in get_system_prefabs():
            build_name = getattr(entry.build, "__name__", "") if entry.build else ""
            if build_name == "build_" + str(comp_cls_name):
                return self._create_system_prefab(entry.menu_path, None)
        from core.foundation.cmd import CreateEntityCommand, get_history
        from core.ecs import ComponentRegistry
        from core.components import Transform
        cls = ComponentRegistry.get(comp_cls_name)
        if not cls:
            return
        cmd = CreateEntityCommand(self._scene, name)
        get_history().execute(cmd)
        e = self._scene.get_entity(cmd._entity_id)
        if e:
            e.add_component(Transform())
            e.add_component(cls())
            if extra_setup:
                extra_setup(e)
        self._refresh()
        if e:
            self._collab_sync_create(e)
            self._selected_entity = e
            self.entity_selected.emit(e)
            item = self._find_item(e.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)
    def _save_prefab(self, entity: Entity):
        from PyQt6.QtWidgets import QFileDialog
        from core.ecs.prefabp import Prefab
        path, _ = QFileDialog.getSaveFileName(self, "Save Prefab", "prefabs/", "Prefabs (*.zpep)")
        if path:
            if not path.endswith(".zpep"):
                path += ".zpep"
            pref = Prefab(entity.name)
            pref.capture([entity])
            pref.save(path)
    def _apply_prefab(self, entity: Entity):
        from core.foundation.cmd import ApplyPrefabOverridesCommand, get_history
        from core.ecs.prefabp import Prefab
        roots = Prefab.get_prefab_roots([entity])
        get_history().execute(ApplyPrefabOverridesCommand(self._scene, roots))
        self._scene.mark_dirty()
        self._refresh()
    def _revert_prefab(self, entity: Entity):
        from core.foundation.cmd import RevertPrefabInstanceCommand, get_history
        from core.ecs.prefabp import Prefab
        roots = Prefab.get_prefab_roots([entity])
        cmd = RevertPrefabInstanceCommand(self._scene, roots)
        get_history().execute(cmd)
        self._scene.mark_dirty()
        self._refresh()
    def _unpack_prefab(self, entity: Entity):
        from core.foundation.cmd import UnpackPrefabCommand, get_history
        from core.ecs.prefabp import Prefab
        roots = Prefab.get_prefab_roots([entity])
        cmd = UnpackPrefabCommand(self._scene, roots)
        get_history().execute(cmd)
        self._scene.mark_dirty()
        self._refresh()
    def _on_history_changed(self, cmd=None):
        if self._scene is None:
            return
        rv = getattr(self._scene, '_render_version', -1)
        if rv == self._last_render_version:
            return
        now = time.perf_counter()
        if now - getattr(self, '_last_refresh_time', 0.0) >= 0.5:
            self._last_refresh_time = now
            self._refresh()
            return
        if getattr(self, '_hc_refresh_timer', None) is None:
            self._hc_refresh_timer = QTimer(self)
            self._hc_refresh_timer.setSingleShot(True)
            self._hc_refresh_timer.setInterval(60)
            self._hc_refresh_timer.timeout.connect(self._on_history_changed_debounced)
        self._hc_refresh_timer.start()
    def _on_history_changed_debounced(self):
        now = time.perf_counter()
        if now - getattr(self, '_last_refresh_time', 0.0) < 0.5:
            self._hc_refresh_timer.start()
            return
        self._last_refresh_time = now
        self._refresh()
    def _periodic_refresh(self):
        if not self._scene:
            return
        rv = getattr(self._scene, '_render_version', -1)
        if rv != self._last_render_version:
            self._last_render_version = rv
            if self._tree.state() != QTreeWidget.State.EditingState and not self._tree._drag_started and self._tree._press_item is None:
                now = time.perf_counter()
                if now - getattr(self, '_last_refresh_time', 0) < 0.5:
                    return
                self._last_refresh_time = now
                self._refresh()
        if self._tree.currentItem() is None and self._selected_entity:
            self._restore_selection(self._selected_entity.id)
