# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PyQt6.QtWidgets import QMessageBox, QApplication


class CollaborationActionsMixin:
    def _common_name(self, fallback: str) -> str:
        try:
            return str(self._name_input.text() or fallback)[:32]
        except Exception:
            return str(fallback)

    def _common_room(self) -> str:
        try:
            return str(self._room_input.text() or "").strip()
        except Exception:
            return ""

    def _common_password(self) -> str:
        try:
            return str(self._password_input.text() or "")
        except Exception:
            return ""

    def _on_upnp_toggle(self, checked: bool):
        if not self._collab:
            return
        try:
            self._collab.set_upnp_enabled(bool(checked))
        except Exception:
            pass
        if checked:
            try:
                self._collab.refresh_upnp()
            except Exception:
                pass
        self._update_upnp_label()

    def _on_host(self):
        if not self._collab:
            return
        name = self._common_name("Host")
        host = self._host_input.text() or "0.0.0.0"
        port = self._port_input.value()
        room = self._common_room()
        password = self._common_password()
        try:
            use_upnp = bool(self._upnp_check.isChecked())
        except Exception:
            use_upnp = True
        try:
            self._collab.start_server(host, port, password=password, room=room, use_upnp=use_upnp)
            self._collab.connect("127.0.0.1", port, name, password=password, room=room or self._collab.room)
        except Exception:
            pass
        self._update_status()

    def _on_connect(self):
        if not self._collab:
            return
        name = self._common_name("User")
        host = self._connect_host_input.text() or "127.0.0.1"
        port = self._connect_port_input.value()
        room = self._common_room()
        password = self._common_password()
        try:
            self._collab.connect(host, port, name, password=password, room=room)
        except Exception:
            pass
        self._update_status()

    def _on_host_relay(self):
        if not self._collab:
            return
        name = self._common_name("Host")
        relay = self._relay_input.text() or "ws://127.0.0.1:8765"
        room = self._common_room()
        password = self._common_password()
        try:
            created = self._collab.host_relay(relay, room, password, name)
            if created:
                self._room_input.setText(str(created))
        except Exception:
            pass
        self._update_status()

    def _on_join_relay(self):
        if not self._collab:
            return
        name = self._common_name("User")
        relay = self._relay_input.text() or "ws://127.0.0.1:8765"
        room = self._common_room()
        password = self._common_password()
        if not room:
            try:
                room = self._invite_input.text().strip()
                if room.startswith("ZARIN1:"):
                    self._on_join_invite()
                    return
            except Exception:
                pass
        if not room:
            QMessageBox.warning(self, "Relay", "Enter room code.")
            return
        try:
            self._collab.join_relay(relay, room, password, name)
        except Exception:
            pass
        self._update_status()

    def _on_relay_server_toggle(self, checked: bool):
        if checked:
            try:
                from core.network.relayp import RelayServer
            except Exception:
                self._relay_server_btn.setChecked(False)
                return
            text = self._relay_input.text() or "ws://127.0.0.1:8765"
            host = "0.0.0.0"
            port = 8765
            try:
                rest = text.split("://", 1)[1] if "://" in text else text
                rest = rest.rstrip("/")
                if ":" in rest:
                    h, p = rest.rsplit(":", 1)
                    host = "0.0.0.0"
                    port = int(p)
            except Exception:
                port = 8765
            try:
                self._relay_server = RelayServer(host, port)
                ok = self._relay_server.start_sync()
                if not ok:
                    self._relay_server = None
                    self._relay_server_btn.setChecked(False)
                    return
                self._relay_server_btn.setText(" Stop Relay Server")
                try:
                    self._relay_port = int(port)
                except Exception:
                    pass
                try:
                    if self._collab is not None:
                        self._collab.map_extra_port(int(port), "ZarinEngine-Relay")
                except Exception:
                    pass
            except Exception:
                self._relay_server = None
                self._relay_server_btn.setChecked(False)
        else:
            try:
                if self._relay_server is not None:
                    self._relay_server.stop_sync()
            except Exception:
                pass
            self._relay_server = None
            try:
                if self._collab is not None:
                    self._collab.unmap_extra_port(int(getattr(self, "_relay_port", 8765)))
            except Exception:
                pass
            self._relay_server_btn.setText(" Start Relay Server")

    def _on_copy_invite(self):
        if not self._collab:
            return
        try:
            code = self._collab.create_invite()
        except Exception:
            return
        try:
            self._invite_input.setText(str(code))
        except Exception:
            pass
        try:
            QApplication.clipboard().setText(str(code))
        except Exception:
            pass

    def _on_join_invite(self):
        if not self._collab:
            return
        code = self._invite_input.text().strip()
        if not code:
            return
        name = self._common_name("User")
        password = self._common_password()
        try:
            relay_text = self._relay_input.text().strip()
            if relay_text and ("://" in code or code.startswith("ZARIN1:") is False):
                pass
        except Exception:
            pass
        ok = False
        try:
            ok = bool(self._collab.join_invite(code, name, password=password))
        except Exception:
            ok = False
        if not ok:
            QMessageBox.warning(self, "Invite", "Bad invite code.")
        self._update_status()

    def _on_disconnect(self):
        if self._collab:
            try:
                self._collab.stop()
            except Exception:
                pass
        self._update_status()

    def _on_play_toggle(self, checked: bool):
        if self._collab:
            try:
                self._collab.send_play_mode(bool(checked))
            except Exception:
                pass

    def _on_sync_assets(self):
        if not self._collab or not self._collab.connected:
            return
        try:
            self._collab.request_asset_list()
        except Exception:
            pass
