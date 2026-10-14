# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os, threading
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import QDialog, QFileDialog, QMenu, QMessageBox, QTreeWidgetItem
from editor.panels import pkgcore as core
from editor.panels.pkgmgr.bridge import _TaskBridge
from editor.panels.pkgmgr.dialogs import _DownloadDialog, _InstallDialog
FILTER_ALL = "All"
FILTER_UPDATES = "Updates available"
FILTER_UPTODATE = "Up to date"
TREE_DEPS = "Dependencies"
TREE_REVERSE = "Dependents"
class PackageManagerOpsMixin:
    def _set_busy(self, busy: bool):
        self._busy = max(0, self._busy + (1 if busy else -1))
        running = self._busy > 0
        self._progress.setRange(0, 0 if running else 1)
        self._stop_btn.setEnabled(running)
        for b in (self._install_btn, self._update_all_btn, self._refresh_btn, self._check_btn, self._import_btn, self._download_btn):
            b.setEnabled(not running)
    def _cancel_running(self):
        self._cancel.set()
        self._append_log("Stopping current operation...")
    def _run_async(self, work, on_done=None, on_failed=None, on_line=None):
        bridge = _TaskBridge(self)
        if on_line is not None:
            bridge.line.connect(on_line)
        if on_done is not None:
            bridge.done.connect(on_done)
        if on_failed is not None:
            bridge.failed.connect(on_failed)
        else:
            bridge.failed.connect(self._on_task_failed)
        def runner():
            try:
                result = work(bridge)
                bridge.done.emit(result)
            except Exception as e:
                bridge.failed.emit(str(e))
        self._set_busy(True)
        threading.Thread(target=runner, daemon=True).start()
        return bridge
    def _on_task_failed(self, message: str):
        self._set_busy(False)
        self._append_log(f"ERROR: {message}")
        self._status.setText("Ready")
    def _pip_task(self, args: list[str], label: str, after=None):
        self._append_log(f"$ pip {' '.join(args)}")
        def work(bridge):
            def on_line(line):
                bridge.line.emit(line)
            code = core.run_pip_streaming(args, on_line=on_line, cancel_event=self._cancel)
            return code
        def on_line(line):
            self._append_log(line)
        def on_done(code):
            self._set_busy(False)
            self._cancel.clear()
            self._append_log(f"{label} finished with code {code}")
            if after is not None:
                after(code)
            self.refresh(check_updates=False)
        self._run_async(work, on_done=on_done, on_line=on_line)
    def refresh(self, check_updates: bool = True):
        self._status.setText("Reading installed packages...")
        known_latest = dict(self._latest)
        def load(bridge):
            return core.list_installed(with_size=True)
        def check(bridge):
            return core.check_outdated()
        def on_outdated(result):
            outdated, raw = result
            self._set_busy(False)
            merged = dict(self._latest)
            merged.update(outdated)
            self._latest = {k: v for k, v in merged.items() if k in self._by_key}
            self._apply_latest()
            self._fill_table()
            self._update_status()
            updates = sum(1 for p in self._packages if p.status == "update")
            self._append_log(f"Update check done: {updates} package(s) can be updated")
            if raw and not outdated and "ERROR" in raw.upper():
                self._append_log(raw)
        def on_loaded(packages):
            self._packages = packages
            self._by_key = {p.key: p for p in packages}
            self._latest = {k: v for k, v in known_latest.items() if k in self._by_key}
            self._apply_latest()
            self._set_busy(False)
            self._fill_table()
            self._fill_tree()
            self._update_details()
            self._update_status()
            self._append_log(f"Loaded {len(packages)} installed packages")
            if check_updates:
                self._status.setText("Checking for updates...")
                self._run_async(check, on_done=on_outdated)
        self._run_async(load, on_done=on_loaded)
    def _apply_latest(self):
        for p in self._packages:
            latest = self._latest.get(p.key, "")
            p.latest = latest
            if not latest:
                p.status = "editable" if p.editable else "unknown"
            elif latest == p.version:
                p.status = "up to date"
            else:
                p.status = "update"
    def _flush_pending_detail(self):
        name = self._pending_detail
        self._pending_detail = ""
        if name:
            self._fetch_online_details(name)
    def _fetch_online_details(self, name: str):
        if self._client.cached_project(name) is not None:
            try:
                meta = self._client.metadata(name)
            except Exception:
                return
            self._apply_online_details(name, meta)
            return
        def work(bridge):
            return self._client.metadata(name)
        def on_done(meta):
            self._set_busy(False)
            self._apply_online_details(name, meta)
        self._run_async(work, on_done=on_done)
    def _apply_online_details(self, name: str, meta: dict):
        keys = self._selected_keys()
        if len(keys) != 1:
            return
        p = self._by_key.get(keys[0])
        if p is None or core.normalize_name(p.name) != core.normalize_name(name):
            return
        if meta.get("version"):
            self._detail_fields["latest"].setText(str(meta["version"]))
        self._detail_fields["requires_python"].setText(str(meta.get("requires_python") or "-"))
        if meta.get("home_page"):
            self._detail_fields["home_page"].setText(str(meta["home_page"]))
        if meta.get("author") and not p.author:
            self._detail_fields["author"].setText(str(meta["author"]))
        if meta.get("license") and not p.license:
            self._detail_fields["license"].setText(str(meta["license"])[:120])
        online_reqs = meta.get("requires_dist") or []
        if online_reqs:
            existing = {self._detail_requires.topLevelItem(i).text(0).replace("  [extra]", "") for i in range(self._detail_requires.topLevelItemCount())}
            for raw in online_reqs:
                req = core.parse_requirement(raw)
                if req.display in existing:
                    continue
                target = self._by_key.get(req.key)
                label = req.display
                if core.requirement_is_optional(req):
                    label += "  [extra]"
                node = QTreeWidgetItem([label, target.version if target else "missing"])
                if target is None:
                    node.setForeground(1, QColor(chr(35) + "e06c75"))
                self._detail_requires.addTopLevelItem(node)
        latest = str(meta.get("version") or "")
        if latest and latest != self._latest.get(p.key):
            self._latest[p.key] = latest
            p.latest = latest
            self._apply_latest()
            self._fill_table()
    def _copy_tree(self):
        lines = []
        def walk(item: QTreeWidgetItem, depth: int):
            text = "  " * depth + item.text(0)
            if item.text(1) and item.text(1) != "-":
                text += f" {item.text(1)}"
            if item.text(2):
                text += f"  {item.text(2)}"
            if item.text(3):
                text += f"  [{item.text(3)}]"
            lines.append(text)
            for i in range(item.childCount()):
                walk(item.child(i), depth + 1)
        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i), 0)
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))
        self._status.setText("Dependency tree copied to clipboard")
    def _jump_to_item_package(self, item: QTreeWidgetItem, *_):
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key:
            key = core.normalize_name(item.text(0))
        self._select_key_in_table(key)
    def _select_key_in_table(self, key: str):
        key = core.normalize_name(key)
        self._search.clear()
        self._filter.setCurrentText(FILTER_ALL)
        self._fill_table()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                self._table.clearSelection()
                self._table.selectRow(row)
                self._table.scrollToItem(item)
                return
    def _tree_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if item is None:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole) or ""
        menu = QMenu(self)
        act_select = menu.addAction("Select in list")
        act_deps = menu.addAction("Show dependencies")
        act_rev = menu.addAction("Show dependents")
        act_pypi = menu.addAction("Open on PyPI")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen is act_select:
            self._select_key_in_table(key)
        elif chosen is act_deps:
            self._tree_mode.setCurrentText(TREE_DEPS)
            self._tree_scope.setChecked(True)
            self._select_key_in_table(key)
            self._fill_tree()
        elif chosen is act_rev:
            self._tree_mode.setCurrentText(TREE_REVERSE)
            self._tree_scope.setChecked(True)
            self._select_key_in_table(key)
            self._fill_tree()
        elif chosen is act_pypi:
            self._show_on_pypi(item.text(0))
    def _table_context_menu(self, pos):
        keys = self._selected_keys()
        menu = QMenu(self)
        act_install = menu.addAction("Install package...")
        act_update = menu.addAction("Update selected")
        act_uninstall = menu.addAction("Uninstall selected")
        menu.addSeparator()
        act_spec = menu.addAction("Install specific version...")
        act_download = menu.addAction("Download wheel...")
        menu.addSeparator()
        act_deps = menu.addAction("Show dependency tree")
        act_rev = menu.addAction("Show dependents")
        act_pypi = menu.addAction("Open on PyPI")
        act_copy = menu.addAction("Copy name==version")
        act_loc = menu.addAction("Open location")
        act_update.setEnabled(bool(keys))
        act_uninstall.setEnabled(bool(keys))
        act_spec.setEnabled(len(keys) == 1)
        act_download.setEnabled(bool(keys))
        act_deps.setEnabled(bool(keys))
        act_rev.setEnabled(bool(keys))
        act_pypi.setEnabled(len(keys) == 1)
        act_copy.setEnabled(bool(keys))
        act_loc.setEnabled(len(keys) == 1)
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_install:
            self._open_install()
        elif chosen is act_update:
            self._update_selected()
        elif chosen is act_uninstall:
            self._uninstall_selected()
        elif chosen is act_spec:
            self._open_install(package_name=self._by_key[keys[0]].name)
        elif chosen is act_download:
            self._open_download()
        elif chosen is act_deps:
            self._tree_mode.setCurrentText(TREE_DEPS)
            self._tree_scope.setChecked(True)
            self._fill_tree()
            self._tabs.setCurrentIndex(1)
        elif chosen is act_rev:
            self._tree_mode.setCurrentText(TREE_REVERSE)
            self._tree_scope.setChecked(True)
            self._fill_tree()
            self._tabs.setCurrentIndex(1)
        elif chosen is act_pypi:
            self._show_on_pypi(self._by_key[keys[0]].name)
        elif chosen is act_copy:
            text = "\n".join(f"{p.name}=={p.version}" for p in self._selected_packages())
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self._status.setText("Copied to clipboard")
        elif chosen is act_loc:
            path = self._by_key[keys[0]].location
            if path and os.path.isdir(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    def _show_on_pypi(self, name: str):
        QDesktopServices.openUrl(QUrl(core.PYPI_PROJECT_URL.format(name=core.normalize_name(name))))
    def _open_install(self, package_name: str = ""):
        if not isinstance(package_name, str):
            package_name = ""
        dlg = _InstallDialog(self, self._client, package_name, self._index)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        spec = dlg.spec()
        if not spec:
            return
        self._cancel.clear()
        self._pip_task(core.install_args(spec, upgrade=dlg.upgrade_enabled(), no_deps=dlg.no_deps_enabled(), pre=dlg.pre_enabled(), extra=dlg.extra_args()), "Install")
    def _open_download(self):
        selected = self._selected_packages()
        default_spec = selected[0].name if selected else ""
        dlg = _DownloadDialog(self, default_spec)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        spec = dlg.spec()
        if not spec:
            return
        dest = dlg.destination()
        os.makedirs(dest, exist_ok=True)
        self._cancel.clear()
        self._pip_task(core.download_args(spec, dest, with_deps=dlg.with_deps(), pre=dlg.pre_enabled()), "Download")
    def _update_selected(self):
        packages = self._selected_packages()
        if not packages:
            QMessageBox.information(self, "Update", "Select one or more packages first.")
            return
        self._cancel.clear()
        names = [p.name for p in packages]
        self._pip_task(core.install_args(names, upgrade=True), "Update")
    def _update_all(self):
        self._status.setText("Checking for updates...")
        def work(bridge):
            outdated, raw = core.check_outdated()
            return outdated, raw
        def on_done(result):
            self._set_busy(False)
            outdated, raw = result
            if not outdated:
                self._append_log("Everything is up to date")
                self._status.setText("Everything is up to date")
                self.refresh()
                return
            names = sorted(outdated.keys())
            self._append_log(f"Updating {len(names)} packages: {', '.join(names)}")
            self._cancel.clear()
            self._pip_task(core.install_args(names, upgrade=True), "Update all")
        self._run_async(work, on_done=on_done)
    def _uninstall_selected(self):
        packages = self._selected_packages()
        if not packages:
            QMessageBox.information(self, "Uninstall", "Select one or more packages first.")
            return
        names = ", ".join(p.name for p in packages)
        answer = QMessageBox.question(self, "Uninstall packages", f"Uninstall {len(packages)} package(s)?\n\n{names}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._cancel.clear()
        self._pip_task(core.uninstall_args([p.name for p in packages]), "Uninstall")
    def _check_updates_online(self):
        self._status.setText("Querying PyPI...")
        names = [p.name for p in self._packages]
        if not names:
            return
        def work(bridge):
            def on_result(name, latest):
                bridge.line.emit(f"{name} -> {latest}")
            return core.fetch_latest_versions(names, client=self._client, on_result=on_result)
        def on_line(line):
            self._append_log(line)
        def on_done(result):
            self._set_busy(False)
            self._latest.update(result)
            self._apply_latest()
            self._fill_table()
            self._update_details()
            updates = sum(1 for p in self._packages if p.status == "update")
            self._status.setText(f"PyPI check done: {len(result)} resolved, {updates} updates available")
            self._append_log(f"PyPI check done: {updates} updates available")
        self._run_async(work, on_done=on_done, on_line=on_line)
    def _export_requirements(self):
        packages = self._visible_packages() or self._packages
        path, _ = QFileDialog.getSaveFileName(self, "Export requirements.txt", "requirements.txt", "Requirements (*.txt);;All files (*.*)")
        if not path:
            return
        try:
            core.write_requirements(path, packages, pinned=True)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self._append_log(f"Exported {len(packages)} packages to {path}")
        self._status.setText(f"Exported {len(packages)} packages")
    def _install_requirements(self):
        path, _ = QFileDialog.getOpenFileName(self, "Install from requirements.txt", "", "Requirements (*.txt);;All files (*.*)")
        if not path:
            return
        self._cancel.clear()
        self._pip_task(["install", "-r", path], "Install requirements")
    def _freeze_to_log(self):
        def work(bridge):
            code, out = core.run_pip_capture(["freeze"])
            return code, out
        def on_done(result):
            self._set_busy(False)
            code, out = result
            self._append_log(out.strip() or "(empty)")
            self._status.setText("pip freeze output written to log")
        self._run_async(work, on_done=on_done)
    def _update_status(self):
        updates = sum(1 for p in self._packages if p.status == "update")
        total_size = sum(p.size for p in self._packages)
        self._status.setText(f"Python {core.python_version_label()} \u00b7 {core.python_executable()} \u00b7 {len(self._packages)} packages \u00b7 {core.format_size(total_size)} \u00b7 {updates} updates")
    def closeEvent(self, event):
        self._cancel.set()
        super().closeEvent(event)
