# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import io
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
def _z180_sh_mask(n: int) -> np.ndarray:
    m = np.zeros(max(0, int(n)), dtype=np.bool_)
    if int(n) == 9:
        m[np.array([0, 2, 3, 5, 6, 8], dtype=np.int64)] = True
        return m
    if int(n) == 24:
        m[np.array([0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22], dtype=np.int64)] = True
        return m
    if int(n) == 45:
        m[np.array([0, 2, 4, 6, 8, 10, 12, 14, 15, 17, 19, 21, 23, 25, 27, 29, 30, 32, 34, 36, 38, 40, 42, 44], dtype=np.int64)] = True
        return m
    return m
def _apply_z180(pos: np.ndarray, quat_xyzw: np.ndarray, sh: np.ndarray) -> None:
    pos[:, 0] *= np.float32(-1.0)
    pos[:, 1] *= np.float32(-1.0)
    tx = quat_xyzw[:, 0].copy()
    tz = quat_xyzw[:, 2].copy()
    quat_xyzw[:, 0] = -quat_xyzw[:, 1]
    quat_xyzw[:, 1] = tx
    quat_xyzw[:, 2] = quat_xyzw[:, 3]
    quat_xyzw[:, 3] = -tz
    try:
        r = int(sh.shape[1] - 3)
    except Exception:
        return
    if r <= 0:
        return
    mk = _z180_sh_mask(r)
    try:
        has = bool(np.any(mk))
    except Exception:
        return
    if not has:
        return
    rs = sh[:, 3:]
    rs[:, mk] = -rs[:, mk]
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
    _apply_z180(pos, quat_xyzw, sh)
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
    s_raw[:, 0] = scales_code[sl[:, 0].astype(np.int64)]
    s_raw[:, 1] = scales_code[sl[:, 1].astype(np.int64)]
    s_raw[:, 2] = scales_code[sl[:, 2].astype(np.int64)]
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
    dc_raw[:, 0] = sh0_code[c0[:, 0].astype(np.int64)]
    dc_raw[:, 1] = sh0_code[c0[:, 1].astype(np.int64)]
    dc_raw[:, 2] = sh0_code[c0[:, 2].astype(np.int64)]
    dc = dc_raw * np.float32(SH_C0) + np.float32(0.5)
    del dc_raw
    opa = (c0[:, 3].astype(np.float32) / 255.0).astype(np.float32)
    del c0, c0_arr
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
                    del lab, lab_arr
                    pal = _build_palette_v2(cent_arr, coeffs, palette_count, sh_code)
                    del cent_arr
                    rest = _gather_rest(pal, labels, count)
                    del pal, labels
                    num_sh = int(bands + 1)
            except Exception:
                rest = np.zeros((count, 0), dtype=np.float32)
                num_sh = 1
    return _finalize(pos, dc, rest, opa, scl, quat, num_sh)
