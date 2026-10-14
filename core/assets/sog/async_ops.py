# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
import os
import zipfile
from typing import Optional
from core.assets.ply_loader import GaussianSplatData
from core.assets.sog.loader import _concat_datas
from core.assets.sog.loader import _decode_sog_meta
from core.assets.sog.loader import _find_zip_entry
from core.assets.sog.loader import _load_sog_from_dir
from core.assets.sog.loader import _load_sog_from_zip
from core.assets.sog.loader import _lod0_files
from core.assets.sog.loader import _norm_zip_name
def _load_ssog_from_dir(lod_path: str) -> Optional[GaussianSplatData]:
    try:
        lod_path = os.path.abspath(lod_path)
        if os.path.isdir(lod_path):
            cand = os.path.join(lod_path, "lod-meta.json")
            if not os.path.isfile(cand):
                return None
            lod_path = cand
        base = os.path.dirname(lod_path)
        with open(lod_path, "r", encoding="utf-8") as f:
            lod = json.load(f)
    except Exception:
        return None
    try:
        filenames = list(lod.get("filenames", []))
    except Exception:
        return None
    wanted = _lod0_files(lod)
    if not wanted:
        try:
            wanted = set(range(len(filenames)))
        except Exception:
            return None
    datas: list = []
    for idx in sorted(list(wanted)):
        try:
            rel = filenames[int(idx)]
        except Exception:
            continue
        chunk_meta = os.path.normpath(os.path.join(base, rel.replace("\\", "/")))
        d = _load_sog_from_dir(chunk_meta)
        if d is not None:
            datas.append(d)
    try:
        env_rel = lod.get("environment", None)
    except Exception:
        env_rel = None
    if isinstance(env_rel, str) and env_rel:
        env_meta = os.path.normpath(os.path.join(base, env_rel.replace("\\", "/")))
        d = _load_sog_from_dir(env_meta)
        if d is not None:
            datas.append(d)
    return _concat_datas(datas)
def _load_ssog_from_zip(zip_path: str) -> Optional[GaussianSplatData]:
    try:
        z = zipfile.ZipFile(zip_path, "r")
    except Exception:
        return None
    try:
        names = z.namelist()
        lod_name = _find_zip_entry(names, "lod-meta.json")
        if lod_name is None:
            return None
        try:
            raw = z.read(lod_name)
            lod = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            return None
        prefix = "/".join(_norm_zip_name(lod_name).split("/")[:-1])
        if prefix:
            prefix = prefix + "/"
        else:
            prefix = ""
        try:
            filenames = list(lod.get("filenames", []))
        except Exception:
            filenames = []
        wanted = _lod0_files(lod)
        if not wanted and filenames:
            wanted = set(range(len(filenames)))
        norm_map: dict = {}
        for n in names:
            norm_map[_norm_zip_name(n)] = n
        def read_norm(rel: str) -> bytes:
            key = _norm_zip_name(rel)
            cands = [prefix + key, key]
            for c in cands:
                if c in norm_map:
                    return z.read(norm_map[c])
            base_only = key.split("/")[-1]
            for k, orig in norm_map.items():
                if k.split("/")[-1].lower() == base_only.lower():
                    return z.read(orig)
            raise FileNotFoundError(rel)
        tmp: dict = {}
        def chunk_loader(chunk_rel: str):
            chunk_norm = _norm_zip_name(chunk_rel)
            chunk_prefix = "/".join((prefix + chunk_norm).split("/")[:-1])
            if chunk_prefix:
                chunk_prefix = chunk_prefix + "/"
            else:
                chunk_prefix = prefix
            try:
                chunk_raw = read_norm(chunk_rel)
                chunk_meta = json.loads(chunk_raw.decode("utf-8", errors="ignore"))
            except Exception:
                return None
            def inner(fname: str) -> bytes:
                fk = _norm_zip_name(fname)
                cands = [chunk_prefix + fk, prefix + fk, fk]
                for c in cands:
                    if c in norm_map:
                        return z.read(norm_map[c])
                raise FileNotFoundError(fname)
            return _decode_sog_meta(chunk_meta, inner)
        datas: list = []
        for idx in sorted(list(wanted)):
            try:
                rel = filenames[int(idx)]
            except Exception:
                continue
            d = chunk_loader(rel)
            if d is not None:
                datas.append(d)
        try:
            env_rel = lod.get("environment", None)
        except Exception:
            env_rel = None
        if isinstance(env_rel, str) and env_rel:
            d = chunk_loader(env_rel)
            if d is not None:
                datas.append(d)
        return _concat_datas(datas)
    finally:
        try:
            z.close()
        except Exception:
            pass
def load_ssog_gaussian_splat(path: str) -> Optional[GaussianSplatData]:
    try:
        ap = os.path.abspath(path)
    except Exception:
        return None
    if os.path.isdir(ap):
        return _load_ssog_from_dir(ap)
    if not os.path.isfile(ap):
        return None
    low = ap.lower()
    base = os.path.basename(low)
    if base == "lod-meta.json":
        return _load_ssog_from_dir(ap)
    if base == "meta.json":
        return _load_sog_from_dir(ap)
    if zipfile.is_zipfile(ap):
        r = _load_ssog_from_zip(ap)
        if r is not None:
            return r
        return _load_sog_from_zip(ap)
    if low.endswith(".ssog"):
        return _load_ssog_from_dir(ap)
    return None
def splat_exists(path: str) -> bool:
    try:
        if not path:
            return False
        ap = os.path.abspath(path)
        if os.path.isfile(ap):
            return True
        if os.path.isdir(ap):
            if os.path.isfile(os.path.join(ap, "meta.json")):
                return True
            if os.path.isfile(os.path.join(ap, "lod-meta.json")):
                return True
            return True
        return False
    except Exception:
        return False
def is_sog_path(path: str) -> bool:
    try:
        low = str(path).lower().replace("\\", "/")
        if low.endswith(".sog"):
            return True
        if low.endswith("/meta.json") or low == "meta.json":
            return True
        return False
    except Exception:
        return False
def is_ssog_path(path: str) -> bool:
    try:
        low = str(path).lower().replace("\\", "/")
        if low.endswith(".ssog"):
            return True
        if low.endswith("/lod-meta.json") or low == "lod-meta.json":
            return True
        return False
    except Exception:
        return False
def is_splat_path(path: str) -> bool:
    try:
        low = str(path).lower()
        base = os.path.basename(low)
        if base == "meta.json" or base == "lod-meta.json":
            return True
        for e in (".ply", ".sog", ".ssog", ".zip"):
            if low.endswith(e):
                return True
        ap = os.path.abspath(str(path))
        if os.path.isdir(ap):
            if os.path.isfile(os.path.join(ap, "meta.json")):
                return True
            if os.path.isfile(os.path.join(ap, "lod-meta.json")):
                return True
        return False
    except Exception:
        return False
def load_gaussian_splat(path: str) -> Optional[GaussianSplatData]:
    try:
        ap = os.path.abspath(path)
    except Exception:
        return None
    if os.path.isdir(ap):
        if os.path.isfile(os.path.join(ap, "lod-meta.json")):
            return _load_ssog_from_dir(ap)
        if os.path.isfile(os.path.join(ap, "meta.json")):
            return _load_sog_from_dir(ap)
        return None
    if not os.path.isfile(ap):
        return None
    low = ap.lower()
    base = os.path.basename(low)
    if base == "meta.json":
        return _load_sog_from_dir(ap)
    if base == "lod-meta.json":
        return _load_ssog_from_dir(ap)
    if low.endswith(".ply"):
        try:
            from core.assets.ply_loader import load_ply_gaussian_splat as _load_ply
            return _load_ply(ap)
        except Exception:
            return None
    if low.endswith(".sog"):
        if zipfile.is_zipfile(ap):
            names = []
            try:
                zz = zipfile.ZipFile(ap, "r")
                try:
                    names = [n.lower().split("/")[-1] for n in zz.namelist()]
                finally:
                    try:
                        zz.close()
                    except Exception:
                        pass
            except Exception:
                names = []
            if "lod-meta.json" in names:
                return _load_ssog_from_zip(ap)
            return _load_sog_from_zip(ap)
        return _load_sog_from_dir(ap)
    if low.endswith(".ssog"):
        return load_ssog_gaussian_splat(ap)
    if low.endswith(".zip"):
        if zipfile.is_zipfile(ap):
            r = _load_ssog_from_zip(ap)
            if r is not None:
                return r
            return _load_sog_from_zip(ap)
        return None
    try:
        from core.assets.ply_loader import load_ply_gaussian_splat as _load_ply2
        d = _load_ply2(ap)
        if d is not None:
            return d
    except Exception:
        pass
    return None
def expand_splat_files(path: str) -> list:
    try:
        ap = os.path.abspath(path)
    except Exception:
        return []
    if os.path.isfile(ap):
        return [ap]
    if os.path.isdir(ap):
        out = []
        for root, dirs, files in os.walk(ap):
            for fn in files:
                out.append(os.path.join(root, fn))
        return out
    base = os.path.basename(ap).lower()
    if base == "meta.json" or base == "lod-meta.json":
        d = os.path.dirname(ap)
        if os.path.isdir(d):
            return expand_splat_files(d)
        return [ap] if os.path.isfile(ap) else []
    return []
def get_splat_info(path: str) -> Optional[dict]:
    try:
        ap = os.path.abspath(path)
    except Exception:
        return None
    if os.path.isdir(ap):
        if os.path.isfile(os.path.join(ap, "lod-meta.json")):
            ap = os.path.join(ap, "lod-meta.json")
        elif os.path.isfile(os.path.join(ap, "meta.json")):
            ap = os.path.join(ap, "meta.json")
        else:
            return None
    if not os.path.isfile(ap):
        return None
    low = ap.lower()
    base = os.path.basename(low)
    if low.endswith(".ply"):
        try:
            with open(ap, "rb") as f:
                head = []
                for _ in range(32):
                    line = f.readline()
                    if not line:
                        break
                    t = line.decode("ascii", errors="ignore").strip()
                    head.append(t)
                    if t == "end_header":
                        break
            count = 0
            for h in head:
                if h.startswith("element vertex"):
                    try:
                        count = int(h.split()[2])
                    except Exception:
                        count = 0
            return {"kind": "ply", "count": int(count), "path": ap}
        except Exception:
            return None
    if base == "meta.json" or low.endswith(".sog") or (low.endswith(".zip") and True):
        meta = None
        kind = "sog"
        if os.path.isfile(ap) and zipfile.is_zipfile(ap):
            try:
                z = zipfile.ZipFile(ap, "r")
                try:
                    names = z.namelist()
                    mn = _find_zip_entry(names, "meta.json")
                    ln = _find_zip_entry(names, "lod-meta.json")
                    if mn is None and ln is not None:
                        raw = z.read(ln)
                        lod = json.loads(raw.decode("utf-8", errors="ignore"))
                        return {"kind": "ssog", "count": int(lod.get("count", 0)), "lodLevels": int(lod.get("lodLevels", 1)), "path": ap}
                    if mn is None:
                        return None
                    raw = z.read(mn)
                    meta = json.loads(raw.decode("utf-8", errors="ignore"))
                finally:
                    try:
                        z.close()
                    except Exception:
                        pass
            except Exception:
                return None
        else:
            mp = ap if base == "meta.json" else None
            if mp is None:
                return None
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                return None
        if not isinstance(meta, dict):
            return None
        try:
            count = int(meta.get("count", meta.get("means", {}).get("shape", [0])[0]))
        except Exception:
            count = 0
        try:
            ver = meta.get("version", 1)
        except Exception:
            ver = 1
        bands = 0
        try:
            if isinstance(meta.get("shN", None), dict):
                bands = int(meta["shN"].get("bands", 0))
        except Exception:
            bands = 0
        return {"kind": kind, "count": int(count), "version": int(ver) if isinstance(ver, int) else ver, "bands": int(bands), "path": ap}
    if base == "lod-meta.json" or low.endswith(".ssog"):
        lod = None
        if os.path.isfile(ap) and zipfile.is_zipfile(ap):
            try:
                z = zipfile.ZipFile(ap, "r")
                try:
                    names = z.namelist()
                    ln = _find_zip_entry(names, "lod-meta.json")
                    if ln is None:
                        return None
                    raw = z.read(ln)
                    lod = json.loads(raw.decode("utf-8", errors="ignore"))
                finally:
                    try:
                        z.close()
                    except Exception:
                        pass
            except Exception:
                return None
        else:
            try:
                with open(ap, "r", encoding="utf-8") as f:
                    lod = json.load(f)
            except Exception:
                return None
        if not isinstance(lod, dict):
            return None
        try:
            count = int(lod.get("count", 0))
        except Exception:
            count = 0
        try:
            levels = int(lod.get("lodLevels", 1))
        except Exception:
            levels = 1
        return {"kind": "ssog", "count": int(count), "lodLevels": int(levels), "path": ap}
    return None
