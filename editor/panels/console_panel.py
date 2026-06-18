from __future__ import annotations
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QCheckBox, QLabel, QLineEdit,
                              QStyle, QTextBrowser)
from PyQt6.QtCore import QTimer, QByteArray, QBuffer
from PyQt6.QtGui import QFont
from core.logger import Logger, LogLevel, LogEntry
import time as _time
import re

_LEVEL_META = {
    LogLevel.DEBUG:   ("#c0c0c0", "#2d2d2d", QStyle.StandardPixmap.SP_ArrowRight),
    LogLevel.INFO:    ("#ffffff", "#1a2a4a", QStyle.StandardPixmap.SP_MessageBoxInformation),
    LogLevel.WARNING: ("#ffffff", "#3a2e00", QStyle.StandardPixmap.SP_MessageBoxWarning),
    LogLevel.ERROR:   ("#ffffff", "#4a1a1a", QStyle.StandardPixmap.SP_MessageBoxCritical),
}

_NUM_RE = re.compile(r"\d+(\.\d+)?")


def _normalize(msg: str) -> str:
    return _NUM_RE.sub("{n}", msg)


def _fmt_time(ts: float) -> str:
    return _time.strftime("%H:%M:%S", _time.localtime(ts))


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ConsoleGroup:
    def __init__(self, entry: LogEntry):
        self.message: str = entry.message
        self._pattern: str = _normalize(entry.message)
        self.level: LogLevel = entry.level
        self.traceback: str = entry.traceback_str or ""
        self.count: int = 1
        self.entries: list[LogEntry] = [entry]
        self.expanded: bool = False

    def matches(self, entry: LogEntry) -> bool:
        return (self._pattern == _normalize(entry.message)
                and self.level == entry.level
                and (entry.traceback_str or "") == self.traceback)


class ConsolePanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Console", parent)
        self._show_debug: bool = True
        self._show_info: bool = True
        self._show_warning: bool = True
        self._show_error: bool = True
        self._filter_text: str = ""
        self._font_family: str = "Segoe UI"
        self._font_size: int = 10
        self._max_groups: int = 500
        self._refresh_interval: int = 100
        self._groups: list[ConsoleGroup] = []
        self._icon_cache: dict[QStyle.StandardPixmap, str] = {}
        self._setup_ui()
        Logger.add_listener(self._on_log_entry)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._flush_pending)
        self._refresh_timer.start(self._refresh_interval)
        self._pending: list[LogEntry] = []

    def load_config(self, config) -> None:
        self._font_family = config.get("console.font_family", self._font_family)
        self._font_size = config.get("console.font_size", self._font_size)
        self._max_groups = config.get("console.max_blocks", self._max_groups)
        self._refresh_interval = config.get("console.refresh_interval", self._refresh_interval)
        self._refresh_timer.setInterval(self._refresh_interval)
        font = QFont(self._font_family, self._font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._browser.setFont(font)

    def _icon_uri(self, sp: QStyle.StandardPixmap) -> str:
        if sp not in self._icon_cache:
            pix = self.style().standardIcon(sp).pixmap(16, 16)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            pix.save(buf, "PNG")
            buf.close()
            self._icon_cache[sp] = "data:image/png;base64," + ba.toBase64().data().decode()
        return self._icon_cache[sp]

    def _setup_ui(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        toolbar = QHBoxLayout()

        clear_btn = QPushButton()
        clear_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        clear_btn.setToolTip("Clear Console")
        clear_btn.setFixedWidth(28)
        clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(clear_btn)

        coll_btn = QPushButton()
        coll_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        coll_btn.setToolTip("Collapse All")
        coll_btn.setFixedWidth(28)
        coll_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(coll_btn)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter...")
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_edit, 1)

        self._dbg_cb = QCheckBox("Debug")
        self._dbg_cb.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self._dbg_cb.setChecked(True)
        self._dbg_cb.toggled.connect(lambda v: setattr(self, "_show_debug", v) or self._rebuild())
        toolbar.addWidget(self._dbg_cb)

        self._info_cb = QCheckBox("Info")
        self._info_cb.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self._info_cb.setChecked(True)
        self._info_cb.toggled.connect(lambda v: setattr(self, "_show_info", v) or self._rebuild())
        toolbar.addWidget(self._info_cb)

        self._warn_cb = QCheckBox("Warn")
        self._warn_cb.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning))
        self._warn_cb.setChecked(True)
        self._warn_cb.toggled.connect(lambda v: setattr(self, "_show_warning", v) or self._rebuild())
        toolbar.addWidget(self._warn_cb)

        self._err_cb = QCheckBox("Error")
        self._err_cb.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical))
        self._err_cb.setChecked(True)
        self._err_cb.toggled.connect(lambda v: setattr(self, "_show_error", v) or self._rebuild())
        toolbar.addWidget(self._err_cb)

        toolbar.addStretch()

        self._dbg_count = QLabel("0")
        self._dbg_count.setStyleSheet("color: #888; padding: 0 4px;")
        toolbar.addWidget(self._dbg_count)
        self._info_count = QLabel("0")
        self._info_count.setStyleSheet("color: #8ab4f8; padding: 0 4px;")
        toolbar.addWidget(self._info_count)
        self._warn_count = QLabel("0")
        self._warn_count.setStyleSheet("color: #f9a825; padding: 0 4px;")
        toolbar.addWidget(self._warn_count)
        self._err_count = QLabel("0")
        self._err_count.setStyleSheet("color: #f14c4c; padding: 0 4px;")
        toolbar.addWidget(self._err_count)

        layout.addLayout(toolbar)

        self._browser = QTextBrowser()
        self._browser.setReadOnly(True)
        self._browser.setOpenExternalLinks(False)
        self._browser.setOpenLinks(False)
        font = QFont(self._font_family, self._font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._browser.setFont(font)
        self._browser.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                border: none;
                padding: 2px;
            }
        """)
        self._browser.anchorClicked.connect(self._on_anchor_clicked)
        layout.addWidget(self._browser)
        self.setWidget(w)

    def _on_anchor_clicked(self, url):
        try:
            idx = int(url.toString())
            if 0 <= idx < len(self._groups):
                self._groups[idx].expanded = not self._groups[idx].expanded
                self._render()
        except ValueError:
            pass

    def _on_log_entry(self, entry: LogEntry):
        self._pending.append(entry)

    def _flush_pending(self):
        if not self._pending:
            return
        entries = self._pending[:]
        self._pending.clear()
        changed = False
        for entry in entries:
            if self._add_entry(entry):
                changed = True
        if changed:
            self._render()
            self._update_counts()

    def _add_entry(self, entry: LogEntry) -> bool:
        if not self._should_show(entry):
            return False
        for g in self._groups:
            if g.matches(entry):
                g.count += 1
                g.entries.append(entry)
                return True
        g = ConsoleGroup(entry)
        self._groups.append(g)
        if len(self._groups) > self._max_groups:
            self._groups.pop(0)
        return True

    def _should_show(self, entry: LogEntry) -> bool:
        if not {LogLevel.DEBUG: self._show_debug, LogLevel.INFO: self._show_info,
                LogLevel.WARNING: self._show_warning, LogLevel.ERROR: self._show_error}.get(entry.level, True):
            return False
        if self._filter_text and self._filter_text.lower() not in entry.message.lower():
            return False
        return True

    def _render(self):
        body_parts = ['<html><body style="margin:0;padding:2px;font-family:monospace;font-size:10pt">']
        for i, g in enumerate(self._groups):
            if not {LogLevel.DEBUG: self._show_debug, LogLevel.INFO: self._show_info,
                    LogLevel.WARNING: self._show_warning, LogLevel.ERROR: self._show_error}.get(g.level, True):
                continue
            if self._filter_text and self._filter_text.lower() not in g.message.lower():
                continue
            fg, bg, sp = _LEVEL_META[g.level]
            icon_uri = self._icon_uri(sp)

            arrow = "&#9660;" if g.expanded else "&#9654;"
            link = f'<a href="{i}" style="color:{fg};text-decoration:none">{arrow}</a>'
            icon = f'<img src="{icon_uri}" width="16" height="16" style="vertical-align:middle;margin:0 4px"/>'
            badge = f'<span style="background:{fg};color:{bg};padding:0 7px;border-radius:3px;font-weight:bold;font-size:9pt;margin:0 6px 0 2px">{g.count}</span>'
            msg = _escape(g.message)

            body = ""
            if g.expanded:
                for e in g.entries:
                    body += f'<div style="padding:1px 0 1px 34px;color:#ddd;font-size:9pt">&nbsp;{_fmt_time(e.timestamp)} {_escape(e.message)}</div>'
                    if e.traceback_str:
                        for tb_line in e.traceback_str.strip().split("\n")[:5]:
                            body += f'<div style="padding:0 0 0 48px;color:#bbb;font-size:8pt">{_escape(tb_line)}</div>'

            div = f'<div style="background:{bg};color:{fg};padding:2px 4px;margin:1px 0;border-radius:3px">{link}{icon}{badge}{msg}{body}</div>'
            body_parts.append(div)

        body_parts.append("</body></html>")
        html = "\n".join(body_parts)

        scroll = self._browser.verticalScrollBar()
        at_bottom = scroll.value() >= scroll.maximum() - 20
        self._browser.setHtml(html)
        if at_bottom:
            QTimer.singleShot(10, lambda: scroll.setValue(scroll.maximum()))

    def _update_counts(self):
        counts = {LogLevel.DEBUG: 0, LogLevel.INFO: 0, LogLevel.WARNING: 0, LogLevel.ERROR: 0}
        for g in self._groups:
            if g.level in counts:
                counts[g.level] += g.count
        self._dbg_count.setText(str(counts[LogLevel.DEBUG]))
        self._info_count.setText(str(counts[LogLevel.INFO]))
        self._warn_count.setText(str(counts[LogLevel.WARNING]))
        self._err_count.setText(str(counts[LogLevel.ERROR]))

    def _collapse_all(self):
        for g in self._groups:
            g.expanded = False
        self._render()

    def _rebuild(self):
        self._groups.clear()
        for entry in Logger.get_entries():
            for g in self._groups:
                if g.matches(entry):
                    g.count += 1
                    g.entries.append(entry)
                    break
            else:
                g = ConsoleGroup(entry)
                self._groups.append(g)
                if len(self._groups) > self._max_groups:
                    self._groups.pop(0)
        self._render()
        self._update_counts()

    def _clear(self):
        Logger.clear()
        self._groups.clear()
        self._browser.clear()
        self._update_counts()

    def _on_filter_changed(self, text: str):
        self._filter_text = text
        self._rebuild()
