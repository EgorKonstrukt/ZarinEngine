# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import base64
import concurrent.futures
import hashlib
import json
import os
import tempfile
import zlib
from typing import Callable, Optional

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


_EMBED_STAT_CACHE: dict[tuple[str, int], tuple[float, int, str, str, int]] = {}


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
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_read_raw_digest, v, root, compress_level): v for v in uniq}
            for fu in concurrent.futures.as_completed(futs):
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
    for k, e in storage.items():
        try:
            dg = e.get("digest")
            nm = _sanitize_name(str(e.get("name") or os.path.basename(k)))
            if dg:
                bname_index[f"{dg}_{nm}"] = k
            bname_index[nm] = k
        except Exception:
            pass
    for ed, comp, path, val in fields:
        if ed.get("id") not in flagged_ids:
            done += 1
            continue
        storage_key = next((k for k in _key_candidates(val, root) if k in storage), None)
        if storage_key is None:
            bname = _sanitize_name(os.path.basename(_norm(val).rstrip("/")))
            storage_key = bname_index.get(bname)
        if storage_key is not None:
            needed_keys.setdefault(storage_key, []).append((ed, comp, path, val))
        done += 1
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = {ex.submit(_decode_entry_raw, k, storage): k for k in missing}
                    for fu in concurrent.futures.as_completed(futs):
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
        for storage_key, usages in needed_keys.items():
            cache_path = ready.get(storage_key)
            if not cache_path:
                continue
            for ed, comp, pth, val in usages:
                _set_nested(comp, pth, cache_path)
                if _is_material_file(storage_key):
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
    changed = False
    for slot, tex in textures.items():
        if not isinstance(tex, str) or not tex:
            continue
        storage_key = next((k for k in _key_candidates(tex, root) if k in storage), None)
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