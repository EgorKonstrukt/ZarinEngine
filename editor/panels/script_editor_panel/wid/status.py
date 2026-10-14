# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QMessageBox
from PyQt6.QtGui import QFont, QColor

from core.config.editor_scale import scale

from ..tabsp import ScriptTab
from .. import ot as ot_mod


class StatusMixin:

    def _try_detect_repo(self):
        eng = None
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
        except Exception:
            pass
        if eng and self._git is not None:
            project_path = getattr(eng, "_project_path", "") or ""
            if project_path:
                try:
                    self._git_available = self._git.detect(project_path)
                except Exception:
                    self._git_available = False
                self._update_vcs_statusbar()
                return
        self._git_available = False
        self._update_vcs_statusbar()

    def _vcs_timer_tick(self):
        if not self.isVisible():
            return
        eng = None
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
        except Exception:
            pass
        if eng:
            project_path = getattr(eng, "_project_path", "") or ""
            if project_path:
                if project_path != self._vcs_last_project:
                    self._vcs_last_project = project_path
                    try:
                        self._git_available = self._git.detect(project_path) if self._git is not None else False
                    except Exception:
                        self._git_available = False
                    self._vcs_last_file = ""
                    self._vcs_branch_time = 0.0
                tab = self._current_tab()
                file_path = tab._file_path if tab and tab._file_path else ""
                if file_path != self._vcs_last_file:
                    self._vcs_last_file = file_path
                    if tab and file_path and self._git_available:
                        tab._editor.vcs_refresh()
                self._update_vcs_statusbar()

    def _vcs_commit(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            QMessageBox.information(self, "No Repository", "No git repository detected.")
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        rc, _, _ = self._git.add([rel])
        if rc != 0:
            QMessageBox.warning(self, "Stage Failed", "Failed to stage file.")
            return
        from PyQt6.QtWidgets import QInputDialog
        msg, ok = QInputDialog.getText(self, "Commit", "Commit message:")
        if not ok or not msg.strip():
            self._git.unstage([rel])
            return
        rc, out, err = self._git.commit(msg.strip())
        if rc == 0:
            QMessageBox.information(self, "Committed", f"Committed:{chr(10)}{msg.strip()}")
            tab._editor.vcs_refresh()
            self._update_vcs_statusbar()
        else:
            QMessageBox.critical(self, "Commit Failed", f"Error:{chr(10)}{err or out}")

    def _vcs_diff(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        diff = self._git.file_diff(rel)
        if not diff:
            diff = self._git.file_diff(rel, staged=True)
        if not diff:
            diff = "No changes against HEAD"
        from editor.panels.vcsp import _DiffView
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Diff: {os.path.basename(tab._file_path)}")
        dlg.setMinimumSize(scale(700), scale(500))
        layout = QVBoxLayout(dlg)
        diff_view = _DiffView()
        diff_view.show_diff(diff)
        layout.addWidget(diff_view)
        dlg.exec()

    def _vcs_history(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        rc, out, _ = self._git.run_sync("log", "--oneline", "--decorate", "--", rel, timeout=15)
        if rc != 0 or not out.strip():
            QMessageBox.information(self, "History", "No history for this file.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"History: {os.path.basename(tab._file_path)}")
        dlg.setMinimumSize(scale(600), scale(400))
        layout = QVBoxLayout(dlg)
        te = QPlainTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Courier New", 10))
        te.setPlainText(out)
        layout.addWidget(te)
        dlg.exec()

    def _vcs_revert(self):
        tab = self._current_tab()
        if not tab or not tab._file_path:
            return
        if not self._git_available or not self._git.repo_root:
            return
        reply = QMessageBox.question(
            self, "Revert File",
            f"Discard all changes to {os.path.basename(tab._file_path)}?{chr(10)}"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            rel = os.path.relpath(tab._file_path, self._git.repo_root)
        except ValueError:
            return
        rel = rel.replace("\\", "/")
        rc, _, err = self._git.restore([rel])
        if rc == 0:
            tab.open_file(tab._file_path)
            self._update_vcs_statusbar()
        else:
            QMessageBox.critical(self, "Revert Failed", f"Error:{chr(10)}{err}")

    def _on_cursor(self, line: int, col: int):
        self._status_pos.setText(f"Ln {line}, Col {col}")

    def _on_modified(self, modified: bool):
        tab = self._current_tab()
        if tab is not None:
            self._status_info.setText("Modified" if modified else "")

    def _on_local_text_changed(self):
        self._auto_save_timer.start(2000)

    def _do_auto_save(self):
        tab = self._current_tab()
        if tab is None or not tab._file_path or not tab._dirty:
            return
        try:
            with open(tab._file_path, "w", encoding="utf-8") as f:
                f.write(tab._editor.toPlainText())
            tab._dirty = False
            tab._editor.document().setModified(False)
            tab._editor.vcs_set_file(tab._file_path)
            tab._update_title()
            if tab._file_path:
                self.collab_file_saved.emit(tab._file_path, tab._editor.toPlainText())
        except Exception:
            pass

    def _on_op_captured(self, tab, pos: int, removed: int, added: str):
        path = tab._file_path
        if not path:
            return
        self._pending_local_ops.setdefault(path, []).append((pos, removed, added))
        self._ops_buffers.setdefault(path, []).append((pos, removed, added))
        if not self._ops_flush_timer.isActive():
            self._ops_flush_timer.start(100)

    def _flush_and_send_ops(self):
        for path, buffer in list(self._ops_buffers.items()):
            if buffer:
                batch = list(buffer)
                buffer.clear()
                self.collab_ops_ready.emit(path, batch)

    def apply_remote_ops(self, path: str, ops: list):
        from PyQt6.QtGui import QTextCursor as _QTC
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, ScriptTab) and tab._file_path == path:
                editor = tab._editor
                pending = list(self._pending_local_ops.get(path, []))
                transformed = []
                for rop in ops:
                    for lop in pending:
                        rop = ot_mod.transform_op(rop, lop)
                    transformed.append(rop)
                editor._suppress_ops = True
                editor.document().blockSignals(True)
                for pos, removed, added in transformed:
                    if pos < 0:
                        continue
                    text_len = len(editor.toPlainText())
                    if removed and removed > 0 and pos + removed > text_len:
                        continue
                    tc = editor.textCursor()
                    tc.setPosition(pos)
                    if removed and removed > 0:
                        end = min(pos + removed, text_len)
                        tc.setPosition(end, _QTC.MoveMode.KeepAnchor)
                    tc.insertText(added)
                editor.document().blockSignals(False)
                editor._old_text = editor.toPlainText()
                editor._suppress_ops = False
                new_pending = []
                for lop in pending:
                    for rop in transformed:
                        lop = ot_mod.transform_op(lop, rop)
                    new_pending.append(lop)
                self._pending_local_ops[path] = new_pending
                return

    def clear_pending_ops(self, path: str):
        self._pending_local_ops.pop(path, None)
        self._ops_buffers.pop(path, None)

    def _do_full_sync(self):
        tab = self._current_tab()
        if tab and tab._file_path:
            self.clear_pending_ops(tab._file_path)
            self.collab_file_saved.emit(tab._file_path, tab._editor.toPlainText())

    def _on_local_cursor_moved(self):
        self._cursor_sync_timer.start(50)

    def _send_cursor_sync(self):
        tab = self._current_tab()
        if tab is None or not tab._file_path:
            return
        cursor = tab._editor.textCursor()
        pos = cursor.position()
        self.collab_cursor_changed.emit(tab._file_path, pos, cursor.anchor(), pos)

    def update_remote_cursor(self, peer_id: str, path: str, pos: int, sel_anchor: int, sel_end: int, color: list[float], name: str):
        if not path:
            return
        cursors_for_path = self._remote_cursors.setdefault(path, {})
        cursors_for_path[peer_id] = {
            "pos": pos,
            "sel_anchor": sel_anchor,
            "sel_end": sel_end,
            "color": QColor.fromRgbF(*color[:3]),
            "name": name,
        }
        tab = self._current_tab()
        if tab and tab._file_path == path:
            tab._editor.set_remote_cursors(cursors_for_path)

    def _update_label(self):
        tab = self._current_tab()
        if tab is None:
            self._file_label.setText("  No file")
        elif tab._file_path:
            self._file_label.setText(f"  {os.path.basename(tab._file_path)}")
        else:
            self._file_label.setText("  Untitled Script")

    def _update_vcs_statusbar(self):
        import time as _time
        branch = ""
        status = ""
        if self._git_available and self._git is not None:
            try:
                repo = self._git.repo_root
            except Exception:
                repo = ""
            if repo:
                if _time.perf_counter() - self._vcs_branch_time > 30.0 or not self._vcs_cached_branch:
                    try:
                        self._vcs_cached_branch = self._git.current_branch() or ""
                    except Exception:
                        self._vcs_cached_branch = ""
                    self._vcs_branch_time = _time.perf_counter()
                branch = self._vcs_cached_branch
                tab = self._current_tab()
                if isinstance(tab, ScriptTab):
                    ed = tab._editor
                    file_status = ed.vcs_file_status()
                    if file_status:
                        status_labels = {
                            "modified": " modified",
                            "untracked": " untracked",
                            "deleted": " deleted",
                            "conflict": " conflict",
                        }
                        status = status_labels.get(file_status, file_status)
        if branch:
            self._vcs_branch_label.setText(f"  [{branch}]  ")
            self._vcs_branch_label.show()
            self._vcs_status_label.setText(status)
            self._vcs_status_label.show()
        else:
            self._vcs_branch_label.hide()
            self._vcs_status_label.hide()
