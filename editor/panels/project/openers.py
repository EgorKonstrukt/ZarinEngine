# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from PyQt6.QtWidgets import QFileDialog, QListWidget, QApplication, QLineEdit
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QWheelEvent
from core.config.editor_scale import scale, scale_xy
from editor.constants import MIN_THUMB, MAX_THUMB, VIEW_ICON, VIEW_LIST, VIEW_DETAILS
from .icons import _qta_icon, qta
from .pane import _FilePane


class OpenersMixin:
    def _try_plugin_opener(self, path: str) -> bool:
        try:
            from core.foundation.plugins import open_file_with_plugin
            return bool(open_file_with_plugin(self._engine, path))
        except Exception:
            return False
    def _open_scene_file(self, path: str):
        cb = getattr(self, '_open_scene_callback', None)
        if cb is not None:
            cb(path)
        else:
            self._engine.load_scene_async(path)
    def _open_path(self, path: str):
        pane = self._active_pane()
        if os.path.isdir(path):
            self._navigate_to(pane, path, record=True)
        else:
            if self._try_plugin_opener(path):
                return
            ext = os.path.splitext(path)[1].lower()
            if ext == ".zpes":
                self._open_scene_file(path)
            elif ext == ".zpep":
                self.file_double_clicked.emit(path)
            elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
                self.import_model_requested.emit(path)
            elif ext in (".animclip", ".animcontroller"):
                self.file_double_clicked.emit(path)
            else:
                self.file_double_clicked.emit(path)
    def _open_item_by_path(self, path: str):
        if path:
            self._open_path(path)
    def _open_path_with_default_app(self, path):
        import subprocess, sys
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    def open_resource(self, path: str):
        path = self._resolve_resource_path(path)
        if os.path.isdir(path):
            return
        if self._try_plugin_opener(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".zpes":
            self._open_scene_file(path)
        elif ext == ".zpep":
            self.file_double_clicked.emit(path)
        elif ext in (".obj", ".fbx", ".stl", ".usdz", ".gltf", ".glb"):
            self.import_model_requested.emit(path)
        elif ext in (".animclip", ".animcontroller"):
            self.file_double_clicked.emit(path)
        elif ext == ".zterr":
            self.file_double_clicked.emit(path)
        else:
            self._open_path_with_default_app(path)
    def reveal_resource(self, path: str):
        norm = os.path.normpath(self._resolve_resource_path(path))
        if not os.path.exists(norm):
            return
        target = os.path.dirname(norm) if os.path.isfile(norm) else norm
        if not self._is_inside_root(target):
            return
        pane = self._active_pane()
        self._navigate_to(pane, target, record=True)
        item = self._find_item_by_path(norm)
        if item:
            pane.active_widget().setCurrentItem(item)
            pane.active_widget().scrollToItem(item)
            self._flash_item(item)
    def _reveal_file(self, path: str):
        import subprocess, sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    def _refresh(self):
        self._refresh_vcs_status()
        self._populate_tree()
        self._pane_a.refresh()
        if self._pane_b:
            self._pane_b.refresh()
    def _force_refresh_thumbnails(self):
        from editor.picker import _get_thumb_service
        _get_thumb_service().invalidate_thumbnails()
        from editor.thumb_cache import cache_root_for_project
        _get_thumb_service().set_cache_dir(cache_root_for_project(self._project_root))
        self._refresh()
    def _connect_mesh_loader(self):
        from editor.picker import _get_thumb_service
        loader = _get_thumb_service()
        loader.thumbnail_ready.connect(self._on_mesh_data_ready, Qt.ConnectionType.QueuedConnection)
    def _on_mesh_data_ready(self, path: str, size: int, pixmap):
        if pixmap is None or pixmap.isNull():
            return
        icon = QIcon(pixmap)
        for pane in (self._pane_a, self._pane_b):
            if not pane:
                continue
            if self._view_mode == VIEW_DETAILS:
                tree = pane._detail_tree
                for i in range(tree.topLevelItemCount()):
                    item = tree.topLevelItem(i)
                    item_path = item.data(0, Qt.ItemDataRole.UserRole)
                    if item_path == path:
                        item.setIcon(0, icon)
            else:
                fl = pane._file_list
                for i in range(fl.count()):
                    item = fl.item(i)
                    item_path = item.data(Qt.ItemDataRole.UserRole)
                    if item_path == path:
                        item.setIcon(icon)
    def _instantiate_prefab(self, path: str):
        if not self._engine.scene:
            return
        from core.ecs.prefabp import Prefab
        from core.engine.eng import Engine
        pref = Prefab.load(path)
        if pref:
            e = pref.instantiate(self._engine.scene, Engine.instance()._component_registry)
            if e:
                self._engine._emit_event("entity_created", e)
    def _update_view_mode_icon(self):
        icon_map = {
            VIEW_ICON: ("fa5s.th", "Icon View"),
            VIEW_DETAILS: ("fa5s.list", "Details View"),
        }
        icon_name, tip = icon_map.get(self._view_mode, ("fa5s.th", "View Mode"))
        if qta is not None:
            self._view_mode_btn.setIcon(qta.icon(icon_name, color="#d4d4d4"))
            self._view_mode_btn.setIconSize(QSize(*scale_xy(18, 18)))
            self._view_mode_btn.setText("")
        self._view_mode_btn.setToolTip(tip)
    def _toggle_view_mode(self):
        if self._view_mode == VIEW_ICON:
            self._view_mode = VIEW_DETAILS
        else:
            self._view_mode = VIEW_ICON
        self._apply_view_mode()
        self._update_view_mode_icon()
        self._pane_a.refresh()
        if self._pane_b:
            self._pane_b.refresh()
        try:
            self._schedule_save()
        except Exception:
            pass
    def _apply_view_mode(self):
        is_detail = self._view_mode == VIEW_DETAILS
        for pane in (self._pane_a, self._pane_b):
            if not pane:
                continue
            pane._stack.setCurrentIndex(1 if is_detail else 0)
            fl = pane._file_list
            if not is_detail:
                fl.setViewMode(QListWidget.ViewMode.IconMode)
                fl.setIconSize(QSize(self._thumb_size, self._thumb_size))
                fl.setGridSize(QSize(self._thumb_size + scale(20), self._thumb_size + scale(36)))
                fl.setWordWrap(True)
                fl.setSpacing(2)
                fl.setUniformItemSizes(True)
                fl.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._zoom_slider.setVisible(True)
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta != 0:
                step = 8 if abs(delta) > 120 else 4
                new_val = self._thumb_size + (step if delta > 0 else -step)
                new_val = max(MIN_THUMB, min(MAX_THUMB, new_val))
                self._thumb_size = new_val
                self._zoom_slider.setValue(new_val)
            event.accept()
        else:
            super().wheelEvent(event)
    def _on_zoom_changed(self, val: int):
        self._thumb_size = val
        if self._view_mode == VIEW_ICON:
            for pane in (self._pane_a, self._pane_b):
                if not pane:
                    continue
                pane._file_list.setIconSize(QSize(val, val))
                pane._file_list.setGridSize(QSize(val + scale(20), val + scale(36)))
        else:
            icon_sz = max(16, min(64, int(val * 0.5)))
            for pane in (self._pane_a, self._pane_b):
                if not pane:
                    continue
                pane._detail_tree.setIconSize(QSize(icon_sz, icon_sz))
        try:
            self._schedule_save()
        except Exception:
            pass
    def _apply_dual_pane_state(self):
        want = bool(self._dual_pane)
        if want:
            if self._pane_b is None:
                self._pane_b = _FilePane(self)
                self._pane_splitter.addWidget(self._pane_b)
                try:
                    self._pane_b._current_dir = self._pane_a._current_dir
                    self._pane_b.populate_files(self._pane_a._current_dir)
                except Exception:
                    pass
                self._install_pane_focus(self._pane_b)
                self._apply_view_mode()
                try:
                    self._pane_splitter.setSizes([self._pane_splitter.width() // 2] * 2)
                except Exception:
                    pass
            self._set_active_pane(self._active_pane())
        else:
            if getattr(self, "_pane_b", None) is not None:
                try:
                    self._pane_b.setParent(None)
                    self._pane_b.deleteLater()
                except Exception:
                    pass
                self._pane_b = None
            try:
                self._set_active_pane(self._pane_a)
            except Exception:
                pass
    def _toggle_dual_pane(self, checked):
        if self._restoring_state:
            self._dual_pane = bool(checked)
            return
        self._dual_pane = bool(checked)
        self._apply_dual_pane_state()
        try:
            self._schedule_save()
        except Exception:
            pass
    def _install_pane_focus(self, pane):
        try:
            pane._file_list.installEventFilter(self)
            pane._detail_tree.installEventFilter(self)
            pane._breadcrumb_bar.installEventFilter(self)
            pane.installEventFilter(self)
            pane._file_list.viewport().installEventFilter(self)
            pane._detail_tree.viewport().installEventFilter(self)
        except Exception:
            pass
    def _is_rename_editing(self) -> bool:
        try:
            fw = QApplication.focusWidget()
            if fw is None:
                return False
            for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                try:
                    if isinstance(fw, QLineEdit):
                        return True
                except Exception:
                    pass
            from PyQt6.QtWidgets import QAbstractItemView
            try:
                if isinstance(fw, QLineEdit):
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False
    def _project_has_focus(self) -> bool:
        try:
            fw = QApplication.focusWidget()
            if fw is None:
                return False
            cur = fw
            while cur is not None:
                if cur is self:
                    return True
                try:
                    cur = cur.parent()
                except Exception:
                    break
            for pane in (self._pane_a, getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                for w in (pane._file_list, pane._detail_tree, pane._breadcrumb_bar, pane):
                    try:
                        if fw is w:
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False
