# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QLineEdit, QSpinBox,
                              QListWidget, QListWidgetItem, QFrame,
                              QProgressBar, QMessageBox, QFileDialog, QApplication)
from PyQt6.QtCore import Qt, QTimer
import qtawesome as qta
from PyQt6.QtGui import QColor, QFont


class CollaborationPanel(QDockWidget):
    def __init__(self, engine, parent=None):
        super().__init__("Collaboration", parent)
        self._engine = engine
        self._collab: Optional = None
        self._relay_server = None
        self._setup_ui()
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._refresh_peers)
        self._update_timer.start(500)

    def set_collaboration_manager(self, mgr):
        self._collab = mgr
        try:
            self._collab.set_on_scene_sync(self._on_scene_sync)
        except Exception:
            pass
        try:
            self._collab.set_on_auth_failed(self._on_auth_failed)
        except Exception:
            pass
        try:
            self._relay_input.setText(str(getattr(mgr.settings, "relay_url", "ws://127.0.0.1:8765")))
        except Exception:
            pass

    def _on_auth_failed(self, reason: str):
        try:
            self._status_label.setText(f"Auth failed: {reason}")
        except Exception:
            pass

    def _on_scene_sync(self, scene_data: dict) -> bool:
        scene = self._engine.scene
        if scene and scene.dirty:
            btn = QMessageBox.question(
                self, "Scene Not Saved",
                "The current scene has unsaved changes.\n"
                "Save before syncing with the collaborator's scene?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if btn == QMessageBox.StandardButton.Cancel:
                return False
            if btn == QMessageBox.StandardButton.Save:
                if scene.path:
                    self._engine.save_scene()
                else:
                    path, _ = QFileDialog.getSaveFileName(
                        self, "Save Scene", "scenes/", "Scenes (*.zpes)"
                    )
                    if path:
                        if not path.endswith(".zpes"):
                            path += ".zpes"
                        self._engine.save_scene(path)
                    else:
                        return False
        return True

    def _setup_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        title = QLabel("Collaboration")
        title.setStyleSheet("font-size: 11px; font-weight: bold; padding: 2px;")
        layout.addWidget(title)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)
        self._status_label = QLabel("Disconnected")
        self._status_label.setStyleSheet("font-size: 10px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Your name")
        self._name_input.setText("User")
        layout.addWidget(self._name_input)
        lan_title = QLabel("LAN (direct TCP)")
        lan_title.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(lan_title)
        host_row = QHBoxLayout()
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("Host")
        self._host_input.setText("0.0.0.0")
        host_row.addWidget(self._host_input)
        self._port_input = QSpinBox()
        self._port_input.setRange(1024, 65535)
        self._port_input.setValue(9876)
        host_row.addWidget(self._port_input)
        layout.addLayout(host_row)
        sec_row = QHBoxLayout()
        self._room_input = QLineEdit()
        self._room_input.setPlaceholderText("Room (optional)")
        self._room_input.setMaxLength(24)
        sec_row.addWidget(self._room_input)
        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Password")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        sec_row.addWidget(self._password_input)
        layout.addLayout(sec_row)
        self._host_btn = QPushButton(qta.icon("fa5s.server", color="#fff"), " Host LAN")
        self._host_btn.setStyleSheet("QPushButton { background: #2471a3; }")
        self._host_btn.clicked.connect(self._on_host)
        layout.addWidget(self._host_btn)
        connect_row = QHBoxLayout()
        self._connect_host_input = QLineEdit()
        self._connect_host_input.setPlaceholderText("Server IP")
        self._connect_host_input.setText("127.0.0.1")
        connect_row.addWidget(self._connect_host_input)
        self._connect_port_input = QSpinBox()
        self._connect_port_input.setRange(1024, 65535)
        self._connect_port_input.setValue(9876)
        connect_row.addWidget(self._connect_port_input)
        layout.addLayout(connect_row)
        self._connect_btn = QPushButton(qta.icon("fa5s.plug", color="#fff"), " Connect LAN")
        self._connect_btn.setStyleSheet("QPushButton { background: #2e7d32; }")
        self._connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self._connect_btn)
        net_title = QLabel("Internet (relay, no port forwarding)")
        net_title.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(net_title)
        self._relay_input = QLineEdit()
        self._relay_input.setPlaceholderText("Relay ws://host:port")
        self._relay_input.setText("ws://127.0.0.1:8765")
        layout.addWidget(self._relay_input)
        relay_btn_row = QHBoxLayout()
        self._host_relay_btn = QPushButton(qta.icon("fa5s.globe", color="#fff"), " Host Net")
        self._host_relay_btn.setStyleSheet("QPushButton { background: #6c3483; }")
        self._host_relay_btn.clicked.connect(self._on_host_relay)
        relay_btn_row.addWidget(self._host_relay_btn)
        self._join_relay_btn = QPushButton(qta.icon("fa5s.sign-in-alt", color="#fff"), " Join Net")
        self._join_relay_btn.setStyleSheet("QPushButton { background: #1a7f5a; }")
        self._join_relay_btn.clicked.connect(self._on_join_relay)
        relay_btn_row.addWidget(self._join_relay_btn)
        layout.addLayout(relay_btn_row)
        self._relay_server_btn = QPushButton(qta.icon("fa5s.cloud", color="#d4d4d4"), " Start Relay Server")
        self._relay_server_btn.setCheckable(True)
        self._relay_server_btn.clicked.connect(self._on_relay_server_toggle)
        layout.addWidget(self._relay_server_btn)
        invite_title = QLabel("Invite code")
        invite_title.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(invite_title)
        self._invite_input = QLineEdit()
        self._invite_input.setPlaceholderText("ZARIN1:...")
        layout.addWidget(self._invite_input)
        invite_row = QHBoxLayout()
        self._copy_invite_btn = QPushButton(qta.icon("fa5s.copy", color="#d4d4d4"), " Copy")
        self._copy_invite_btn.clicked.connect(self._on_copy_invite)
        invite_row.addWidget(self._copy_invite_btn)
        self._join_invite_btn = QPushButton(qta.icon("fa5s.ticket-alt", color="#d4d4d4"), " Join")
        self._join_invite_btn.clicked.connect(self._on_join_invite)
        invite_row.addWidget(self._join_invite_btn)
        layout.addLayout(invite_row)
        self._disconnect_btn = QPushButton(qta.icon("fa5s.unlink", color="#fff"), " Disconnect")
        self._disconnect_btn.setStyleSheet("QPushButton { background: #c0392b; }")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._disconnect_btn.setEnabled(False)
        layout.addWidget(self._disconnect_btn)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)
        self._play_btn = QPushButton(qta.icon("fa5s.play", color="#d4d4d4"), " Play Mode (Lock)")
        self._play_btn.setCheckable(True)
        self._play_btn.clicked.connect(self._on_play_toggle)
        layout.addWidget(self._play_btn)
        bw_row = QHBoxLayout()
        self._bw_sent_label = QLabel("Up: 0 B")
        self._bw_sent_label.setStyleSheet("font-size: 9px;")
        bw_row.addWidget(self._bw_sent_label)
        self._bw_recv_label = QLabel("Down: 0 B")
        self._bw_recv_label.setStyleSheet("font-size: 9px;")
        bw_row.addWidget(self._bw_recv_label)
        layout.addLayout(bw_row)
        self._latency_label = QLabel("Latency: -- ms")
        self._latency_label.setStyleSheet("font-size: 9px;")
        layout.addWidget(self._latency_label)
        sep_assets = QFrame()
        sep_assets.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep_assets)
        asset_title = QLabel("Asset Sync")
        asset_title.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(asset_title)
        self._asset_status = QLabel("Idle")
        self._asset_status.setStyleSheet("font-size: 9px;")
        layout.addWidget(self._asset_status)
        self._asset_progress = QProgressBar()
        self._asset_progress.setRange(0, 100)
        self._asset_progress.setValue(0)
        self._asset_progress.setFixedHeight(12)
        self._asset_progress.setVisible(False)
        layout.addWidget(self._asset_progress)
        self._sync_btn = QPushButton(qta.icon("fa5s.sync-alt", color="#d4d4d4"), " Sync Assets")
        self._sync_btn.clicked.connect(self._on_sync_assets)
        layout.addWidget(self._sync_btn)
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep3)
        peer_title = QLabel("Connected Peers")
        peer_title.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(peer_title)
        self._peer_list = QListWidget()
        layout.addWidget(self._peer_list)
        layout.addStretch()
        self.setWidget(container)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

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

    def _on_host(self):
        if not self._collab:
            return
        name = self._common_name("Host")
        host = self._host_input.text() or "0.0.0.0"
        port = self._port_input.value()
        room = self._common_room()
        password = self._common_password()
        try:
            self._collab.start_server(host, port, password=password, room=room)
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
                from core.network.relay import RelayServer
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

    def _update_status(self):
        connected = bool(self._collab and self._collab.connected)
        if connected:
            try:
                mode = str(self._collab.connection_mode)
                room = str(self._collab.room)
                extra = f" ({mode} {room})" if room else f" ({mode})"
            except Exception:
                extra = ""
            self._status_label.setText("Connected" + extra)
            self._status_label.setStyleSheet("font-size: 10px;")
        else:
            try:
                err = str(self._collab.auth_error) if self._collab else ""
            except Exception:
                err = ""
            if err:
                self._status_label.setText(f"Disconnected ({err})")
            else:
                self._status_label.setText("Disconnected")
            self._status_label.setStyleSheet("font-size: 10px;")
        self._host_btn.setEnabled(not connected)
        self._connect_btn.setEnabled(not connected)
        self._host_relay_btn.setEnabled(not connected)
        self._join_relay_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)

    def _on_play_toggle(self, checked: bool):
        if self._collab:
            try:
                self._collab.send_play_mode(bool(checked))
            except Exception:
                pass

    def _refresh_peers(self):
        if not self._collab:
            return
        self._update_status()
        try:
            self._peer_list.clear()
        except Exception:
            pass
        collab = self._collab
        try:
            peers = dict(collab.peers)
        except Exception:
            peers = {}
        for pid, peer in peers.items():
            try:
                c = peer.color
                r, g, b = int(c[0]*255), int(c[1]*255), int(c[2]*255)
                ping_text = f"  [{peer.ping_ms:.0f}ms]" if float(peer.ping_ms) > 0 else ""
                tab = f" @{peer.current_tab}" if getattr(peer, "current_tab", "") else ""
                item = QListWidgetItem(f"{peer.name}{ping_text}{tab}")
                item.setForeground(QColor(r, g, b))
                f = QFont("Segoe UI", 9)
                item.setFont(f)
                self._peer_list.addItem(item)
            except Exception:
                pass
        try:
            bw_sent = int(collab.bytes_sent)
            bw_recv = int(collab.bytes_received)
            self._bw_sent_label.setText(f"Up: {self._format_bytes(bw_sent)}")
            self._bw_recv_label.setText(f"Down: {self._format_bytes(bw_recv)}")
            latency = float(collab.latency_ms)
            self._latency_label.setText(f"Latency: {latency:.0f} ms" if latency > 0 else "Latency: -- ms")
            try:
                self._play_btn.setEnabled(bool(collab.is_host))
            except Exception:
                pass
            try:
                self._play_btn.setChecked(bool(collab.play_mode_active))
            except Exception:
                pass
            self._update_asset_sync()
        except Exception:
            pass

    def _update_asset_sync(self):
        if not self._collab:
            return
        try:
            progress = self._collab.asset_sync_progress
        except Exception:
            return
        total = int(progress.get("total", 0))
        current = int(progress.get("current", 0))
        file_name = str(progress.get("current_file", ""))
        failed = int(progress.get("failed", 0))
        try:
            syncing = bool(self._collab.asset_syncing)
        except Exception:
            syncing = False
        if syncing and total > 0:
            pct = int(current / total * 100) if total > 0 else 0
            self._asset_progress.setValue(pct)
            self._asset_progress.setVisible(True)
            self._asset_status.setText(f"Syncing: {file_name} ({current}/{total})")
            self._sync_btn.setEnabled(False)
        else:
            self._asset_progress.setVisible(total > 0 and not syncing)
            if total > 0 and not syncing:
                self._asset_progress.setValue(100)
            if failed:
                self._asset_status.setText(f"Synced ({failed} failed)")
                self._asset_status.setStyleSheet("font-size: 9px;")
            elif total > 0 and not syncing:
                self._asset_status.setText("Synced")
                self._asset_status.setStyleSheet("font-size: 9px;")
            else:
                self._asset_status.setText("Idle")
                self._asset_status.setStyleSheet("font-size: 9px;")
            try:
                self._sync_btn.setEnabled(bool(self._collab.connected))
            except Exception:
                pass

    def _on_sync_assets(self):
        if not self._collab or not self._collab.connected:
            return
        try:
            self._collab.request_asset_list()
        except Exception:
            pass

    @staticmethod
    def _format_bytes(b: int) -> str:
        try:
            v = int(b)
        except Exception:
            v = 0
        if v < 1024:
            return f"{v} B"
        elif v < 1024 * 1024:
            return f"{v / 1024:.1f} KB"
        else:
            return f"{v / (1024 * 1024):.1f} MB"
