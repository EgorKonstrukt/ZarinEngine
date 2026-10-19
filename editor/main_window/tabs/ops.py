# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun


from __future__ import annotations

import os

from PySide6.QtCore import Qt


class SceneTabOpsMixin:
    def show_quick_open(self):
        try:
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem
            bar = self._tab_bar
            if bar.count() == 0:
                return
            rows: list[tuple[str, str, str]] = []
            for i in range(bar.count()):
                if self.is_script_tab(i):
                    p = self.script_path_at(i)
                    rows.append(("script", p, os.path.basename(p) or "Untitled"))
                else:
                    nm = self.tab_name_at(i)
                    if nm is None:
                        continue
                    info = self._tabs.get(nm)
                    sub = (info.path or "") if info is not None else ""
                    rows.append(("scene", nm, sub))
            dlg = QDialog(self._mw)
            dlg.setWindowTitle("Go to Tab")
            dlg.resize(520, 380)
            lay = QVBoxLayout(dlg)
            edit = QLineEdit(dlg)
            edit.setPlaceholderText("Type to filter tabs...")
            edit.setClearButtonEnabled(True)
            lay.addWidget(edit)
            lst = QListWidget(dlg)
            lay.addWidget(lst)
            state = {"rows": rows}

            def refilter(text: str):
                lst.clear()
                q = (text or "").lower()
                for kind, key, sub in state["rows"]:
                    hay = (key + " " + sub).lower()
                    if q and q not in hay:
                        continue
                    shown = key + ("  —  " + sub if sub else "")
                    item = QListWidgetItem(shown)
                    item.setData(Qt.ItemDataRole.UserRole, (kind, key))
                    lst.addItem(item)
                if lst.count() > 0:
                    lst.setCurrentRow(0)

            def activate_current():
                item = lst.currentItem()
                if item is None:
                    return
                kind, key = item.data(Qt.ItemDataRole.UserRole)
                dlg.accept()
                if kind == "script":
                    try:
                        self._mw._script_editor._script_widget.open_script(key)
                    except Exception:
                        pass
                else:
                    self.switch_to_tab(key)

            edit.textChanged.connect(refilter)
            edit.returnPressed.connect(activate_current)
            lst.itemDoubleClicked.connect(lambda _item: activate_current())
            refilter("")
            edit.setFocus()
            dlg.exec()
        except Exception:
            pass

    def sort_scene_tabs(self):
        try:
            bar = self._tab_bar
            pinned = sorted([n for n in self._tab_names if self.is_pinned(n)], key=str.lower)
            rest = sorted([n for n in self._tab_names if not self.is_pinned(n)], key=str.lower)
            order = pinned + rest
            if order == list(self._tab_names):
                self.refresh_all_tab_titles()
                return
            cur_data = bar.tabData(bar.currentIndex())
            bar.blockSignals(True)
            self.begin_restore()
            try:
                for i in range(bar.count() - 1, -1, -1):
                    if not self.is_script_tab(i):
                        bar.removeTab(i)
                self._tab_names = []
                for pos, name in enumerate(order):
                    self._tab_names.append(name)
                    idx = bar.insertTab(pos, self._tab_title(self._tabs[name]))
                    bar.setTabData(idx, name)
                    bar.setTabIcon(idx, self._get_zarin_icon())
                    self.refresh_tab_title(name)
                for i in range(bar.count()):
                    if bar.tabData(i) == cur_data:
                        bar.setCurrentIndex(i)
                        break
            finally:
                self.end_restore()
                bar.blockSignals(False)
            self.refresh_all_tab_titles()
        except Exception:
            pass

    def close_fileless_tabs(self):
        try:
            bar = self._tab_bar
            indices = []
            for i in range(bar.count()):
                if self.is_script_tab(i):
                    continue
                nm = self.tab_name_at(i)
                if nm is None:
                    continue
                info = self._tabs.get(nm)
                if info is None or info.prefab_path or info.pinned:
                    continue
                try:
                    if getattr(info, "model_path", "") or "":
                        continue
                except Exception:
                    pass
                if not info.path:
                    indices.append(i)
            indices.sort(reverse=True)
            for i in indices:
                if i < 0 or i >= bar.count():
                    continue
                if not self.close_tab_at(i):
                    break
        except Exception:
            pass

    def _tab_key(self, idx: int):
        try:
            if self.is_script_tab(idx):
                p = self._norm_path(self.script_path_at(idx))
                if p:
                    return ("script-file", p)
                return ("script-untitled", "")
            name = self.tab_name_at(idx)
            if name is None:
                return ("invalid", str(idx))
            info = self._tabs.get(name)
            if info is not None and getattr(info, "path", None):
                return ("scene-file", self._norm_path(info.path))
            return ("scene-name", name)
        except Exception:
            return ("invalid", str(idx))

    def _duplicate_indices(self, idx: int) -> list[int]:
        try:
            if idx < 0 or idx >= self._tab_bar.count():
                return []
            key = self._tab_key(idx)
            out: list[int] = []
            for i in range(self._tab_bar.count()):
                if i == idx:
                    continue
                if self._tab_key(i) == key:
                    out.append(i)
            return out
        except Exception:
            return []

    def duplicate_count(self, idx: int) -> int:
        return len(self._duplicate_indices(idx))

    def _bulk_skips(self, i: int) -> bool:
        try:
            if self.is_script_tab(i):
                return False
            nm = self.tab_name_at(i)
            return nm is not None and self.is_pinned(nm)
        except Exception:
            return False

    def close_other_tabs(self, keep_idx: int):
        try:
            bar = self._tab_bar
            if keep_idx < 0 or keep_idx >= bar.count():
                return
            indices = [i for i in range(bar.count()) if i != keep_idx]
            indices.sort(reverse=True)
            for i in indices:
                if i < 0 or i >= bar.count():
                    continue
                if self._bulk_skips(i):
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    if i < bar.count():
                        try:
                            still_exists = False
                            if self.is_script_tab(i):
                                still_exists = True
                            else:
                                nm = self.tab_name_at(i)
                                still_exists = nm is not None and nm in self._tabs
                            if still_exists:
                                break
                        except Exception:
                            break
        except Exception:
            pass

    def close_tabs_left(self, idx: int):
        try:
            bar = self._tab_bar
            if idx <= 0 or idx >= bar.count():
                return
            indices = [i for i in range(idx - 1, -1, -1)]
            for i in indices:
                if i < 0 or i >= bar.count():
                    continue
                if self._bulk_skips(i):
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def close_tabs_right(self, idx: int):
        try:
            bar = self._tab_bar
            if idx < 0 or idx >= bar.count() - 1:
                return
            indices = [i for i in range(bar.count() - 1, idx, -1)]
            for i in indices:
                if i < 0 or i >= bar.count():
                    continue
                if self._bulk_skips(i):
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass

    def close_duplicate_tabs(self, idx: int):
        try:
            dup = self._duplicate_indices(idx)
            dup.sort(reverse=True)
            for i in dup:
                if i < 0 or i >= self._tab_bar.count():
                    continue
                if self._bulk_skips(i):
                    continue
                ok = self.close_tab_at(i)
                if not ok:
                    break
        except Exception:
            pass
