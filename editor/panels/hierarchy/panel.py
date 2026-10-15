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
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QMenu, QLineEdit, QLabel, QInputDialog, QAbstractItemView, QStyledItemDelegate, QApplication, QHeaderView)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData
from PyQt6.QtGui import QKeySequence, QAction, QDrag, QColor, QKeyEvent, QBrush, QPixmap, QIcon
from editor.inspector.helpersp import _flash_overlay
from core.config.editor_scale import scale, scale_xy
if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.engine.eng import Engine
from editor.panels.hierarchy.tree import _cached_icon, HierarchyTree
from editor.panels.hierarchy.dnd import HierarchyDndMixin
from editor.panels.hierarchy.menu import HierarchyMenuMixin
class HierarchyPanel(HierarchyDndMixin, HierarchyMenuMixin, QDockWidget):
    entity_selected = pyqtSignal(object)
    entities_selected = pyqtSignal(list)
    entity_double_clicked = pyqtSignal(str)
    select_prefab_asset = pyqtSignal(str)
    open_prefab_editor = pyqtSignal(str)
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Hierarchy", parent)
        self._engine = engine
        self._scene: Optional[Scene] = None
        self._selected_entity: Optional[Entity] = None
        self._editing_item: Optional[QTreeWidgetItem] = None
        self._last_render_version: int = -1
        self._setup_ui()
        engine.on("scene_loaded", self._on_scene_loaded)
        engine.on("scene_saved", lambda _: self._refresh())
        engine.on("history_changed", lambda _: self._on_history_changed())
    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 2)
        toolbar.setSpacing(2)
        add_btn = QPushButton(qta.icon("fa5s.plus", color=QColor(255, 255, 255)), "")
        add_btn.setFixedSize(*scale_xy(24, 24))
        add_btn.setToolTip("Create Entity")
        add_btn.setStyleSheet("QPushButton { background: rgb(46, 125, 50); }")
        add_btn.clicked.connect(self._show_create_menu)
        toolbar.addWidget(add_btn)
        self._add_btn = add_btn
        self._search = QLineEdit()
        self._search.setPlaceholderText("  All")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        self._search.addAction(qta.icon("fa5s.search", color=QColor(212, 212, 212)), QLineEdit.ActionPosition.LeadingPosition)
        toolbar.addWidget(self._search, 1)
        collapse_btn = QPushButton(qta.icon("fa5s.chevron-up", color=QColor(212, 212, 212)), "")
        collapse_btn.setFixedSize(*scale_xy(24, 24))
        collapse_btn.setToolTip("Collapse All")
        collapse_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(collapse_btn)
        self._embed_all_btn = QPushButton(qta.icon("fa5s.archive", color=QColor(212, 212, 212)), "")
        self._embed_all_btn.setCheckable(True)
        self._embed_all_btn.setFixedSize(*scale_xy(24, 24))
        self._embed_all_btn.setToolTip("Embed all entity resources into the scene file")
        self._embed_all_btn.clicked.connect(self._toggle_embed_all)
        toolbar.addWidget(self._embed_all_btn)
        self._compress_btn = QPushButton(qta.icon("fa5s.file-archive", color=QColor(212, 212, 212)), "")
        self._compress_btn.setCheckable(True)
        self._compress_btn.setFixedSize(*scale_xy(24, 24))
        self._compress_btn.setToolTip("Compress embedded resources")
        self._compress_btn.toggled.connect(self._toggle_compress)
        toolbar.addWidget(self._compress_btn)
        layout.addLayout(toolbar)

        self._scene_header = QWidget()
        header_layout = QHBoxLayout(self._scene_header)
        header_layout.setContentsMargins(8, 0, 8, 2)
        header_layout.setSpacing(4)
        self._scene_icon = QLabel()
        icon_path = os.path.join(os.path.dirname(__file__), '..', '..', 'zarin_icon.svg')
        icon_pix = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._scene_icon.setPixmap(icon_pix)
        header_layout.addWidget(self._scene_icon)
        self._scene_label = QLabel()
        header_layout.addWidget(self._scene_label)
        header_layout.addStretch()
        self._update_scene_header()
        layout.addWidget(self._scene_header)

        self._tree = HierarchyTree(self)
        self._tree.setHeaderLabels(["Name", "Save"])
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(1, scale(30))
        header.setStretchLastSection(False)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_click)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.entity_reparented.connect(self._on_reparent)
        self._tree.component_drop_requested.connect(self._on_component_drop)
        self._tree.delete_requested.connect(self._delete_entities_by_ids)
        self._tree.copy_requested.connect(self._on_copy)
        self._tree.paste_requested.connect(self._on_paste)
        layout.addWidget(self._tree)
        self.setWidget(w)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._periodic_refresh)
        self._refresh_timer.start(2000)
    def load_config(self, config) -> None:
        refresh_interval = config.get("hierarchy.refresh_interval", 2000)
        self._refresh_timer.setInterval(refresh_interval)
    def _update_scene_header(self):
        if self._scene:
            self._scene_label.setText(getattr(self._scene, 'name', 'Scene'))
        else:
            self._scene_label.setText("No Scene")
    def _on_scene_loaded(self, scene: Scene):
        self._scene = scene
        self._selected_entity = None
        self._last_render_version = -1
        self._embed_all_btn.setChecked(bool(getattr(scene, 'embed_all', False)))
        self._compress_btn.setChecked(bool(getattr(scene, 'compress_resources', False)))
        self._update_scene_header()
        self._refresh()
    def _refresh(self):
        if not self._scene:
            self._tree.clear()
            self._selected_entity = None
            return
        self._last_render_version = getattr(self._scene, "_render_version", -1)
        try:
            has_items = self._tree.topLevelItemCount() > 0
        except Exception:
            has_items = True
        old_expanded: set = set()
        if has_items:
            try:
                old_expanded = self._get_expanded_ids()
            except Exception:
                old_expanded = set()
        old_selection = self._selected_entity.id if self._selected_entity else None
        self._tree.blockSignals(True)
        try:
            self._tree.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            try:
                self._tree.setUniformRowHeights(True)
            except Exception:
                pass
            self._tree.clear()
            filter_text = self._search.text().strip().lower()
            root_entities = self._scene.get_root_entities()
            live_ids = set(self._scene._entities.keys())
            prefab_index: dict = {}
            override_cache: dict = {}
            try:
                from core.ecs.prefabp import Prefab as _Prefab
                from core.ecs.prefabp import PrefabLibrary as _PrefabLib
                guids: set = set()
                for e in self._scene._entities.values():
                    g = getattr(e, "_prefab_guid", None)
                    if g:
                        guids.add(g)
                for g in guids:
                    try:
                        ppath = _PrefabLib.path_for_guid(g)
                        if not ppath:
                            continue
                        prefab = _PrefabLib.load(ppath)
                        if prefab is None:
                            continue
                        flat: dict = {}
                        stack = list(getattr(prefab, "roots_data", []) or [])
                        while stack:
                            item = stack.pop()
                            try:
                                sid = item.get("source_id") or item.get("id")
                                if sid and sid not in flat:
                                    flat[sid] = item
                                kids = item.get("children") or []
                                if kids:
                                    stack.extend(kids)
                            except Exception:
                                continue
                        prefab_index[g] = flat
                    except Exception:
                        continue
            except Exception:
                prefab_index = {}
            system_roots = [e for e in root_entities if e.system]
            normal_roots = [e for e in root_entities if not e.system]
            root_item = self._tree.invisibleRootItem()
            for entity in normal_roots:
                if entity.id not in live_ids:
                    continue
                self._add_entity_item(entity, root_item, filter_text, live_ids, prefab_index, override_cache)
            if system_roots:
                sys_item = QTreeWidgetItem(root_item)
                sys_item.setText(0, "System")
                sys_item.setFlags(sys_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                sys_item.setExpanded(True)
                for entity in system_roots:
                    if entity.id not in live_ids:
                        continue
                    self._add_entity_item(entity, sys_item, filter_text, live_ids, prefab_index, override_cache)
            if old_expanded:
                self._restore_expanded(old_expanded)
            if old_selection and old_selection in live_ids:
                self._restore_selection(old_selection)
            else:
                self._selected_entity = None
        finally:
            try:
                self._tree.setUpdatesEnabled(True)
            except Exception:
                pass
            self._tree.blockSignals(False)
    def _prefab_mark(self, entity: Entity, prefab_index: dict, override_cache: dict) -> str:
        try:
            if not getattr(entity, "_prefab_guid", None):
                return ""
            eid = getattr(entity, "_id", None) or entity.id
            hit = override_cache.get(eid)
            if hit is not None:
                return " *" if hit else ""
            guid = entity._prefab_guid
            src = entity._prefab_source_id
            flat = prefab_index.get(guid)
            if flat is None:
                from core.ecs.prefabp import Prefab
                try:
                    has = bool(Prefab.compute_overrides(entity))
                except Exception:
                    has = False
                override_cache[eid] = has
                return " *" if has else ""
            pdata = flat.get(src) if src else None
            if pdata is None:
                override_cache[eid] = False
                return ""
            from core.ecs.prefabp import Prefab as _P
            try:
                current = entity.serialize()
                is_root = _P._is_root_of_instance(entity)
                has = bool(_P._diff_entity(current, pdata, entity, is_root))
            except Exception:
                has = False
            override_cache[eid] = has
            return " *" if has else ""
        except Exception:
            return ""
    def _add_entity_item(self, entity: Entity, parent_item, filter_text: str, live_ids: set, prefab_index: dict | None = None, override_cache: dict | None = None) -> bool:
        base_name = entity.name
        if entity.is_prefab_instance:
            if prefab_index is None:
                prefab_index = {}
            if override_cache is None:
                override_cache = {}
            name = f"{base_name}{self._prefab_mark(entity, prefab_index, override_cache)}"
        else:
            name = base_name
        if not filter_text:
            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setData(0, Qt.ItemDataRole.UserRole, entity.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
            try:
                item.setCheckState(1, Qt.CheckState.Checked if entity.embed_resources else Qt.CheckState.Unchecked)
            except Exception:
                pass
            item.setToolTip(1, "Embed entity resources into the scene file on save")
            icon_cls = None
            if len(entity._components) > 1:
                for c in entity._components.values():
                    tc = type(c)
                    if getattr(tc, "_show_gizmo_icon", True) and tc.__name__ != "Transform":
                        icon_cls = tc
                        break
            if icon_cls is not None:
                try:
                    icon = _cached_icon(icon_cls)
                    if icon is not None:
                        item.setIcon(0, icon)
                except Exception:
                    pass
            if entity.is_prefab_instance:
                item.setForeground(0, QBrush(QColor(136, 204, 255)))
            if not entity.active:
                try:
                    gray = self._tree.palette().color(self._tree.palette().ColorRole.PlaceholderText)
                    item.setForeground(0, QBrush(gray))
                except Exception:
                    pass
            for child in entity.children:
                if child.id not in live_ids:
                    continue
                self._add_entity_item(child, item, filter_text, live_ids, prefab_index, override_cache)
            item.setExpanded(True)
            return True
        children = [c for c in entity.children if c.id in live_ids]
        has_visible_child = any(self._entity_matches_filter(c, filter_text, live_ids) for c in children)
        matches_filter = (filter_text in name.lower()) or has_visible_child
        if not matches_filter:
            return False
        item = QTreeWidgetItem(parent_item)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, entity.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(1, Qt.CheckState.Checked if entity.embed_resources else Qt.CheckState.Unchecked)
        item.setToolTip(1, "Embed entity resources into the scene file on save")
        icon_cls = None
        if len(entity._components) > 1:
            for c in entity._components.values():
                tc = type(c)
                if getattr(tc, "_show_gizmo_icon", True) and tc.__name__ != "Transform":
                    icon_cls = tc
                    break
        if icon_cls is not None:
            try:
                icon = _cached_icon(icon_cls)
                if icon is not None:
                    item.setIcon(0, icon)
            except Exception:
                pass
        if entity.is_prefab_instance:
            item.setForeground(0, QBrush(QColor(136, 204, 255)))
        if not entity.active:
            gray = self._tree.palette().color(self._tree.palette().ColorRole.PlaceholderText)
            item.setForeground(0, QBrush(gray))
        child_filter = "" if has_visible_child else filter_text
        for child in children:
            self._add_entity_item(child, item, child_filter, live_ids, prefab_index, override_cache)
        item.setExpanded(True)
        return True
    def _entity_matches_filter(self, entity: Entity, filter_text: str, live_ids: set = None) -> bool:
        if live_ids is not None and entity.id not in live_ids:
            return False
        if not filter_text:
            return True
        if filter_text in entity.name.lower():
            return True
        children = entity.children if live_ids is None else [c for c in entity.children if c.id in live_ids]
        return any(self._entity_matches_filter(c, filter_text, live_ids) for c in children)
    def _get_expanded_ids(self) -> set:
        expanded = set()
        self._collect_expanded(self._tree.invisibleRootItem(), expanded)
        return expanded
    def _collect_expanded(self, parent_item, expanded: set):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.isExpanded():
                eid = child.data(0, Qt.ItemDataRole.UserRole)
                if eid:
                    expanded.add(eid)
            self._collect_expanded(child, expanded)
    def _restore_expanded(self, expanded: set):
        self._restore_expanded_items(self._tree.invisibleRootItem(), expanded)
    def _restore_expanded_items(self, parent_item, expanded: set):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            eid = child.data(0, Qt.ItemDataRole.UserRole)
            if eid and eid in expanded:
                child.setExpanded(True)
            self._restore_expanded_items(child, expanded)
    def _on_item_double_click(self, item: QTreeWidgetItem, col: int):
        eid = item.data(0, Qt.ItemDataRole.UserRole)
        if self._scene and eid:
            self.entity_double_clicked.emit(eid)
    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        eid = item.data(0, Qt.ItemDataRole.UserRole)
        if not self._scene or not eid:
            return
        entity = self._scene.get_entity(eid)
        if not entity:
            return
        if col == 1:
            checked = item.checkState(1) == Qt.CheckState.Checked
            if entity.embed_resources != checked:
                entity.embed_resources = checked
                self._scene.mark_dirty()
            return
        new_name = item.text(0)
        if entity.name != new_name:
            entity.name = new_name
            self._scene.mark_dirty()
    def _on_search(self, text: str):
        self._refresh()
    def _collapse_all(self):
        def collapse_items(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                child.setExpanded(False)
                collapse_items(child)
        collapse_items(self._tree.invisibleRootItem())
    def _toggle_embed_all(self, checked: bool):
        if not self._scene:
            return
        self._scene.embed_all = checked
        self._scene.mark_dirty()
        self._refresh()
    def _toggle_compress(self, checked: bool):
        if not self._scene:
            return
        self._scene.compress_resources = checked
        self._scene.mark_dirty()
        self._refresh()
    def refresh(self):
        self._refresh()
    @staticmethod
    def _flash_item(item: QTreeWidgetItem):
        try:
            tree = item.treeWidget()
            if not tree:
                return
            _flash_overlay(tree.viewport(), tree.visualItemRect(item))
        except RuntimeError:
            pass
