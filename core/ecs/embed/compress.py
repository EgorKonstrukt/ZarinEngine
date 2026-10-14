# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import base64
import hashlib
import os
import tempfile
import zlib
from typing import Optional
_CACHE_SUBDIR = os.path.join("Library", "Embedded")
_PATH_SUFFIX = "_path"
_MATERIAL_EXTS = (".mat", ".zpem")
def _compress(raw: bytes, level: int) -> bytes:
    if level <= 0 or len(raw) < 64:
        return raw
    comp = zlib.compress(raw, level)
    if len(comp) < len(raw):
        return comp
    return raw
def _decompress(data: bytes) -> bytes:
    if not data:
        return b""
    try:
        return zlib.decompress(data)
    except zlib.error:
        return data
def _is_material_file(abs_path: str) -> bool:
    return abs_path.lower().endswith(_MATERIAL_EXTS)
def _norm(p: str) -> str:
    return p.replace("\\", "/")
def _sanitize_name(name: str) -> str:
    name = "".join(c for c in name if c not in ':"/\\*?<>|') or "resource.bin"
    return name
def _key_candidates(val: str, root: str) -> set:
    v = _norm(val).lstrip("/")
    candidates = {v}
    if root:
        root_n = _norm(os.path.normpath(root)).rstrip("/") + "/"
        if v.lower().startswith(root_n.lower()):
            candidates.add(v[len(root_n):])
        if not os.path.isabs(val):
            for cand in (os.path.join(root, val), os.path.join(root, "assets", val)):
                candidates.add(_storage_key(_norm(os.path.normpath(cand)), root))
    absv = _abs_path(val, root)
    if absv:
        candidates.add(_storage_key(absv, root))
    return candidates
def _abs_path(val: str, root: str) -> Optional[str]:
    if not val:
        return None
    if os.path.isabs(val):
        if os.path.exists(val):
            return _norm(os.path.normpath(val))
        return None
    for cand in (os.path.join(root, val), os.path.join(root, "assets", val)):
        if os.path.exists(cand):
            return _norm(os.path.normpath(cand))
    return None
def _storage_key(abs_path: str, root: str) -> str:
    try:
        rel = os.path.relpath(abs_path, root)
        if not os.path.isabs(rel):
            return _norm(rel)
    except ValueError:
        pass
    return _norm(abs_path)
def _cache_dir(root: str, mode: str) -> str:
    if mode != "temp" and root:
        base = os.path.join(root, _CACHE_SUBDIR)
        try:
            os.makedirs(base, exist_ok=True)
            return base
        except OSError:
            pass
    base = os.path.join(tempfile.gettempdir(), "ZarinEngine", "Embedded")
    os.makedirs(base, exist_ok=True)
    return base
def _entry_cache_basename(entry: dict, storage: Optional[dict] = None) -> str:
    entry = _resolve_alias(entry, storage)
    digest = entry.get("digest")
    name = _sanitize_name(str(entry.get("name") or "resource.bin"))
    if not digest:
        raw = _entry_raw_bytes(entry)
        digest = hashlib.sha1(raw).hexdigest()[:16]
    return f"{digest}_{name}"
def _resolve_alias(entry: dict, storage: Optional[dict] = None) -> dict:
    if storage is None:
        return entry
    seen = 0
    while isinstance(entry.get("alias"), str):
        nxt = storage.get(entry["alias"])
        if nxt is None:
            break
        entry = nxt
        seen += 1
        if seen > 32:
            break
    return entry
def _entry_raw_bytes(entry: dict) -> bytes:
    data = base64.b64decode(entry["data"])
    if entry.get("compression"):
        return _decompress(data)
    return data
def _cache_path_for(storage_key: str, storage: dict, cache_dir: str) -> str:
    entry = storage.get(storage_key)
    if not entry:
        return ""
    entry = _resolve_alias(entry, storage)
    raw = _entry_raw_bytes(entry)
    digest = entry.get("digest")
    if not digest:
        digest = hashlib.sha1(raw).hexdigest()[:16]
    name = _sanitize_name(str(entry.get("name") or os.path.basename(storage_key)))
    path = os.path.join(cache_dir, f"{digest}_{name}")
    if not os.path.exists(path):
        try:
            with open(path, "wb") as f:
                f.write(raw)
        except OSError:
            return ""
    return _norm(os.path.abspath(path))
def _iter_component_path_entries(data: dict):
    entities = data.get("entities", {})
    for ed in entities.values():
        comps = ed.get("components", [])
        if not comps:
            continue
        for comp in comps:
            for key, val in comp.items():
                if key.endswith(_PATH_SUFFIX) and isinstance(val, str) and val:
                    yield ed, comp, (key,), val
            materials = comp.get("materials")
            if isinstance(materials, list):
                for i, entry in enumerate(materials):
                    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
                        yield ed, comp, ("materials", i, "path"), entry["path"]
            elif isinstance(materials, dict):
                for i, entry in enumerate(materials.values()):
                    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
                        yield ed, comp, ("materials", i, "path"), entry["path"]
def _set_nested(comp: dict, path: tuple, value: str):
    obj = comp
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value
def _flagged_entity_ids(data: dict, entities: dict) -> set:
    if data.get("embed_all"):
        return set(entities.keys())
    flagged = {eid for eid, ed in entities.items() if ed.get("embed_resources")}
    if not flagged:
        return set()
    children: dict[str, list[str]] = {}
    for eid, ed in entities.items():
        pid = ed.get("parent")
        if pid:
            children.setdefault(pid, []).append(eid)
    stack = list(flagged)
    result = set(flagged)
    while stack:
        eid = stack.pop()
        for cid in children.get(eid, []):
            if cid not in result:
                result.add(cid)
                stack.append(cid)
    return result
