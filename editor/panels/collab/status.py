# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from PyQt6.QtWidgets import QListWidgetItem
from PyQt6.QtGui import QColor, QFont


class CollaborationStatusMixin:
    def _update_upnp_label(self):
        if not self._collab:
            return
        try:
            snap = self._collab.upnp_status
        except Exception:
            return
        try:
            state = str(snap.get("state", "idle"))
            if state == "mapped":
                self._upnp_label.setText(f"UPnP: {snap.get('external_ip', '')}:{snap.get('external_port', '')} mapped")
            elif state == "discovering":
                self._upnp_label.setText("UPnP: discovering router...")
            elif state == "failed":
                err = str(snap.get("error", ""))[:60]
                self._upnp_label.setText(f"UPnP: failed ({err}), use relay")
            elif state == "disabled":
                self._upnp_label.setText("UPnP: off")
            else:
                self._upnp_label.setText("UPnP: idle")
        except Exception:
            pass

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

    def _refresh_peers(self):
        if not self._collab:
            return
        self._update_status()
        try:
            self._update_upnp_label()
        except Exception:
            pass
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
