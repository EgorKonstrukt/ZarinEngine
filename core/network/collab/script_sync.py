# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Callable
from core.network.protocol import MessageType
class ScriptSyncMixin:
    def send_script_open(self, path: str, content: str):
        self._send_link(MessageType.SCRIPT_OPEN, {"path": str(path), "content": str(content)})
    def send_script_change(self, path: str, content: str):
        self._send_link(MessageType.SCRIPT_CHANGE, {"path": str(path), "content": str(content)})
    def send_script_cursor(self, path: str, pos: int, sel_anchor: int, sel_end: int):
        self._send_link(MessageType.SCRIPT_CURSOR, {"path": str(path), "pos": int(pos), "sel_anchor": int(sel_anchor), "sel_end": int(sel_end)})
    def send_script_ops(self, path: str, ops: list):
        self._send_link(MessageType.SCRIPT_OPS, {"path": str(path), "ops": list(ops)})
    def _handle_script_branch(self, msg_type: int, data: dict):
        if msg_type == int(MessageType.SCRIPT_OPEN):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_open:
                self._touch(pid)
                try:
                    self._on_remote_script_open(data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.SCRIPT_CHANGE):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_change:
                self._touch(pid)
                try:
                    self._on_remote_script_change(data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.SCRIPT_CURSOR):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_cursor:
                self._touch(pid)
                try:
                    self._on_remote_script_cursor(pid, data)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.SCRIPT_OPS):
            pid = str(data.get("id", ""))
            own = self.own_peer_id
            if pid != own and self._on_remote_script_ops:
                self._touch(pid)
                try:
                    self._on_remote_script_ops(pid, data)
                except Exception:
                    pass
            return True
        return False
