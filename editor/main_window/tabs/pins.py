# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun


from __future__ import annotations


class SceneTabPinsMixin:
    def is_pinned(self, tab_name: str) -> bool:
        try:
            info = self._tabs.get(tab_name)
            return bool(info is not None and info.pinned)
        except Exception:
            return False

    def set_pinned(self, tab_name: str, pinned: bool):
        try:
            info = self._tabs.get(tab_name)
            if info is None or info.prefab_path:
                return
            info.pinned = bool(pinned)
            self._move_bar_tab_silent(self._scene_tab_idx(tab_name), self._pinned_slot(exclude=tab_name))
            self.refresh_tab_title(tab_name)
        except Exception:
            pass

    def toggle_pin(self, tab_name: str):
        try:
            self.set_pinned(tab_name, not self.is_pinned(tab_name))
        except Exception:
            pass

    def _pinned_slot(self, exclude: str = "") -> int:
        try:
            n = 0
            for i in range(self._tab_bar.count()):
                nm = self.tab_name_at(i)
                if nm is not None and nm != exclude and self.is_pinned(nm):
                    n += 1
            return n
        except Exception:
            return 0

    def _move_bar_tab_silent(self, from_idx: int, to_idx: int):
        try:
            bar = self._tab_bar
            if from_idx < 0 or to_idx < 0 or from_idx >= bar.count():
                return
            to_idx = max(0, min(to_idx, bar.count() - 1))
            if from_idx == to_idx:
                return
            cur_data = bar.tabData(bar.currentIndex())
            bar.blockSignals(True)
            try:
                bar.moveTab(from_idx, to_idx)
                for i in range(bar.count()):
                    if bar.tabData(i) == cur_data:
                        bar.setCurrentIndex(i)
                        break
            finally:
                bar.blockSignals(False)
        except Exception:
            pass

    def _toggle_pin_at(self, idx: int):
        try:
            if self.is_script_tab(idx):
                return
            nm = self.tab_name_at(idx)
            if nm is not None:
                self.toggle_pin(nm)
        except Exception:
            pass
