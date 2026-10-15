# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QSpinBox, QListWidget, QFrame, QCheckBox, QProgressBar, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, QTimer
import editor.icons as qta
from PyQt6.QtGui import QColor
from editor.panels.collab.actions import CollaborationActionsMixin
from editor.panels.collab.status import CollaborationStatusMixin


class CollaborationPanel(CollaborationActionsMixin, CollaborationStatusMixin, QDockWidget):
    def __init__(self, engine, parent=None):
        super().__init__("Collaboration", parent)
        self._engine = engine
        self._collab: Optional = None
        self._relay_server = None
        self._relay_port = 8765
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
        try:
            self._upnp_check.setChecked(bool(getattr(mgr.settings, "upnp_enabled", True)))
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
        self._host_btn = QPushButton(qta.icon("fa5s.server", color=QColor(255, 255, 255)), " Host LAN")
        self._host_btn.setStyleSheet("QPushButton { background: rgb(36, 113, 163); }")
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
        self._connect_btn = QPushButton(qta.icon("fa5s.plug", color=QColor(255, 255, 255)), " Connect LAN")
        self._connect_btn.setStyleSheet("QPushButton { background: rgb(46, 125, 50); }")
        self._connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self._connect_btn)
        upnp_row = QHBoxLayout()
        self._upnp_check = QCheckBox("UPnP port forwarding (auto)")
        self._upnp_check.setChecked(True)
        self._upnp_check.toggled.connect(self._on_upnp_toggle)
        upnp_row.addWidget(self._upnp_check)
        layout.addLayout(upnp_row)
        self._upnp_label = QLabel("UPnP: idle")
        self._upnp_label.setStyleSheet("font-size: 9px;")
        self._upnp_label.setWordWrap(True)
        layout.addWidget(self._upnp_label)
        net_title = QLabel("Internet (relay, no port forwarding)")
        net_title.setStyleSheet("font-size: 10px; font-weight: bold;")
        layout.addWidget(net_title)
        self._relay_input = QLineEdit()
        self._relay_input.setPlaceholderText("Relay ws://host:port")
        self._relay_input.setText("ws://127.0.0.1:8765")
        layout.addWidget(self._relay_input)
        relay_btn_row = QHBoxLayout()
        self._host_relay_btn = QPushButton(qta.icon("fa5s.globe", color=QColor(255, 255, 255)), " Host Net")
        self._host_relay_btn.setStyleSheet("QPushButton { background: rgb(108, 52, 131); }")
        self._host_relay_btn.clicked.connect(self._on_host_relay)
        relay_btn_row.addWidget(self._host_relay_btn)
        self._join_relay_btn = QPushButton(qta.icon("fa5s.sign-in-alt", color=QColor(255, 255, 255)), " Join Net")
        self._join_relay_btn.setStyleSheet("QPushButton { background: rgb(26, 127, 90); }")
        self._join_relay_btn.clicked.connect(self._on_join_relay)
        relay_btn_row.addWidget(self._join_relay_btn)
        layout.addLayout(relay_btn_row)
        self._relay_server_btn = QPushButton(qta.icon("fa5s.cloud", color=QColor(212, 212, 212)), " Start Relay Server")
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
        self._copy_invite_btn = QPushButton(qta.icon("fa5s.copy", color=QColor(212, 212, 212)), " Copy")
        self._copy_invite_btn.clicked.connect(self._on_copy_invite)
        invite_row.addWidget(self._copy_invite_btn)
        self._join_invite_btn = QPushButton(qta.icon("fa5s.ticket-alt", color=QColor(212, 212, 212)), " Join")
        self._join_invite_btn.clicked.connect(self._on_join_invite)
        invite_row.addWidget(self._join_invite_btn)
        layout.addLayout(invite_row)
        self._disconnect_btn = QPushButton(qta.icon("fa5s.unlink", color=QColor(255, 255, 255)), " Disconnect")
        self._disconnect_btn.setStyleSheet("QPushButton { background: rgb(192, 57, 43); }")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._disconnect_btn.setEnabled(False)
        layout.addWidget(self._disconnect_btn)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)
        self._play_btn = QPushButton(qta.icon("fa5s.play", color=QColor(212, 212, 212)), " Play Mode (Lock)")
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
        self._sync_btn = QPushButton(qta.icon("fa5s.sync-alt", color=QColor(212, 212, 212)), " Sync Assets")
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
