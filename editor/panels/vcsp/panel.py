# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os, threading
from PyQt6.QtWidgets import QDialog, QDockWidget, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QProgressBar, QPushButton, QSplitter, QTabWidget, QToolBar, QVBoxLayout, QWidget
from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from core.config.editor_scale import scale
from .commit import _CommitPanel, _CreateRepoDialog, _RepoSetupWorker
from .diff import _DiffView
from .git import _Git, _parse_porcelain
from .widgets import _BranchList, _LogTree, _RemoteWidget, _StashList, _StatusTree

class VcsPanel(QDockWidget):
    _status_result_ready = pyqtSignal(int, str)
    def __init__(self, parent=None):
        super().__init__("Version Control", parent)
        self.setObjectName("VersionControlDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures( QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self._git = _Git()
        self._project_path: str = ""
        self._recent_commits: list[dict] = []
        self._branches_text: str = ""
        self._branches_list: list[str] = []
        self._status_entries: list[dict] = []
        self._last_status_output: str = ""
        self._status_refreshing: bool = False
        self._status_pending: bool = False
        self._watch_timer = QTimer(self)
        self._watch_timer.timeout.connect(self._on_timer)
        self._watch_interval: int = 3000
        self._diff_cache: dict[str, str] = {}
        self._status_result_ready.connect(self._on_status_result)
        self._setup_ui()
        self._watch_timer.start(self._watch_interval)
        self._on_timer()
    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(scale(16), scale(16)))
        toolbar.setMovable(False)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_all)
        toolbar.addWidget(self._refresh_btn)
        self._repo_label = QLabel(" No repo ")
        self._repo_label.setStyleSheet("padding: 2px 6px;")
        toolbar.addWidget(self._repo_label)
        self._branch_label = QLabel("")
        self._branch_label.setStyleSheet("padding: 2px 6px; font-weight: bold;")
        toolbar.addWidget(self._branch_label)
        self._ahead_behind_label = QLabel("")
        toolbar.addWidget(self._ahead_behind_label)
        toolbar.addSeparator()
        self._stash_btn = QPushButton("Stash")
        self._stash_btn.clicked.connect(self._stash_push)
        toolbar.addWidget(self._stash_btn)
        toolbar.addSeparator()
        self._create_repo_btn = QPushButton("Create Repo")
        self._create_repo_btn.setToolTip("Create repository on GitHub")
        self._create_repo_btn.clicked.connect(self._create_repo)
        toolbar.addWidget(self._create_repo_btn)
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(scale(150))
        self._progress.setMaximumHeight(scale(14))
        self._progress.hide()
        toolbar.addWidget(self._progress)
        layout.addWidget(toolbar)
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._status_tree = _StatusTree()
        self._status_tree.file_selected.connect(self._on_file_selected)
        self._status_tree.file_action_requested.connect(self._on_file_action)
        top_splitter.addWidget(self._status_tree)
        tabs = QTabWidget()
        self._diff_view = _DiffView()
        tabs.addTab(self._diff_view, "Diff")
        self._log_tree = _LogTree()
        self._log_tree.commit_selected.connect(self._on_commit_selected)
        tabs.addTab(self._log_tree, "Log")
        self._branch_list = _BranchList()
        self._branch_list.branch_selected.connect(self._switch_branch)
        tabs.addTab(self._branch_list, "Branches")
        self._stash_list = _StashList()
        self._stash_list.stash_action.connect(self._on_stash_action)
        tabs.addTab(self._stash_list, "Stashes")
        self._remote_widget = _RemoteWidget()
        self._remote_widget.push_requested.connect(self._on_push)
        self._remote_widget.pull_requested.connect(self._on_pull)
        self._remote_widget.fetch_requested.connect(self._on_fetch)
        tabs.addTab(self._remote_widget, "Remotes")
        tabs.currentChanged.connect(self._on_tab_changed)
        top_splitter.addWidget(tabs)
        top_splitter.setSizes([scale(300), scale(500)])
        main_splitter.addWidget(top_splitter)
        self._commit_panel = _CommitPanel()
        self._commit_panel.commit_requested.connect(self._on_commit)
        main_splitter.addWidget(self._commit_panel)
        main_splitter.setSizes([scale(400), scale(120)])
        layout.addWidget(main_splitter)
        self.setWidget(w)
    def _try_detect(self):
        eng = None
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
        except Exception:
            pass
        project_path = ""
        if eng:
            project_path = getattr(eng, "_project_path", "") or ""
        self._project_path = project_path
        if not project_path:
            self._repo_label.setText(" No project open ")
            self._branch_label.setText("")
            self._ahead_behind_label.setText("")
            self._commit_panel.set_status("Open a project to use Version Control")
            self._set_widgets_enabled(False)
            return False
        self._set_widgets_enabled(True)
        if self._git.detect(project_path):
            self._repo_label.setText(f" {os.path.basename(self._git.repo_root)} ")
            self._repo_label.setToolTip(self._git.repo_root)
            return True
        else:
            self._repo_label.setText(" No repository ")
            self._branch_label.setText("")
            self._ahead_behind_label.setText("")
            self._commit_panel.set_status("Project has no git repository")
            return False
    def _set_widgets_enabled(self, enabled: bool):
        for w in [self._status_tree, self._commit_panel, self._stash_btn, self._diff_view, self._log_tree, self._branch_list, self._stash_list, self._remote_widget]:
            w.setEnabled(enabled)
    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._watch_timer.isActive():
            self._watch_timer.start(self._watch_interval)
        self._on_timer()
    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._watch_timer.stop()
    def _on_timer(self):
        if not self.isVisible():
            return
        eng = None
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
        except Exception:
            pass
        current_path = getattr(eng, "_project_path", "") if eng else ""
        if current_path != self._project_path:
            self._git._repo_root = ""
            self._git._cwd = ""
            self._try_detect()
        if self._git.repo_root:
            self._refresh_status()
        else:
            self._refresh_all()
    def _refresh_all(self):
        if not self._git.available:
            return
        if not self._git.repo_root:
            self._try_detect()
            if not self._git.repo_root:
                return
        self._refresh_branch_info()
        self._refresh_status()
        self._refresh_log()
        self._refresh_branches()
        self._refresh_stashes()
        self._refresh_remotes()
        self._refresh_tags()
    def _refresh_branch_info(self):
        branch = self._git.current_branch()
        if branch:
            self._branch_label.setText(f" [{branch}] ")
            self._branch_label.setToolTip(f"Current branch: {branch}")
        ab = self._git.ahead_behind(branch) if branch else ""
        self._ahead_behind_label.setText(ab)
    def _refresh_status(self):
        if not self._git.repo_root:
            return
        if self._status_refreshing:
            self._status_pending = True
            return
        self._status_refreshing = True
        threading.Thread(target=self._status_worker, daemon=True).start()
    def _status_worker(self):
        try:
            rc, out, _ = self._git.status()
        except Exception:
            rc, out = -3, ""
        self._status_result_ready.emit(rc, out)
    def _on_status_result(self, rc: int, out: str):
        self._status_refreshing = False
        try:
            if rc == 0 and self._git.repo_root and out != self._last_status_output:
                self._last_status_output = out
                self._status_entries = _parse_porcelain(out)
                self._status_tree.set_entries(self._status_entries)
                staged = sum(1 for e in self._status_entries if e["staged"])
                unstaged = sum(1 for e in self._status_entries
                               if not e["staged"] and e["status"] != "untracked")
                untracked = sum(1 for e in self._status_entries if e["status"] == "untracked")
                conflicts = sum(1 for e in self._status_entries if e["status"] == "conflict")
                parts = []
                if conflicts:
                    parts.append(f"Conflicts: {conflicts}")
                if staged:
                    parts.append(f"Staged: {staged}")
                if unstaged:
                    parts.append(f"Modified: {unstaged}")
                if untracked:
                    parts.append(f"Untracked: {untracked}")
                self._commit_panel.set_status(" | ".join(parts) if parts else " Working tree clean")
                self._diff_cache.clear()
        except RuntimeError:
            return
        if self._status_pending:
            self._status_pending = False
            self._refresh_status()
    def _refresh_log(self):
        commits = self._git.log(100)
        if commits != self._recent_commits:
            self._recent_commits = commits
            graph_text = self._git.log_graph(100)
            self._log_tree.set_log(graph_text, commits)
    def _refresh_branches(self):
        rc, out, _ = self._git.branch_list()
        if rc == 0:
            self._branches_text = out
            current = self._git.current_branch()
            self._branch_list.set_branches(out, current)
            self._branches_list = []
            for line in out.strip().split("\n"):
                line = line.strip()
                if line:
                    name = line[2:] if line.startswith("* ") else line
                    self._branches_list.append(name.strip())
            self._remote_widget.set_remotes(self._git.remotes(), self._branches_list, current)
    def _refresh_stashes(self):
        stashes = self._git.stash_list()
        self._stash_list.set_stashes(stashes)
    def _refresh_remotes(self):
        remotes = self._git.remotes()
        self._remote_widget.set_remotes(remotes, self._branches_list, self._git.current_branch())
    def _refresh_tags(self):
        pass
    def _on_file_selected(self, path: str, staged: bool):
        cache_key = f"{'staged' if staged else 'unstaged'}:{path}"
        if cache_key in self._diff_cache:
            self._diff_view.show_diff(self._diff_cache[cache_key])
            return
        diff = self._git.file_diff(path, staged)
        self._diff_cache[cache_key] = diff
        self._diff_view.show_diff(diff)
    def _on_file_action(self, path: str, action: str):
        if action == "stage":
            rc, _, err = self._git.add([path])
            if rc == 0:
                self._refresh_status()
                self._commit_panel.set_status(f"Staged: {path}")
            else:
                self._commit_panel.set_status(f"Error: {err}")
        elif action == "unstage":
            rc, _, err = self._git.unstage([path])
            if rc == 0:
                self._refresh_status()
                self._commit_panel.set_status(f"Unstaged: {path}")
            else:
                self._commit_panel.set_status(f"Error: {err}")
        elif action == "discard":
            reply = QMessageBox.question( self, "Discard Changes", f"Discard changes in {path}?\nThis cannot be undone.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                rc, _, err = self._git.restore([path])
                if rc == 0:
                    self._refresh_status()
                    self._commit_panel.set_status(f"Restored: {path}")
                else:
                    self._commit_panel.set_status(f"Error: {err}")
        elif action == "open":
            full = os.path.join(self._git.repo_root, path)
            try:
                os.startfile(full)
            except Exception:
                pass
        elif action == "gitignore":
            gi_path = os.path.join(self._git.repo_root, ".gitignore")
            try:
                with open(gi_path, "a", encoding="utf-8") as f:
                    f.write(f"\n/{path}\n")
                self._refresh_status()
                self._commit_panel.set_status(f"Added {path} to .gitignore")
            except Exception as e:
                self._commit_panel.set_status(f"Error: {e}")
    def _on_commit(self, message: str, amend: bool, signoff: bool):
        rc, out, err = self._git.commit(message, amend, signoff)
        if rc == 0:
            self._commit_panel.clear_message()
            self._commit_panel.set_status(f"Committed: {message}")
            self._refresh_all()
        else:
            err_str = err or out
            self._commit_panel.set_status(f"Commit failed: {err_str[:200]}")
    def _on_commit_selected(self, rev: str):
        detail = self._git.show_commit(rev)
        idx = self._log_tree.parent().indexOf(self._log_tree)
        if idx >= 0:
            parent_tabs = self._log_tree.parent()
            for i in range(parent_tabs.count()):
                if parent_tabs.widget(i) is self._diff_view:
                    parent_tabs.setCurrentIndex(i)
                    break
        self._diff_view.show_diff(detail)
    def _switch_branch(self, name: str):
        current = self._git.current_branch()
        if name == current:
            return
        reply = QMessageBox.question( self, "Switch Branch", f"Switch to branch '{name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        rc, out, err = self._git.switch_branch(name)
        if rc == 0:
            self._commit_panel.set_status(f"Switched to branch '{name}'")
            self._refresh_all()
        else:
            self._commit_panel.set_status(f"Error: {err or out}")
    def _delete_branch(self, name: str):
        current = self._git.current_branch()
        if name == current:
            self._commit_panel.set_status("Cannot delete current branch")
            return
        reply = QMessageBox.question( self, "Delete Branch", f"Delete branch '{name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        rc, out, err = self._git.delete_branch(name)
        if rc == 0:
            self._commit_panel.set_status(f"Deleted branch '{name}'")
            self._refresh_branches()
        else:
            self._commit_panel.set_status(f"Error: {err or out}")
    def _merge_branch(self, name: str):
        reply = QMessageBox.question( self, "Merge Branch", f"Merge '{name}' into current branch?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        rc, out, err = self._git.merge_branch(name)
        if rc == 0:
            self._commit_panel.set_status(f"Merged '{name}'")
            self._refresh_all()
        else:
            self._commit_panel.set_status(f"Merge error: {err or out}")
    def _stash_push(self):
        msg, ok = QInputDialog.getText(self, "Stash Changes", "Stash message (optional):")
        if not ok:
            return
        rc, out, err = self._git.stash_push(msg)
        if rc == 0:
            self._commit_panel.set_status("Changes stashed")
            self._refresh_all()
        else:
            self._commit_panel.set_status(f"Stash error: {err or out}")
    def _on_stash_action(self, ref: str, action: str):
        if action == "pop":
            rc, out, err = self._git.stash_pop(ref)
            if rc == 0:
                self._commit_panel.set_status(f"Popped {ref}")
                self._refresh_all()
            else:
                self._commit_panel.set_status(f"Error: {err or out}")
        elif action == "drop":
            reply = QMessageBox.question( self, "Drop Stash", f"Drop {ref}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                rc, out, err = self._git.stash_drop(ref)
                if rc == 0:
                    self._commit_panel.set_status(f"Dropped {ref}")
                    self._refresh_stashes()
                else:
                    self._commit_panel.set_status(f"Error: {err or out}")
    def _on_push(self, remote: str, branch: str):
        self._progress.show()
        self._progress.setValue(0)
        self._progress.setRange(0, 0)
        proc = self._git.push(remote, branch)
        proc.finished.connect(lambda rc, out, err: self._on_async_done( rc, out, err, "Push"))
        self._commit_panel.set_status(f"Pushing to {remote}/{branch or '(current)'}...")
    def _on_pull(self, remote: str, branch: str):
        self._progress.show()
        self._progress.setRange(0, 0)
        proc = self._git.pull(remote, branch)
        proc.finished.connect(lambda rc, out, err: self._on_async_done( rc, out, err, "Pull"))
        self._commit_panel.set_status(f"Pulling from {remote}/{branch or '(current)'}...")
    def _on_fetch(self, remote: str):
        self._progress.show()
        self._progress.setRange(0, 0)
        proc = self._git.fetch(remote)
        proc.finished.connect(lambda rc, out, err: self._on_async_done( rc, out, err, "Fetch"))
        self._commit_panel.set_status(f"Fetching from {remote}...")
    def _on_async_done(self, rc: int, out: str, err: str, label: str):
        self._progress.hide()
        if rc == 0:
            self._commit_panel.set_status(f"{label} completed")
            QTimer.singleShot(500, self._refresh_all)
        else:
            err_msg = err or out
            self._commit_panel.set_status(f"{label} failed: {err_msg[:200]}")
            self._diff_view.show_diff(f"--- {label} Output ---\n{out}\n{err}")
    def _on_tab_changed(self, index: int):
        tab = self.sender()
        if tab and tab.widget(index) is self._log_tree:
            self._refresh_log()
    def _create_repo(self):
        if not self._project_path:
            self._commit_panel.set_status("Open a project first")
            return
        dlg = _CreateRepoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        r = dlg.result
        if not r:
            return
        self._progress.show()
        self._progress.setRange(0, 0)
        self._progress.setValue(0)
        self._set_widgets_enabled(False)
        self._create_repo_btn.setEnabled(False)
        self._commit_panel.set_status("Creating GitHub repository...")
        self._worker = _RepoSetupWorker( self._git._path, self._project_path, r)
        self._worker.status_update.connect(self._commit_panel.set_status)
        self._worker.done.connect(self._on_repo_setup_done)
        self._worker.start()
    def _on_repo_setup_done(self, rc: int, repo_url: str, error: str):
        self._progress.hide()
        self._set_widgets_enabled(True)
        self._create_repo_btn.setEnabled(True)
        if rc == 0:
            self._commit_panel.set_status(f"Repository ready: {repo_url}")
            self._git.detect(self._project_path)
            self._refresh_all()
        else:
            self._commit_panel.set_status(f"Repo setup failed: {error[:200]}")
    def load_config(self, config):
        pass
