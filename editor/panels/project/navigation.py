# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
from PySide6.QtWidgets import QTreeWidgetItem, QListWidgetItem, QFileIconProvider
from PySide6.QtCore import Qt
from editor.constants import VIEW_DETAILS
from editor.inspector.helpersp import _flash_overlay
from .icons import _accent_hex, _VCS_COLORS
_SKIP_TREE_DIRS = {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".idea", ".vs", ".vscode"}
from core.config.editor_scale import scale
class NavigationMixin:
    def _navigate_to(self, pane, path: str, record: bool = True) -> None:
        if pane is None or not path:
            return
        try:
            target = os.path.normpath(os.path.abspath(path))
        except Exception:
            return
        if not self._is_inside_root(target):
            return
        if not os.path.isdir(target):
            try:
                os.makedirs(target, exist_ok=True)
            except Exception:
                return
        cur = os.path.normpath(pane._current_dir) if pane._current_dir else ""
        if cur == target:
            try:
                pane.populate_files(target)
            except Exception:
                pass
            return
        if record and not pane._navigating:
            try:
                pane._hist_back.append(pane._current_dir)
                if len(pane._hist_back) > 100:
                    pane._hist_back = pane._hist_back[-100:]
                pane._hist_fwd.clear()
            except Exception:
                pass
        self._set_active_pane(pane)
        try:
            pane.populate_files(target)
        except Exception:
            pass
        try:
            self._sync_tree_selection(target)
        except Exception:
            pass
        try:
            self._schedule_save()
        except Exception:
            pass
    def _push_history(self, path: str, pane=None):
        try:
            if pane is None:
                pane = self._active_pane()
            target = os.path.normpath(os.path.abspath(path))
            cur = os.path.normpath(pane._current_dir)
            if cur == target:
                self._update_nav_buttons()
                return
            self._navigate_to(pane, target, record=True)
        except Exception:
            pass
    def _go_back(self):
        pane = self._active_pane()
        if pane._hist_back:
            try:
                pane._navigating = True
                pane._hist_fwd.append(pane._current_dir)
                path = pane._hist_back.pop()
                pane.populate_files(path)
                try:
                    self._sync_tree_selection(path)
                except Exception:
                    pass
            finally:
                pane._navigating = False
            self._update_nav_buttons()
            try:
                self._schedule_save()
            except Exception:
                pass
    def _go_forward(self):
        pane = self._active_pane()
        if pane._hist_fwd:
            try:
                pane._navigating = True
                pane._hist_back.append(pane._current_dir)
                path = pane._hist_fwd.pop()
                pane.populate_files(path)
                try:
                    self._sync_tree_selection(path)
                except Exception:
                    pass
            finally:
                pane._navigating = False
            self._update_nav_buttons()
            try:
                self._schedule_save()
            except Exception:
                pass
    def _update_nav_buttons(self):
        try:
            pane = self._active_pane()
            if self._nav_bar:
                self._nav_bar._back_btn.setEnabled(len(pane._hist_back) > 0)
                self._nav_bar._forward_btn.setEnabled(len(pane._hist_fwd) > 0)
        except Exception:
            pass
    def _update_pane_selection_style(self, pane) -> None:
        try:
            accent = _accent_hex()
        except Exception:
            accent = "#0078d7"
        try:
            is_active = bool(pane._active)
        except Exception:
            is_active = True
        try:
            if is_active:
                sel = f"QTreeWidget::item:selected {{ background: {accent}; color: white; }} QTreeWidget::item:selected:!active {{ background: {accent}; color: white; }} QListWidget::item:selected {{ background: {accent}; color: white; }}"
            else:
                sel = "QTreeWidget::item:selected { background: #4a4a4a; color: white; } QTreeWidget::item:selected:!active { background: #3d3d3d; color: #d4d4d4; } QListWidget::item:selected { background: #4a4a4a; color: white; }"
            base_tree = f"QTreeWidget {{ border: none; outline: none; show-decoration-selected: 1; background: #252526; alternate-background-color: #2a2a2d; }} QTreeWidget::item {{ padding: 1px 2px; min-height: 20px; }} QTreeWidget::item:alternate {{ background: #2a2a2d; }} {sel}"
            base_list = f"QListWidget {{ border: none; outline: none; }} {sel}"
            try:
                pane._detail_tree.setStyleSheet(base_tree)
            except Exception:
                pass
            try:
                pane._file_list.setStyleSheet(base_list)
            except Exception:
                pass
        except Exception:
            pass
    def _on_folder_selected(self, item, col):
        dirpath = item.data(0, Qt.ItemDataRole.UserRole)
        if dirpath and os.path.isdir(dirpath):
            self._navigate_to(self._active_pane(), dirpath, record=True)
    def _populate_tree(self):
        self._folder_tree.clear()
        root_item = QTreeWidgetItem(self._folder_tree)
        root_item.setText(0, os.path.basename(self._project_root))
        root_item.setData(0, Qt.ItemDataRole.UserRole, self._project_root)
        root_item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
        self._add_subfolders(root_item, self._project_root)
        root_item.setExpanded(True)
    def _add_subfolders(self, parent_item: QTreeWidgetItem, dirpath: str):
        from editor.panels.project import fscache as _fsc
        try:
            rows = _fsc.list_dir(dirpath)
        except Exception:
            return
        for entry, is_dir, _sz, _mt in rows:
            if is_dir and not entry.startswith(".") and entry != "__pycache__" and entry not in _SKIP_TREE_DIRS:
                full = os.path.join(dirpath, entry)
                item = QTreeWidgetItem(parent_item)
                item.setText(0, entry)
                item.setData(0, Qt.ItemDataRole.UserRole, full)
                item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
                status = self._vcs_status_of(full)
                c = _VCS_COLORS.get(status)
                if c:
                    item.setForeground(0, c)
                self._add_subfolders(item, full)
    def _on_list_item_changed(self, item: QListWidgetItem):
        if self._in_file_undo:
            return
        try:
            if self._is_up_item(item):
                return
        except Exception:
            pass
        old_path = item.data(Qt.ItemDataRole.UserRole)
        if not old_path or not os.path.exists(old_path):
            return
        new_name = item.text()
        if not new_name:
            return
        old_name = os.path.basename(old_path)
        if new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        if os.path.exists(new_path):
            item.blockSignals(True)
            item.setText(old_name)
            item.blockSignals(False)
            return
        try:
            os.rename(old_path, new_path)
            item.setData(Qt.ItemDataRole.UserRole, new_path)
            self._push_file_undo({"kind": "rename", "old": old_path, "new": new_path, "label": "Rename"})
            old_tip = item.toolTip()
            if "\n" in old_tip:
                item.setToolTip(new_name + "\n" + old_tip.split("\n", 1)[1])
            else:
                item.setToolTip(new_name)
        except OSError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Could not rename:\n{e}")
            item.blockSignals(True)
            item.setText(old_name)
            item.blockSignals(False)
    def _on_tree_item_changed(self, item: QTreeWidgetItem, col: int):
        if col != 0:
            return
        if self._in_file_undo:
            return
        try:
            if self._is_up_item(item):
                return
        except Exception:
            pass
        old_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not old_path or not os.path.exists(old_path):
            return
        new_name = item.text(0)
        if not new_name:
            return
        old_name = os.path.basename(old_path)
        if new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        if os.path.exists(new_path):
            item.blockSignals(True)
            item.setText(0, old_name)
            item.blockSignals(False)
            return
        try:
            os.rename(old_path, new_path)
            item.setData(0, Qt.ItemDataRole.UserRole, new_path)
            self._push_file_undo({"kind": "rename", "old": old_path, "new": new_path, "label": "Rename"})
            if not os.path.isdir(new_path):
                try:
                    item.setText(1, self._active_pane()._type_label(new_name, False))
                except Exception:
                    pass
            new_p = item.data(0, Qt.ItemDataRole.UserRole)
            if new_p and os.path.isfile(new_p):
                self.file_selected.emit(new_p)
        except OSError:
            pass
    def _on_file_single_click(self, item):
        if isinstance(item, QTreeWidgetItem):
            path = item.data(0, Qt.ItemDataRole.UserRole)
        elif hasattr(item, 'data'):
            path = item.data(Qt.ItemDataRole.UserRole)
        else:
            path = None
        if path and os.path.isfile(path):
            self.file_selected.emit(path)
    def _on_file_double_click(self, item):
        if isinstance(item, QTreeWidgetItem):
            path = item.data(0, Qt.ItemDataRole.UserRole)
        else:
            path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        if os.path.isdir(path):
            self._navigate_to(self._active_pane(), path, record=True)
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
            elif ext == ".zterr":
                self.file_double_clicked.emit(path)
            else:
                self._open_path_with_default_app(path)
    def _sync_tree_selection(self, dirpath: str):
        root = self._folder_tree.topLevelItem(0)
        if not root:
            return
        stack = [(root, root.data(0, Qt.ItemDataRole.UserRole))]
        while stack:
            item, path = stack.pop()
            if path == dirpath:
                self._folder_tree.setCurrentItem(item)
                self._folder_tree.scrollToItem(item)
                return
            for i in range(item.childCount()):
                child = item.child(i)
                stack.append((child, child.data(0, Qt.ItemDataRole.UserRole)))
    def _go_to_parent(self):
        pane = self._active_pane()
        try:
            cur = os.path.normpath(pane._current_dir)
            parent = os.path.normpath(os.path.dirname(cur))
        except Exception:
            return
        if parent and self._is_inside_root(parent) and parent != cur:
            self._navigate_to(pane, parent, record=True)
    def _go_to_root(self):
        self._navigate_to(self._active_pane(), self._project_root, record=True)
    def _find_item_by_path(self, norm):
        pane = self._active_pane()
        if self._view_mode == VIEW_DETAILS:
            tree = pane._detail_tree
            for i in range(tree.topLevelItemCount()):
                it = tree.topLevelItem(i)
                if it and it.data(0, Qt.ItemDataRole.UserRole) == norm:
                    return it
        else:
            lst = pane._file_list
            for i in range(lst.count()):
                it = lst.item(i)
                if it and it.data(Qt.ItemDataRole.UserRole) == norm:
                    return it
        return None
    def _flash_item(self, item):
        try:
            if isinstance(item, QTreeWidgetItem):
                tree = item.treeWidget()
                if not tree:
                    return
                _flash_overlay(tree.viewport(), tree.visualItemRect(item))
            else:
                lst = item.listWidget()
                if not lst:
                    return
                _flash_overlay(lst.viewport(), lst.visualItemRect(item))
        except RuntimeError:
            pass
    def flash_resource(self, path: str):
        norm = os.path.normpath(self._resolve_resource_path(path))
        if not os.path.exists(norm):
            return
        target = os.path.dirname(norm) if os.path.isfile(norm) else norm
        if not self._is_inside_root(target):
            return
        pane = self._active_pane()
        cur = os.path.normpath(pane._current_dir)
        if cur != os.path.normpath(target):
            self._navigate_to(pane, target, record=True)
        item = self._find_item_by_path(norm)
        if item:
            pane.active_widget().scrollToItem(item)
            self._flash_item(item)
    def _on_sort_changed(self, pane, logical: int) -> None:
        try:
            if self._sort_guard:
                return
            order = pane._detail_tree.header().sortIndicatorOrder()
            self._sort_col = int(logical)
            self._sort_order = order
            self._apply_sort_indicators()
            pane.refresh()
            if getattr(self, "_pane_b", None) is not None:
                try:
                    self._pane_b.refresh()
                except Exception:
                    pass
            self._schedule_save()
        except Exception:
            pass
    def _apply_sort_indicators(self) -> None:
        try:
            self._sort_guard = True
            for pane in (getattr(self, "_pane_a", None), getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                try:
                    h = pane._detail_tree.header()
                    h.blockSignals(True)
                    h.setSortIndicator(self._sort_col, self._sort_order)
                    h.blockSignals(False)
                except Exception:
                    pass
        finally:
            try:
                self._sort_guard = False
            except Exception:
                pass
    def _sorted_entries(self, dirpath: str, entries: list[str]):
        try:
            reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        except Exception:
            reverse = False
        col = getattr(self, "_sort_col", 0)
        try:
            from editor.panels.project import fscache as _fsc
            cached = {r[0]: r for r in _fsc.list_dir(dirpath)}
        except Exception:
            cached = {}
        rows = []
        for e in entries:
            r = cached.get(e)
            if r is not None:
                _nm, is_dir, sz, mt = r
                if is_dir:
                    try:
                        sz = int(self._dir_size_cache.get(os.path.normpath(os.path.join(dirpath, e)), -1))
                    except Exception:
                        sz = -1
                ext = os.path.splitext(e)[1].lower() if not is_dir else ""
                rows.append((e, os.path.join(dirpath, e), is_dir, sz, mt / 1e9, ext))
                continue
            full = os.path.join(dirpath, e)
            try:
                is_dir = os.path.isdir(full)
            except Exception:
                is_dir = False
            try:
                sz = os.path.getsize(full) if not is_dir else int(self._dir_size_cache.get(os.path.normpath(full), -1))
            except Exception:
                sz = -1
            try:
                mt = os.path.getmtime(full)
            except Exception:
                mt = 0
            ext = os.path.splitext(e)[1].lower() if not is_dir else ""
            rows.append((e, full, is_dir, sz, mt, ext))
        try:
            if col == 3:
                rows.sort(key=lambda r: (r[3] < 0, r[3], r[0].lower()), reverse=reverse)
            elif col == 2:
                rows.sort(key=lambda r: (r[4], r[0].lower()), reverse=reverse)
            elif col == 1:
                rows.sort(key=lambda r: (r[5] if not r[2] else "", r[0].lower()), reverse=reverse)
            else:
                rows.sort(key=lambda r: r[0].lower(), reverse=reverse)
        except Exception:
            pass
        dirs = [r for r in rows if r[2]]
        files = [r for r in rows if not r[2]]
        return dirs + files
