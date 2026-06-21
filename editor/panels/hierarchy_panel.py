from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                              QTreeWidget, QTreeWidgetItem, QPushButton,
                              QMenu, QLineEdit, QLabel, QInputDialog, QAbstractItemView,
                              QStyledItemDelegate, QStyle, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData
from PyQt6.QtGui import QAction, QDrag, QColor, QKeyEvent, QBrush, QPixmap, QIcon
if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.engine import Engine
_ENTITY_MIME = "application/x-zpe-entity"

import os
def _get_component_icon_pixmap(cls, size: int = 16) -> QPixmap:
    icon_name = getattr(cls, '_icon', None)
    if icon_name:
        icons_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'core', 'components', 'icons')
        icon_path = os.path.join(icons_dir, icon_name)
        if os.path.exists(icon_path):
            return QPixmap(icon_path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    gizmo_dir = os.path.join(os.path.dirname(__file__), '..', 'gizmo_icons')
    icon_path = os.path.join(gizmo_dir, f'{cls.__name__}.png')
    if os.path.exists(icon_path):
        return QPixmap(icon_path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    r, g, b = getattr(cls, '_gizmo_icon_color', (140, 60, 200))
    label = getattr(cls, '_gizmo_icon_label', '?')
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    from PyQt6.QtGui import QPainter, QColor as QC, QFont as QF, QBrush as QB
    from PyQt6.QtCore import QRect
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QB(QC(r, g, b)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, size, size, 3, 3)
    if label:
        p.setPen(QC(255, 255, 255))
        f = QF("Segoe UI", size // 2, QF.Weight.Bold)
        p.setFont(f)
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, label[0].upper())
    p.end()
    return pix
class HierarchyTree(QTreeWidget):
    entity_reparented = pyqtSignal(object, object)
    delete_requested = pyqtSignal(list)
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QTreeWidget.DragDropMode.DragDrop)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._press_item = None
        self._press_pos = None
        self._drag_started = False
        self._last_clicked_item = None
    def _select_range(self, item):
        if not self._last_clicked_item:
            self.setCurrentItem(item)
            return
        items = []
        collecting = False
        stop = False

        def walk(parent):
            nonlocal collecting, stop
            if stop:
                return
            for i in range(parent.childCount()):
                if stop:
                    return
                child = parent.child(i)
                if child == self._last_clicked_item or child == item:
                    items.append(child)
                    if collecting:
                        stop = True
                        return
                    collecting = True
                elif collecting:
                    items.append(child)
                walk(child)

        walk(self.invisibleRootItem())
        self.clearSelection()
        for it in items:
            it.setSelected(True)
        self.setCurrentItem(item)
    def supportedDropActions(self):
        return Qt.DropAction.MoveAction
    def mimeTypes(self):
        return [_ENTITY_MIME]
    def mimeData(self, items):
        mime = QMimeData()
        eids = []
        for item in items:
            eid = item.data(0, Qt.ItemDataRole.UserRole)
            if eid:
                eids.append(eid)
        if eids:
            mime.setData(_ENTITY_MIME, ",".join(eids).encode("utf-8"))
        return mime
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._press_item = self.itemAt(self._press_pos)
            if self._press_item:
                self._drag_started = False
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_item and self._press_pos:
            delta = event.position().toPoint() - self._press_pos
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._drag_started = True
                items = self.selectedItems()
                if not items:
                    items = [self._press_item]
                elif self._press_item not in items:
                    items.append(self._press_item)
                mime = self.mimeData(items)
                drag = QDrag(self)
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
                self._press_item = None
                self._press_pos = None
                return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_started:
                self._drag_started = False
                self._press_item = None
                self._press_pos = None
                return
            if self._press_item:
                item = self._press_item
                self._press_item = None
                self._press_pos = None
                modifiers = event.modifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    item.setSelected(not item.isSelected())
                    self._last_clicked_item = item
                elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self._select_range(item)
                else:
                    self.clearSelection()
                    item.setSelected(True)
                    self.setCurrentItem(item)
                    self._last_clicked_item = item
                return
        super().mouseReleaseEvent(event)
    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(_ENTITY_MIME):
            event.ignore()
            return
        target_item = self.itemAt(event.position().toPoint())
        dragged_ids = bytes(event.mimeData().data(_ENTITY_MIME)).decode("utf-8").split(",")
        if target_item is not None:
            target_eid = target_item.data(0, Qt.ItemDataRole.UserRole)
            if not target_eid or not dragged_ids:
                event.ignore()
                return
            if target_eid in dragged_ids:
                event.ignore()
                return
            for did in dragged_ids:
                dragged_item = self._find_item_by_id(did)
                if dragged_item and self._is_descendant(target_item, dragged_item):
                    event.ignore()
                    return
        event.acceptProposedAction()
    def _find_item_by_id(self, eid: str):
        return self._find_recursive(eid, self.invisibleRootItem())
    def _find_recursive(self, eid: str, parent_item):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == eid:
                return child
            found = self._find_recursive(eid, child)
            if found:
                return found
        return None
    def _is_descendant(self, ancestor_item, check_item):
        if not check_item or not ancestor_item:
            return False
        parent = check_item.parent()
        while parent:
            if parent == ancestor_item:
                return True
            parent = parent.parent()
        return False
    def dropEvent(self, event):
        if not event.mimeData().hasFormat(_ENTITY_MIME):
            event.ignore()
            return
        target_item = self.itemAt(event.position().toPoint())
        dragged_ids = bytes(event.mimeData().data(_ENTITY_MIME)).decode("utf-8").split(",")
        if not dragged_ids:
            event.ignore()
            return
        if target_item is None:
            for did in dragged_ids:
                self.entity_reparented.emit(did, None)
            event.acceptProposedAction()
            return
        target_eid = target_item.data(0, Qt.ItemDataRole.UserRole)
        if not target_eid:
            event.ignore()
            return
        for did in dragged_ids:
            if did == target_eid:
                event.ignore()
                return
        pos = self.dropIndicatorPosition()
        if pos in (QAbstractItemView.DropIndicatorPosition.AboveItem, QAbstractItemView.DropIndicatorPosition.BelowItem):
            target_parent = target_item.parent()
            if target_parent:
                parent_eid = target_parent.data(0, Qt.ItemDataRole.UserRole)
            else:
                parent_eid = None
            for did in dragged_ids:
                self.entity_reparented.emit(did, parent_eid)
        else:
            for did in dragged_ids:
                self.entity_reparented.emit(did, target_eid)
        event.acceptProposedAction()
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mods = event.modifiers()
        nvk = event.nativeVirtualKey()
        if mods & Qt.KeyboardModifier.ControlModifier:
            if nvk == 67 or key == Qt.Key.Key_C:
                self.copy_requested.emit()
                event.accept()
                return
            if nvk == 86 or key == Qt.Key.Key_V:
                self.paste_requested.emit()
                event.accept()
                return
        if key == Qt.Key.Key_F2:
            items = self.selectedItems()
            if items:
                self.editItem(items[0], 0)
        elif key == Qt.Key.Key_Delete:
            items = self.selectedItems()
            eids = []
            for item in items:
                eid = item.data(0, Qt.ItemDataRole.UserRole)
                if eid:
                    eids.append(eid)
            if eids:
                self.delete_requested.emit(eids)
        else:
            super().keyPressEvent(event)
class HierarchyPanel(QDockWidget):
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
    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 2)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search, 1)
        add_btn = QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setToolTip("Create Entity")
        add_btn.clicked.connect(self._show_create_menu)
        toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)
        self._tree = HierarchyTree()
        self._tree.setHeaderHidden(True)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setStyleSheet(
            "QTreeWidget::item:selected { background: #264f78; color: #fff; }"
            "QTreeWidget::item:selected:active { background: #264f78; }"
            "QTreeWidget::item:hover { background: #2a2d2e; }"
        )
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_click)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.entity_reparented.connect(self._on_reparent)
        self._tree.delete_requested.connect(self._delete_entities_by_ids)
        self._tree.copy_requested.connect(self._on_copy)
        self._tree.paste_requested.connect(self._on_paste)
        layout.addWidget(self._tree)
        self.setWidget(w)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._periodic_refresh)
        self._refresh_timer.start(500)
    def load_config(self, config) -> None:
        refresh_interval = config.get("hierarchy.refresh_interval", 500)
        self._refresh_timer.setInterval(refresh_interval)
    def _on_scene_loaded(self, scene: Scene):
        self._scene = scene
        self._selected_entity = None
        self._last_render_version = -1
        self._refresh()
    def _refresh(self):
        if not self._scene:
            self._tree.clear()
            return
        self._last_render_version = getattr(self._scene, '_render_version', -1)
        old_expanded = self._get_expanded_ids()
        old_selection = self._selected_entity.id if self._selected_entity else None
        self._tree.blockSignals(True)
        self._tree.clear()
        filter_text = self._search.text().strip().lower()
        root_entities = self._scene.get_root_entities()
        for entity in root_entities:
            self._add_entity_item(entity, self._tree.invisibleRootItem(), filter_text)
        self._restore_expanded(old_expanded)
        if old_selection:
            self._restore_selection(old_selection)
        self._tree.blockSignals(False)
    def _add_entity_item(self, entity: Entity, parent_item, filter_text: str) -> bool:
        name = entity.name
        if entity.is_prefab_instance:
            from core.prefab import Prefab
            overrides = Prefab.compute_overrides(entity)
            override_mark = " *" if overrides else ""
            name = f"{name}{override_mark}"
        has_visible_child = any(self._entity_matches_filter(c, filter_text) for c in entity.children)
        matches_filter = (not filter_text) or (filter_text in name.lower()) or has_visible_child
        if not matches_filter:
            return False
        item = QTreeWidgetItem(parent_item)
        item.setText(0, name)
        item.setData(0, Qt.ItemDataRole.UserRole, entity.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        icon_cls = None
        for c in entity.get_all_components():
            if getattr(type(c), '_show_gizmo_icon', True) and type(c).__name__ != "Transform":
                icon_cls = type(c)
                break
        if icon_cls:
            item.setIcon(0, QIcon(_get_component_icon_pixmap(icon_cls, 16)))
        if entity.is_prefab_instance:
            item.setForeground(0, QBrush(QColor("#88ccff")))
        if not entity.active:
            gray = self._tree.palette().color(self._tree.palette().ColorRole.PlaceholderText)
            item.setForeground(0, QBrush(gray))
        child_filter = "" if (has_visible_child and filter_text) else filter_text
        for child in entity.children:
            self._add_entity_item(child, item, child_filter)
        item.setExpanded(True)
        return True
    def _entity_matches_filter(self, entity: Entity, filter_text: str) -> bool:
        if not filter_text:
            return True
        if filter_text in entity.name.lower():
            return True
        return any(self._entity_matches_filter(c, filter_text) for c in entity.children)
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
    def _restore_selection(self, eid: str):
        item = self._find_item(eid, self._tree.invisibleRootItem())
        if item:
            self._tree.setCurrentItem(item)
    def _find_item(self, eid: str, parent_item) -> Optional[QTreeWidgetItem]:
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == eid:
                return child
            found = self._find_item(eid, child)
            if found:
                return found
        return None
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
    def _on_item_double_click(self, item: QTreeWidgetItem, col: int):
        eid = item.data(0, Qt.ItemDataRole.UserRole)
        if self._scene and eid:
            self.entity_double_clicked.emit(eid)
    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        eid = item.data(0, Qt.ItemDataRole.UserRole)
        new_name = item.text(0)
        if not self._scene or not eid:
            return
        entity = self._scene.get_entity(eid)
        if entity and entity.name != new_name:
            entity.name = new_name
            self._scene.mark_dirty()
    def _on_search(self, text: str):
        self._refresh()
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
    def _is_ancestor(self, potential_ancestor: Entity, entity: Entity) -> bool:
        current = entity.parent
        while current:
            if current == potential_ancestor:
                return True
            current = current.parent
        return False
    def _periodic_refresh(self):
        if not self._scene:
            return
        rv = getattr(self._scene, '_render_version', -1)
        if rv != self._last_render_version:
            self._last_render_version = rv
            if self._tree.state() != QTreeWidget.State.EditingState and not self._tree._drag_started and self._tree._press_item is None:
                self._refresh()
        if self._tree.currentItem() is None and self._selected_entity:
            self._restore_selection(self._selected_entity.id)
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
                create_child_act = QAction("Create Child", self)
                create_child_act.triggered.connect(lambda: self._create_child(entity))
                menu.addAction(create_child_act)
                menu.addSeparator()
                if entity.is_prefab_instance:
                    from core.prefab import Prefab, PrefabLibrary
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
                menu.addSeparator()
                save_pref_act = QAction("Save as Prefab...", self)
                save_pref_act.triggered.connect(lambda: self._save_prefab(entity))
                menu.addAction(save_pref_act)
                menu.addSeparator()
                del_act = QAction("Delete", self)
                del_act.triggered.connect(lambda: self._delete_entity(entity))
                menu.addAction(del_act)
                menu.addSeparator()
        self._add_create_menu_entries(menu)
        menu.exec(self._tree.mapToGlobal(pos))
    def _add_create_menu_entries(self, menu: QMenu):
        create_empty = QAction("Create Empty", self)
        create_empty.triggered.connect(self._create_entity)
        menu.addAction(create_empty)
        primitives_menu = menu.addMenu("3D Object")
        for name in ["Cube", "Sphere", "Plane"]:
            act = QAction(name, self)
            act.triggered.connect(lambda checked=False, n=name.lower(): self._create_primitive(n))
            primitives_menu.addAction(act)
        probuilder_menu = menu.addMenu("ProBuilder Shape")
        from core.components.mesh_editor.primitives import get_primitive_names
        for name in get_primitive_names():
            act = QAction(name, self)
            act.triggered.connect(lambda checked=False, n=name: self._create_probuilder_primitive(n))
            probuilder_menu.addAction(act)
        lights_menu = menu.addMenu("Light")
        for ltype, label in [("directional", "Directional Light"), ("point", "Point Light"), ("spot", "Spot Light")]:
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, lt=ltype: self._create_light(lt))
            lights_menu.addAction(act)
        cam_act = QAction("Camera", self)
        cam_act.triggered.connect(self._create_camera)
        menu.addAction(cam_act)
    def _show_create_menu(self):
        btn = self.sender()
        menu = QMenu(self)
        self._add_create_menu_entries(menu)
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
    def _collab_sync_create(self, entity):
        mgr = getattr(self._engine, "collab_manager", None)
        if mgr and mgr.connected:
            mgr.send_entity_create(entity.serialize())

    def _collab_sync_delete(self, entity_id: str):
        mgr = getattr(self._engine, "collab_manager", None)
        if mgr and mgr.connected:
            mgr.send_entity_delete(entity_id)

    def _create_entity(self):
        if not self._scene:
            return
        from core.commands import CreateEntityCommand, get_history
        cmd = CreateEntityCommand(self._scene, "GameObject")
        get_history().execute(cmd)
        e = self._scene.get_entity(cmd._entity_id)
        if e:
            from core.components import Transform
            e.add_component(Transform())
        self._refresh()
        if e:
            self._collab_sync_create(e)
            self._selected_entity = e
            self.entity_selected.emit(e)
            item = self._find_item(e.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)
                self._tree.editItem(item, 0)
    def _create_child(self, parent: Entity):
        if not self._scene:
            return
        from core.commands import CreateEntityCommand, get_history
        cmd = CreateEntityCommand(self._scene, "GameObject")
        get_history().execute(cmd)
        e = self._scene.get_entity(cmd._entity_id)
        if e:
            from core.components import Transform
            e.add_component(Transform())
            e.set_parent(parent)
        self._refresh()
        if e:
            self._collab_sync_create(e)
            self._selected_entity = e
            self.entity_selected.emit(e)
            item = self._find_item(e.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)
                self._tree.editItem(item, 0)
    def _create_primitive(self, mesh_name: str):
        if not self._scene:
            return
        from core.commands import CreateEntityCommand, get_history
        from core.components import Transform, MeshFilter, MeshRenderer
        cmd = CreateEntityCommand(self._scene, mesh_name.capitalize())
        get_history().execute(cmd)
        e = self._scene.get_entity(cmd._entity_id)
        if e:
            mf = MeshFilter()
            mf.mesh_name = mesh_name
            e.add_component(Transform())
            e.add_component(mf)
            e.add_component(MeshRenderer())
        self._refresh()
        if e:
            self._collab_sync_create(e)
            self._selected_entity = e
            self.entity_selected.emit(e)
            item = self._find_item(e.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)
    def _create_probuilder_primitive(self, name: str):
        if not self._scene:
            return
        from core.commands import CreateEntityCommand, get_history
        from core.components import Transform, MeshFilter, MeshRenderer
        from core.components.mesh_editor import ProBuilderMesh, create_primitive
        cmd = CreateEntityCommand(self._scene, name)
        get_history().execute(cmd)
        e = self._scene.get_entity(cmd._entity_id)
        if e:
            e.add_component(Transform())
            mf = MeshFilter()
            e.add_component(mf)
            e.add_component(MeshRenderer())
            pb = ProBuilderMesh()
            e.add_component(pb)
            positions, indices = create_primitive(name)
            pb.set_mesh_data(positions, indices)
            mf.mesh_name = f"ProBuilder_{e.id[:6]}"
        self._refresh()
        if e:
            self._collab_sync_create(e)
            self._selected_entity = e
            self.entity_selected.emit(e)
            item = self._find_item(e.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)

    def _create_light(self, ltype: str):
        if not self._scene:
            return
        from core.commands import CreateEntityCommand, get_history
        from core.components import Transform, Light, LightType
        name_map = {"directional": "Directional Light", "point": "Point Light", "spot": "Spot Light"}
        cmd = CreateEntityCommand(self._scene, name_map.get(ltype, "Light"))
        get_history().execute(cmd)
        e = self._scene.get_entity(cmd._entity_id)
        if e:
            t = Transform()
            e.add_component(t)
            l = Light()
            type_map = {"directional": LightType.DIRECTIONAL, "point": LightType.POINT, "spot": LightType.SPOT}
            l.light_type = type_map[ltype]
            e.add_component(l)
        self._refresh()
        if e:
            self._collab_sync_create(e)
            self._selected_entity = e
            self.entity_selected.emit(e)
            item = self._find_item(e.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)
    def _create_camera(self):
        if not self._scene:
            return
        from core.commands import CreateEntityCommand, get_history
        from core.components import Transform, Camera
        cmd = CreateEntityCommand(self._scene, "Camera")
        get_history().execute(cmd)
        e = self._scene.get_entity(cmd._entity_id)
        if e:
            e.add_component(Transform())
            e.add_component(Camera())
        self._refresh()
        if e:
            self._collab_sync_create(e)
            self._selected_entity = e
            self.entity_selected.emit(e)
            item = self._find_item(e.id, self._tree.invisibleRootItem())
            if item:
                self._tree.setCurrentItem(item)
    def _duplicate_entity(self, entity: Entity):
        if not self._scene:
            return
        import copy, uuid
        data = copy.deepcopy(entity.serialize())
        data["id"] = str(uuid.uuid4())
        data["name"] = entity.name
        data["parent"] = None
        for comp_data in data.get("components", []):
            pass
        from core.ecs import Entity as Ent
        from core.engine import Engine
        new_e = Ent.deserialize(data, Engine.instance()._component_registry)
        self._scene.add_entity(new_e)
        if entity.parent:
            new_e.set_parent(entity.parent)
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
        from core.commands import DeleteEntityCommand, get_history
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
            data = copy.deepcopy(e.serialize())
            if is_top:
                data["parent"] = None
            t = e.get_component_by_name("Transform")
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
    def _save_prefab(self, entity: Entity):
        from PyQt6.QtWidgets import QFileDialog
        from core.prefab import Prefab
        path, _ = QFileDialog.getSaveFileName(self, "Save Prefab", "prefabs/", "Prefabs (*.zpep)")
        if path:
            if not path.endswith(".zpep"):
                path += ".zpep"
            pref = Prefab(entity.name)
            pref.capture([entity])
            pref.save(path)
    def _get_prefab_roots(self, entity: Entity) -> list[Entity]:
        roots = []
        seen = set()
        def walk(e):
            if e.id in seen:
                return
            seen.add(e.id)
            if e.is_prefab_instance and e._prefab_guid == entity._prefab_guid:
                p = e._parent
                while p and p.is_prefab_instance and p._prefab_guid == e._prefab_guid:
                    p = p._parent
                if p is None or not p.is_prefab_instance or p._prefab_guid != e._prefab_guid:
                    roots.append(e)
            for c in e.children:
                walk(c)
        walk(entity)
        if not roots and entity.is_prefab_instance:
            roots = [entity]
        return roots

    def _apply_prefab(self, entity: Entity):
        from core.prefab import Prefab, PrefabLibrary
        from core.commands import get_history
        prefab_path = PrefabLibrary.path_for_guid(entity._prefab_guid)
        if not prefab_path:
            from core.logger import Logger
            Logger.warning("Cannot find prefab asset path for this instance.")
            return
        roots = self._get_prefab_roots(entity)
        all_entities = []
        def collect(e):
            all_entities.append(e)
            for c in e.children:
                collect(c)
        for r in roots:
            collect(r)
        current_data = {}
        for e in all_entities:
            current_data[e.id] = e.serialize()
        pref = Prefab(entity.name, entity._prefab_guid)
        pref.roots_data = [current_data[r.id] for r in roots]
        pref.save(prefab_path)
        PrefabLibrary.invalidate(prefab_path)
        self._scene.mark_dirty()
        self._refresh()

    def _revert_prefab(self, entity: Entity):
        from core.commands import RevertPrefabInstanceCommand, get_history
        roots = self._get_prefab_roots(entity)
        cmd = RevertPrefabInstanceCommand(self._scene, roots)
        get_history().execute(cmd)
        self._scene.mark_dirty()
        self._refresh()

    def _unpack_prefab(self, entity: Entity):
        from core.commands import UnpackPrefabCommand, get_history
        roots = self._get_prefab_roots(entity)
        cmd = UnpackPrefabCommand(self._scene, roots)
        get_history().execute(cmd)
        self._scene.mark_dirty()
        self._refresh()

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
        for entity in entities:
            if entity:
                item = self._find_item(entity.id, self._tree.invisibleRootItem())
                if item:
                    item.setSelected(True)
        self._tree.blockSignals(False)
        if entities:
            self._selected_entity = entities[0]
    def refresh(self):
        self._refresh()
