# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os, subprocess, threading
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from .icons import _VCS_COLORS, _parse_vcs_status
class VcsMixin:
    def _refresh_vcs_status(self):
        if not self.isVisible():
            return
        if self._vcs_refreshing:
            self._vcs_pending = True
            return
        self._vcs_refreshing = True
        root = self._project_root
        threading.Thread(target=self._vcs_worker, args=(root,), daemon=True).start()
    def _vcs_worker(self, root: str):
        try:
            result = _parse_vcs_status(root)
        except Exception:
            result = {}
        self._vcs_result_ready.emit(result)
    def _on_vcs_result(self, result: dict[str, str]):
        self._vcs_refreshing = False
        self._vcs_status = result
        if hasattr(self, "_pane_a"):
            try:
                self._apply_vcs_colors()
            except RuntimeError:
                pass
        if self._vcs_pending:
            self._vcs_pending = False
            self._refresh_vcs_status()
    def _vcs_status_of(self, full_path: str) -> str:
        if not self._vcs_status or not full_path:
            return ""
        try:
            rel = os.path.relpath(full_path, self._project_root)
        except ValueError:
            return ""
        rel = rel.replace("\\", "/")
        return self._vcs_status.get(rel, "")
    def _apply_vcs_colors(self):
        if not self._vcs_status:
            return
        default = QBrush()
        for pane in (self._pane_a, self._pane_b):
            if not pane:
                continue
            for i in range(pane._file_list.count()):
                item = pane._file_list.item(i)
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.isfile(path):
                    status = self._vcs_status_of(path)
                    item.setForeground(_VCS_COLORS.get(status, default))
            for i in range(pane._detail_tree.topLevelItemCount()):
                item = pane._detail_tree.topLevelItem(i)
                path = item.data(0, Qt.ItemDataRole.UserRole)
                if path and os.path.isfile(path):
                    status = self._vcs_status_of(path)
                    item.setForeground(0, _VCS_COLORS.get(status, default))
    def _git_run(self, *args: str) -> tuple[int, str, str]:
        for candidate in ["git.exe", "git"]:
            try:
                r = subprocess.run([candidate, "--version"], capture_output=True,
                                   text=True, timeout=5)
                if r.returncode == 0:
                    break
            except FileNotFoundError:
                continue
        else:
            return -1, "", "git not found"
        try:
            r = subprocess.run([candidate] + list(args), capture_output=True,
                               text=True, cwd=self._project_root, timeout=30)
            return r.returncode, r.stdout, r.stderr
        except Exception as e:
            return -1, "", str(e)
    def _git_add_file(self, path: str):
        if not isinstance(path, str) or not path:
            return
        try:
            rel = os.path.relpath(path, self._project_root)
        except ValueError:
            return
        rc, _, err = self._git_run("add", "--", rel)
        if rc == 0:
            self._refresh_vcs_status()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Git Add Failed", err[:200])
    def _git_unstage_file(self, path: str):
        if not isinstance(path, str) or not path:
            return
        try:
            rel = os.path.relpath(path, self._project_root)
        except ValueError:
            return
        rc, _, err = self._git_run("restore", "--staged", "--", rel)
        if rc == 0:
            self._refresh_vcs_status()
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Git Unstage Failed", err[:200])
    def _git_ignore_file(self, path: str):
        if not isinstance(path, str) or not path:
            return
        try:
            rel = os.path.relpath(path, self._project_root)
        except ValueError:
            return
        gi_path = os.path.join(self._project_root, ".gitignore")
        try:
            with open(gi_path, "a", encoding="utf-8") as f:
                f.write(f"\n/{rel}\n")
            self._refresh_vcs_status()
        except OSError as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Could not update .gitignore:\n{e}")
def _undo_file_op_impl(self):
        try:
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit) and fw.isReadOnly() is False:
                try:
                    if fw.isUndoAvailable():
                        fw.undo()
                        return
                except Exception:
                    return
        except Exception:
            pass
        if not self._file_undo:
            return
        op = self._file_undo.pop()
        self._in_file_undo = True
        try:
            kind = op.get("kind")
            if kind == "rename":
                old = op.get("old")
                new = op.get("new")
                if new and old and os.path.exists(new) and not os.path.exists(old):
                    try:
                        os.rename(new, old)
                    except Exception:
                        pass
            elif kind == "move":
                for src, dst in reversed(op.get("items", [])):
                    if dst and os.path.exists(dst) and not os.path.exists(src):
                        try:
                            os.makedirs(os.path.dirname(src), exist_ok=True)
                            shutil.move(dst, src)
                        except Exception:
                            pass
            elif kind == "copy":
                for src, dst in reversed(op.get("items", [])):
                    if dst and os.path.exists(dst):
                        self._fs_remove(dst)
            elif kind == "delete":
                for orig, backup in op.get("items", []):
                    if backup and os.path.exists(backup) and not os.path.exists(orig):
                        try:
                            os.makedirs(os.path.dirname(orig), exist_ok=True)
                            shutil.move(backup, orig)
                        except Exception:
                            pass
            elif kind == "create":
                paths = op.get("paths", [])
                trash_items = []
                try:
                    trash_dir = os.path.join(self._trash_base(), f"create_{int(time.time()*1000)}")
                    os.makedirs(trash_dir, exist_ok=True)
                except Exception:
                    trash_dir = self._trash_base()
                for p in reversed(paths):
                    if p and os.path.exists(p):
                        b = os.path.join(trash_dir, os.path.basename(p))
                        k = 1
                        bb = b
                        while os.path.exists(bb):
                            base, ext = os.path.splitext(os.path.basename(p))
                            bb = os.path.join(trash_dir, f"{base} ({k}){ext}")
                            k += 1
                        try:
                            shutil.move(p, bb)
                            trash_items.append((p, bb))
                        except Exception:
                            pass
                op["trash_items"] = trash_items
                op["trash_dir"] = trash_dir
            self._file_redo.append(op)
        finally:
            self._in_file_undo = False
        try:
            try:
                k = op.get("kind")
                if k == "rename":
                    self._invalidate_dir_size(op.get("old", ""))
                    self._invalidate_dir_size(op.get("new", ""))
                elif k in ("move", "copy"):
                    for s, d in op.get("items", []):
                        self._invalidate_dir_size(s)
                        self._invalidate_dir_size(d)
                elif k == "delete":
                    for o, _b in op.get("items", []):
                        self._invalidate_dir_size(o)
                elif k == "create":
                    for p in op.get("paths", []):
                        self._invalidate_dir_size(p)
            except Exception:
                pass
            self._refresh()
        except Exception:
            pass
def _redo_file_op_impl(self):
        try:
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit) and fw.isReadOnly() is False:
                try:
                    if fw.isRedoAvailable():
                        fw.redo()
                        return
                except Exception:
                    return
        except Exception:
            pass
        if not self._file_redo:
            return
        op = self._file_redo.pop()
        self._in_file_undo = True
        try:
            kind = op.get("kind")
            if kind == "rename":
                old = op.get("old")
                new = op.get("new")
                if old and new and os.path.exists(old) and not os.path.exists(new):
                    try:
                        os.rename(old, new)
                    except Exception:
                        pass
            elif kind == "move":
                for src, dst in op.get("items", []):
                    if src and os.path.exists(src) and not os.path.exists(dst):
                        try:
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.move(src, dst)
                        except Exception:
                            pass
                    elif src and os.path.exists(src) and os.path.exists(dst):
                        alt = self._unique_dst(os.path.dirname(dst), os.path.basename(dst))
                        try:
                            shutil.move(src, alt)
                        except Exception:
                            pass
            elif kind == "copy":
                for src, dst in op.get("items", []):
                    if src and os.path.exists(src):
                        target = dst
                        if os.path.exists(target):
                            target = self._unique_dst(os.path.dirname(dst), os.path.basename(dst))
                        self._fs_copy(src, target)
            elif kind == "delete":
                for orig, backup in op.get("items", []):
                    if orig and os.path.exists(orig):
                        try:
                            os.makedirs(os.path.dirname(backup), exist_ok=True)
                            shutil.move(orig, backup)
                        except Exception:
                            pass
            elif kind == "create":
                for p, b in op.get("trash_items", []):
                    if b and os.path.exists(b) and not os.path.exists(p):
                        try:
                            os.makedirs(os.path.dirname(p), exist_ok=True)
                            shutil.move(b, p)
                        except Exception:
                            pass
            self._file_undo.append(op)
        finally:
            self._in_file_undo = False
        try:
            try:
                k = op.get("kind")
                if k == "rename":
                    self._invalidate_dir_size(op.get("old", ""))
                    self._invalidate_dir_size(op.get("new", ""))
                elif k in ("move", "copy"):
                    for s, d in op.get("items", []):
                        self._invalidate_dir_size(s)
                        self._invalidate_dir_size(d)
                elif k == "delete":
                    for o, _b in op.get("items", []):
                        self._invalidate_dir_size(o)
                elif k == "create":
                    for p, _b in op.get("trash_items", []):
                        self._invalidate_dir_size(p)
            except Exception:
                pass
            self._refresh()
        except Exception:
            pass
