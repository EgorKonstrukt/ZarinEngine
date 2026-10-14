# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, shutil, time
from PyQt6.QtWidgets import QListWidgetItem, QTreeWidgetItem, QMessageBox
from PyQt6.QtCore import Qt, QMimeData, QUrl, QByteArray
from PyQt6.QtGui import QDrag, QGuiApplication
from .icons import _ENTITY_MIME
_file_clipboard: list[str] = []
_clipboard_is_cut: bool = False
class DndMixin:
    def _start_drag_list(self, supported_actions):
        fl = self._active_pane()._file_list
        items = [i for i in fl.selectedItems() if not self._is_up_item(i)]
        if not items:
            return
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in items if i.data(Qt.ItemDataRole.UserRole)]
        paths = [p for p in paths if p]
        if not paths:
            return
        drag = QDrag(fl)
        mime = QMimeData()
        uri_paths = ["file:///" + os.path.abspath(p).replace("\\", "/") for p in paths]
        mime.setUrls([QUrl(u) for u in uri_paths])
        mime.setText("\n".join(paths))
        if len(paths) == 1:
            ext = os.path.splitext(paths[0])[1].lower()
            if ext == ".zpep":
                mime.setData("application/x-zpep", QByteArray(paths[0].encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
    def _on_file_list_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths:
            return
        base = self._active_pane()._current_dir
        target = self._drop_target_dir(event, base)
        self._move_or_copy_files(paths, dest_dir=target)
        event.acceptProposedAction()
    def _on_detail_tree_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths:
            return
        base = self._active_pane()._current_dir
        target = self._drop_target_dir(event, base)
        self._move_or_copy_files(paths, dest_dir=target)
        event.acceptProposedAction()
    def _on_folder_tree_drop(self, event):
        paths = self._extract_drop_paths(event)
        if not paths:
            return
        try:
            target_item = self._folder_tree.itemAt(event.position().toPoint())
        except Exception:
            target_item = None
        if target_item:
            target_path = target_item.data(0, Qt.ItemDataRole.UserRole)
        else:
            root = self._folder_tree.topLevelItem(0)
            target_path = root.data(0, Qt.ItemDataRole.UserRole) if root else self._project_root
        self._move_or_copy_files(paths, dest_dir=target_path)
        event.acceptProposedAction()
    def _on_entity_drop(self, event):
        if not event.mimeData().hasFormat(_ENTITY_MIME):
            return
        raw = bytes(event.mimeData().data(_ENTITY_MIME)).decode("utf-8")
        eids = [x.strip() for x in raw.split(",") if x.strip()]
        if not eids or not self._engine.scene:
            return
        from core.ecs.prefabp import Prefab
        entity = self._engine.scene.get_entity(eids[0])
        if not entity:
            return
        prefab = Prefab(entity.name)
        prefab.capture([entity])
        ext = ".zpep"
        name = entity.name.replace(" ", "_").replace("/", "_")
        dest_dir = self._active_pane()._current_dir
        path = os.path.join(dest_dir, f"{name}{ext}")
        counter = 1
        while os.path.exists(path):
            path = os.path.join(dest_dir, f"{name}_{counter}{ext}")
            counter += 1
        prefab.save(path)
        self._push_file_undo({"kind": "create", "paths": [path], "label": "Create prefab"})
        self._refresh()
        event.acceptProposedAction()
    def _extract_drop_paths(self, event):
        if event.mimeData().hasUrls():
            out = []
            for u in event.mimeData().urls():
                try:
                    lf = u.toLocalFile()
                except Exception:
                    continue
                if lf:
                    out.append(os.path.normpath(lf))
            if out:
                return out
        if event.mimeData().hasText():
            paths = []
            for line in event.mimeData().text().splitlines():
                line = line.strip().strip('"')
                if line:
                    paths.append(os.path.normpath(line))
            return paths
        return []
    def _start_drag_detail(self, supported_actions):
        dt = self._active_pane()._detail_tree
        items = [i for i in dt.selectedItems() if not self._is_up_item(i)]
        if not items:
            return
        paths = [i.data(0, Qt.ItemDataRole.UserRole) for i in items]
        paths = [p for p in paths if p]
        if not paths:
            return
        drag = QDrag(dt)
        mime = QMimeData()
        uri_paths = ["file:///" + os.path.abspath(p).replace("\\", "/") for p in paths]
        mime.setUrls([QUrl(u) for u in uri_paths])
        mime.setText("\n".join(paths))
        ext = os.path.splitext(paths[0])[1].lower()
        if len(paths) == 1 and ext == ".zpep":
            mime.setData("application/x-zpep", QByteArray(paths[0].encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
    def _get_selected_paths(self):
        widget = self._active_widget()
        paths = []
        for item in widget.selectedItems():
            try:
                if self._is_up_item(item):
                    continue
            except Exception:
                pass
            d = item.data(0, Qt.ItemDataRole.UserRole) if isinstance(item, QTreeWidgetItem) else item.data(Qt.ItemDataRole.UserRole)
            if d:
                paths.append(d)
        return paths
    def _copy_selected(self):
        global _file_clipboard, _clipboard_is_cut
        paths = self._get_selected_paths()
        if paths:
            _file_clipboard = list(paths)
            _clipboard_is_cut = False
    def _cut_selected(self):
        global _file_clipboard, _clipboard_is_cut
        paths = self._get_selected_paths()
        if paths:
            _file_clipboard = list(paths)
            _clipboard_is_cut = True
    def _paste_clipboard(self):
        global _file_clipboard, _clipboard_is_cut
        if not _file_clipboard:
            return
        target = self._active_pane()._current_dir
        try:
            target = os.path.normpath(os.path.abspath(target))
        except Exception:
            return
        moved = []
        copied = []
        errors = []
        for src in list(_file_clipboard):
            if not src or not os.path.exists(src):
                continue
            try:
                src_n = os.path.normpath(os.path.abspath(src))
            except Exception:
                continue
            name = os.path.basename(src)
            dst = os.path.join(target, name)
            if self._norm(src_n) == self._norm(dst):
                if _clipboard_is_cut:
                    continue
                dst = self._unique_dst(target, name)
            elif os.path.exists(dst):
                try:
                    if _clipboard_is_cut and os.path.samefile(src_n, dst):
                        continue
                except Exception:
                    pass
                dst = self._unique_dst(target, name)
            if self._norm(dst).startswith(self._norm(src_n) + os.sep):
                errors.append(f"{name}: target inside itself")
                continue
            try:
                if _clipboard_is_cut:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src_n, dst)
                    moved.append((src_n, dst))
                else:
                    ok = self._fs_copy(src_n, dst)
                    if ok:
                        copied.append((src_n, dst))
                    else:
                        errors.append(f"{name}: copy failed")
            except Exception as e:
                errors.append(f"{name}: {e}")
        if _clipboard_is_cut:
            _file_clipboard = []
            _clipboard_is_cut = False
        if moved:
            self._push_file_undo({"kind": "move", "items": moved, "label": "Paste move"})
        if copied:
            self._push_file_undo({"kind": "copy", "items": copied, "label": "Paste copy"})
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Paste Errors", "\n".join(errors))
    def _duplicate_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        copied = []
        errors = []
        for src in paths:
            if not os.path.exists(src):
                continue
            name = os.path.basename(src)
            dst = self._unique_dst(os.path.dirname(src), name)
            if self._norm(dst).startswith(self._norm(src) + os.sep):
                continue
            try:
                ok = self._fs_copy(src, dst)
                if ok:
                    copied.append((src, dst))
                else:
                    errors.append(f"{name}: copy failed")
            except Exception as e:
                errors.append(f"{name}: {e}")
        if copied:
            self._push_file_undo({"kind": "copy", "items": copied, "label": "Duplicate"})
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Duplicate Errors", "\n".join(errors))
    def _delete_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            return
        from PyQt6.QtWidgets import QMessageBox
        names = "\n".join(os.path.basename(p) for p in paths[:10])
        if len(paths) > 10:
            names += f"\n... and {len(paths) - 10} more"
        reply = QMessageBox.question(self, "Delete",
            f"Delete {len(paths)} item(s)?\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                trash_dir = os.path.join(self._trash_base(), f"del_{int(time.time()*1000)}")
                os.makedirs(trash_dir, exist_ok=True)
            except Exception:
                trash_dir = self._trash_base()
            items = []
            errors = []
            for p in paths:
                if not os.path.exists(p):
                    continue
                b = os.path.join(trash_dir, os.path.basename(p))
                k = 1
                bb = b
                while os.path.exists(bb):
                    base, ext = os.path.splitext(os.path.basename(p))
                    bb = os.path.join(trash_dir, f"{base} ({k}){ext}")
                    k += 1
                try:
                    shutil.move(p, bb)
                    items.append((p, bb))
                except Exception as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
            if items:
                self._push_file_undo({"kind": "delete", "items": items, "label": "Delete"})
            self._refresh()
            if errors:
                QMessageBox.warning(self, "Delete Errors", "\n".join(errors))
    def _copy_path(self, path: str):
        QGuiApplication.clipboard().setText(path)
    def _is_up_item(self, item) -> bool:
        try:
            if isinstance(item, QTreeWidgetItem):
                if item.data(0, Qt.ItemDataRole.UserRole + 1) == "up":
                    return True
                if item.text(0) == "..":
                    return True
            else:
                if item.data(Qt.ItemDataRole.UserRole + 1) == "up":
                    return True
                if item.text() == "..":
                    return True
        except Exception:
            pass
        return False
