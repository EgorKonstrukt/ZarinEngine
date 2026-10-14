# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
import msgpack
from core.config.config import get_global_config
class SettingsMixin:
    def apply_settings(self):
        try:
            self._poll_thread._interval = max(0.001, float(self.settings.poll_interval) / 1000.0)
        except Exception:
            pass
    def _load_settings_from_config(self):
        try:
            cfg = get_global_config()
        except Exception:
            return
        s = self.settings
        try:
            s.cursor_interval = 1.0 / max(1.0, float(cfg.get("collab.cursor_rate", 30.0)))
            s.camera_interval = 1.0 / max(1.0, float(cfg.get("collab.camera_rate", 15.0)))
            s.transform_interval = 1.0 / max(1.0, float(cfg.get("collab.transform_rate", 20.0)))
            s.gizmo_interval = 1.0 / max(1.0, float(cfg.get("collab.gizmo_rate", 10.0)))
            s.ping_interval = float(cfg.get("collab.ping_interval", 3.0))
            s.poll_interval = int(cfg.get("collab.poll_interval", 8))
            s.scene_sync_interval = float(cfg.get("collab.scene_sync_interval", 2.0))
            s.relay_url = str(cfg.get("collab.relay_url", s.relay_url))
            s.auto_reconnect = bool(cfg.get("collab.auto_reconnect", True))
            s.heartbeat_timeout = float(cfg.get("collab.heartbeat_timeout", 30.0))
            s.upnp_enabled = bool(cfg.get("collab.upnp_enabled", True))
            s.upnp_lease = int(cfg.get("collab.upnp_lease", 3600))
        except Exception:
            pass
    def save_settings_to_config(self):
        try:
            cfg = get_global_config()
        except Exception:
            return
        s = self.settings
        try:
            cfg.set("collab.cursor_rate", 1.0 / max(0.001, float(s.cursor_interval)))
            cfg.set("collab.camera_rate", 1.0 / max(0.001, float(s.camera_interval)))
            cfg.set("collab.transform_rate", 1.0 / max(0.001, float(s.transform_interval)))
            cfg.set("collab.gizmo_rate", 1.0 / max(0.001, float(s.gizmo_interval)))
            cfg.set("collab.ping_interval", float(s.ping_interval))
            cfg.set("collab.poll_interval", int(s.poll_interval))
            cfg.set("collab.scene_sync_interval", float(s.scene_sync_interval))
            cfg.set("collab.relay_url", str(s.relay_url))
            cfg.set("collab.auto_reconnect", bool(s.auto_reconnect))
            cfg.set("collab.heartbeat_timeout", float(s.heartbeat_timeout))
            cfg.set("collab.upnp_enabled", bool(s.upnp_enabled))
            cfg.set("collab.upnp_lease", int(s.upnp_lease))
            cfg.save()
        except Exception:
            pass
    def _handle_chunk_impl(self, data: dict):
        pid = str(data.get("id", ""))
        cid = str(data.get("cid", ""))
        if not cid or not pid:
            return
        try:
            idx = int(data.get("idx", 0))
            total = int(data.get("total", 0))
            inner_type = int(data.get("inner_type", 0))
        except Exception:
            return
        part = data.get("part")
        if part is None or total <= 0 or total > 4096 or idx < 0 or idx >= total:
            return
        if isinstance(part, str):
            part = part.encode("utf-8")
        key = (pid, cid)
        with self._chunk_lock:
            entry = self._chunk_in.get(key)
            if entry is None:
                entry = {"total": total, "inner_type": inner_type, "parts": {}, "time": time.time()}
                self._chunk_in[key] = entry
            if entry.get("total") != total:
                return
            parts = entry["parts"]
            if idx not in parts:
                parts[idx] = bytes(part)
            if len(parts) < total:
                return
            ordered = b"".join(parts[i] for i in range(total))
            try:
                del self._chunk_in[key]
            except Exception:
                pass
        try:
            obj = msgpack.unpackb(ordered, raw=False)
            t = int(obj["t"])
            d = dict(obj["d"])
        except Exception:
            return
        d["id"] = pid
        try:
            self._handle_message(int(t), d)
        except Exception:
            pass
        now = time.time()
        with self._chunk_lock:
            for k in [k for k, v in self._chunk_in.items() if now - float(v.get("time", now)) > 30.0]:
                try:
                    del self._chunk_in[k]
                except Exception:
                    pass
