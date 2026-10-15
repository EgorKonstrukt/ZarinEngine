# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import fnmatch
import importlib.util
import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from core.foundation.plugins import current_architecture
except Exception:
    import platform

    def current_architecture() -> str:
        sys_name = {"win32": "win", "darwin": "macos"}.get(sys.platform, sys.platform)
        machine = {"amd64": "x86_64", "x86_64": "x86_64", "x64": "x86_64",
                   "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
        return f"{sys_name}_{machine}"

_ed_gen = None
_ed_pub = None
_ed_sign = None
_pm_canonical = None
_pm_split_requirement = None
_pm_split_spec = None
_PM_OK = False
try:
    from core.foundation.ed25519 import (
        generate_hex as _ed_gen,
    )
    from core.foundation.ed25519 import (
        publickey_hex as _ed_pub,
    )
    from core.foundation.ed25519 import (
        sign_hex as _ed_sign,
    )
    from core.foundation.plugins import (
        _canonical_manifest_bytes as _pm_canonical,
    )
    from core.foundation.plugins import (
        _split_requirement as _pm_split_requirement,
    )
    from core.foundation.plugins import (
        _split_spec as _pm_split_spec,
    )
    _PM_OK = True
except Exception:
    _PM_OK = False

DEFAULT_EXCLUDES = ["__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "*.egg-info"]

def load_source_manifest(plugin_dir: str) -> dict:
    path = os.path.join(plugin_dir, "manifest.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No manifest.json in '{plugin_dir}'")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not data.get("name"):
        raise ValueError(f"Invalid manifest.json in '{plugin_dir}' (need at least a 'name')")
    return data

def _excluded(rel_path: str, patterns: list[str]) -> bool:
    parts = rel_path.replace(os.sep, "/").split("/")
    for pat in patterns:
        if any(fnmatch.fnmatchcase(p, pat) for p in parts):
            return True
        if fnmatch.fnmatchcase(rel_path.replace(os.sep, "/"), pat):
            return True
    return False

def lint_manifest(plugin_src: str) -> list:
    try:
        meta = load_source_manifest(plugin_src)
    except (FileNotFoundError, ValueError) as e:
        return [str(e)]
    errors = []
    name = str(meta.get("name", ""))
    if not name:
        errors.append("manifest needs a 'name'")
    ptype = str(meta.get("type", "plugin"))
    if ptype not in ("plugin", "library"):
        errors.append(f"unknown type '{ptype}' (want 'plugin' or 'library')")
    module = str(meta.get("module", name))
    entry = str(meta.get("entry", f"{module}/__init__.py" if ptype == "plugin" else ""))
    if ptype == "plugin" and entry:
        parent = os.path.dirname(os.path.abspath(plugin_src))
        if not os.path.isfile(os.path.join(parent, entry)) and not os.path.isfile(os.path.join(plugin_src, entry)):
            errors.append(f"entry '{entry}' not found")
    if ptype == "library" and not meta.get("provides") and not os.path.isdir(os.path.join(plugin_src, "libs")):
        errors.append("library pack needs 'provides' or a libs/ directory")
    if _PM_OK:
        for dep in meta.get("dependencies", []) or []:
            if not _pm_split_requirement(dep)[0]:
                errors.append(f"bad dependency '{dep}'")
        for spec in (meta.get("engine_api", ""), meta.get("python_requires", "")):
            if spec and not all(op in ("==", "!=", ">=", "<=", "~=", ">", "<", "=") and want for op, want in _pm_split_spec(spec)):
                errors.append(f"bad version spec '{spec}'")
        for req in meta.get("requires", []) or []:
            if isinstance(req, dict):
                good = bool(req.get("name"))
            else:
                good = bool(_pm_split_requirement(str(req))[0])
            if not good:
                errors.append(f"bad plugin requirement '{req}'")
        sig = meta.get("signature")
        if sig is not None and (not isinstance(sig, dict) or not sig.get("sig")):
            errors.append("malformed 'signature' (want {'by': ..., 'sig': ...})")
    return errors

def _dist_top_levels(dist) -> list:
    try:
        tl = dist.read_text("top_level.txt")
        if tl:
            return [t.strip() for t in tl.split() if t.strip()]
    except Exception:
        pass
    tops = []
    try:
        files = dist.files or []
    except Exception:
        return tops
    for f in files:
        parts = str(f).replace("\\", "/").split("/")
        if not parts or parts[0].startswith(("_", ".")):
            continue
        if len(parts) == 1:
            if parts[0].endswith(".py"):
                tops.append(parts[0][:-3])
        elif not parts[0].endswith((".dist-info", ".egg-info")):
            tops.append(parts[0])
    return sorted(set(tops))

def _find_distribution(top: str):
    from importlib import metadata as _md
    try:
        return _md.distribution(top)
    except Exception:
        pass
    try:
        for dist in _md.distributions():
            if top in _dist_top_levels(dist):
                return dist
    except Exception:
        pass
    return None

def _dist_version(top: str) -> str:
    try:
        dist = _find_distribution(top)
        if dist is not None:
            return dist.version
    except Exception:
        pass
    return "unknown"

def _copy_dist_info(top: str, libs: str):
    try:
        dist = _find_distribution(top)
        src = str(getattr(dist, "_path", "") or "") if dist is not None else ""
        if src and os.path.isdir(src) and src.endswith(".dist-info"):
            dst = os.path.join(libs, os.path.basename(src))
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    except Exception as e:
        print(f"  bundle: dist-info for '{top}' skipped: {e}")

def _resolve_bundle_modules(names) -> list:
    out = []
    for raw in names or []:
        top = str(raw).strip().split(".")[0]
        if not top:
            continue
        try:
            found = importlib.util.find_spec(top) is not None
        except Exception:
            found = False
        if found:
            out.append(top)
            continue
        resolved = False
        try:
            from importlib import metadata as _md
            tops = _dist_top_levels(_md.distribution(top))
            if tops:
                out.extend(tops)
                resolved = True
        except Exception:
            pass
        if not resolved:
            out.append(top)
    seen = set()
    ordered = []
    for m in out:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered

def _wheel_name_version(whl_path):
    base = os.path.basename(whl_path)
    if base.endswith(".whl"):
        base = base[:-4]
    parts = base.split("-")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return base, "unknown"

def _wheel_top_levels(whl_path) -> list:
    tops = []
    try:
        with zipfile.ZipFile(whl_path) as zf:
            for n in zf.namelist():
                if n.endswith("/"):
                    continue
                parts = n.split("/")
                if not parts or parts[0].startswith(("_", ".")):
                    continue
                if parts[0].endswith((".dist-info", ".egg-info", ".data")):
                    continue
                if len(parts) == 1:
                    if parts[0].endswith(".py"):
                        tops.append(parts[0][:-3])
                else:
                    tops.append(parts[0])
    except Exception:
        pass
    return sorted(set(tops))

def _normalize_mod_name(name: str) -> str:
    return str(name or "").lower().replace("-", "_").replace(".", "_")

def _hash_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _hash_zip_member(zf, member: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with zf.open(member) as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _scan_stage_libs(libs: str) -> dict:
    provides = {}
    if not os.path.isdir(libs):
        return provides
    for entry in sorted(os.listdir(libs)):
        if entry.startswith((".", "_")) or entry == "__pycache__" or entry.endswith(".dist-info"):
            continue
        full = os.path.join(libs, entry)
        if entry.endswith(".py") and os.path.isfile(full):
            provides[entry[:-3]] = "unknown"
        elif os.path.isdir(full) and os.path.isfile(os.path.join(full, "__init__.py")):
            provides[entry] = "unknown"
    return provides

def _freeze_stage(stage: str) -> dict:
    import hashlib
    files = {}
    for root, _dirs, fns in os.walk(stage):
        for fn in sorted(fns):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, stage).replace(os.sep, "/")
            if rel == "manifest.json":
                continue
            h = hashlib.sha256()
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            files[rel] = h.hexdigest()
    return files

def _sign_manifest(manifest: dict, key_hex: str) -> dict:
    pub = _ed_pub(key_hex)
    manifest["signature"] = {"by": pub, "sig": _ed_sign(_pm_canonical(manifest), key_hex)}
    return manifest

ARCH_CHOICES = ["any", "current", "win_x86_64", "win_arm64",
                "linux_x86_64", "linux_arm64", "macos_x86_64", "macos_arm64"]

def list_installed_distributions() -> list:
    from importlib import metadata as _md
    out = []
    seen = set()
    for dist in _md.distributions():
        try:
            name = dist.metadata["Name"] or ""
        except Exception:
            continue
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tops = []
        try:
            tops = _dist_top_levels(dist)
        except Exception:
            pass
        if not tops:
            tops = [name.replace("-", "_")]
        try:
            version = dist.version
        except Exception:
            version = "unknown"
        out.append({"name": name, "version": version, "modules": tops})
    return sorted(out, key=lambda d: d["name"].lower())

def _pin_installed_versions(modules) -> list:
    from importlib import metadata as _md
    pinned = []
    for raw in modules or []:
        top = str(raw).strip().split(".")[0]
        if not top:
            continue
        try:
            dist = _find_distribution(top)
            dname = (dist.metadata["Name"] if dist is not None else top) or top
            ver = dist.version if dist is not None else ""
            pinned.append(f"{dname}=={ver}" if ver and ver != "unknown" else dname)
        except Exception:
            pinned.append(top)
    return pinned
