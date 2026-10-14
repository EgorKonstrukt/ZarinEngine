# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import qtawesome as qta
from PyQt6.QtGui import QAction, QKeySequence, QFont
from PyQt6.QtWidgets import QMenu, QMessageBox, QInputDialog, QDialog, QVBoxLayout, QPlainTextEdit

from editor.panels.vcsp import _Git, _DiffView


def _setup_vcs_menu(mw, vcs_menu):
    _qta = lambda n, c=chr(35) + "d4d4c0": qta.icon(n, color=c)
    _act_commit = QAction(_qta("fa5s.check-circle"), "Commit...", mw)
    _act_commit.setShortcut(QKeySequence("Ctrl+Shift+C"))
    _act_commit.triggered.connect(lambda: _vcs_commit(mw))
    vcs_menu.addAction(_act_commit)
    _act_diff = QAction(_qta("fa5s.file-alt"), "Diff...", mw)
    _act_diff.setShortcut(QKeySequence("Ctrl+Shift+D"))
    _act_diff.triggered.connect(lambda: _vcs_diff(mw))
    vcs_menu.addAction(_act_diff)
    _act_history = QAction(_qta("fa5s.history"), "Show History", mw)
    _act_history.setShortcut(QKeySequence("Ctrl+Shift+H"))
    _act_history.triggered.connect(lambda: _vcs_log(mw))
    vcs_menu.addAction(_act_history)
    _act_vcs_panel = QAction(_qta("fa5s.code-branch"), "Version Control Panel", mw)
    _act_vcs_panel.setShortcut(QKeySequence("Ctrl+Shift+V"))
    _act_vcs_panel.triggered.connect(lambda: mw._vcs.show() or mw._vcs.raise_())
    vcs_menu.addAction(_act_vcs_panel)
    vcs_menu.addSeparator()
    push_menu = vcs_menu.addMenu("Push")
    _act_push = QAction("Push to origin", mw)
    _act_push.triggered.connect(lambda: _vcs_push(mw, "origin"))
    push_menu.addAction(_act_push)
    _act_push_all = QAction("Push to all remotes", mw)
    _act_push_all.triggered.connect(lambda: _vcs_push_all(mw))
    push_menu.addAction(_act_push_all)
    pull_menu = vcs_menu.addMenu("Pull")
    _act_pull = QAction("Pull from origin", mw)
    _act_pull.triggered.connect(lambda: _vcs_pull(mw, "origin"))
    pull_menu.addAction(_act_pull)
    _act_fetch = QAction(_qta("fa5s.cloud-download-alt"), "Fetch", mw)
    _act_fetch.triggered.connect(lambda: _vcs_fetch(mw))
    vcs_menu.addAction(_act_fetch)
    vcs_menu.addSeparator()
    branch_menu = vcs_menu.addMenu("Branch")
    _act_new_branch = QAction(_qta("fa5s.code-branch"), "New Branch...", mw)
    _act_new_branch.triggered.connect(lambda: _vcs_new_branch(mw))
    branch_menu.addAction(_act_new_branch)
    _act_switch = QAction(_qta("fa5s.code-branch"), "Switch Branch...", mw)
    _act_switch.triggered.connect(lambda: _vcs_switch_branch(mw))
    branch_menu.addAction(_act_switch)
    branch_menu.addSeparator()
    _act_show_branches = QAction(_qta("fa5s.list-ul"), "Show All Branches", mw)
    _act_show_branches.triggered.connect(lambda: _vcs_show_branches(mw))
    branch_menu.addAction(_act_show_branches)
    stash_menu = vcs_menu.addMenu("Stash")
    _act_stash_push = QAction(_qta("fa5s.box"), "Stash Changes...", mw)
    _act_stash_push.triggered.connect(lambda: _vcs_stash_push(mw))
    stash_menu.addAction(_act_stash_push)
    _act_stash_pop = QAction(_qta("fa5s.box-open"), "Pop Stash...", mw)
    _act_stash_pop.triggered.connect(lambda: _vcs_stash_pop(mw))
    stash_menu.addAction(_act_stash_pop)
    vcs_menu.addSeparator()
    _act_create_repo = QAction(_qta("fa5s.folder-plus"), "Create Repository...", mw)
    _act_create_repo.triggered.connect(lambda: _vcs_create_repo(mw))
    vcs_menu.addAction(_act_create_repo)


def _vcs_git(mw) -> _Git | None:
    if hasattr(mw, "_vcs") and hasattr(mw._vcs, "_git"):
        return mw._vcs._git
    g = _Git()
    eng = getattr(mw, "_engine", None)
    if eng:
        project_path = getattr(eng, "_project_path", "")
        if project_path:
            g.detect(project_path)
    return g


def _vcs_ensure_repo(mw) -> bool:
    git = _vcs_git(mw)
    if git and git.available and git.repo_root:
        return True
    QMessageBox.information(mw, "No Repository", "No git repository detected.")
    return False


def _vcs_commit(mw):
    if not _vcs_ensure_repo(mw):
        return
    msg, ok = QInputDialog.getText(mw, "Commit", "Commit message:")
    if not ok or not msg.strip():
        return
    git = _vcs_git(mw)
    rc, out, err = git.run_sync("commit", "-m", msg.strip())
    if rc == 0:
        QMessageBox.information(mw, "Committed", f"Committed:\n{msg.strip()}")
        if hasattr(mw, "_vcs"):
            mw._vcs._refresh_all()
    else:
        QMessageBox.critical(mw, "Commit Failed", f"Error:\n{err or out}")


def _vcs_diff(mw):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    rc, out, _ = git.run_sync("diff", "--no-color")
    if not out.strip():
        rc2, out2, _ = git.run_sync("diff", "--cached", "--no-color")
        out = out2
    if not out.strip():
        out = "No changes against HEAD"
    dlg = QDialog(mw)
    dlg.setWindowTitle("Working Tree Diff")
    dlg.setMinimumSize(700, 500)
    layout = QVBoxLayout(dlg)
    dv = _DiffView()
    dv.show_diff(out)
    layout.addWidget(dv)
    dlg.exec()


def _vcs_log(mw):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    rc, out, _ = git.run_sync("log", "--oneline", "--graph", "--decorate", "--all", "-50")
    if rc != 0 or not out.strip():
        out = "No commits yet."
    dlg = QDialog(mw)
    dlg.setWindowTitle("Git Log")
    dlg.setMinimumSize(700, 500)
    layout = QVBoxLayout(dlg)
    te = QPlainTextEdit()
    te.setReadOnly(True)
    te.setFont(QFont("Courier New", 10))
    te.setPlainText(out)
    layout.addWidget(te)
    dlg.exec()


def _vcs_push(mw, remote: str):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    proc = git.push(remote)
    proc.finished.connect(lambda rc, out, err: _vcs_async_done(mw, rc, out, err, f"Push to {remote}"))
    if hasattr(mw, "_vcs"):
        mw._vcs._progress.show()
        mw._vcs._progress.setRange(0, 0)


def _vcs_push_all(mw):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    for remote in git.remotes():
        proc = git.push(remote["name"])
        proc.finished.connect(lambda rc, out, err, r=remote["name"]: _vcs_async_done(mw, rc, out, err, f"Push to {r}"))


def _vcs_pull(mw, remote: str):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    proc = git.pull(remote)
    proc.finished.connect(lambda rc, out, err: _vcs_async_done(mw, rc, out, err, f"Pull from {remote}"))


def _vcs_fetch(mw):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    proc = git.fetch()
    proc.finished.connect(lambda rc, out, err: _vcs_async_done(mw, rc, out, err, "Fetch"))


def _vcs_async_done(mw, rc, out, err, label):
    if hasattr(mw, "_vcs"):
        mw._vcs._progress.hide()
    if rc == 0:
        if hasattr(mw, "_vcs"):
            mw._vcs._commit_panel.set_status(f"{label} completed")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, mw._vcs._refresh_all)
        QMessageBox.information(mw, label, f"{label} completed successfully.")
    else:
        QMessageBox.critical(mw, f"{label} Failed", f"{err or out}")


def _vcs_new_branch(mw):
    if not _vcs_ensure_repo(mw):
        return
    name, ok = QInputDialog.getText(mw, "New Branch", "Branch name:")
    if not ok or not name.strip():
        return
    git = _vcs_git(mw)
    rc, out, err = git.create_branch(name.strip())
    if rc == 0:
        QMessageBox.information(mw, "Branch Created", f"Branch '{name.strip()}' created.")
        if hasattr(mw, "_vcs"):
            mw._vcs._refresh_branches()
    else:
        QMessageBox.critical(mw, "Branch Failed", f"Error:\n{err or out}")


def _vcs_switch_branch(mw):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    rc, out, _ = git.run_sync("branch", "-a")
    if rc != 0:
        return
    branches = [b.strip() for b in out.strip().split("\n") if b.strip()]
    lines = []
    for b in branches:
        name = b[2:] if b.startswith("* ") else b
        lines.append(name)
    current = git.current_branch()
    dlg = QInputDialog(mw)
    dlg.setWindowTitle("Switch Branch")
    dlg.setLabelText(f"Current: {current}\nSelect branch:")
    dlg.setComboBoxItems(lines)
    dlg.setOption(QInputDialog.InputDialogOption.UseListViewForComboBoxItems)
    if dlg.exec() != QInputDialog.DialogCode.Accepted:
        return
    target = dlg.textValue()
    if not target or target == current:
        return
    reply = QMessageBox.question(mw, "Switch Branch", f"Switch to '{target}'?",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if reply != QMessageBox.StandardButton.Yes:
        return
    rc, out, err = git.switch_branch(target)
    if rc == 0:
        QMessageBox.information(mw, "Switched", f"Switched to '{target}'")
        if hasattr(mw, "_vcs"):
            mw._vcs._refresh_all()
    else:
        QMessageBox.critical(mw, "Switch Failed", f"Error:\n{err or out}")


def _vcs_show_branches(mw):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    rc, out, _ = git.run_sync("branch", "-a")
    if rc != 0:
        out = "No branches."
    dlg = QDialog(mw)
    dlg.setWindowTitle("Branches")
    dlg.setMinimumSize(500, 400)
    layout = QVBoxLayout(dlg)
    te = QPlainTextEdit()
    te.setReadOnly(True)
    te.setFont(QFont("Courier New", 10))
    te.setPlainText(out)
    layout.addWidget(te)
    dlg.exec()


def _vcs_stash_push(mw):
    if not _vcs_ensure_repo(mw):
        return
    msg, ok = QInputDialog.getText(mw, "Stash Changes", "Stash message (optional):")
    if not ok:
        return
    git = _vcs_git(mw)
    rc, out, err = git.stash_push(msg)
    if rc == 0:
        QMessageBox.information(mw, "Stashed", "Changes stashed.")
        if hasattr(mw, "_vcs"):
            mw._vcs._refresh_all()
    else:
        QMessageBox.critical(mw, "Stash Failed", f"Error:\n{err or out}")


def _vcs_stash_pop(mw):
    if not _vcs_ensure_repo(mw):
        return
    git = _vcs_git(mw)
    stashes = git.stash_list()
    if not stashes:
        QMessageBox.information(mw, "No Stashes", "No stashes found.")
        return
    ref = stashes[0]["ref"]
    rc, out, err = git.stash_pop(ref)
    if rc == 0:
        QMessageBox.information(mw, "Popped", f"Popped {ref}")
        if hasattr(mw, "_vcs"):
            mw._vcs._refresh_all()
    else:
        QMessageBox.critical(mw, "Pop Failed", f"Error:\n{err or out}")


def _vcs_create_repo(mw):
    if hasattr(mw, "_vcs"):
        mw._vcs._create_repo()
