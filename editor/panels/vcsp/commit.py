# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json, os, subprocess
from PyQt6.QtWidgets import QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QTextEdit, QVBoxLayout, QWidget
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from core.config.editor_scale import scale
from .diff import _GhLoginDialog, _find_gh, _gh_run, _github_api, _github_create_repo
from .git import _git_run, _open_url

class _CommitPanel(QWidget):
    commit_requested = pyqtSignal(str, bool, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._subject = QLineEdit()
        self._subject.setPlaceholderText("Commit message (Ctrl+Enter to commit)")
        layout.addWidget(self._subject)

        opt_row = QHBoxLayout()
        opt_row.setSpacing(8)
        self._amend_cb = QCheckBox("Amend")
        opt_row.addWidget(self._amend_cb)
        self._signoff_cb = QCheckBox("Sign-off")
        opt_row.addWidget(self._signoff_cb)
        opt_row.addStretch()
        self._commit_btn = QPushButton("Commit")
        self._commit_btn.clicked.connect(self._on_commit)
        opt_row.addWidget(self._commit_btn)
        layout.addLayout(opt_row)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    def _on_commit(self):
        msg = self._subject.text().strip()
        if not msg:
            self._status_label.setText("Commit message is required")
            return
        self.commit_requested.emit(msg, self._amend_cb.isChecked(),
                                   self._signoff_cb.isChecked())

    def clear_message(self):
        self._subject.clear()
        self._amend_cb.setChecked(False)
        self._status_label.setText("")

    def set_status(self, text: str):
        self._status_label.setText(text)


class _RepoSetupWorker(QThread):
    status_update = pyqtSignal(str)
    done = pyqtSignal(int, str, str)

    def __init__(self, git_path: str, project_path: str, config: dict):
        super().__init__()
        self._git_path = git_path
        self._project_path = project_path
        self._config = config

    def run(self):
        self.status_update.emit("Creating GitHub repository...")
        gh = _find_gh()
        repo_url = ""
        if gh and not self._config["token"]:
            args = ["repo", "create", self._config["name"],
                    "--" + ("private" if self._config["private"] else "public"),
                    "--description", self._config["description"] or self._config["name"]]
            if self._config["init_readme"]:
                args.append("--add-readme")
            if self._config["gitignore"]:
                args.extend(["--gitignore", self._config["gitignore"]])
            if self._config["license"]:
                args.extend(["--license", self._config["license"]])
            rc, out, err = _gh_run(gh, args)
            if rc != 0:
                self.done.emit(rc, "", f"GitHub creation failed: {err or out}")
                return
            for line in out.split("\n"):
                if line.startswith("http"):
                    repo_url = line.strip()
                    break
            if not repo_url:
                try:
                    data = json.loads(out)
                    repo_url = data.get("clone_url", data.get("html_url", ""))
                except Exception:
                    repo_url = f"https://github.com/{self._config['name']}.git"
        else:
            token = self._config["token"]
            if not token and not gh:
                self.done.emit(1, "", "GitHub token required")
                return
            if not token:
                self.done.emit(1, "", "gh CLI token not available")
                return
            status, result = _github_create_repo(
                token, self._config["name"], self._config["description"],
                self._config["private"], self._config["gitignore"],
                self._config["license"])
            if status != 0:
                self.done.emit(status, "", f"GitHub API error: {result}")
                return
            repo_url = result if isinstance(result, str) else ""
            if not repo_url.startswith("http"):
                repo_url = f"https://github.com/{self._config['name']}.git"

        self.status_update.emit(f"Setting up local repository...")
        rc, _, err = _git_run(self._git_path, ["init"], cwd=self._project_path)
        if rc != 0:
            self.done.emit(rc, "", f"git init failed: {err}")
            return
        readme_path = os.path.join(self._project_path, "README.md")
        if self._config["init_readme"] and not os.path.exists(readme_path):
            try:
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(f"# {self._config['name']}\n\n{self._config['description']}\n")
            except Exception:
                pass
        self.status_update.emit("Staging files...")
        rc, _, err = _git_run(self._git_path, ["add", "-A"],
                               cwd=self._project_path)
        if rc == 0:
            self.status_update.emit("Creating initial commit...")
            _git_run(self._git_path, ["commit", "-m", "Initial commit"],
                      cwd=self._project_path)

        self.status_update.emit("Adding remote...")
        rc, _, err = _git_run(self._git_path, ["remote", "add", "origin", repo_url],
                               cwd=self._project_path)
        if rc != 0:
            existing, _, _ = _git_run(self._git_path, ["remote", "get-url", "origin"],
                                       cwd=self._project_path)
            if existing.strip():
                _git_run(self._git_path, ["remote", "set-url", "origin", repo_url],
                          cwd=self._project_path)

        self.status_update.emit("Pushing to GitHub...")
        rc, out, err = _git_run(self._git_path, ["push", "-u", "origin", "HEAD"],
                                 cwd=self._project_path, timeout=120)
        if rc != 0:
            self.done.emit(rc, repo_url, f"Push failed: {err or out}")
            return
        self.done.emit(0, repo_url, "")


class _CreateRepoDialog(QDialog):
    _GH_CLIENT_ID = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create GitHub Repository")
        self.setMinimumWidth(scale(450))
        self._result: dict | None = None
        self._token: str = ""
        self._auth_method: str = "none"
        self._setup_ui()
        self._check_auth()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("my-awesome-project")
        form.addRow("Repository name:", self._name_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setMaximumHeight(scale(60))
        self._desc_edit.setPlaceholderText("Short description of the project")
        form.addRow("Description:", self._desc_edit)

        vis_group = QGroupBox("Visibility")
        vis_layout = QHBoxLayout(vis_group)
        self._public_rb = QRadioButton("Public")
        self._public_rb.setChecked(True)
        self._private_rb = QRadioButton("Private")
        vis_layout.addWidget(self._public_rb)
        vis_layout.addWidget(self._private_rb)
        vis_layout.addStretch()
        form.addRow(vis_group)

        self._init_readme_cb = QCheckBox("Initialize with README")
        self._init_readme_cb.setChecked(True)
        form.addRow(self._init_readme_cb)

        self._gitignore_combo = QComboBox()
        self._gitignore_combo.setEditable(True)
        self._gitignore_combo.setPlaceholderText("None")
        templates = ["", "Python", "VisualStudio", "C++", "Java",
                      "Node", "Unity", "UnrealEngine", "Rust", "Go",
                      "Ruby", "Swift", "Kotlin", "CMake"]
        for t in templates:
            self._gitignore_combo.addItem(t)
        form.addRow(".gitignore template:", self._gitignore_combo)

        self._license_combo = QComboBox()
        self._license_combo.setEditable(True)
        licenses = ["", "mit", "apache-2.0", "gpl-3.0", "gpl-2.0",
                     "bsd-3-clause", "bsd-2-clause", "mpl-2.0",
                     "lgpl-3.0", "lgpl-2.1", "unlicense"]
        for l in licenses:
            self._license_combo.addItem(l)
        form.addRow("License:", self._license_combo)

        auth_group = QGroupBox("GitHub Authentication")
        auth_layout = QVBoxLayout(auth_group)

        self._auth_status = QLabel("Checking authentication...")
        self._auth_status.setWordWrap(True)
        auth_layout.addWidget(self._auth_status)

        self._login_btn = QPushButton("Login with GitHub (opens browser)")
        self._login_btn.clicked.connect(self._login_github)
        auth_layout.addWidget(self._login_btn)

        self._install_btn = QPushButton("Install gh CLI")
        self._install_btn.clicked.connect(self._install_gh)
        self._install_btn.hide()
        auth_layout.addWidget(self._install_btn)

        manual_group = QGroupBox("Manual Token (alternative)")
        manual_layout = QVBoxLayout(manual_group)
        self._token_edit = QLineEdit()
        self._token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText("ghp_xxxxxxxxxxxxxxxxxxxx")
        manual_layout.addWidget(self._token_edit)
        manual_btn_row = QHBoxLayout()
        self._create_token_btn = QPushButton("Open Token Settings")
        self._create_token_btn.clicked.connect(
            lambda: _open_url("https://github.com/settings/tokens/new?scopes=repo&description=Zarin+Engine"))
        manual_btn_row.addWidget(self._create_token_btn)
        self._use_token_btn = QPushButton("Use This Token")
        self._use_token_btn.clicked.connect(self._use_manual_token)
        manual_btn_row.addWidget(self._use_token_btn)
        manual_layout.addLayout(manual_btn_row)
        manual_label = QLabel("Required scope: repo (Full control of private repositories)")
        manual_label.setWordWrap(True)
        manual_label.setStyleSheet("color: #888; font-size: 10px;")
        manual_layout.addWidget(manual_label)
        auth_layout.addWidget(manual_group)

        form.addRow(auth_group)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _check_auth(self):
        gh = _find_gh()
        if gh:
            self._install_btn.hide()
            rc, out, _ = _gh_run(gh, ["auth", "status"])
            if rc == 0:
                trc, tok, _ = _gh_run(gh, ["auth", "token"])
                if trc == 0:
                    self._token = tok.strip()
                    self._auth_method = "gh"
                    self._auth_status.setText("Authenticated via gh CLI")
                    self._auth_status.setStyleSheet("color: #6a9955; font-weight: bold;")
                    self._login_btn.hide()
                    self._token_edit.setEnabled(False)
                    self._token_edit.setPlaceholderText("Using gh CLI token")
                    return
        self._auth_status.setText("Not authenticated")
        self._auth_status.setStyleSheet("color: #dcdcaa;")
        if not gh:
            self._install_btn.show()

    def _install_gh(self):
        self._install_btn.setEnabled(False)
        self._install_btn.setText("Installing...")
        self._auth_status.setText("Installing gh CLI...")
        QApplication.processEvents()
        attempts = [
            ("winget", ["winget", "install", "--id", "GitHub.cli",
                         "--silent", "--accept-package-agreements",
                         "--accept-source-agreements"]),
            ("scoop", ["scoop", "install", "gh"]),
            ("choco", ["choco", "install", "gh", "-y"]),
        ]
        installed = False
        for name, cmd in attempts:
            try:
                subprocess.run(cmd, capture_output=True, text=True,
                               timeout=120)
            except FileNotFoundError:
                continue
            except Exception:
                continue
            if _find_gh():
                installed = True
                break
        if not installed:
            installed = bool(_find_gh())
        if installed:
            self._check_auth()
            if self._auth_method == "none":
                self._auth_status.setText("gh CLI installed. Click Login.")
                self._auth_status.setStyleSheet("color: #6a9955;")
            self._install_btn.hide()
        else:
            self._auth_status.setText(
                "Could not install automatically.\n"
                "Download from: https://cli.github.com/")
            self._auth_status.setStyleSheet("color: #f44747;")
            self._install_btn.setText("Open Download Page")
            self._install_btn.setEnabled(True)
            self._install_btn.clicked.disconnect()
            self._install_btn.clicked.connect(
                lambda: _open_url("https://cli.github.com/"))

    def _login_github(self):
        gh = _find_gh()
        if gh:
            dlg = _GhLoginDialog(gh, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                trc, tok, _ = _gh_run(gh, ["auth", "token"])
                if trc == 0:
                    self._token = tok.strip()
                    self._auth_method = "gh"
                    self._auth_status.setText("Authenticated via gh CLI")
                    self._auth_status.setStyleSheet("color: #6a9955; font-weight: bold;")
                    self._login_btn.hide()
                    self._token_edit.setPlaceholderText("Using gh CLI token")
                    return
            self._auth_status.setText("Login cancelled or failed")
            self._auth_status.setStyleSheet("color: #f44747;")
        else:
            _open_url("https://cli.github.com/")
            self._auth_status.setText(
                "gh CLI not found. Install it and try again.")
            self._auth_status.setStyleSheet("color: #dcdcaa;")

    def _use_manual_token(self):
        tok = self._token_edit.text().strip()
        if not tok:
            QMessageBox.warning(self, "Empty Token", "Paste your GitHub token first.")
            return
        status, result = _github_api("https://api.github.com/user", tok)
        if status == 200:
            self._token = tok
            self._auth_method = "token"
            username = result.get("login", "?") if isinstance(result, dict) else "?"
            self._auth_status.setText(f"Authenticated as {username}")
            self._auth_status.setStyleSheet("color: #6a9955; font-weight: bold;")
            self._token_edit.setEnabled(False)
        else:
            msg = result.get("message", str(result)) if isinstance(result, dict) else str(result)
            self._auth_status.setText(f"Token invalid: {msg}")
            self._auth_status.setStyleSheet("color: #f44747;")

    def _on_accept(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name",
                                "Repository name is required.")
            return
        if not self._token:
            QMessageBox.warning(self, "Not Authenticated",
                                "Login with GitHub or provide a token first.")
            return
        self._result = {
            "name": name,
            "description": self._desc_edit.toPlainText().strip(),
            "private": self._private_rb.isChecked(),
            "init_readme": self._init_readme_cb.isChecked(),
            "gitignore": self._gitignore_combo.currentText(),
            "license": self._license_combo.currentText(),
            "token": self._token,
        }
        self.accept()

    @property
    def result(self) -> dict | None:
        return self._result
