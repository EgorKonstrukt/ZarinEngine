# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from typing import Callable, Optional
from .compress import _cache_dir
from .compress import _cache_path_for
from .compress import _entry_raw_bytes
from .compress import _flagged_entity_ids
from .compress import _is_material_file
from .compress import _iter_component_path_entries
from .compress import _norm
from .compress import _resolve_alias
from .compress import _sanitize_name
from .compress import _set_nested
def _decode_entry_raw(storage_key: str, storage: dict):
    entry = storage.get(storage_key)
    if not entry:
        return (storage_key, None, None, None)
    entry = _resolve_alias(entry, storage)
    try:
        raw = _entry_raw_bytes(entry)
    except Exception:
        return (storage_key, None, None, None)
    digest = entry.get("digest")
    if not digest:
        try:
            digest = hashlib.sha1(raw).hexdigest()[:16]
        except Exception:
            digest = None
    name = _sanitize_name(str(entry.get("name") or os.path.basename(storage_key)))
    return (storage_key, raw, digest, name)
def _target_for_key(storage_key: str, storage: dict, cache_dir: str):
    entry = storage.get(storage_key)
    if not entry:
        return None
    entry = _resolve_alias(entry, storage)
    digest = entry.get("digest")
    if not digest or not isinstance(digest, str):
        return None
    name = _sanitize_name(str(entry.get("name") or os.path.basename(storage_key)))
    return (os.path.join(cache_dir, f"{digest}_{name}"), digest, name)
def extract_embedded_resources(data: dict, root: str, cache_mode: str = "project",
                               progress_cb: Optional[Callable] = None) -> dict:
    storage = data.get("embedded_resources")
    if not isinstance(storage, dict) or not storage:
        data.pop("embedded_resources", None)
        if progress_cb:
            progress_cb(0, 0, "")
        return {}
    cache_dir = _cache_dir(root, cache_mode)
    entities = data.get("entities", {})
    fields = list(_iter_component_path_entries(data))
    total = len(fields)
    done = 0
    progress_cb = progress_cb or (lambda *_: None)
    flagged_ids = _flagged_entity_ids(data, entities)
    needed_keys: dict[str, list[tuple]] = {}
    bname_index: dict[str, str] = {}
    norm_index: dict[str, str] = {}
    storage_set = set(storage.keys())
    for k, e in storage.items():
        try:
            dg = e.get("digest")
            nm = _sanitize_name(str(e.get("name") or os.path.basename(k)))
            if dg:
                bname_index[f"{dg}_{nm}"] = k
            if nm not in bname_index:
                bname_index[nm] = k
            nk = _norm(k).lstrip("/")
            if nk not in norm_index:
                norm_index[nk] = k
            lk = nk.lower()
            if lk not in norm_index:
                norm_index[lk] = k
        except Exception:
            pass
    step = max(1, total // 100)
    for ed, comp, path, val in fields:
        if ed.get("id") not in flagged_ids:
            done += 1
            if done % step == 0 or done >= total:
                progress_cb(done, total, "")
            continue
        storage_key = None
        if val in storage_set:
            storage_key = val
        else:
            vn = _norm(val).lstrip("/")
            hit = norm_index.get(vn)
            if hit is None:
                hit = norm_index.get(vn.lower())
            if hit is None and "/" in vn:
                parts = vn.split("/")
                for i in range(1, len(parts)):
                    sub = "/".join(parts[i:])
                    hit = norm_index.get(sub)
                    if hit is None:
                        hit = norm_index.get(sub.lower())
                    if hit is not None:
                        break
            if hit is not None:
                storage_key = hit
            else:
                bname = _sanitize_name(os.path.basename(vn.rstrip("/")))
                storage_key = bname_index.get(bname)
        if storage_key is not None:
            needed_keys.setdefault(storage_key, []).append((ed, comp, path, val))
        done += 1
        if done % step == 0 or done >= total:
            progress_cb(done, total, os.path.basename(str(val)))
    if needed_keys:
        keys = list(needed_keys.keys())
        ready: dict[str, str] = {}
        missing: list[str] = []
        for k in keys:
            t = _target_for_key(k, storage, cache_dir)
            if t is None:
                missing.append(k)
                continue
            p, _, _ = t
            if os.path.exists(p):
                ready[k] = _norm(os.path.abspath(p))
            else:
                missing.append(k)
        decoded: dict[str, tuple] = {}
        if missing:
            if len(missing) > 1:
                workers = min(8, max(2, os.cpu_count() or 4))
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = {ex.submit(_decode_entry_raw, k, storage): k for k in missing}
                    for fu in as_completed(futs):
                        try:
                            sk, raw, digest, name = fu.result()
                        except Exception:
                            continue
                        decoded[sk] = (raw, digest, name)
            else:
                for k in missing:
                    sk, raw, digest, name = _decode_entry_raw(k, storage)
                    decoded[sk] = (raw, digest, name)
            for storage_key in missing:
                raw, digest, name = decoded.get(storage_key, (None, None, None))
                if raw is None or digest is None or name is None:
                    continue
                path = os.path.join(cache_dir, f"{digest}_{name}")
                if not os.path.exists(path):
                    try:
                        with open(path, "wb") as f:
                            f.write(raw)
                    except OSError:
                        continue
                ready[storage_key] = _norm(os.path.abspath(path))
        rewritten: set[str] = set()
        for storage_key, usages in needed_keys.items():
            cache_path = ready.get(storage_key)
            if not cache_path:
                continue
            for ed, comp, pth, val in usages:
                _set_nested(comp, pth, cache_path)
            if _is_material_file(storage_key) and cache_path not in rewritten:
                rewritten.add(cache_path)
                _rewrite_material_textures(cache_path, storage, root, cache_dir)
    data.pop("embedded_resources", None)
    return storage
def _rewrite_material_textures(mat_cache_path: str, storage: dict, root: str, cache_dir: str):
    try:
        with open(mat_cache_path, "r", encoding="utf-8") as f:
            mat = json.load(f)
    except Exception:
        return
    textures = mat.get("textures")
    if not isinstance(textures, dict) or not textures:
        return
    norm_index: dict[str, str] = {}
    bnames: dict[str, str] = {}
    try:
        for k, e in storage.items():
            nk = _norm(k).lstrip("/")
            if nk not in norm_index:
                norm_index[nk] = k
            lk = nk.lower()
            if lk not in norm_index:
                norm_index[lk] = k
            try:
                nm = _sanitize_name(str(e.get("name") or os.path.basename(k)))
                if nm not in bnames:
                    bnames[nm] = k
            except Exception:
                pass
    except Exception:
        pass
    storage_set = set(storage.keys())
    changed = False
    for slot, tex in textures.items():
        if not isinstance(tex, str) or not tex:
            continue
        storage_key = None
        if tex in storage_set:
            storage_key = tex
        else:
            vn = _norm(tex).lstrip("/")
            hit = norm_index.get(vn)
            if hit is None:
                hit = norm_index.get(vn.lower())
            if hit is None and "/" in vn:
                parts = vn.split("/")
                for i in range(1, len(parts)):
                    sub = "/".join(parts[i:])
                    hit = norm_index.get(sub)
                    if hit is None:
                        hit = norm_index.get(sub.lower())
                    if hit is not None:
                        break
            if hit is not None:
                storage_key = hit
            else:
                try:
                    bname = _sanitize_name(os.path.basename(vn.rstrip("/")))
                    storage_key = bnames.get(bname)
                except Exception:
                    storage_key = None
        if storage_key is None:
            continue
        tex_cache = _cache_path_for(storage_key, storage, cache_dir)
        if tex_cache:
            textures[slot] = tex_cache
            changed = True
    if changed:
        try:
            with open(mat_cache_path, "w", encoding="utf-8") as f:
                json.dump(mat, f, indent=2)
        except OSError:
            pass
