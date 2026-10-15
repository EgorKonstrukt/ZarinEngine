# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import subprocess, sys
from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import QApplication
try:
    import editor.icons as qta
except ImportError:
    qta = None
_QTA_COLORS = {
    "folder": "#d4d4d4",
    "file": "#d4d4d4",
    "nav": "#d4d4d4",
    "create": "#9ccc65",
    "refresh": "#d4d4d4",
    "dual": "#d4d4d4",
    "view": "#d4d4d4",
}
def _qta_icon(name: str, color: str | None = None) -> QIcon:
    if qta is None:
        return QIcon()
    c = color if color else _QTA_COLORS.get(name.split(".")[-1] if "." in name else name, "#d4d4d4")
    return qta.icon(name, color=c)
def _system_accent() -> QColor:
    try:
        app = QApplication.instance()
        if app is not None:
            c = app.palette().color(QPalette.ColorRole.Highlight)
            if c.isValid():
                return c
    except Exception:
        pass
    try:
        if sys.platform == "win32":
            import winreg
            for sub in ("Software\\Microsoft\\Windows\\DWM", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Accent"):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                        for val in ("AccentColor", "AccentColorMenu"):
                            try:
                                v, _ = winreg.QueryValueEx(k, val)
                                b = v & 0xFF
                                g = (v >> 8) & 0xFF
                                r = (v >> 16) & 0xFF
                                if r + g + b > 30:
                                    return QColor(r, g, b)
                            except Exception:
                                continue
                except Exception:
                    continue
    except Exception:
        pass
    return QColor("#0078d7")
def _accent_hex() -> str:
    try:
        return _system_accent().name()
    except Exception:
        return "#0078d7"
def _accent_rgba(alpha: int) -> str:
    try:
        c = _system_accent()
        return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"
    except Exception:
        return f"rgba(0,120,215,{alpha})"
_ENTITY_MIME = "application/x-zpe-entity"
_VCS_COLORS = {
    "untracked": QColor("#3C9B3C"),
    "added":     QColor("#3C9B3C"),
    "modified":  QColor("#3C6E9B"),
    "staged":    QColor("#3C6E9B"),
    "unstaged":  QColor("#3C6E9B"),
    "deleted":   QColor("#9B3C3C"),
    "conflict":  QColor("#9B3C3C"),
    "renamed":   QColor("#9B6E3C"),
}
def _parse_vcs_status(project_path: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for candidate in ["git.exe", "git"]:
        try:
            r = subprocess.run([candidate, "--version"], capture_output=True,
                               text=True, timeout=5)
            if r.returncode == 0:
                break
        except FileNotFoundError:
            continue
    else:
        return result
    try:
        r = subprocess.run([candidate, "status", "--porcelain", "-u"],
                           capture_output=True, text=True,
                           cwd=project_path, timeout=15)
    except Exception:
        return result
    for line in r.stdout.strip().split("\n"):
        line = line.rstrip()
        if not line or len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:]
        if xy[0] == "?" and xy[1] == "?":
            result[path.replace("\\", "/")] = "untracked"
        elif xy[0] == "A" or xy[0] == "A ":
            result[path.replace("\\", "/")] = "added"
        elif xy[0] == "M" or xy[1] == "M":
            result[path.replace("\\", "/")] = "modified"
        elif xy[0] == "D" or xy[1] == "D":
            result[path.replace("\\", "/")] = "deleted"
        elif xy[0] == "R" or xy[1] == "R":
            result[path.replace("\\", "/")] = "renamed"
        elif xy[0] == "U" or xy[1] == "U":
            result[path.replace("\\", "/")] = "conflict"
    return result
