# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QTabBar, QMessageBox

from core.ecs import Scene
from core.foundation.logger import Logger
from core.foundation.cmd import CommandHistory, set_history_provider
from editor.main_window.tabs.info import SceneTabInfo
from editor.main_window.tabs.sync import SceneTabSyncMixin
from editor.main_window.tabs.pins import SceneTabPinsMixin
from editor.main_window.tabs.reopen import SceneTabReopenMixin
from editor.main_window.tabs.ops import SceneTabOpsMixin
from editor.main_window.tabs.peers import SceneTabPeersMixin, _icon_for_script


class SceneTabManager(QObject, SceneTabSyncMixin, SceneTabPinsMixin, SceneTabReopenMixin, SceneTabOpsMixin, SceneTabPeersMixin):
    tab_switched = pyqtSignal(str)
    tab_added = pyqtSignal(str)
    script_tab_selected = pyqtSignal(str)
    script_tab_closed = pyqtSignal(str)
    SCRIPT_TAB_PREFIX = "__script__"

    def __init__(self, engine, tab_bar: QTabBar, mw):
        super().__init__(mw)
        self._engine = engine
        self._tab_bar = tab_bar
        self._mw = mw
        self._tabs: dict[str, SceneTabInfo] = {}
        self._tab_names: list[str] = []
        self._active_tab: Optional[str] = None
        self._switching = False
        self._restoring = False
        self._closed_stack: list[dict] = []
        self._max_closed = 25

        tab_bar.currentChanged.connect(self._on_tab_changed)
        tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        tab_bar.tabMoved.connect(self._on_tab_moved)
        tab_bar.setTabsClosable(True)
        tab_bar.setMovable(True)
        tab_bar.setDrawBase(False)
        tab_bar.setExpanding(False)
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._on_context_menu)
        self._reopen_action = QAction("Reopen Closed Tab", tab_bar)
        self._reopen_action.triggered.connect(lambda: self.reopen_closed_tab())
        try:
            tab_bar.addAction(self._reopen_action)
        except Exception:
            pass
        self._fallback_history = CommandHistory()
        try:
            set_history_provider(self._resolve_active_history)
        except Exception:
            pass
        try:
            engine.on("scene_saved", self._on_engine_scene_saved)
        except Exception:
            pass

    def begin_restore(self):
        self._restoring = True

    def end_restore(self):
        self._restoring = False

    def add_script_tab(self, path: str, title: str) -> int:
        pos = len(self._tab_names)
        idx = self._tab_bar.insertTab(pos, title)
        self._tab_bar.setTabData(idx, self.SCRIPT_TAB_PREFIX + path)
        self._tab_bar.setTabIcon(idx, _icon_for_script(path))
        return idx

    def is_script_tab(self, idx: int) -> bool:
        data = self._tab_bar.tabData(idx)
        return isinstance(data, str) and data.startswith(self.SCRIPT_TAB_PREFIX)

    def script_path_at(self, idx: int) -> str:
        data = self._tab_bar.tabData(idx)
        if isinstance(data, str) and data.startswith(self.SCRIPT_TAB_PREFIX):
            return data[len(self.SCRIPT_TAB_PREFIX):]
        return ""

    def update_script_tab_title(self, path: str, title: str):
        for i in range(self._tab_bar.count()):
            if self.script_path_at(i) == path:
                self._tab_bar.setTabText(i, title)
                break

    def remove_script_tab_by_path(self, path: str):
        for i in range(self._tab_bar.count()):
            if self.script_path_at(i) == path:
                self._tab_bar.removeTab(i)
                break

    def _on_tab_moved(self, from_idx: int, to_idx: int):
        self._tab_names = []
        for i in range(self._tab_bar.count()):
            data = self._tab_bar.tabData(i)
            if isinstance(data, str) and not data.startswith(self.SCRIPT_TAB_PREFIX):
                self._tab_names.append(data)

    _ZARIN_ICON = None

    @classmethod
    def _get_zarin_icon(cls) -> QIcon:
        if cls._ZARIN_ICON is None:
            svg = os.path.join(os.path.dirname(__file__), "..", "..", "zarin_icon.svg")
            if os.path.exists(svg):
                cls._ZARIN_ICON = QIcon(svg)
            else:
                cls._ZARIN_ICON = QIcon()
        return cls._ZARIN_ICON

    def _scene_tab_idx(self, tab_name: str) -> int:
        for i in range(self._tab_bar.count()):
            if self._tab_bar.tabData(i) == tab_name:
                return i
        return -1

    def add_tab(self, name: str, path: Optional[str] = None, scene: Optional[Scene] = None) -> str:
        tab_name = self._unique_name(name)
        if scene is None:
            self._save_current_to_tab()
            self._active_tab = tab_name
            self._engine.new_scene(tab_name)
            if path:
                self._engine.scene.path = path
            scene = self._engine.scene
        info = SceneTabInfo(tab_name, path, scene)
        self._tabs[tab_name] = info
        pos = len(self._tab_names)
        self._tab_names.append(tab_name)
        idx = self._tab_bar.insertTab(pos, tab_name)
        self._tab_bar.setTabData(idx, tab_name)
        self._tab_bar.setTabIcon(idx, self._get_zarin_icon())
        self.refresh_tab_title(tab_name)
        self._tab_bar.setCurrentIndex(idx)
        if not self._restoring and not self._switching and self._active_tab != tab_name:
            self._on_tab_changed(idx)
        self.tab_added.emit(tab_name)
        return tab_name

    def add_lazy_tab(self, name: str, path: Optional[str] = None, snapshot: str = "") -> str:
        tab_name = self._unique_name(name)
        info = SceneTabInfo(tab_name, path, None)
        if snapshot:
            info.pending_snapshot = os.path.basename(snapshot)
            info.restored_snapshot = os.path.basename(snapshot)
            info.dirty = False
        self._tabs[tab_name] = info
        self._tab_names.append(tab_name)
        pos = self._tab_bar.count()
        idx = self._tab_bar.insertTab(pos, tab_name)
        self._tab_bar.setTabData(idx, tab_name)
        self._tab_bar.setTabIcon(idx, self._get_zarin_icon())
        self.refresh_tab_title(tab_name)
        self.tab_added.emit(tab_name)
        return tab_name

    def remove_tab(self, tab_name: str):
        if tab_name not in self._tabs:
            return
        idx = self._scene_tab_idx(tab_name)
        self._tab_names.remove(tab_name)
        self._tabs.pop(tab_name, None)
        if idx >= 0:
            self._tab_bar.removeTab(idx)

    def switch_to_tab(self, tab_name: str):
        if tab_name not in self._tabs:
            return
        idx = self._scene_tab_idx(tab_name)
        if idx >= 0:
            if idx == self._tab_bar.currentIndex() and self._active_tab != tab_name:
                self._on_tab_changed(idx)
            else:
                self._tab_bar.setCurrentIndex(idx)

    def cycle_tab(self, delta: int):
        try:
            n = self._tab_bar.count()
            if n <= 1:
                return
            self._tab_bar.setCurrentIndex((self._tab_bar.currentIndex() + delta) % n)
        except Exception:
            pass

    def tab_name_at(self, idx: int) -> Optional[str]:
        data = self._tab_bar.tabData(idx)
        if isinstance(data, str) and not data.startswith(self.SCRIPT_TAB_PREFIX):
            return data
        return None

    @property
    def tab_names(self) -> list[str]:
        return list(self._tab_names)

    @property
    def active_tab(self) -> Optional[str]:
        return self._active_tab

    def get_tab_info(self, tab_name: str) -> Optional[SceneTabInfo]:
        return self._tabs.get(tab_name)

    def _unique_name(self, base: str) -> str:
        if base not in self._tabs:
            return base
        i = 2
        while f"{base} {i}" in self._tabs:
            i += 1
        return f"{base} {i}"

    def _on_tab_changed(self, idx: int):
        if self._switching or self._restoring:
            return
        if self.is_script_tab(idx):
            self._save_current_to_tab()
            self._active_tab = None
            self.script_tab_selected.emit(self.script_path_at(idx))
            return
        self._switching = True
        try:
            target = self.tab_name_at(idx)
            if target is None or target == self._active_tab:
                return
            self._save_current_to_tab()
            if self._engine.play_mode:
                self._engine.stop_play()
                from core.ecs import Scene as S
                from core.engine.eng import Engine as Eng
                active_info = self._tabs.get(self._active_tab)
                if active_info and active_info.scene_snapshot:
                    restored = S.deserialize(active_info.scene_snapshot, Eng.instance()._component_registry)
                    restored.path = self._engine.scene.path if self._engine.scene else active_info.path
                    try:
                        if getattr(self._mw, "_pre_play_dirty", False):
                            restored.mark_dirty()
                    except Exception:
                        pass
                    self._engine._scene = restored
                    self._engine._plugin_manager.notify_scene_loaded(restored)
                    active_info.scene = restored
                    active_info.scene_snapshot = None
                    active_info.play_mode = False
            info = self._tabs.get(target)
            if info is None:
                return
            previous_tab = self._active_tab
            previous_scene = self._engine.scene if self._engine else None
            self._active_tab = target
            try:
                self._load_scene(info)
            except Exception as e:
                Logger.error(f"Failed to load scene tab '{target}': {e}", e)
                self._active_tab = previous_tab
                if self._engine is not None:
                    try:
                        self._engine._scene = previous_scene
                    except Exception as e2:
                        Logger.error(f"Failed to roll back scene: {e2}", e2)
                return
            self.tab_switched.emit(target)
        finally:
            self._switching = False

    def _on_tab_close_requested(self, idx: int):
        self.close_tab_at(idx)

    def close_tab_at(self, idx: int) -> bool:
        try:
            if idx < 0 or idx >= self._tab_bar.count():
                return False
            snap = self._snapshot_for_reopen(idx)
            ok = self._try_close_single(idx)
            if ok and snap is not None:
                self._push_closed(snap)
            return ok
        except Exception:
            return False

    def _try_close_single(self, idx: int) -> bool:
        try:
            bar = self._tab_bar
            if idx < 0 or idx >= bar.count():
                return False
            if self.is_script_tab(idx):
                path = self.script_path_at(idx)
                w = self._find_internal_script_tab(idx)
                if w is not None:
                    try:
                        sw = self._mw._script_editor._script_widget
                        before_internal = sw._tabs.count()
                    except Exception:
                        before_internal = -1
                    before_bar = bar.count()
                    try:
                        w._close_self()
                    except Exception:
                        pass
                    try:
                        sw2 = self._mw._script_editor._script_widget
                        after_internal = sw2._tabs.count()
                        still = False
                        for k in range(sw2._tabs.count()):
                            try:
                                if sw2._tabs.widget(k) is w:
                                    still = True
                                    break
                            except Exception:
                                continue
                        if still:
                            return False
                        if before_internal >= 0 and after_internal >= before_internal:
                            return False
                    except Exception:
                        pass
                    try:
                        after_bar = bar.count()
                    except Exception:
                        after_bar = before_bar
                    if after_bar < before_bar:
                        return True
                    try:
                        if idx < bar.count() and self.is_script_tab(idx):
                            bar.removeTab(idx)
                            return True
                        for k in range(bar.count() - 1, -1, -1):
                            try:
                                if self.is_script_tab(k) and self.script_path_at(k) == path:
                                    bar.removeTab(k)
                                    return True
                            except Exception:
                                continue
                    except Exception:
                        pass
                    return True
                try:
                    self.script_tab_closed.emit(path)
                except Exception:
                    pass
                try:
                    for k in range(bar.count() - 1, -1, -1):
                        try:
                            if self.is_script_tab(k) and self.script_path_at(k) == path:
                                bar.removeTab(k)
                                return True
                        except Exception:
                            continue
                    if idx < bar.count():
                        bar.removeTab(idx)
                        return True
                except Exception:
                    pass
                return False
            tab_name = self.tab_name_at(idx)
            if tab_name is None:
                return False
            info = self._tabs.get(tab_name)
            if info is None:
                try:
                    bar.removeTab(idx)
                except Exception:
                    pass
                return False
            scene = info.scene if info else None
            if info and info.prefab_path:
                from core.ecs.prefabp import PrefabLibrary
                pref = PrefabLibrary.load(info.prefab_path)
                prefab_guid = pref.guid if pref else None
                scene = info.scene
                if scene:
                    from editor.main_window.handlersp import _save_prefab_direct
                    _save_prefab_direct(info.prefab_path, scene)
                origin = info.origin_tab
                if origin and origin in self._tabs:
                    origin_info = self._tabs.get(origin)
                    if origin_info and origin_info.scene and prefab_guid:
                        from editor.main_window.handlersp import _refresh_prefab_instances
                        _refresh_prefab_instances(origin_info.scene, prefab_guid, self._mw._engine._component_registry)
                if tab_name == self._active_tab:
                    self._active_tab = None
                self.remove_tab(tab_name)
                try:
                    self._mw._prefab_mode = False
                    self._mw._prefab_path = None
                    self._mw._viewport._prefab_btns.hide()
                    from core.config.editor_scale import scale
                    self._mw._viewport._toolbar.setFixedHeight(scale(30))
                except Exception:
                    pass
                return True
            is_dirty = self._is_tab_dirty(info)
            if is_dirty:
                reply = QMessageBox.question(
                    self._mw, "Unsaved Changes",
                    f"Scene '{info.name}' has unsaved changes. Save before closing?",
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Cancel
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return False
                if reply == QMessageBox.StandardButton.Yes:
                    if scene is None:
                        if not self.ensure_tab_loaded(tab_name):
                            return False
                        scene = info.scene
                    self._save_scene_tab(info)
            if tab_name == self._active_tab and self._engine.play_mode:
                try:
                    self._engine.stop_play()
                except Exception:
                    pass
                if info and info.scene_snapshot:
                    try:
                        from core.ecs import Scene as S
                        from core.engine.eng import Engine as Eng
                        restored = S.deserialize(info.scene_snapshot, Eng.instance()._component_registry)
                        restored.path = self._engine.scene.path if self._engine.scene else info.path
                        try:
                            if getattr(self._mw, '_pre_play_dirty', False):
                                restored.mark_dirty()
                        except Exception:
                            pass
                        self._engine._scene = restored
                        self._engine._plugin_manager.notify_scene_loaded(restored)
                    except Exception:
                        pass
            if tab_name == self._active_tab:
                self._active_tab = None
            self.remove_tab(tab_name)
            return True
        except Exception:
            return False

