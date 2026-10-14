# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class _CollabProxy(QObject):
    scene_open = pyqtSignal(object)
    tab_switch = pyqtSignal(str, str)
    tab_close = pyqtSignal(str)
    peers_changed = pyqtSignal()
    script_open = pyqtSignal(str, str)
    script_change = pyqtSignal(str, str)
    script_cursor = pyqtSignal(str, object)


class _ToolbarHostMixin:
    def _init_collab_scene_tabs(self):
        mgr = self._scene_tab_manager
        mgr.tab_switched.connect(lambda name: self._on_scene_tab_switched(name))
        mgr.tab_added.connect(lambda name: self._on_scene_tab_added(name))
        collab = self._engine.collab_manager
        if collab:
            self._collab_proxy = _CollabProxy()
            self._collab_proxy.scene_open.connect(self._on_remote_scene_open)
            self._collab_proxy.tab_switch.connect(self._on_remote_tab_switch)
            self._collab_proxy.tab_close.connect(mgr.remove_tab)
            self._collab_proxy.peers_changed.connect(self._update_tab_peer_indicators)
            collab.set_on_remote_scene_open(lambda data: self._collab_proxy.scene_open.emit(data))
            collab.set_on_remote_tab_switch(lambda pid, name: self._collab_proxy.tab_switch.emit(pid, name))
            collab.set_on_remote_tab_close(lambda name: self._collab_proxy.tab_close.emit(name))
            collab.set_peer_joined_callback(lambda _: self._collab_proxy.peers_changed.emit())
            collab.set_peer_left_callback(lambda _: self._collab_proxy.peers_changed.emit())
            self._collab_proxy.script_open.connect(self._on_remote_script_open)
            self._collab_proxy.script_change.connect(self._on_remote_script_change)
            self._collab_proxy.script_cursor.connect(self._on_remote_script_cursor)
            collab.set_on_remote_script_open(lambda data: self._collab_proxy.script_open.emit(data.get("path", ""), data.get("content", "")))
            collab.set_on_remote_script_change(lambda data: self._collab_proxy.script_change.emit(data.get("path", ""), data.get("content", "")))
            collab.set_on_remote_script_cursor(lambda pid, data: self._collab_proxy.script_cursor.emit(pid, data))
            print("[COLLAB] Tab callbacks registered", flush=True)

    def _init_script_tabs(self):
        sw = self._script_editor._script_widget
        mgr = self._scene_tab_manager
        self._syncing_script = False
        self._script_peer_editors: dict[str, list[list[float]]] = {}
        for i in range(sw._tabs.count()):
            tab = sw._tabs.widget(i)
            path = tab._file_path or ""
            mgr.add_script_tab(path, tab._tab_title())
        sw.tab_opened.connect(self._on_script_tab_opened)
        sw.tab_closed.connect(self._on_script_tab_closed_internal)
        sw.tab_switched.connect(self._on_script_internal_tab_switched)
        mgr.script_tab_selected.connect(self._on_script_tab_in_bar_selected)
        mgr.script_tab_closed.connect(self._on_script_tab_closed_from_bar)
        collab = self._engine.collab_manager
        if collab:
            sw.collab_file_opened.connect(lambda path, content: collab.send_script_open(path, content))
            sw.collab_file_saved.connect(lambda path, content: collab.send_script_change(path, content))
            sw.collab_cursor_changed.connect(lambda path, pos, anchor, end: collab.send_script_cursor(path, pos, anchor, end))
            sw.collab_ops_ready.connect(lambda path, ops: collab.send_script_ops(path, ops))
            collab.set_on_remote_script_ops(lambda pid, data: sw.apply_remote_ops(data.get("path", ""), data.get("ops", [])))

    def _on_script_tab_opened(self, path: str):
        sw = self._script_editor._script_widget
        for i in range(sw._tabs.count()):
            tab = sw._tabs.widget(i)
            if tab._file_path == path:
                self._scene_tab_manager.add_script_tab(path, tab._tab_title())
                return

    def _on_script_tab_closed_internal(self, path: str):
        self._scene_tab_manager.remove_script_tab_by_path(path)

    def _on_script_tab_in_bar_selected(self, path: str):
        sw = self._script_editor._script_widget
        tab = sw._current_tab()
        if tab and (tab._file_path or "") == path:
            self._script_editor.show()
            self._script_editor.raise_()
            return
        if self._syncing_script:
            return
        self._syncing_script = True
        try:
            sw.open_script(path)
            self._script_editor.show()
            self._script_editor.raise_()
        finally:
            self._syncing_script = False

    def _on_script_tab_closed_from_bar(self, path: str):
        sw = self._script_editor._script_widget
        for i in range(sw._tabs.count()):
            tab = sw._tabs.widget(i)
            if tab._file_path == path:
                tab._close_self()
                return

    def _on_script_internal_tab_switched(self, path: str):
        if self._syncing_script:
            return
        mgr = self._scene_tab_manager
        for i in range(self._scene_tab_bar.count()):
            if mgr.script_path_at(i) == path:
                if self._scene_tab_bar.currentIndex() != i:
                    self._scene_tab_bar.blockSignals(True)
                    self._scene_tab_bar.setCurrentIndex(i)
                    self._scene_tab_bar.blockSignals(False)
                return

    def _on_remote_script_open(self, path: str, content: str):
        if not path:
            return
        sw = self._script_editor._script_widget
        for i in range(sw._tabs.count()):
            tab = sw._tabs.widget(i)
            if tab._file_path == path:
                return
        sw.open_script(path)

    def _on_remote_script_change(self, path: str, content: str):
        if not path:
            return
        sw = self._script_editor._script_widget
        for i in range(sw._tabs.count()):
            tab = sw._tabs.widget(i)
            if tab._file_path == path:
                if tab._dirty:
                    return
                tab.set_content(content, from_remote=True)
                return
        sw.open_script(path)

    def _on_remote_script_cursor(self, peer_id: str, data: dict):
        path = data.get("path", "")
        pos = data.get("pos", 0)
        sel_anchor = data.get("sel_anchor", pos)
        sel_end = data.get("sel_end", pos)
        collab = self._engine.collab_manager
        peer = collab.get_peer(peer_id) if collab else None
        if peer and path:
            self._script_editor._script_widget.update_remote_cursor(
                peer_id, path, pos, sel_anchor, sel_end, peer.color, peer.name
            )
            self._script_peer_editors[path] = [
                p.color for p in collab.peers.values()
                if p.peer_id in self._script_editor._script_widget._remote_cursors.get(path, {})
            ]
            self._scene_tab_manager.update_script_peer_indicators(self._script_peer_editors)

    def _on_remote_scene_open(self, data: dict):
        try:
            name = data.get("name", "RemoteScene")
            path = data.get("path", "")
            scene_data = data.get("data")
            print(f"[COLLAB] _on_remote_scene_open called: name={name}, path={path}, has_data={scene_data is not None}", flush=True)
            if scene_data is None:
                return
            from core.ecs import Scene, ComponentRegistry
            scene = Scene.deserialize(scene_data, ComponentRegistry)
            scene.mark_dirty()
            if path:
                scene.path = path
            self._tab_add_lock = True
            tab_name = self._scene_tab_manager.add_tab(name, path=path, scene=scene)
            print(f"[COLLAB] Tab created: {tab_name}", flush=True)
            collab = self._engine.collab_manager
            if collab and tab_name:
                collab.set_current_tab(tab_name)
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            self._tab_add_lock = False

    def _on_scene_tab_added(self, name: str):
        locked = getattr(self, "_tab_add_lock", False)
        if locked:
            return
        mgr = getattr(self, "_scene_tab_manager", None)
        if mgr is not None and getattr(mgr, "_restoring", False):
            return
        collab = self._engine.collab_manager
        if collab and collab.connected:
            info = self._scene_tab_manager.get_tab_info(name)
            if info and info.scene:
                try:
                    data = info.scene.serialize()
                    collab.send_scene_open(info.name, info.path or "", data)
                    if collab.is_host:
                        collab.update_server_scene(info.scene)
                except Exception:
                    import traceback
                    traceback.print_exc()

    def _on_remote_tab_switch(self, peer_id: str, tab_name: str):
        self._update_tab_peer_indicators()

    def _update_tab_peer_indicators(self):
        collab = self._engine.collab_manager
        peers = collab.peers if collab and collab.connected else {}
        tab_peers: dict[str, list[list[float]]] = {}
        for p in peers.values():
            if p.current_tab:
                tab_peers.setdefault(p.current_tab, []).append(p.color)
        self._scene_tab_manager.update_peer_indicators(tab_peers)
        self._scene_tab_manager.update_script_peer_indicators(self._script_peer_editors)

    def _on_scene_tab_switched(self, name: str):
        self._viewport_dock.show()
        self._viewport_dock.raise_()
        collab = self._engine.collab_manager
        if collab:
            collab.set_current_tab(name)
            if collab.connected:
                collab.send_scene_tab_switch(name)
        self._schedule_session_autosave()
