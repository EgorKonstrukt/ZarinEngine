# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun


from __future__ import annotations

import os


class SceneTabReopenMixin:
    def closed_snapshot_files(self) -> set:
        out: set = set()
        try:
            for entry in list(self._closed_stack):
                try:
                    if not isinstance(entry, dict):
                        continue
                    for k in ("reopen_snapshot",):
                        v = entry.get(k) or ""
                        if v:
                            out.add(os.path.basename(v))
                    info = entry.get("info")
                    if info is not None:
                        for v in (getattr(info, "pending_snapshot", "") or "",
                                  getattr(info, "restored_snapshot", "") or ""):
                            if v:
                                out.add(os.path.basename(v))
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def can_reopen(self) -> bool:
        return len(self._closed_stack) > 0

    def _find_internal_script_tab(self, bar_idx: int):
        try:
            sw = self._mw._script_editor._script_widget
        except Exception:
            return None
        try:
            path = self.script_path_at(bar_idx)
        except Exception:
            return None
        try:
            if path:
                for i in range(sw._tabs.count()):
                    try:
                        w = sw._tabs.widget(i)
                        if getattr(w, "_file_path", None) == path:
                            return w
                    except Exception:
                        continue
                return None
            bar_untitled: list[int] = []
            for i in range(self._tab_bar.count()):
                try:
                    if self.is_script_tab(i) and self.script_path_at(i) == "":
                        bar_untitled.append(i)
                except Exception:
                    continue
            try:
                ordinal = bar_untitled.index(bar_idx)
            except Exception:
                ordinal = 0
            internal_untitled = []
            for i in range(sw._tabs.count()):
                try:
                    w = sw._tabs.widget(i)
                    fp = getattr(w, "_file_path", None)
                    if not fp:
                        internal_untitled.append(w)
                except Exception:
                    continue
            if internal_untitled:
                if 0 <= ordinal < len(internal_untitled):
                    return internal_untitled[ordinal]
                return internal_untitled[0]
        except Exception:
            return None
        return None

    def _snapshot_for_reopen(self, idx: int):
        try:
            if idx < 0 or idx >= self._tab_bar.count():
                return None
            if self.is_script_tab(idx):
                path = self.script_path_at(idx)
                try:
                    title = self._tab_bar.tabText(idx)
                except Exception:
                    title = path or "Untitled"
                content = ""
                dirty = False
                w = self._find_internal_script_tab(idx)
                if w is not None:
                    try:
                        content = w._editor.toPlainText()
                    except Exception:
                        content = ""
                    try:
                        dirty = bool(w._dirty)
                    except Exception:
                        dirty = False
                return {"kind": "script", "path": path, "title": title, "content": content, "dirty": dirty, "bar_index": idx}
            name = self.tab_name_at(idx)
            if name is None:
                return None
            info = self._tabs.get(name)
            if info is None:
                return None
            snap = info.pending_snapshot or info.restored_snapshot or ""
            return {"kind": "scene", "info": info, "bar_index": idx,
                    "was_active": (name == self._active_tab),
                    "reopen_snapshot": os.path.basename(snap) if snap else ""}
        except Exception:
            return None

    def _push_closed(self, entry):
        try:
            if entry is None:
                return
            self._closed_stack.append(entry)
            while len(self._closed_stack) > self._max_closed:
                self._closed_stack.pop(0)
        except Exception:
            pass

    def _restore_scene_entry(self, entry: dict) -> bool:
        try:
            info = entry.get("info")
            orig = int(entry.get("bar_index", 0))
            if info is None:
                return False
            if getattr(info, "scene", None) is None:
                for cand in (getattr(info, "pending_snapshot", "") or "",
                             entry.get("reopen_snapshot", "") or "",
                             getattr(info, "restored_snapshot", "") or ""):
                    if not cand:
                        continue
                    try:
                        from editor.main_window.statep import _session_dir
                        if os.path.isfile(os.path.join(_session_dir(), os.path.basename(cand))):
                            info.pending_snapshot = os.path.basename(cand)
                            break
                    except Exception:
                        continue
            name = getattr(info, "name", "Scene") or "Scene"
            if name in self._tabs:
                name = self._unique_name(name)
                try:
                    info.name = name
                except Exception:
                    pass
            pos = max(0, min(orig, self._tab_bar.count()))
            scene_before = 0
            try:
                limit = min(pos, self._tab_bar.count())
                for i in range(limit):
                    try:
                        d = self._tab_bar.tabData(i)
                        if isinstance(d, str) and not d.startswith(self.SCRIPT_TAB_PREFIX):
                            scene_before += 1
                    except Exception:
                        continue
            except Exception:
                scene_before = len(self._tab_names)
            if scene_before > len(self._tab_names):
                scene_before = len(self._tab_names)
            self._tabs[name] = info
            try:
                self._tab_names.insert(scene_before, name)
            except Exception:
                self._tab_names.append(name)
            idx = self._tab_bar.insertTab(pos, name)
            self._tab_bar.setTabData(idx, name)
            try:
                self._tab_bar.setTabIcon(idx, self._get_zarin_icon())
            except Exception:
                pass
            try:
                self.refresh_tab_title(name)
            except Exception:
                pass
            try:
                self._tab_bar.setCurrentIndex(idx)
            except Exception:
                pass
            try:
                self.tab_added.emit(name)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _restore_script_entry(self, entry: dict) -> bool:
        try:
            path = entry.get("path", "") or ""
            content = entry.get("content", "") or ""
            dirty = bool(entry.get("dirty", False))
            orig = int(entry.get("bar_index", 0))
            try:
                sw = self._mw._script_editor._script_widget
            except Exception:
                return False
            restored = None
            if path and os.path.isfile(path):
                found = None
                try:
                    for i in range(sw._tabs.count()):
                        try:
                            w = sw._tabs.widget(i)
                            if getattr(w, "_file_path", None) == path:
                                found = w
                                break
                        except Exception:
                            continue
                except Exception:
                    found = None
                if found is None:
                    try:
                        sw.open_script(path)
                    except Exception:
                        pass
                    try:
                        for i in range(sw._tabs.count()):
                            try:
                                w = sw._tabs.widget(i)
                                if getattr(w, "_file_path", None) == path:
                                    found = w
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass
                restored = found
                if restored is not None and dirty and content:
                    try:
                        cur = restored._editor.toPlainText()
                    except Exception:
                        cur = ""
                    if cur != content:
                        try:
                            restored._editor.blockSignals(True)
                            restored._editor.setPlainText(content)
                            restored._editor.blockSignals(False)
                            try:
                                restored._editor._old_text = content
                            except Exception:
                                pass
                            restored._dirty = True
                            restored._update_title()
                            try:
                                self.update_script_tab_title(path, restored._tab_title())
                            except Exception:
                                pass
                        except Exception:
                            pass
            else:
                try:
                    sw._new_tab()
                except Exception:
                    return False
                try:
                    restored = sw._tabs.currentWidget()
                except Exception:
                    restored = None
                if restored is not None and content:
                    try:
                        restored._editor.blockSignals(True)
                        restored._editor.setPlainText(content)
                        restored._editor.blockSignals(False)
                        try:
                            restored._editor._old_text = content
                        except Exception:
                            pass
                        restored._dirty = bool(dirty) or True
                        if path and not os.path.isfile(path) and path:
                            try:
                                restored._file_path = path
                            except Exception:
                                pass
                        restored._update_title()
                    except Exception:
                        pass
            try:
                bar = self._tab_bar
                target = -1
                if path:
                    for i in range(bar.count()):
                        try:
                            if self.is_script_tab(i) and self.script_path_at(i) == path:
                                target = i
                        except Exception:
                            continue
                else:
                    for i in range(bar.count() - 1, -1, -1):
                        try:
                            if self.is_script_tab(i) and self.script_path_at(i) == "":
                                target = i
                                break
                        except Exception:
                            continue
                if target >= 0:
                    dest = max(0, min(orig, bar.count() - 1))
                    if target != dest:
                        try:
                            bar.moveTab(target, dest)
                        except Exception:
                            pass
                    try:
                        bar.setCurrentIndex(dest)
                    except Exception:
                        pass
            except Exception:
                pass
            return True
        except Exception:
            return False

    def reopen_closed_tab(self) -> bool:
        try:
            if not self._closed_stack:
                return False
            entry = self._closed_stack.pop()
            if entry.get("kind") == "scene":
                return self._restore_scene_entry(entry)
            return self._restore_script_entry(entry)
        except Exception:
            return False
