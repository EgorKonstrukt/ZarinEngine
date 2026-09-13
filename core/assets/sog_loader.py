# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import io
import json
import os
import zipfile
import numpy as np
from typing import Optional
from PIL import Image
from core.assets.ply_loader import GaussianSplatData, SH_C0
SOG_EXTS = frozenset({".sog"})
SSOG_EXTS = frozenset({".ssog"})
SPLAT_EXTS = frozenset({".ply", ".sog", ".ssog", ".zip"})
_QUAT_IDX = ((1, 2, 3), (0, 2, 3), (0, 1, 3), (0, 1, 2))
_SH_COEFFS = (0, 3, 8, 15)
_SQRT2 = 1.4142135623730951
_V1_WIDTH_TO_BANDS = {192: 1, 512: 2, 960: 3}
_CHUNK = 262144
def _decode_image_bytes(data: bytes) -> np.ndarray:
    buf = io.BytesIO(data)
    img = Image.open(buf)
    img = img.convert("RGBA")
    arr = np.array(img, dtype=np.uint8)
    return np.ascontiguousarray(arr)
def _flat_pixels(arr: np.ndarray, count: int) -> np.ndarray:
    flat = np.ascontiguousarray(arr.reshape(-1, 4))
    if flat.shape[0] < count:
        raise ValueError("texture too small")
    return flat[:count]
def _inv_log_transform(v: np.ndarray) -> np.ndarray:
    d = v.astype(np.float64)
    a = np.abs(d)
    e = np.expm1(a)
    s = np.sign(d)
    return (s * e).astype(np.float32)
def _sigmoid(x: np.ndarray) -> np.ndarray:
    d = x.astype(np.float64)
    out = 1.0 / (1.0 + np.exp(-d))
    return out.astype(np.float32)
def _unpack_quats(qr: np.ndarray) -> np.ndarray:
    n = int(qr.shape[0])
    out = np.empty((n, 4), dtype=np.float32)
    out[:, 0] = 1.0
    out[:, 1] = 0.0
    out[:, 2] = 0.0
    out[:, 3] = 0.0
    if n == 0:
        return out
    tag = qr[:, 3].astype(np.int32)
    valid = (tag >= 252) & (tag <= 255)
    if not bool(np.any(valid)):
        return out
    a = (qr[:, 0].astype(np.float32) / 255.0 * 2.0 - 1.0) / np.float32(_SQRT2)
    b = (qr[:, 1].astype(np.float32) / 255.0 * 2.0 - 1.0) / np.float32(_SQRT2)
    c = (qr[:, 2].astype(np.float32) / 255.0 * 2.0 - 1.0) / np.float32(_SQRT2)
    maxc = tag - 252
    t = 1.0 - (a * a + b * b + c * c)
    t = np.maximum(t, 0.0)
    s = np.sqrt(t).astype(np.float32)
    for m in range(4):
        mask = valid & (maxc == m)
        if not bool(np.any(mask)):
            continue
        i0, i1, i2 = _QUAT_IDX[m]
        out[mask, i0] = a[mask]
        out[mask, i1] = b[mask]
        out[mask, i2] = c[mask]
        out[mask, m] = s[mask]
    return out
def _build_palette_v2(cent: np.ndarray, sh_coeffs: int, palette_count: int, codebook: np.ndarray) -> np.ndarray:
    rest = int(sh_coeffs * 3)
    pal = np.zeros((max(0, palette_count), rest), dtype=np.float32)
    if palette_count <= 0 or rest <= 0:
        return pal
    ch = int(cent.shape[0])
    cw = int(cent.shape[1])
    expected = int(64 * sh_coeffs)
    if cw != expected:
        return pal
    if ch <= 0:
        return pal
    resh = np.ascontiguousarray(cent.reshape(ch, 64, sh_coeffs, 4))
    r_idx = resh[..., 0].astype(np.int64)
    g_idx = resh[..., 1].astype(np.int64)
    b_idx = resh[..., 2].astype(np.int64)
    np.clip(r_idx, 0, 255, out=r_idx)
    np.clip(g_idx, 0, 255, out=g_idx)
    np.clip(b_idx, 0, 255, out=b_idx)
    r_val = codebook[r_idx]
    g_val = codebook[g_idx]
    b_val = codebook[b_idx]
    total = int(ch * 64)
    r_flat = np.ascontiguousarray(r_val.reshape(total, sh_coeffs))
    g_flat = np.ascontiguousarray(g_val.reshape(total, sh_coeffs))
    b_flat = np.ascontiguousarray(b_val.reshape(total, sh_coeffs))
    full = np.concatenate([r_flat, g_flat, b_flat], axis=1)
    n = min(int(full.shape[0]), int(palette_count))
    if n > 0:
        pal[:n] = full[:n]
    return pal
def _build_palette_v1(cent: np.ndarray, sh_coeffs: int, palette_count: int, smin: float, sspan: float) -> np.ndarray:
    rest = int(sh_coeffs * 3)
    pal = np.zeros((max(0, palette_count), rest), dtype=np.float32)
    if palette_count <= 0 or rest <= 0:
        return pal
    ch = int(cent.shape[0])
    cw = int(cent.shape[1])
    if cw <= 0 or ch <= 0:
        return pal
    per_row = int(cw // max(1, sh_coeffs))
    if per_row <= 0:
        return pal
    resh_ok = (cw == per_row * sh_coeffs)
    if not resh_ok:
        return pal
    resh = np.ascontiguousarray(cent.reshape(ch, per_row, sh_coeffs, 4).astype(np.float32))
    scale = np.float32(sspan / 255.0) if sspan != 0 else np.float32(0.0)
    base = np.float32(smin)
    r_f = base + resh[..., 0] * scale
    g_f = base + resh[..., 1] * scale
    b_f = base + resh[..., 2] * scale
    total = int(ch * per_row)
    r_flat = np.ascontiguousarray(r_f.reshape(total, sh_coeffs))
    g_flat = np.ascontiguousarray(g_f.reshape(total, sh_coeffs))
    b_flat = np.ascontiguousarray(b_f.reshape(total, sh_coeffs))
    full = np.concatenate([r_flat, g_flat, b_flat], axis=1)
    n = min(int(full.shape[0]), int(palette_count))
    if n > 0:
        pal[:n] = full[:n]
    return pal
def _gather_rest(palette: np.ndarray, labels: np.ndarray, count: int) -> np.ndarray:
    rest = int(palette.shape[1]) if palette.ndim == 2 else 0
    out = np.zeros((count, rest), dtype=np.float32)
    if count == 0 or rest == 0:
        return out
    valid = labels < int(palette.shape[0])
    if not bool(np.any(valid)):
        return out
    for s in range(0, count, _CHUNK):
        e = min(s + _CHUNK, count)
        m = valid[s:e]
        if not bool(np.any(m)):
            continue
        idx = labels[s:e][m]
        rows = np.arange(s, e, dtype=np.int64)[m]
        out[rows] = palette[idx]
    return out
def _finalize(pos: np.ndarray, dc: np.ndarray, rest: np.ndarray, opa: np.ndarray, scl: np.ndarray, quat_xyzw: np.ndarray, num_sh: int) -> Optional[GaussianSplatData]:
    n = int(pos.shape[0])
    if n == 0:
        return None
    if dc.shape[0] != n or opa.shape[0] != n or scl.shape[0] != n or quat_xyzw.shape[0] != n:
        return None
    if rest.shape[0] != n:
        if rest.shape[0] == 0 and rest.shape[1] == 0:
            rest = np.zeros((n, 0), dtype=np.float32)
        else:
            return None
    sh = np.concatenate([dc.astype(np.float32), rest.astype(np.float32)], axis=1) if rest.shape[1] > 0 else np.ascontiguousarray(dc.astype(np.float32))
    valid = np.isfinite(pos).all(axis=1)
    valid &= np.isfinite(sh).all(axis=1)
    valid &= np.isfinite(opa)
    valid &= np.isfinite(scl).all(axis=1)
    valid &= np.isfinite(quat_xyzw).all(axis=1)
    valid &= scl.max(axis=1) > 0.0
    if not bool(np.any(valid)):
        return None
    if not bool(np.all(valid)):
        pos = np.ascontiguousarray(pos[valid])
        sh = np.ascontiguousarray(sh[valid])
        opa = np.ascontiguousarray(opa[valid])
        scl = np.ascontiguousarray(scl[valid])
        quat_xyzw = np.ascontiguousarray(quat_xyzw[valid])
    normals = np.zeros_like(pos)
    return GaussianSplatData(positions=np.ascontiguousarray(pos, dtype=np.float32), normals=np.ascontiguousarray(normals, dtype=np.float32), sh_coeffs=np.ascontiguousarray(sh, dtype=np.float32), opacity=np.ascontiguousarray(opa.reshape(-1).astype(np.float32)), scales=np.ascontiguousarray(scl, dtype=np.float32), quaternions=np.ascontiguousarray(quat_xyzw, dtype=np.float32), num_sh=int(num_sh))
def _decode_v2(meta: dict, load_fn) -> Optional[GaussianSplatData]:
    try:
        count = int(meta.get("count", 0))
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
        scales_code = np.array(list(meta["scales"]["codebook"]), dtype=np.float32)
        sh0_code = np.array(list(meta["sh0"]["codebook"]), dtype=np.float32)
    except Exception:
        return None
    if len(means_files) < 2 or len(scales_files) < 1 or len(quats_files) < 1 or len(sh0_files) < 1:
        return None
    if scales_code.shape[0] != 256 or sh0_code.shape[0] != 256:
        return None
    try:
        lo_arr = _decode_image_bytes(load_fn(means_files[0]))
        hi_arr = _decode_image_bytes(load_fn(means_files[1]))
        sl_arr = _decode_image_bytes(load_fn(scales_files[0]))
        qr_arr = _decode_image_bytes(load_fn(quats_files[0]))
        c0_arr = _decode_image_bytes(load_fn(sh0_files[0]))
    except Exception:
        return None
    try:
        lo = _flat_pixels(lo_arr, count)
        hi = _flat_pixels(hi_arr, count)
        sl = _flat_pixels(sl_arr, count)
        qr = _flat_pixels(qr_arr, count)
        c0 = _flat_pixels(c0_arr, count)
    except Exception:
        return None
    xs = (lo[:, 0].astype(np.float32) + hi[:, 0].astype(np.float32) * 256.0) / 65535.0
    ys = (lo[:, 1].astype(np.float32) + hi[:, 1].astype(np.float32) * 256.0) / 65535.0
    zs = (lo[:, 2].astype(np.float32) + hi[:, 2].astype(np.float32) * 256.0) / 65535.0
    x_min = float(means_mins[0])
    x_sc = float(means_maxs[0] - means_mins[0]) or 1.0
    y_min = float(means_mins[1])
    y_sc = float(means_maxs[1] - means_mins[1]) or 1.0
    z_min = float(means_mins[2])
    z_sc = float(means_maxs[2] - means_mins[2]) or 1.0
    lx = (x_min + x_sc * xs).astype(np.float64)
    ly = (y_min + y_sc * ys).astype(np.float64)
    lz = (z_min + z_sc * zs).astype(np.float64)
    pos = np.empty((count, 3), dtype=np.float32)
    pos[:, 0] = _inv_log_transform(lx)
    pos[:, 1] = _inv_log_transform(ly)
    pos[:, 2] = _inv_log_transform(lz)
    wxyz = _unpack_quats(qr)
    quat = np.empty((count, 4), dtype=np.float32)
    quat[:, 0] = wxyz[:, 1]
    quat[:, 1] = wxyz[:, 2]
    quat[:, 2] = wxyz[:, 3]
    quat[:, 3] = wxyz[:, 0]
    s_raw = np.empty((count, 3), dtype=np.float32)
    s_raw[:, 0] = scales_code[sl[:, 0].astype(np.int64)]
    s_raw[:, 1] = scales_code[sl[:, 1].astype(np.int64)]
    s_raw[:, 2] = scales_code[sl[:, 2].astype(np.int64)]
    scl = np.exp(s_raw.astype(np.float64)).astype(np.float32)
    dc_raw = np.empty((count, 3), dtype=np.float32)
    dc_raw[:, 0] = sh0_code[c0[:, 0].astype(np.int64)]
    dc_raw[:, 1] = sh0_code[c0[:, 1].astype(np.int64)]
    dc_raw[:, 2] = sh0_code[c0[:, 2].astype(np.int64)]
    dc = dc_raw * np.float32(SH_C0) + np.float32(0.5)
    opa = (c0[:, 3].astype(np.float32) / 255.0).astype(np.float32)
    shn = meta.get("shN")
    rest = np.zeros((count, 0), dtype=np.float32)
    num_sh = 1
    if isinstance(shn, dict):
        try:
            bands = int(shn.get("bands", 0))
        except Exception:
            bands = 0
        coeffs = int(_SH_COEFFS[bands]) if 0 <= bands <= 3 else 0
        if coeffs > 0:
            try:
                palette_count = int(shn.get("count", 0))
                sh_code = np.array(list(shn.get("codebook", [])), dtype=np.float32)
                sh_files = list(shn.get("files", []))
                if sh_code.shape[0] == 256 and len(sh_files) >= 2 and palette_count > 0:
                    cent_arr = _decode_image_bytes(load_fn(sh_files[0]))
                    lab_arr = _decode_image_bytes(load_fn(sh_files[1]))
                    lab = _flat_pixels(lab_arr, count)
                    labels = (lab[:, 0].astype(np.int32) | (lab[:, 1].astype(np.int32) << 8)).astype(np.int64)
                    pal = _build_palette_v2(cent_arr, coeffs, palette_count, sh_code)
                    rest = _gather_rest(pal, labels, count)
                    num_sh = int(bands + 1)
            except Exception:
                rest = np.zeros((count, 0), dtype=np.float32)
                num_sh = 1
    return _finalize(pos, dc, rest, opa, scl, quat, num_sh)
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
        sl_arr = _decode_image_bytes(load_fn(scales_files[0]))
        qr_arr = _decode_image_bytes(load_fn(quats_files[0]))
        c0_arr = _decode_image_bytes(load_fn(sh0_files[0]))
    except Exception:
        return None
    try:
        lo = _flat_pixels(lo_arr, count)
        hi = _flat_pixels(hi_arr, count)
        sl = _flat_pixels(sl_arr, count)
        qr = _flat_pixels(qr_arr, count)
        c0 = _flat_pixels(c0_arr, count)
    except Exception:
        return None
    xs = (lo[:, 0].astype(np.float32) + hi[:, 0].astype(np.float32) * 256.0) / 65535.0
    ys = (lo[:, 1].astype(np.float32) + hi[:, 1].astype(np.float32) * 256.0) / 65535.0
    zs = (lo[:, 2].astype(np.float32) + hi[:, 2].astype(np.float32) * 256.0) / 65535.0
    x_min = float(means_mins[0])
    x_sc = float(means_maxs[0] - means_mins[0]) or 1.0
    y_min = float(means_mins[1])
    y_sc = float(means_maxs[1] - means_mins[1]) or 1.0
    z_min = float(means_mins[2])
    z_sc = float(means_maxs[2] - means_mins[2]) or 1.0
    lx = (x_min + x_sc * xs).astype(np.float64)
    ly = (y_min + y_sc * ys).astype(np.float64)
    lz = (z_min + z_sc * zs).astype(np.float64)
    pos = np.empty((count, 3), dtype=np.float32)
    pos[:, 0] = _inv_log_transform(lx)
    pos[:, 1] = _inv_log_transform(ly)
    pos[:, 2] = _inv_log_transform(lz)
    wxyz = _unpack_quats(qr)
    quat = np.empty((count, 4), dtype=np.float32)
    quat[:, 0] = wxyz[:, 1]
    quat[:, 1] = wxyz[:, 2]
    quat[:, 2] = wxyz[:, 3]
    quat[:, 3] = wxyz[:, 0]
    s_raw = np.empty((count, 3), dtype=np.float32)
    s_raw[:, 0] = (float(s_mins[0]) + float(s_maxs[0] - s_mins[0]) * (sl[:, 0].astype(np.float32) / 255.0)).astype(np.float32)
    s_raw[:, 1] = (float(s_mins[1]) + float(s_maxs[1] - s_mins[1]) * (sl[:, 1].astype(np.float32) / 255.0)).astype(np.float32)
    s_raw[:, 2] = (float(s_mins[2]) + float(s_maxs[2] - s_mins[2]) * (sl[:, 2].astype(np.float32) / 255.0)).astype(np.float32)
    scl = np.exp(s_raw.astype(np.float64)).astype(np.float32)
    dc_raw = np.empty((count, 3), dtype=np.float32)
    dc_raw[:, 0] = (float(c_mins[0]) + float(c_maxs[0] - c_mins[0]) * (c0[:, 0].astype(np.float32) / 255.0)).astype(np.float32)
    dc_raw[:, 1] = (float(c_mins[1]) + float(c_maxs[1] - c_mins[1]) * (c0[:, 1].astype(np.float32) / 255.0)).astype(np.float32)
    dc_raw[:, 2] = (float(c_mins[2]) + float(c_maxs[2] - c_mins[2]) * (c0[:, 2].astype(np.float32) / 255.0)).astype(np.float32)
    dc = dc_raw * np.float32(SH_C0) + np.float32(0.5)
    op_logit = (float(c_mins[3]) + float(c_maxs[3] - c_mins[3]) * (c0[:, 3].astype(np.float32) / 255.0)).astype(np.float32)
    opa = _sigmoid(op_logit)
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
                    per_row = int(cw // max(1, coeffs))
                    chh = int(cent_arr.shape[0])
                    palette_count = int(per_row * chh)
                    smin = float(shn.get("mins", 0.0))
                    smax = float(shn.get("maxs", 1.0))
                    sspan = float(smax - smin)
                    pal = _build_palette_v1(cent_arr, coeffs, palette_count, smin, sspan)
                    rest = _gather_rest(pal, labels, count)
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
        return load_ssog_gaussian_splat(ap)
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
                return load_ssog_gaussian_splat(ap)
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
    norms = []
    shs = []
    opas = []
    scls = []
    quats = []
    top_sh = 1
    for d in items:
        poss.append(np.ascontiguousarray(d.positions, dtype=np.float32))
        norms.append(np.zeros_like(np.ascontiguousarray(d.positions, dtype=np.float32)))
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
