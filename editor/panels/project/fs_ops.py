# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, shutil, tempfile, time, threading, queue
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt
from .icons import _ENTITY_MIME
class FsOpsMixin:
    def _norm(self, p: str) -> str:
        try:
            return os.path.normcase(os.path.normpath(os.path.abspath(p)))
        except Exception:
            return os.path.normpath(p)
    def _is_subpath(self, parent: str, child: str) -> bool:
        try:
            pn = self._norm(parent)
            cn = self._norm(child)
            return cn == pn or cn.startswith(pn + os.sep)
        except Exception:
            return False
    def _unique_dst(self, dest_dir: str, name: str) -> str:
        dst = os.path.join(dest_dir, name)
        if not os.path.exists(dst):
            return dst
        base, ext = os.path.splitext(name)
        counter = 1
        while True:
            cand = os.path.join(dest_dir, f"{base} ({counter}){ext}")
            if not os.path.exists(cand):
                return cand
            counter += 1
    def _trash_base(self) -> str:
        try:
            base = os.path.join(tempfile.gettempdir(), "zarin_project_trash", str(os.getpid()))
            os.makedirs(base, exist_ok=True)
            return base
        except Exception:
            base = os.path.join(self._project_root, ".trash_tmp")
            try:
                os.makedirs(base, exist_ok=True)
            except Exception:
                pass
            return base
    def _push_file_undo(self, op: dict) -> None:
        if self._in_file_undo:
            return
        try:
            self._file_undo.append(op)
            if len(self._file_undo) > 100:
                self._file_undo = self._file_undo[-100:]
            self._file_redo.clear()
        except Exception:
            pass
        try:
            kind = op.get("kind")
            if kind == "rename":
                try:
                    self._invalidate_dir_size(op.get("old", ""))
                except Exception:
                    pass
                try:
                    self._invalidate_dir_size(op.get("new", ""))
                except Exception:
                    pass
            elif kind in ("move", "copy"):
                for s, d in op.get("items", []):
                    try:
                        self._invalidate_dir_size(s)
                    except Exception:
                        pass
                    try:
                        self._invalidate_dir_size(d)
                    except Exception:
                        pass
            elif kind == "delete":
                for o, _b in op.get("items", []):
                    try:
                        self._invalidate_dir_size(o)
                    except Exception:
                        pass
            elif kind == "create":
                for p in op.get("paths", []):
                    try:
                        self._invalidate_dir_size(p)
                    except Exception:
                        pass
        except Exception:
            pass
    def _fs_copy(self, src: str, dst: str) -> bool:
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    return False
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return True
        except Exception:
            return False
    def _fs_move(self, src: str, dst: str) -> bool:
        try:
            if self._norm(src) == self._norm(dst):
                return False
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            return True
        except Exception:
            return False
    def _fs_remove(self, path: str) -> bool:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    return True
            return True
        except Exception:
            return False
    def _decide_is_move(self, srcs: list[str], dest_dir: str) -> bool:
        try:
            mods = QApplication.keyboardModifiers()
        except Exception:
            mods = Qt.KeyboardModifier.NoModifier
        if mods & Qt.KeyboardModifier.ControlModifier:
            return False
        if mods & Qt.KeyboardModifier.ShiftModifier:
            return True
        try:
            root = self._norm(self._project_root)
            for s in srcs:
                sn = self._norm(s)
                if not (sn == root or sn.startswith(root + os.sep)):
                    return False
            dn = self._norm(dest_dir)
            if not (dn == root or dn.startswith(root + os.sep)):
                return False
            return True
        except Exception:
            return False
    def _drop_target_dir(self, event, default_dir: str) -> str:
        try:
            pos = event.position().toPoint()
        except Exception:
            try:
                pos = event.pos()
            except Exception:
                return default_dir
        try:
            pane = self._active_pane()
            if pane is None:
                return default_dir
            try:
                it = pane._file_list.itemAt(pos)
                if it is not None:
                    p = it.data(Qt.ItemDataRole.UserRole)
                    if p and os.path.isdir(p) and self._is_inside_root(p):
                        return os.path.normpath(p)
                    return default_dir
            except Exception:
                pass
            try:
                it = pane._detail_tree.itemAt(pos)
                if it is not None:
                    p = it.data(0, Qt.ItemDataRole.UserRole)
                    if p and os.path.isdir(p) and self._is_inside_root(p):
                        return os.path.normpath(p)
                    return default_dir
            except Exception:
                pass
        except Exception:
            pass
        return default_dir
    def _undo_file_op(self):
        from .vcs import _undo_file_op_impl
        return _undo_file_op_impl(self)
    def _redo_file_op(self):
        from .vcs import _redo_file_op_impl
        return _redo_file_op_impl(self)
    def _rename_item(self, widget, item):
        if isinstance(item, QTreeWidgetItem):
            widget.editItem(item, 0)
        else:
            widget.editItem(item)
    def _move_or_copy_files(self, paths, dest_dir=None, force_move=None):
        if not dest_dir:
            dest_dir = self._active_pane()._current_dir
        try:
            dest_dir = os.path.normpath(os.path.abspath(dest_dir))
        except Exception:
            return
        if not os.path.isdir(dest_dir):
            try:
                os.makedirs(dest_dir, exist_ok=True)
            except Exception:
                return
        clean = []
        for s in paths:
            if not s:
                continue
            try:
                sn = os.path.normpath(os.path.abspath(s))
            except Exception:
                continue
            if not os.path.exists(sn):
                continue
            if sn not in clean:
                clean.append(sn)
        if not clean:
            return
        if force_move is None:
            is_move = self._decide_is_move(clean, dest_dir)
        else:
            is_move = bool(force_move)
        moved = []
        copied = []
        errors = []
        for src in clean:
            name = os.path.basename(src)
            src_n = self._norm(src)
            dest_n = self._norm(dest_dir)
            if src_n == dest_n:
                continue
            if dest_n.startswith(src_n + os.sep):
                errors.append(f"{name}: target inside itself")
                continue
            same_dir = self._norm(os.path.dirname(src)) == dest_n
            if same_dir and is_move:
                continue
            dst = os.path.join(dest_dir, name)
            if self._norm(src) == self._norm(dst):
                continue
            if self._norm(dst).startswith(src_n + os.sep):
                errors.append(f"{name}: target inside itself")
                continue
            if os.path.exists(dst):
                if is_move:
                    try:
                        if os.path.samefile(src, dst):
                            continue
                    except Exception:
                        pass
                dst = self._unique_dst(dest_dir, name)
            try:
                if is_move:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)
                    moved.append((src, dst))
                else:
                    ok = self._fs_copy(src, dst)
                    if ok:
                        copied.append((src, dst))
                    else:
                        errors.append(f"{name}: copy failed")
            except Exception as e:
                errors.append(f"{name}: {e}")
        if moved:
            self._push_file_undo({"kind": "move", "items": moved, "label": "Move"})
        if copied:
            self._push_file_undo({"kind": "copy", "items": copied, "label": "Copy"})
        try:
            for s, d in moved + copied:
                try:
                    self._invalidate_dir_size(s)
                except Exception:
                    pass
                try:
                    self._invalidate_dir_size(d)
                except Exception:
                    pass
            try:
                self._invalidate_dir_size(dest_dir)
            except Exception:
                pass
        except Exception:
            pass
        self._refresh()
        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Import Errors", "\n".join(errors))
    def _current_dir(self):
        return self._active_pane()._current_dir
    def _compute_dir_size_fast(self, root: str, gen: int):
        total = 0
        try:
            stack = [root]
            steps = 0
            while stack:
                if gen != self._dir_size_gen:
                    return None
                cur = stack.pop()
                try:
                    with os.scandir(cur) as it:
                        for entry in it:
                            steps += 1
                            if steps % 2000 == 0 and gen != self._dir_size_gen:
                                return None
                            try:
                                if entry.is_symlink():
                                    continue
                                if entry.is_dir(follow_symlinks=False):
                                    stack.append(entry.path)
                                elif entry.is_file(follow_symlinks=False):
                                    try:
                                        total += entry.stat(follow_symlinks=False).st_size
                                    except Exception:
                                        pass
                            except Exception:
                                continue
                except Exception:
                    continue
            return total
        except Exception:
            return total
    def _ensure_size_thread(self) -> None:
        try:
            if self._dir_size_thread is not None and self._dir_size_thread.is_alive():
                return
            t = threading.Thread(target=self._dir_size_loop, daemon=True)
            self._dir_size_thread = t
            t.start()
        except Exception:
            pass
    def _dir_size_loop(self) -> None:
        while True:
            try:
                gen, path = self._dir_size_queue.get()
            except Exception:
                continue
            try:
                if gen != self._dir_size_gen:
                    continue
                norm = os.path.normpath(path)
                if norm in self._dir_size_cache:
                    continue
                total = self._compute_dir_size_fast(path, gen)
                if total is None:
                    continue
                if gen != self._dir_size_gen:
                    continue
                self._dir_size_cache[norm] = int(total)
                try:
                    self._dir_size_ready.emit(path, int(total), int(gen))
                except Exception:
                    pass
            except Exception:
                pass
    def _request_dir_sizes(self, folder_paths: list[str]) -> None:
        try:
            self._ensure_size_thread()
            gen = int(self._dir_size_gen)
            for p in folder_paths:
                try:
                    norm = os.path.normpath(p)
                    if norm in self._dir_size_cache:
                        continue
                    self._dir_size_queue.put((gen, p))
                except Exception:
                    continue
        except Exception:
            pass
    def _on_dir_size_ready(self, path: str, size: int, gen: int) -> None:
        try:
            norm = os.path.normpath(path)
            self._dir_size_cache[norm] = int(size)
            for pane in (getattr(self, "_pane_a", None), getattr(self, "_pane_b", None)):
                if pane is None:
                    continue
                try:
                    if os.path.normpath(pane._current_dir) != os.path.normpath(os.path.dirname(path)):
                        continue
                except Exception:
                    pass
                try:
                    tree = pane._detail_tree
                    for i in range(tree.topLevelItemCount()):
                        it = tree.topLevelItem(i)
                        try:
                            if it.data(0, Qt.ItemDataRole.UserRole) == path:
                                it.setText(3, _format_size(int(size)))
                                it.setData(0, Qt.ItemDataRole.UserRole + 2, int(size))
                                it.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                                try:
                                    it.setForeground(3, self._size_brush(int(size)))
                                except Exception:
                                    pass
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            try:
                self._refresh_status_sizes()
            except Exception:
                pass
        except Exception:
            pass
    def _refresh_status_sizes(self) -> None:
        try:
            pane = self._active_pane()
            if pane is None or self._status_bar is None:
                return
            total = 0
            has_total = False
            try:
                for i in range(pane._detail_tree.topLevelItemCount()):
                    it = pane._detail_tree.topLevelItem(i)
                    try:
                        p = it.data(0, Qt.ItemDataRole.UserRole)
                        if not p or os.path.basename(p) == "..":
                            continue
                        if os.path.isdir(p):
                            v = self._dir_size_cache.get(os.path.normpath(p))
                            if v is not None:
                                total += int(v)
                                has_total = True
                        else:
                            try:
                                total += os.path.getsize(p)
                                has_total = True
                            except Exception:
                                pass
                    except Exception:
                        continue
            except Exception:
                pass
            try:
                if has_total:
                    self._status_bar.update_total(_format_size(total))
                else:
                    self._status_bar.update_total("")
            except Exception:
                pass
        except Exception:
            pass
    def _invalidate_dir_size(self, path: str) -> None:
        try:
            cur = os.path.normpath(os.path.abspath(path))
            root = os.path.normpath(self._project_root)
            for _ in range(32):
                try:
                    self._dir_size_cache.pop(cur, None)
                except Exception:
                    pass
                if cur == root:
                    break
                nxt = os.path.normpath(os.path.dirname(cur))
                if nxt == cur:
                    break
                cur = nxt
        except Exception:
            pass
