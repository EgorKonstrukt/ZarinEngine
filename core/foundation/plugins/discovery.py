# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
import os
import platform
import shutil
import tempfile
from core.foundation.logger import Logger
from core.foundation.plugins.base import PLUGIN_API_VERSION, _project_root
from core.foundation.plugins.lifecycle import _compare_versions, _installed_dist_version, _normalize_dist_name, _spec_satisfied, _split_plugin_require, _split_requirement
from core.foundation.plugins.ui_registry import _canonical_manifest_bytes, _hash_file, _read_archive_manifest, _scan_provides, _self_provided_modules


class DiscoveryMixin:
    def _plugin_security_config(self) -> dict:
        cfg = {"allow_unsigned": "warn", "registry_url": "",
               "check_updates_on_startup": False, "trusted_keys_dir": ""}
        try:
            from core.config.config import get_global_config
            g = get_global_config()
            for k in cfg:
                v = g.get("plugins." + k, None)
                if v is not None:
                    cfg[k] = v
        except Exception:
            pass
        return cfg

    def _trusted_keys(self) -> set:
        keys = set()
        custom = str(self._plugin_security_config().get("trusted_keys_dir", "") or "")
        dirs = []
        if custom:
            dirs.append(custom if os.path.isabs(custom) else os.path.join(_project_root(), custom))
        dirs.append(os.path.join(_project_root(), "config", "trusted_keys"))
        for d in dirs:
            try:
                if not os.path.isdir(d):
                    continue
                for fname in sorted(os.listdir(d)):
                    if not fname.endswith(".pub"):
                        continue
                    with open(os.path.join(d, fname), "r", encoding="utf-8") as f:
                        for token in f.read().split():
                            token = token.strip().lower()
                            if len(token) == 64:
                                try:
                                    bytes.fromhex(token)
                                    keys.add(token)
                                except Exception:
                                    pass
            except Exception:
                pass
        return keys

    def verify_manifest_signature(self, manifest: dict):
        sig = manifest.get("signature") if isinstance(manifest, dict) else None
        if not isinstance(sig, dict) or not sig.get("sig"):
            return (False, "unsigned")
        keys = self._trusted_keys()
        if not keys:
            return (False, "no trusted keys configured")
        msg = _canonical_manifest_bytes(manifest)
        by = str(sig.get("by", "") or "").lower()
        candidates = [by] if by in keys else sorted(keys)
        from core.foundation.ed25519 import verify_hex
        for pub in candidates:
            try:
                if verify_hex(str(sig.get("sig", "")), msg, pub):
                    return (True, pub)
            except Exception:
                continue
        return (False, "signature mismatch")

    def verify_zplugin_file(self, path: str):
        manifest = _read_archive_manifest(path)
        if not manifest:
            return (False, "missing or unreadable manifest.json", {})
        ok, reason = self.verify_manifest_signature(manifest)
        if ok:
            return (True, "signed", manifest)
        if reason != "unsigned":
            return (False, reason, manifest)
        policy = str(self._plugin_security_config().get("allow_unsigned", "warn"))
        if policy == "strict":
            return (False, "unsigned package blocked by policy", manifest)
        return (True, "unsigned", manifest)

    def _verify_payload_files(self, payload_dir: str, manifest: dict) -> list:
        errors = []
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(files, dict):
            return ["manifest has no file index"]
        for rel, want in files.items():
            p = os.path.join(payload_dir, str(rel).replace("/", os.sep))
            if not os.path.isfile(p):
                errors.append(f"missing file '{rel}'")
                continue
            try:
                if _hash_file(p) != str(want).lower():
                    errors.append(f"modified file '{rel}'")
            except Exception as e:
                errors.append(f"unreadable file '{rel}': {e}")
        for root, _dirs, fns in os.walk(payload_dir):
            for fn in fns:
                if fn.endswith((".pyd", ".so", ".dll")):
                    rel = os.path.relpath(os.path.join(root, fn), payload_dir).replace(os.sep, "/")
                    if rel.startswith("_native/"):
                        continue
                    if rel not in files:
                        errors.append(f"unindexed native module '{rel}'")
        return errors

    def _check_pip_requirement(self, spec: str, self_provided=frozenset()):
        name, constraint = _split_requirement(spec)
        if not name:
            return (False, f"bad requirement '{spec}'")
        if _normalize_dist_name(name) in self_provided:
            return (True, "")
        ver = _installed_dist_version(name)
        if ver is not None and _spec_satisfied(constraint, ver):
            return (True, "")
        lib = self._libraries.get(_normalize_dist_name(name))
        if lib is not None:
            lv = str(lib.get("version") or "")
            if not constraint or (lv and lv != "unknown" and _spec_satisfied(constraint, lv)):
                return (True, "")
        have = ver if ver is not None else (str(lib.get("version")) if lib else "")
        return (False, f"{spec} ({('have ' + have) if have else 'not installed'})")

    def _manifest_gate_errors(self, manifest: dict, self_provided=frozenset()) -> dict:
        blocked, missing = [], []
        if not isinstance(manifest, dict) or not manifest:
            return {"blocked": blocked, "missing": missing}
        api = manifest.get("engine_api")
        if api and not _spec_satisfied(str(api), str(PLUGIN_API_VERSION)):
            blocked.append(f"engine API {api} not satisfied (current {PLUGIN_API_VERSION})")
        pyreq = manifest.get("python_requires")
        if pyreq and not _spec_satisfied(str(pyreq), platform.python_version()):
            blocked.append(f"python {pyreq} not satisfied (current {platform.python_version()})")
        for dep in manifest.get("dependencies", []) or []:
            ok, reason = self._check_pip_requirement(dep, self_provided)
            if not ok:
                missing.append(f"missing dependency: {reason}")
        for req in manifest.get("requires", []) or []:
            name, verspec = _split_plugin_require(req)
            p = self._plugins.get(name)
            if p is None or not _spec_satisfied(verspec, str(p.VERSION)):
                missing.append(f"requires plugin '{name}{(' ' + verspec) if verspec else ''}'")
        return {"blocked": blocked, "missing": missing}

    def _gate_or_defer(self, kind: str, path: str, manifest: dict) -> bool:
        name = str(manifest.get("name", "") or os.path.basename(path))
        gates = self._manifest_gate_errors(manifest, _self_provided_modules(kind, path, manifest))
        if gates["blocked"]:
            self._set_status(name, "blocked", "; ".join(gates["blocked"]))
            Logger.error(f"[Plugin] '{name}' blocked: {'; '.join(gates['blocked'])}")
            return False
        if gates["missing"]:
            self._pending.append({"kind": kind, "path": path, "manifest": dict(manifest)})
            self._set_status(name, "unresolved", "; ".join(gates["missing"]))
            Logger.warning(f"[Plugin] '{name}' deferred: {'; '.join(gates['missing'])}")
            return False
        return True

    def recheck_pending(self):
        self._drain_pending()

    def _drain_pending(self):
        items, self._pending = self._pending, []
        for item in items:
            manifest = item.get("manifest", {})
            name = str(manifest.get("name", "") or os.path.basename(item.get("path", "")))
            gates = self._manifest_gate_errors(manifest, _self_provided_modules(item.get("kind"), item.get("path"), manifest))
            if gates["blocked"]:
                self._set_status(name, "blocked", "; ".join(gates["blocked"]))
                continue
            if gates["missing"]:
                self._pending.append(item)
                self._set_status(name, "unresolved", "; ".join(gates["missing"]))
                continue
            kind, path = item.get("kind"), item.get("path")
            if kind == "zplugin":
                self.load_zplugin(path)
            elif kind == "package":
                self.load_package(path)
            elif kind == "pyfile":
                self.load_from_file(path)

    def _record_lib_owner(self, mod, owner, path):
        key = (_normalize_dist_name(mod), str(owner), str(path))
        if key not in self._lib_owners:
            self._lib_owners.append(key)

    def _register_library_pack(self, pack_name, version, provides, libs_dir):
        provides = dict(provides) if isinstance(provides, dict) else {}
        if not provides and libs_dir:
            provides = _scan_provides(libs_dir)
        modules = []
        for mod, ver in provides.items():
            key = _normalize_dist_name(mod)
            if not key:
                continue
            self._libraries[key] = {"owner": str(pack_name), "version": str(ver or "unknown"),
                                    "path": str(libs_dir or "")}
            modules.append(key)
        if libs_dir:
            for mod in provides:
                self._record_lib_owner(mod, pack_name, libs_dir)
        self._library_packs[str(pack_name)] = {"version": str(version or "unknown"), "modules": modules}
        self._set_status(str(pack_name), "loaded")

    def _register_library_package(self, dirpath: str, manifest: dict):
        name = str(manifest.get("name", "") or os.path.basename(dirpath))
        version = str(manifest.get("version", "unknown"))
        libs_dir = os.path.join(dirpath, "libs")
        if os.path.isdir(libs_dir):
            self._activate_bundled_libs(libs_dir, manifest.get("dependencies", []), name)
        self._register_library_pack(name, version, manifest.get("provides", {}),
                                    libs_dir if os.path.isdir(libs_dir) else "")
        Logger.info(f"[Plugin] Library pack '{name}' v{version} ready.")

    def _register_library_archive(self, manifest: dict, payload_dir: str):
        name = str(manifest.get("name", "unnamed"))
        version = str(manifest.get("version", "unknown"))
        libs_dir = os.path.join(payload_dir, "libs")
        self._register_library_pack(name, version, manifest.get("provides", {}),
                                    libs_dir if os.path.isdir(libs_dir) else "")
        Logger.info(f"[Plugin] Library pack '{name}' v{version} ready.")

    def _installed_plugin_version(self, name: str):
        p = self._plugins.get(name)
        if p is not None:
            return str(p.VERSION)
        pack = self._library_packs.get(name)
        if pack is not None:
            return str(pack.get("version", "unknown"))
        return None

    def fetch_plugin_index(self, url=None, timeout=15):
        url = url or str(self._plugin_security_config().get("registry_url", "") or "")
        if not url:
            return {}
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=timeout) as r:
                loaded = json.loads(r.read().decode("utf-8"))
                return loaded if isinstance(loaded, dict) else {}
        except Exception as e:
            Logger.error(f"[Plugin] registry fetch failed: {e}")
            return {}

    def check_plugin_updates(self, index=None, url=None):
        if index is None:
            index = self.fetch_plugin_index(url)
        entries = index.get("plugins", []) if isinstance(index, dict) else []
        out = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            name = str(e.get("name", "") or "")
            avail = str(e.get("version", "") or "")
            if not name or not avail:
                continue
            cur = self._installed_plugin_version(name)
            if cur is None or cur == "unknown":
                continue
            try:
                if _compare_versions(avail, cur) > 0:
                    out.append({"name": name, "current": cur, "available": avail,
                                "url": str(e.get("download_url", "") or ""),
                                "sha256": str(e.get("sha256", "") or ""),
                                "summary": str(e.get("summary", "") or "")})
            except Exception:
                continue
        return out

    def download_plugin_file(self, url, dest_dir, expected_sha256=None, timeout=60):
        try:
            import urllib.request
            os.makedirs(dest_dir, exist_ok=True)
            base = os.path.basename(str(url).split("?")[0]) or "download.zplugin"
            fd, tmp = tempfile.mkstemp(dir=dest_dir, suffix=".part")
            os.close(fd)
            try:
                with urllib.request.urlopen(url, timeout=timeout) as r, open(tmp, "wb") as f:
                    shutil.copyfileobj(r, f)
                if expected_sha256 and _hash_file(tmp) != str(expected_sha256).lower():
                    raise ValueError("sha256 mismatch")
                final = os.path.join(dest_dir, base)
                if os.path.abspath(final) == os.path.abspath(tmp):
                    return final
                if os.path.exists(final):
                    os.remove(final)
                os.replace(tmp, final)
                return final
            except Exception:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                raise
        except Exception as e:
            Logger.error(f"[Plugin] download failed: {e}")
            return ""

    def _find_installed_archive(self, name: str, plugins_dir="plugins"):
        try:
            for fname in sorted(os.listdir(plugins_dir)):
                if not fname.endswith(".zplugin"):
                    continue
                manifest = _read_archive_manifest(os.path.join(plugins_dir, fname))
                if manifest.get("name") == name:
                    return os.path.join(plugins_dir, fname)
        except Exception:
            pass
        return ""

    def _pending_queue_path(self, plugins_dir="plugins"):
        d = os.path.join(plugins_dir, ".pending")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "updates.json")

    def _read_pending_queue(self, plugins_dir="plugins"):
        try:
            with open(self._pending_queue_path(plugins_dir), "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    return [q for q in loaded if isinstance(q, dict)]
        except Exception:
            pass
        return []

    def _write_pending_queue(self, queue, plugins_dir="plugins"):
        try:
            with open(self._pending_queue_path(plugins_dir), "w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2)
            return True
        except Exception as e:
            Logger.error(f"[Plugin] could not write update queue: {e}")
            return False

    def install_plugin_file(self, src, plugins_dir="plugins"):
        try:
            if str(src).endswith(".zplugin"):
                ok, reason, _m = self.verify_zplugin_file(src)
                if not ok:
                    return (False, reason)
            os.makedirs(plugins_dir, exist_ok=True)
            dest = os.path.join(plugins_dir, os.path.basename(src))
            shutil.copy2(src, dest)
            return (True, dest)
        except Exception as e:
            return (False, str(e))

    def stage_plugin_update(self, name, url, sha256=None, plugins_dir="plugins"):
        staged = self.download_plugin_file(url, os.path.join(plugins_dir, ".pending"), sha256)
        if not staged:
            return False
        queue = [q for q in self._read_pending_queue(plugins_dir) if q.get("name") != name]
        queue.append({"name": name, "staged": staged,
                      "current": self._find_installed_archive(name, plugins_dir)})
        return self._write_pending_queue(queue, plugins_dir)

    def apply_pending_updates(self, plugins_dir="plugins"):
        queue = self._read_pending_queue(plugins_dir)
        if not queue:
            return []
        backup_dir = os.path.join(plugins_dir, ".backup")
        os.makedirs(backup_dir, exist_ok=True)
        applied, remaining = [], []
        for q in queue:
            try:
                name, staged = q.get("name", ""), q.get("staged", "")
                if not name or not staged or not os.path.isfile(staged):
                    raise ValueError("staged file missing")
                target = os.path.join(plugins_dir, os.path.basename(staged))
                current = q.get("current") or ""
                backup = os.path.join(backup_dir, os.path.basename(target) + ".bak")
                if os.path.exists(backup):
                    os.remove(backup)
                sidecar = backup + ".json"
                if os.path.exists(sidecar):
                    os.remove(sidecar)
                if current and os.path.isfile(current) and os.path.abspath(current) != os.path.abspath(target):
                    shutil.copy2(current, backup)
                    with open(sidecar, "w", encoding="utf-8") as f:
                        json.dump({"original": os.path.basename(current)}, f)
                    os.remove(current)
                elif os.path.isfile(target):
                    os.replace(target, backup)
                os.replace(staged, target)
                applied.append(name)
            except Exception as e:
                Logger.error(f"[Plugin] update apply failed for '{q.get('name', '?')}': {e}")
                remaining.append(q)
        self._write_pending_queue(remaining, plugins_dir)
        return applied

    def rollback_plugin(self, name, plugins_dir="plugins"):
        try:
            current = self._find_installed_archive(name, plugins_dir)
            if not current:
                return False
            backup = os.path.join(plugins_dir, ".backup", os.path.basename(current) + ".bak")
            if not os.path.isfile(backup):
                return False
            sidecar = backup + ".json"
            original = ""
            try:
                with open(sidecar, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        original = str(saved.get("original", "") or "")
            except Exception:
                pass
            os.remove(current)
            if original and original != os.path.basename(current):
                os.replace(backup, os.path.join(plugins_dir, original))
            else:
                os.replace(backup, current)
            try:
                if os.path.isfile(sidecar):
                    os.remove(sidecar)
            except Exception:
                pass
            return True
        except Exception as e:
            Logger.error(f"[Plugin] rollback failed for '{name}': {e}")
            return False
