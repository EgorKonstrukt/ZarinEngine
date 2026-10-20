# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed
import hashlib
import json
import os
import zipfile
from typing import Any, Optional, TYPE_CHECKING
from core.foundation.logger import Logger
from core.foundation.plugins.lifecycle import _normalize_dist_name
if TYPE_CHECKING:
    from core.foundation.plugins.base import PluginBase


def _read_package_manifest(dirpath: str) -> dict:
    try:
        path = os.path.join(dirpath, "manifest.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
    except Exception:
        pass
    return {}


def _read_archive_manifest(path: str) -> dict:
    try:
        with zipfile.ZipFile(path) as zf:
            mname = next((n for n in zf.namelist() if n.endswith("manifest.json")), None)
            if mname is None:
                return {}
            loaded = json.loads(zf.open(mname).read().decode("utf-8"))
            if isinstance(loaded, dict):
                return loaded
    except Exception:
        pass
    return {}


def _scan_provides(libs_dir: str) -> dict:
    provides = {}
    try:
        for entry in sorted(os.listdir(libs_dir)):
            if entry.startswith((".", "_")) or entry == "__pycache__":
                continue
            full = os.path.join(libs_dir, entry)
            if entry.endswith(".py") and os.path.isfile(full):
                provides[entry[:-3]] = "unknown"
            elif os.path.isdir(full) and os.path.isfile(os.path.join(full, "__init__.py")):
                provides[entry] = "unknown"
    except Exception:
        pass
    return provides


_DERIVED_MANIFEST_KEYS = {"signature", "payload_dir", "entry_file", "entry_rel"}


def _canonical_manifest_bytes(manifest: dict) -> bytes:
    slim = {k: v for k, v in manifest.items() if k not in _DERIVED_MANIFEST_KEYS}
    return json.dumps(slim, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_files_many(paths: list[str]) -> dict[str, str]:
    if len(paths) <= 1:
        out: dict[str, str] = {}
        for p in paths:
            try:
                out[p] = _hash_file(p)
            except Exception:
                pass
        return out
    out = {}
    workers = min(8, len(paths))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_hash_file, p): p for p in paths}
        for fu in as_completed(futs):
            try:
                out[futs[fu]] = fu.result()
            except Exception:
                pass
    return out


def _fingerprints_many(paths: list[str]) -> dict[str, dict]:
    if len(paths) <= 1:
        return {p: _zplugin_fingerprint(p) for p in paths}
    out: dict[str, dict] = {}
    workers = min(8, len(paths))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_zplugin_fingerprint, p): p for p in paths}
        for fu in as_completed(futs):
            try:
                out[futs[fu]] = fu.result()
            except Exception:
                pass
    return out


def _self_provided_modules(kind, path, manifest: dict) -> set:
    out = set()
    if isinstance(manifest, dict):
        provides = manifest.get("provides")
        if isinstance(provides, dict):
            for mod in provides:
                key = _normalize_dist_name(mod)
                if key:
                    out.add(key)
    if kind == "package" and path:
        for mod in _scan_provides(os.path.join(path, "libs")):
            out.add(_normalize_dist_name(mod))
    return out


def _zplugin_fingerprint(path: str) -> dict:
    try:
        st = os.stat(path)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return {"sha256": h.hexdigest(), "size": st.st_size, "mtime": st.st_mtime}
    except Exception:
        return {}


class UiRegistryMixin:
    def sync_plugin_ui(self, plugin: PluginBase, kind: str, entry: dict):
        eng = self._engine
        reg = getattr(eng, "plugin_ui_registry", None) if eng is not None else None
        if reg is None:
            return
        if not isinstance(entry, dict) or entry.get("_synced"):
            return
        merged = {k: v for k, v in entry.items() if not k.startswith("_")}
        merged["plugin"] = plugin.NAME
        reg.setdefault(kind, []).append(merged)
        entry["_synced"] = True
        self._fire_runtime({"plugin": plugin.NAME, kind: [merged]}, reg)

    def _fire_runtime(self, payload: dict, reg=None):
        if reg is None:
            eng = self._engine
            reg = getattr(eng, "plugin_ui_registry", None) if eng is not None else None
        if not reg:
            return
        for cb in list(reg.get("runtime_listeners", [])):
            try:
                cb(payload)
            except Exception as e:
                Logger.error(f"[Plugin] UI runtime listener failed: {e}", e)

    def _notify_ui_registrations(self, plugin: PluginBase):
        if self._engine is None:
            return
        pairs = (
            ("docks", plugin._docks),
            ("toolbar_actions", plugin._toolbar_actions),
            ("toolbar_items", plugin._toolbar_items),
            ("menu_items", plugin._menu_items),
            ("file_openers", plugin._file_openers),
        )
        for kind, entries in pairs:
            for entry in list(entries):
                self.sync_plugin_ui(plugin, kind, entry)
