# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
import os
import zipfile
import numpy as np
from typing import Optional
from core.assets.ply_loader import GaussianSplatData, SH_C0
from core.assets.sog.format import _SH_COEFFS
from core.assets.sog.format import _V1_WIDTH_TO_BANDS
from core.assets.sog.format import _build_palette_v1
from core.assets.sog.format import _decode_image_bytes
from core.assets.sog.format import _decode_v2
from core.assets.sog.format import _finalize
from core.assets.sog.format import _flat_pixels
from core.assets.sog.format import _gather_rest
from core.assets.sog.format import _inv_log_transform
from core.assets.sog.format import _sigmoid
from core.assets.sog.format import _unpack_quats
def _decode_v1(meta: dict, load_fn) -> Optional[GaussianSplatData]:
    try:
        count = int(meta["means"]["shape"][0])
    except Exception:
        return None
    if count <= 0:
        return None
    try:
        means_files = list(meta["means"]["files"])
        scales_files = list(meta["scales"]["files"])
        quats_files = list(meta["quats"]["files"])
        sh0_files = list(meta["sh0"]["files"])
        means_mins = np.array(list(meta["means"]["mins"]), dtype=np.float64)
        means_maxs = np.array(list(meta["means"]["maxs"]), dtype=np.float64)
        s_mins = np.array(list(meta["scales"]["mins"]), dtype=np.float64)
        s_maxs = np.array(list(meta["scales"]["maxs"]), dtype=np.float64)
        c_mins = np.array(list(meta["sh0"]["mins"]), dtype=np.float64)
        c_maxs = np.array(list(meta["sh0"]["maxs"]), dtype=np.float64)
    except Exception:
        return None
    if len(means_files) < 2 or len(scales_files) < 1 or len(quats_files) < 1 or len(sh0_files) < 1:
        return None
    try:
        lo_arr = _decode_image_bytes(load_fn(means_files[0]))
        hi_arr = _decode_image_bytes(load_fn(means_files[1]))
    except Exception:
        return None
    try:
        lo = _flat_pixels(lo_arr, count)
        hi = _flat_pixels(hi_arr, count)
    except Exception:
        return None
    xs = (lo[:, 0].astype(np.float32) + hi[:, 0].astype(np.float32) * 256.0) / 65535.0
    ys = (lo[:, 1].astype(np.float32) + hi[:, 1].astype(np.float32) * 256.0) / 65535.0
    zs = (lo[:, 2].astype(np.float32) + hi[:, 2].astype(np.float32) * 256.0) / 65535.0
    del lo, hi, lo_arr, hi_arr
    x_min = float(means_mins[0])
    x_sc = float(means_maxs[0] - means_mins[0]) or 1.0
    y_min = float(means_mins[1])
    y_sc = float(means_maxs[1] - means_mins[1]) or 1.0
    z_min = float(means_mins[2])
    z_sc = float(means_maxs[2] - means_mins[2]) or 1.0
    lx = (x_min + x_sc * xs).astype(np.float64)
    ly = (y_min + y_sc * ys).astype(np.float64)
    lz = (z_min + z_sc * zs).astype(np.float64)
    del xs, ys, zs
    pos = np.empty((count, 3), dtype=np.float32)
    pos[:, 0] = _inv_log_transform(lx)
    pos[:, 1] = _inv_log_transform(ly)
    pos[:, 2] = _inv_log_transform(lz)
    del lx, ly, lz
    try:
        qr_arr = _decode_image_bytes(load_fn(quats_files[0]))
    except Exception:
        return None
    try:
        qr = _flat_pixels(qr_arr, count)
    except Exception:
        return None
    wxyz = _unpack_quats(qr)
    del qr, qr_arr
    quat = np.empty((count, 4), dtype=np.float32)
    quat[:, 0] = wxyz[:, 1]
    quat[:, 1] = wxyz[:, 2]
    quat[:, 2] = wxyz[:, 3]
    quat[:, 3] = wxyz[:, 0]
    del wxyz
    try:
        sl_arr = _decode_image_bytes(load_fn(scales_files[0]))
    except Exception:
        return None
    try:
        sl = _flat_pixels(sl_arr, count)
    except Exception:
        return None
    s_raw = np.empty((count, 3), dtype=np.float32)
    s_raw[:, 0] = (float(s_mins[0]) + float(s_maxs[0] - s_mins[0]) * (sl[:, 0].astype(np.float32) / 255.0)).astype(np.float32)
    s_raw[:, 1] = (float(s_mins[1]) + float(s_maxs[1] - s_mins[1]) * (sl[:, 1].astype(np.float32) / 255.0)).astype(np.float32)
    s_raw[:, 2] = (float(s_mins[2]) + float(s_maxs[2] - s_mins[2]) * (sl[:, 2].astype(np.float32) / 255.0)).astype(np.float32)
    del sl, sl_arr
    scl = np.exp(s_raw.astype(np.float64)).astype(np.float32)
    del s_raw
    try:
        c0_arr = _decode_image_bytes(load_fn(sh0_files[0]))
    except Exception:
        return None
    try:
        c0 = _flat_pixels(c0_arr, count)
    except Exception:
        return None
    dc_raw = np.empty((count, 3), dtype=np.float32)
    dc_raw[:, 0] = (float(c_mins[0]) + float(c_maxs[0] - c_mins[0]) * (c0[:, 0].astype(np.float32) / 255.0)).astype(np.float32)
    dc_raw[:, 1] = (float(c_mins[1]) + float(c_maxs[1] - c_mins[1]) * (c0[:, 1].astype(np.float32) / 255.0)).astype(np.float32)
    dc_raw[:, 2] = (float(c_mins[2]) + float(c_maxs[2] - c_mins[2]) * (c0[:, 2].astype(np.float32) / 255.0)).astype(np.float32)
    dc = dc_raw * np.float32(SH_C0) + np.float32(0.5)
    del dc_raw
    op_logit = (float(c_mins[3]) + float(c_maxs[3] - c_mins[3]) * (c0[:, 3].astype(np.float32) / 255.0)).astype(np.float32)
    del c0, c0_arr
    opa = _sigmoid(op_logit)
    del op_logit
    shn = meta.get("shN")
    rest = np.zeros((count, 0), dtype=np.float32)
    num_sh = 1
    if isinstance(shn, dict):
        try:
            sh_files = list(shn.get("files", []))
            if len(sh_files) >= 2:
                cent_arr = _decode_image_bytes(load_fn(sh_files[0]))
                lab_arr = _decode_image_bytes(load_fn(sh_files[1]))
                cw = int(cent_arr.shape[1])
                bands = int(_V1_WIDTH_TO_BANDS.get(cw, 0))
                coeffs = int(_SH_COEFFS[bands]) if bands else 0
                if coeffs > 0:
                    lab = _flat_pixels(lab_arr, count)
                    labels = (lab[:, 0].astype(np.int32) | (lab[:, 1].astype(np.int32) << 8)).astype(np.int64)
                    del lab, lab_arr
                    per_row = int(cw // max(1, coeffs))
                    chh = int(cent_arr.shape[0])
                    palette_count = int(per_row * chh)
                    smin = float(shn.get("mins", 0.0))
                    smax = float(shn.get("maxs", 1.0))
                    sspan = float(smax - smin)
                    pal = _build_palette_v1(cent_arr, coeffs, palette_count, smin, sspan)
                    del cent_arr
                    rest = _gather_rest(pal, labels, count)
                    del pal, labels
                    num_sh = int(bands + 1)
        except Exception:
            rest = np.zeros((count, 0), dtype=np.float32)
            num_sh = 1
    return _finalize(pos, dc, rest, opa, scl, quat, num_sh)
def _decode_sog_meta(meta: dict, load_fn) -> Optional[GaussianSplatData]:
    try:
        ver = meta.get("version", None)
    except Exception:
        return None
    if ver == 2:
        return _decode_v2(meta, load_fn)
    if ver is None:
        try:
            if "means" in meta and isinstance(meta["means"], dict) and "shape" in meta["means"]:
                return _decode_v1(meta, load_fn)
        except Exception:
            pass
        return _decode_v1(meta, load_fn)
    try:
        ivers = int(ver)
    except Exception:
        return None
    if ivers == 2:
        return _decode_v2(meta, load_fn)
    return None
def _norm_zip_name(name: str) -> str:
    return name.replace("\\", "/")
def _find_zip_entry(names: list, target: str) -> Optional[str]:
    t = _norm_zip_name(target).lower()
    best = None
    best_len = None
    for n in names:
        nn = _norm_zip_name(n)
        base = nn.split("/")[-1].lower()
        if base == t:
            if best is None or len(nn) < best_len:
                best = n
                best_len = len(nn)
    return best
def _load_sog_from_zip(zip_path: str) -> Optional[GaussianSplatData]:
    try:
        z = zipfile.ZipFile(zip_path, "r")
    except Exception:
        return None
    try:
        names = z.namelist()
        meta_name = _find_zip_entry(names, "meta.json")
        if meta_name is None:
            return None
        try:
            raw = z.read(meta_name)
            meta = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            return None
        prefix = "/".join(_norm_zip_name(meta_name).split("/")[:-1])
        if prefix:
            prefix = prefix + "/"
        else:
            prefix = ""
        cache: dict = {}
        def load_fn(fname: str) -> bytes:
            key = _norm_zip_name(fname)
            candidates = [prefix + key, key, key.split("/")[-1], prefix + key.split("/")[-1]]
            for cand in candidates:
                if cand in cache:
                    return cache[cand]
            for cand in candidates:
                try:
                    for n in names:
                        if _norm_zip_name(n) == cand:
                            data = z.read(n)
                            cache[cand] = data
                            return data
                except Exception:
                    continue
            for n in names:
                if _norm_zip_name(n).split("/")[-1].lower() == key.split("/")[-1].lower():
                    data = z.read(n)
                    return data
            raise FileNotFoundError(fname)
        return _decode_sog_meta(meta, load_fn)
    finally:
        try:
            z.close()
        except Exception:
            pass
def _load_sog_from_dir(meta_path: str) -> Optional[GaussianSplatData]:
    try:
        meta_path = os.path.abspath(meta_path)
        if os.path.isdir(meta_path):
            cand = os.path.join(meta_path, "meta.json")
            if not os.path.isfile(cand):
                return None
            meta_path = cand
        base = os.path.dirname(meta_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        def load_fn(fname: str) -> bytes:
            p = fname.replace("\\", "/")
            cands = [os.path.join(base, p), os.path.join(base, os.path.basename(p))]
            for c in cands:
                if os.path.isfile(c):
                    with open(c, "rb") as ff:
                        return ff.read()
            raise FileNotFoundError(fname)
        return _decode_sog_meta(meta, load_fn)
    except Exception:
        return None
def load_sog_gaussian_splat(path: str) -> Optional[GaussianSplatData]:
    try:
        ap = os.path.abspath(path)
    except Exception:
        return None
    if os.path.isdir(ap):
        return _load_sog_from_dir(ap)
    if not os.path.isfile(ap):
        return None
    low = ap.lower()
    base = os.path.basename(low)
    if base == "meta.json":
        return _load_sog_from_dir(ap)
    if base == "lod-meta.json":
        from core.assets.sog.async_ops import load_ssog_gaussian_splat as _ssog_lazy
        return _ssog_lazy(ap)
    if low.endswith(".zip") or low.endswith(".sog"):
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
                from core.assets.sog.async_ops import load_ssog_gaussian_splat as _ssog_lazy2
                return _ssog_lazy2(ap)
            return _load_sog_from_zip(ap)
        return _load_sog_from_dir(ap)
    return None
def _walk_lod_leaves(node: dict, out: list):
    try:
        children = node.get("children", None)
    except Exception:
        return
    if isinstance(children, list) and len(children) == 2:
        _walk_lod_leaves(children[0], out)
        _walk_lod_leaves(children[1], out)
        return
    try:
        lods = node.get("lods", None)
    except Exception:
        lods = None
    if isinstance(lods, dict):
        out.append(lods)
def _lod0_files(lod_meta: dict) -> set:
    files: set = set()
    try:
        tree = lod_meta.get("tree", None)
    except Exception:
        tree = None
    if not isinstance(tree, dict):
        try:
            fns = list(lod_meta.get("filenames", []))
            for i in range(len(fns)):
                files.add(int(i))
            return files
        except Exception:
            return files
    leaves: list = []
    _walk_lod_leaves(tree, leaves)
    for lods in leaves:
        if not isinstance(lods, dict) or not lods:
            continue
        if "0" in lods:
            try:
                files.add(int(lods["0"].get("file")))
            except Exception:
                continue
        else:
            try:
                keys = sorted([int(k) for k in lods.keys()])
            except Exception:
                continue
            if not keys:
                continue
            try:
                files.add(int(lods[str(keys[0])].get("file")))
            except Exception:
                continue
    return files
def _concat_datas(datas: list) -> Optional[GaussianSplatData]:
    items = [d for d in datas if d is not None and d.num_splats > 0]
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    max_rest = 0
    for d in items:
        try:
            r = int(d.sh_coeffs.shape[1] - 3)
        except Exception:
            r = 0
        if r > max_rest:
            max_rest = r
    poss = []
    shs = []
    opas = []
    scls = []
    quats = []
    top_sh = 1
    for d in items:
        poss.append(np.ascontiguousarray(d.positions, dtype=np.float32))
        cur_rest = int(d.sh_coeffs.shape[1] - 3) if d.sh_coeffs.ndim == 2 else 0
        if cur_rest < 0:
            cur_rest = 0
        if cur_rest < max_rest:
            pad = np.zeros((int(d.num_splats), int(max_rest - cur_rest)), dtype=np.float32)
            full_sh = np.concatenate([np.ascontiguousarray(d.sh_coeffs, dtype=np.float32), pad], axis=1)
        else:
            full_sh = np.ascontiguousarray(d.sh_coeffs, dtype=np.float32)
        shs.append(full_sh)
        opas.append(np.ascontiguousarray(d.opacity.reshape(-1).astype(np.float32)))
        scls.append(np.ascontiguousarray(d.scales, dtype=np.float32))
        quats.append(np.ascontiguousarray(d.quaternions, dtype=np.float32))
        try:
            if int(d.num_sh) > top_sh:
                top_sh = int(d.num_sh)
        except Exception:
            pass
    pos = np.ascontiguousarray(np.concatenate(poss, axis=0), dtype=np.float32)
    sh = np.ascontiguousarray(np.concatenate(shs, axis=0), dtype=np.float32)
    opa = np.ascontiguousarray(np.concatenate(opas, axis=0), dtype=np.float32)
    scl = np.ascontiguousarray(np.concatenate(scls, axis=0), dtype=np.float32)
    quat = np.ascontiguousarray(np.concatenate(quats, axis=0), dtype=np.float32)
    n = int(pos.shape[0])
    valid = np.isfinite(pos).all(axis=1)
    valid &= np.isfinite(sh).all(axis=1)
    valid &= np.isfinite(opa)
    valid &= np.isfinite(scl).all(axis=1)
    valid &= np.isfinite(quat).all(axis=1)
    if not bool(np.any(valid)):
        return None
    if not bool(np.all(valid)):
        pos = np.ascontiguousarray(pos[valid])
        sh = np.ascontiguousarray(sh[valid])
        opa = np.ascontiguousarray(opa[valid])
        scl = np.ascontiguousarray(scl[valid])
        quat = np.ascontiguousarray(quat[valid])
    normals = np.zeros_like(pos)
    return GaussianSplatData(positions=pos, normals=np.ascontiguousarray(normals), sh_coeffs=sh, opacity=opa, scales=scl, quaternions=quat, num_sh=int(top_sh))
