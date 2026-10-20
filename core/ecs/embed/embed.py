# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed
import base64
import hashlib
import json
import os
from typing import Callable, Optional
from .compress import _abs_path
from .compress import _compress
from .compress import _entry_cache_basename
from .compress import _flagged_entity_ids
from .compress import _is_material_file
from .compress import _iter_component_path_entries
from .compress import _key_candidates
from .compress import _norm
from .compress import _sanitize_name
from .compress import _storage_key
_EMBED_STAT_CACHE: dict[tuple[str, int], tuple[float, int, str, str, int]] = {}
def _material_textures(mat_abs: str, root: str) -> dict:
    try:
        with open(mat_abs, "r", encoding="utf-8") as f:
            mat = json.load(f)
    except Exception:
        return {}
    out: dict = {}
    textures = mat.get("textures")
    if isinstance(textures, dict):
        for slot, tex in textures.items():
            if isinstance(tex, str) and tex:
                out[slot] = tex
    elif isinstance(textures, list):
        for i, tex in enumerate(textures):
            if isinstance(tex, str) and tex:
                out[f"_{i}"] = tex
    return out
def _read_raw_digest(val: str, root: str, compress_level: int):
    absv = _abs_path(val, root)
    if not absv:
        return (val, None, 0, None, None, 0)
    try:
        st = os.stat(absv)
    except OSError:
        return (val, None, 0, None, None, 0)
    ckey = (absv, int(compress_level))
    hit = _EMBED_STAT_CACHE.get(ckey)
    if hit is not None and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return (val, absv, hit[1], hit[2], hit[3], hit[4])
    try:
        with open(absv, "rb") as f:
            raw = f.read()
    except OSError:
        return (val, None, 0, None, None, 0)
    digest = hashlib.sha1(raw).hexdigest()[:16]
    payload = _compress(raw, compress_level)
    b64 = base64.b64encode(payload).decode("ascii")
    try:
        _EMBED_STAT_CACHE[ckey] = (st.st_mtime, len(raw), digest, b64, len(payload))
    except Exception:
        pass
    return (val, absv, len(raw), digest, b64, len(payload))
def embed_scene_resources(data: dict, root: str, existing: Optional[dict] = None,
                          compress_level: int = 0, progress_cb: Optional[Callable] = None) -> int:
    entities = data.get("entities", {})
    flagged = _flagged_entity_ids(data, entities)
    storage: dict = {}
    if isinstance(existing, dict):
        storage.update(existing)
    else:
        old = data.get("embedded_resources")
        if isinstance(old, dict):
            storage.update(old)
    if not flagged:
        data.pop("embedded_resources", None)
        if progress_cb:
            progress_cb(0, 0, "")
        return 0
    use_compression = bool(data.get("compress_resources") and compress_level > 0)
    has_compressed = any(bool(e.get("compression")) for e in storage.values())
    has_raw_large = any(not e.get("compression") and int(e.get("size", 0)) >= 64 for e in storage.values())
    force_reencode = (use_compression and has_raw_large) or (not use_compression and has_compressed)
    fdata = {"entities": {eid: entities[eid] for eid in flagged if eid in entities}}
    fields = [val for _, _, _, val in _iter_component_path_entries(fdata)]
    total = len(fields)
    done = 0
    progress_cb = progress_cb or (lambda *_: None)
    basename_map: dict[str, str] = {}
    digest_map: dict[str, str] = {}
    for k, entry in storage.items():
        basename_map[_entry_cache_basename(entry, storage)] = k
        dg = entry.get("digest")
        if dg and isinstance(dg, str):
            digest_map.setdefault(dg, k)
    def embed_file(val: str) -> str:
        bname = _sanitize_name(os.path.basename(_norm(val).rstrip("/")))
        if bname and bname in basename_map:
            return basename_map[bname]
        absv = _abs_path(val, root)
        storage_key = _storage_key(absv, root) if absv else None
        if storage_key is None:
            storage_key = next((k for k in _key_candidates(val, root) if k in storage), None)
        if storage_key is None:
            return ""
        if absv:
            try:
                with open(absv, "rb") as f:
                    raw = f.read()
            except OSError:
                return ""
            digest = hashlib.sha1(raw).hexdigest()[:16]
            if not force_reencode and digest in digest_map:
                alias_key = digest_map[digest]
                if alias_key != storage_key:
                    storage[storage_key] = {"key": storage_key, "name": os.path.basename(absv), "alias": alias_key}
                return alias_key
            existing_entry = storage.get(storage_key)
            if existing_entry and existing_entry.get("digest") == digest and not force_reencode:
                return storage_key
            payload = _compress(raw, compress_level)
            entry = {
                "key": storage_key,
                "name": os.path.basename(absv),
                "size": len(raw),
                "digest": digest,
                "data": base64.b64encode(payload).decode("ascii"),
            }
            if len(payload) < len(raw):
                entry["compression"] = "zlib"
                entry["csize"] = len(payload)
            elif not use_compression:
                entry.pop("compression", None)
                entry.pop("csize", None)
            storage[storage_key] = entry
            digest_map[digest] = storage_key
            basename_map[_entry_cache_basename(entry, storage)] = storage_key
            if _is_material_file(absv):
                for tex in _material_textures(absv, root).values():
                    embed_file(tex)
        return storage_key
    def apply_loaded(val: str, absv: str | None, size: int, digest: str | None, b64: str | None, plen: int) -> str:
        if absv is None or digest is None or b64 is None:
            bname = _sanitize_name(os.path.basename(_norm(val).rstrip("/")))
            if bname and bname in basename_map:
                return basename_map[bname]
            storage_key = next((k for k in _key_candidates(val, root) if k in storage), None)
            if storage_key is None:
                return ""
            return storage_key
        raw_len = int(size)
        bname = _sanitize_name(os.path.basename(_norm(val).rstrip("/")))
        if bname and bname in basename_map:
            return basename_map[bname]
        storage_key = _storage_key(absv, root)
        if not force_reencode and digest in digest_map:
            alias_key = digest_map[digest]
            if alias_key != storage_key:
                storage[storage_key] = {"key": storage_key, "name": os.path.basename(absv), "alias": alias_key}
            return alias_key
        existing_entry = storage.get(storage_key)
        if existing_entry and existing_entry.get("digest") == digest and not force_reencode:
            return storage_key
        entry = {
            "key": storage_key,
            "name": os.path.basename(absv),
            "size": raw_len,
            "digest": digest,
            "data": b64,
        }
        if plen < raw_len:
            entry["compression"] = "zlib"
            entry["csize"] = plen
        elif not use_compression:
            entry.pop("compression", None)
            entry.pop("csize", None)
        storage[storage_key] = entry
        digest_map[digest] = storage_key
        basename_map[_entry_cache_basename(entry, storage)] = storage_key
        return storage_key
    uniq = list(dict.fromkeys(fields))
    pending_mats: list[str] = []
    if len(uniq) > 1:
        workers = min(8, max(2, os.cpu_count() or 4))
        loaded: dict[str, tuple] = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_read_raw_digest, v, root, compress_level): v for v in uniq}
            for fu in as_completed(futs):
                try:
                    v, av, sz, dg, b64, plen = fu.result()
                except Exception:
                    continue
                loaded[v] = (av, sz, dg, b64, plen)
        for val in uniq:
            av, sz, dg, b64, plen = loaded.get(val, (None, 0, None, None, 0))
            sk = apply_loaded(val, av, sz, dg, b64, plen)
            if sk and av and _is_material_file(av):
                pending_mats.append(av)
    else:
        for val in fields:
            sk = embed_file(val)
            done += 1
            progress_cb(done, total, os.path.basename(str(val)))
        if not storage:
            data.pop("embedded_resources", None)
            return 0
        data["embedded_resources"] = storage
        return len(storage)
    for mat_abs in pending_mats:
        try:
            texs = _material_textures(mat_abs, root).values()
        except Exception:
            continue
        for tex in texs:
            bname = _sanitize_name(os.path.basename(_norm(tex).rstrip("/")))
            if bname and bname in basename_map:
                continue
            embed_file(tex)
    for val in fields:
        done += 1
        progress_cb(done, total, os.path.basename(str(val)))
    if not storage:
        data.pop("embedded_resources", None)
        return 0
    data["embedded_resources"] = storage
    return len(storage)
