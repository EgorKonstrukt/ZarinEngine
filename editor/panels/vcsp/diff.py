# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json, os, subprocess
import urllib.error
import urllib.request
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout
from PySide6.QtCore import QProcess
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument
from core.config.editor_scale import scale
from .git import _open_url

class _DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, doc: QTextDocument):
        super().__init__(doc)
        self._file_hdr_fmt = QTextCharFormat()
        self._file_hdr_fmt.setForeground(QColor("#569cd6"))
        self._file_hdr_fmt.setFontWeight(700)
        self._add_fmt = QTextCharFormat()
        self._add_fmt.setForeground(QColor("#6a9955"))
        self._del_fmt = QTextCharFormat()
        self._del_fmt.setForeground(QColor("#f44747"))
        self._hunk_fmt = QTextCharFormat()
        self._hunk_fmt.setForeground(QColor("#dcdcaa"))

    def highlightBlock(self, text: str) -> None:
        if not text:
            return
        if text.startswith("+++") or text.startswith("---"):
            self.setFormat(0, len(text), self._file_hdr_fmt)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk_fmt)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self._add_fmt)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._del_fmt)


class _DiffView(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Courier New", 10))
        self.setLineWrapMode(self.LineWrapMode.NoWrap)
        self.setTabStopDistance(scale(24))
        self._highlighter = _DiffHighlighter(self.document())

    def show_diff(self, diff_text: str):
        self.setPlainText(diff_text)

    def clear_diff(self):
        self.clear()


def _find_gh() -> str:
    for candidate in ["gh.exe", "gh"]:
        try:
            r = subprocess.run([candidate, "--version"], capture_output=True,
                               text=True, timeout=5)
            if r.returncode == 0:
                return candidate
        except FileNotFoundError:
            continue
    extra_dirs = [
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.path.expanduser("~\\scoop\\apps\\gh\\current\\bin"),
        os.path.expanduser("~\\AppData\\Local\\GitHubCLI"),
        "C:\\Program Files\\GitHub CLI",
        "C:\\Program Files (x86)\\GitHub CLI",
        "C:\\ProgramData\\chocolatey\\bin",
    ]
    seen = set()
    for base in extra_dirs:
        if not base or base in seen:
            continue
        seen.add(base)
        for exe in ["gh.exe", "gh"]:
            full = os.path.join(base, exe)
            if os.path.isfile(full):
                return full
    return ""


def _gh_run(gh: str, args: list[str], cwd: str | None = None,
            timeout: int = 60) -> tuple[int, str, str]:
    try:
        r = subprocess.run([gh] + args, capture_output=True, text=True,
                           cwd=cwd, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -3, "", str(e)


def _github_api(url: str, token: str, data: dict | None = None,
                method: str = "GET") -> tuple[int, dict | str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ZarinEngine",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    if method != "GET" and body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, str(e)
    except urllib.error.URLError as e:
        return -1, str(e)


def _github_create_repo(token: str, name: str, description: str = "",
                        private: bool = False,
                        gitignore_template: str = "",
                        license_template: str = "") -> tuple[int, str]:
    data: dict = {
        "name": name,
        "description": description,
        "private": private,
    }
    if gitignore_template:
        data["gitignore_template"] = gitignore_template
    if license_template:
        data["license_template"] = license_template
    status, result = _github_api(
        "https://api.github.com/user/repos", token, data, "POST")
    if status in (200, 201):
        if isinstance(result, dict):
            return 0, result.get("clone_url", "")
        return 0, str(result)
    if isinstance(result, dict):
        msg = result.get("message", str(result))
        errors = result.get("errors", [])
        if errors:
            msg += ": " + "; ".join(
                e.get("message", "") for e in errors)
        return status, msg
    return status, str(result)


class _GhLoginDialog(QDialog):
    def __init__(self, gh_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GitHub Login")
        self.setMinimumSize(scale(500), scale(320))
        self._gh = gh_path
        self._success = False
        self._setup_ui()
        self._start_login()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        header = QLabel("GitHub Device Authorization")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Courier New", 10))
        self._output.setMinimumHeight(scale(160))
        layout.addWidget(self._output)

        hint = QLabel(
            "A browser will open with a one-time code.\n"
            "Enter the code shown above and authorize the application.\n"
            "After authorization, this dialog will close automatically.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

    def _start_login(self):
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._proc.start(self._gh, ["auth", "login", "-s", "repo"])

    def _on_output(self):
        data = self._proc.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        self._output.appendPlainText(text)
        lower = text.lower()
        if "http" in lower and ("github" in lower or "device" in lower):
            for word in text.split():
                if word.startswith("http"):
                    _open_url(word.rstrip(".,;"))
                    break
        elif "one-time code" in lower:
            self._output.setStyleSheet("background: #1e1e1e; color: #fff; font-size: 14px;")
        self._output.verticalScrollBar().setValue(
            self._output.verticalScrollBar().maximum())

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        if exit_code == 0:
            self._success = True
            self._output.appendPlainText("\nLogin successful!")
        else:
            err = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
            self._output.appendPlainText(f"\nLogin failed (exit code {exit_code}): {err[:200]}")
        self._cancel_btn.setText("Close")

    def done(self, rc: int):
        if self._success:
            super().done(QDialog.DialogCode.Accepted)
        else:
            super().done(rc)
