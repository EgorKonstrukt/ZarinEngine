# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import hashlib
import json
import os
import time
from typing import Callable
from core.foundation.logger import Logger
from core.network.protocol import MessageType
from .util import _compute_hash, _scan_assets_dir
from .watcher import _AssetWatcher
class AssetSyncMixin:
    def set_asset_progress_callback(self, cb: Callable[[dict], None]):
        self._on_asset_progress = cb
    @property
    def asset_syncing(self) -> bool:
        return bool(self._asset_syncing)
    @property
    def asset_sync_progress(self) -> dict:
        try:
            return dict(self._asset_sync_progress)
        except Exception:
            return {"total": 0, "current": 0, "current_file": "", "failed": 0}
    def _get_assets_dir(self) -> str:
        try:
            root = self._engine.project_root if getattr(self._engine, "project_root", None) else os.getcwd()
        except Exception:
            root = os.getcwd()
        return os.path.join(str(root), "assets")
    def _scan_assets(self) -> dict[str, dict]:
        return _scan_assets_dir(self._get_assets_dir())
    def _load_checksums(self, manifest: dict[str, dict]) -> dict[str, str]:
        cache = {}
        base = self._get_assets_dir()
        for rel in manifest.keys():
            full = os.path.join(base, rel)
            if os.path.exists(full):
                try:
                    cache[rel] = _compute_hash(full)
                except Exception:
                    cache[rel] = ""
            else:
                cache[rel] = ""
        return cache
    def request_asset_list(self):
        self._send_link(MessageType.ASSET_LIST_REQ, {})
    def send_asset_list(self, target_peer_id: str):
        manifest = self._scan_assets()
        self._asset_checksums = self._load_checksums(manifest)
        paths = list(manifest.keys())
        self._send_link(MessageType.ASSET_LIST, {"target": str(target_peer_id), "assets": paths, "checksums": {p: self._asset_checksums.get(p, "") for p in paths}})
    def send_asset_file(self, relative_path: str, target_peer_id: str = ""):
        full = os.path.join(self._get_assets_dir(), str(relative_path))
        if not os.path.exists(full):
            return
        try:
            with open(full, "rb") as f:
                raw = f.read()
        except Exception as e:
            Logger.error(f"Collab read asset '{relative_path}' failed: {e}")
            return
        try:
            checksum = _compute_hash(full)
        except Exception:
            checksum = ""
        payload = {"path": str(relative_path), "data": raw, "checksum": checksum, "size": len(raw)}
        if target_peer_id:
            payload["target"] = str(target_peer_id)
        self._send_link(MessageType.ASSET_SYNC, payload)
    def send_asset_request(self, relative_path: str, target_peer_id: str = ""):
        payload = {"path": str(relative_path)}
        if target_peer_id:
            payload["target"] = str(target_peer_id)
        else:
            try:
                if self._as_host:
                    pass
            except Exception:
                pass
        self._send_link(MessageType.ASSET_REQUEST, payload)
    def _handle_asset_request(self, data: dict):
        rel = str(data.get("path", ""))
        if not rel:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        target = str(data.get("id", ""))
        try:
            self.send_asset_file(rel, target)
        except Exception:
            pass
    def send_asset_delete(self, relative_path: str):
        self._send_link(MessageType.ASSET_DELETE, {"path": str(relative_path)})
    def _send_watch_update(self, relative_path: str):
        try:
            with self._asset_write_lock:
                busy = self._asset_write_count > 0
        except Exception:
            busy = False
        if busy or self._asset_syncing:
            return
        client = self._client
        if client is None:
            return
        try:
            if not client.connected:
                return
        except Exception:
            return
        full = os.path.join(self._get_assets_dir(), str(relative_path))
        if not os.path.exists(full):
            return
        try:
            with open(full, "rb") as f:
                raw = f.read()
        except Exception:
            return
        self._send_link(MessageType.ASSET_WATCH, {"path": str(relative_path), "data": raw, "size": len(raw)})
    def _start_asset_watcher(self):
        try:
            self._stop_asset_watcher()
        except Exception:
            pass
        ad = self._get_assets_dir()
        if not os.path.isdir(ad):
            return
        def _on_watch_change(rel):
            try:
                with self._suppressed_lock:
                    if rel in self._suppressed_paths:
                        self._suppressed_paths.discard(rel)
                        return
                self._send_watch_update(rel)
            except Exception:
                pass
        def _on_watch_delete(rel):
            try:
                with self._suppressed_lock:
                    if rel in self._suppressed_paths:
                        self._suppressed_paths.discard(rel)
                        return
                self.send_asset_delete(rel)
            except Exception:
                pass
        try:
            self._asset_watcher = _AssetWatcher(ad, 2.0, on_change=_on_watch_change, on_delete=_on_watch_delete)
            self._asset_watcher.start()
        except Exception:
            self._asset_watcher = None
    def _stop_asset_watcher(self):
        if self._asset_watcher:
            try:
                self._asset_watcher.stop()
            except Exception:
                pass
            self._asset_watcher = None
    def _scene_hash(self, scene) -> str:
        try:
            data = scene.serialize()
            raw = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
            return hashlib.md5(raw).hexdigest()
        except Exception:
            return ""
    def _sync_server_scene(self):
        if not self._as_host:
            return
        if self._mode != "direct":
            return
        if not self._server:
            return
        now = time.time()
        if now - float(self._last_scene_sync) < float(self.settings.scene_sync_interval):
            return
        self._last_scene_sync = now
        try:
            scene = self._engine.scene
        except Exception:
            scene = None
        if scene:
            try:
                h = self._scene_hash(scene)
            except Exception:
                h = ""
            if h and h == self._last_scene_hash:
                return
            self._last_scene_hash = str(h)
            try:
                self.update_server_scene(scene)
            except Exception:
                pass
    def _handle_asset_list(self, data: dict):
        paths = data.get("assets", [])
        checksums = data.get("checksums", {})
        if not isinstance(paths, list):
            return
        if not isinstance(checksums, dict):
            checksums = {}
        assets_dir = self._get_assets_dir()
        try:
            os.makedirs(assets_dir, exist_ok=True)
        except Exception:
            pass
        need_sync = []
        for rel in paths:
            if not isinstance(rel, str) or not rel or ".." in rel.replace("\\", "/").split("/"):
                continue
            full = os.path.join(assets_dir, rel)
            expected = str(checksums.get(rel, ""))
            if os.path.exists(full):
                try:
                    actual = _compute_hash(full)
                except Exception:
                    actual = ""
                if actual == expected and expected:
                    continue
                if not expected and os.path.exists(full):
                    continue
            need_sync.append(rel)
        self._asset_syncing = True
        self._asset_sync_progress = {"total": len(need_sync), "current": 0, "current_file": "", "failed": 0}
        own = self.own_peer_id
        sender = str(data.get("id", ""))
        for rel in need_sync:
            self._asset_sync_progress["current_file"] = rel
            if self._on_asset_progress:
                try:
                    self._on_asset_progress(dict(self._asset_sync_progress))
                except Exception:
                    pass
            try:
                self._send_link(MessageType.ASSET_REQUEST, {"path": rel, "target": sender})
            except Exception:
                pass
        if not need_sync:
            self._asset_syncing = False
            self._asset_sync_progress["current_file"] = ""
            self._asset_sync_progress["current"] = 0
            if self._on_asset_progress:
                try:
                    self._on_asset_progress(dict(self._asset_sync_progress))
                except Exception:
                    pass
    def _handle_asset_sync(self, data: dict):
        rel = str(data.get("path", ""))
        raw = data.get("data")
        checksum = str(data.get("checksum", ""))
        if not rel or raw is None:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        assets_dir = self._get_assets_dir()
        full = os.path.join(assets_dir, rel)
        try:
            os.makedirs(os.path.dirname(full) or assets_dir, exist_ok=True)
        except Exception:
            pass
        with self._suppressed_lock:
            self._suppressed_paths.add(rel)
        with self._asset_write_lock:
            self._asset_write_count += 1
        try:
            with open(full, "wb") as f:
                f.write(bytes(raw))
        except Exception as e:
            Logger.error(f"Collab asset write failed '{rel}': {e}")
            with self._asset_write_lock:
                self._asset_write_count = max(0, self._asset_write_count - 1)
            try:
                self._asset_sync_progress["failed"] += 1
            except Exception:
                pass
            return
        with self._asset_write_lock:
            self._asset_write_count = max(0, self._asset_write_count - 1)
        if checksum:
            try:
                actual = _compute_hash(full)
                if actual != checksum:
                    Logger.warning(f"Collab asset '{rel}' checksum mismatch")
            except Exception:
                pass
        try:
            self._asset_sync_progress["current"] += 1
            if self._asset_sync_progress["current"] >= self._asset_sync_progress["total"]:
                self._asset_syncing = False
                self._asset_sync_progress["current_file"] = ""
            if self._on_asset_progress:
                self._on_asset_progress(dict(self._asset_sync_progress))
        except Exception:
            pass
    def _handle_asset_watch(self, data: dict):
        rel = str(data.get("path", ""))
        raw = data.get("data")
        if not rel or raw is None:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        assets_dir = self._get_assets_dir()
        full = os.path.join(assets_dir, rel)
        try:
            os.makedirs(os.path.dirname(full) or assets_dir, exist_ok=True)
        except Exception:
            pass
        with self._suppressed_lock:
            self._suppressed_paths.add(rel)
        with self._asset_write_lock:
            self._asset_write_count += 1
        try:
            with open(full, "wb") as f:
                f.write(bytes(raw))
        except Exception as e:
            Logger.error(f"Collab watched asset write failed '{rel}': {e}")
        finally:
            with self._asset_write_lock:
                self._asset_write_count = max(0, self._asset_write_count - 1)
    def _handle_asset_delete(self, data: dict):
        rel = str(data.get("path", ""))
        if not rel:
            return
        if ".." in rel.replace("\\", "/").split("/"):
            return
        assets_dir = self._get_assets_dir()
        full = os.path.join(assets_dir, rel)
        with self._suppressed_lock:
            self._suppressed_paths.add(rel)
        with self._asset_write_lock:
            self._asset_write_count += 1
        try:
            if os.path.exists(full):
                os.remove(full)
                Logger.info(f"Collab removed asset '{rel}'")
        except Exception as e:
            Logger.error(f"Collab remove asset '{rel}' failed: {e}")
        finally:
            with self._asset_write_lock:
                self._asset_write_count = max(0, self._asset_write_count - 1)
    def _handle_asset_branch(self, msg_type: int, data: dict):
        if msg_type == int(MessageType.ASSET_LIST_REQ):
            pid = str(data.get("id", ""))
            self._touch(pid)
            if self._as_host and pid:
                try:
                    self.send_asset_list(pid)
                except Exception:
                    pass
            return True
        if msg_type == int(MessageType.ASSET_LIST):
            own = self.own_peer_id
            target = str(data.get("target", ""))
            if target and target != own:
                return True
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_list(data)
            except Exception:
                pass
            return True
        if msg_type == int(MessageType.ASSET_SYNC):
            own = self.own_peer_id
            target = str(data.get("target", ""))
            if target and target != own:
                return True
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_sync(data)
            except Exception:
                pass
            return True
        if msg_type == int(MessageType.ASSET_WATCH):
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_watch(data)
            except Exception:
                pass
            return True
        if msg_type == int(MessageType.ASSET_DELETE):
            self._touch(str(data.get("id", "")))
            try:
                self._handle_asset_delete(data)
            except Exception:
                pass
            return True
        if msg_type == int(MessageType.ASSET_REQUEST):
            pid = str(data.get("id", ""))
            self._touch(pid)
            target = str(data.get("target", ""))
            own = self.own_peer_id
            if target and target != own and not self._as_host:
                return True
            if self._as_host:
                try:
                    self._handle_asset_request(data)
                except Exception:
                    pass
            return True
        return False
