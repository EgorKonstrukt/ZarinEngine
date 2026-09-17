# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import struct
import numpy as np
from dataclasses import dataclass
from typing import Optional

SH_C0 = 0.28209479177387814
SH_C1 = 0.4886025119029199
SH_C2_0 = 1.0925484305920792
SH_C2_1 = -1.0925484305920792
SH_C2_2 = 0.31539156525252005
SH_C2_3 = -1.0925484305920792
SH_C2_4 = 0.5462742152960396
SH_C3_0 = -0.5900435899266435
SH_C3_1 = 2.890611442640554
SH_C3_2 = -0.4570457994644658
SH_C3_3 = 0.3731763325901154
SH_C3_4 = -0.4570457994644658
SH_C3_5 = 1.4453057213202769
SH_C3_6 = -0.5900435899266435


def _splat_dtype(num_sh: int):
    n_rest = (num_sh * num_sh - 1) * 3
    fields = [
        ("x", np.float32), ("y", np.float32), ("z", np.float32),
        ("nx", np.float32), ("ny", np.float32), ("nz", np.float32),
        ("f_dc_0", np.float32), ("f_dc_1", np.float32), ("f_dc_2", np.float32),
    ]
    for i in range(n_rest):
        fields.append((f"f_rest_{i}", np.float32))
    fields.append(("opacity", np.float32))
    fields.append(("scale_0", np.float32))
    fields.append(("scale_1", np.float32))
    fields.append(("scale_2", np.float32))
    fields.append(("rot_0", np.float32))
    fields.append(("rot_1", np.float32))
    fields.append(("rot_2", np.float32))
    fields.append(("rot_3", np.float32))
    return np.dtype(fields)


@dataclass
class GaussianSplatData:
    positions: np.ndarray
    normals: np.ndarray
    sh_coeffs: np.ndarray
    opacity: np.ndarray
    scales: np.ndarray
    quaternions: np.ndarray
    num_sh: int

    @property
    def num_splats(self) -> int:
        return len(self.positions)


def _parse_header(lines: list[str]):
    vertex_count = 0
    properties = []
    fmt = "binary_little_endian"
    in_vertex = False
    for line in lines:
        s = line.strip()
        if s.startswith("format"):
            parts = s.split()
            if len(parts) >= 2:
                fmt = parts[1]
        elif s.startswith("element vertex"):
            parts = s.split()
            vertex_count = int(parts[2])
            in_vertex = True
        elif s.startswith("element"):
            in_vertex = False
        elif s.startswith("property") and in_vertex:
            parts = s.split()
            dtype_str = parts[1]
            name = parts[2]
            properties.append((dtype_str, name))
    return vertex_count, properties, fmt


def _ply_type(s: str):
    m = {
        "float": np.float32, "float32": np.float32, "double": np.float64,
        "uchar": np.uint8, "uint8": np.uint8,
        "short": np.int16, "int16": np.int16,
        "ushort": np.uint16, "uint16": np.uint16,
        "int": np.int32, "int32": np.int32,
        "uint": np.uint32, "uint32": np.uint32,
    }
    return m.get(s, np.float32)


_SPLAT_TILE_ROWS = 16384

_Z180_REST_SIGN = {
    9: (0, 2, 3, 5, 6, 8),
    24: (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22),
    45: (0, 2, 4, 6, 8, 10, 12, 14, 15, 17, 19, 21, 23, 25, 27, 29, 30,
         32, 34, 36, 38, 40, 42, 44),
}


def _parse_splat_columns(raw, prop_names: list, has_normals: bool):
    n = int(raw.shape[0])
    if n == 0:
        return None
    try:
        col_index = {name: j for j, (name, _) in enumerate(raw.dtype.descr)}
        ix = col_index["x"]
        iy = col_index["y"]
        iz = col_index["z"]
        idc = [col_index["f_dc_0"], col_index["f_dc_1"], col_index["f_dc_2"]]
        iop = col_index["opacity"]
        isc = [col_index["scale_0"], col_index["scale_1"], col_index["scale_2"]]
        iqx = [col_index["rot_1"], col_index["rot_2"],
               col_index["rot_3"], col_index["rot_0"]]
    except KeyError:
        return None
    try:
        for _nm, _dt in raw.dtype.descr:
            if np.dtype(_dt) != np.float32:
                return None
    except (TypeError, ValueError):
        return None
    rest_keys = [k for k in prop_names if k.startswith("f_rest_")]
    if len(rest_keys) > 45:
        rest_keys = rest_keys[:45]
    num_rest = len(rest_keys)
    try:
        rk = [col_index[k] for k in rest_keys]
        if has_normals:
            inx = col_index["nx"]
            iny = col_index["ny"]
            inz = col_index["nz"]
        else:
            inx = iny = inz = -1
    except KeyError:
        return None
    flip = _Z180_REST_SIGN.get(num_rest, ())
    flip_set = set(flip)
    ncols = len(col_index)
    positions = np.empty((n, 3), dtype=np.float32)
    normals = np.zeros((n, 3), dtype=np.float32)
    sh_coeffs = np.empty((n, 3 + num_rest), dtype=np.float32)
    opacity = np.empty(n, dtype=np.float32)
    scales = np.empty((n, 3), dtype=np.float32)
    quaternions = np.empty((n, 4), dtype=np.float32)
    valid = np.ones(n, dtype=np.bool_)
    c0 = np.float32(SH_C0)
    c05 = np.float32(0.5)
    tile = _SPLAT_TILE_ROWS
    for s in range(0, n, tile):
        e = s + tile if s + tile < n else n
        c = np.asarray(raw[s:e]).view(np.float32).reshape(e - s, ncols)
        p = positions[s:e]
        p[:, 0] = c[:, ix]
        p[:, 1] = c[:, iy]
        p[:, 2] = c[:, iz]
        p[:, 0] *= np.float32(-1.0)
        p[:, 1] *= np.float32(-1.0)
        if has_normals:
            nn = normals[s:e]
            nn[:, 0] = c[:, inx]
            nn[:, 1] = c[:, iny]
            nn[:, 2] = c[:, inz]
        sh = sh_coeffs[s:e]
        sh[:, 0] = c[:, idc[0]] * c0 + c05
        sh[:, 1] = c[:, idc[1]] * c0 + c05
        sh[:, 2] = c[:, idc[2]] * c0 + c05
        for j, k in enumerate(rk):
            col = c[:, k]
            if j in flip_set:
                np.negative(col, out=sh[:, 3 + j])
            else:
                sh[:, 3 + j] = col
        op = opacity[s:e]
        op[:] = c[:, iop]
        np.negative(op, out=op)
        np.exp(op, out=op)
        op += np.float32(1.0)
        np.reciprocal(op, out=op)
        sc = scales[s:e]
        sc[:, 0] = c[:, isc[0]]
        sc[:, 1] = c[:, isc[1]]
        sc[:, 2] = c[:, isc[2]]
        np.exp(sc, out=sc)
        qq = quaternions[s:e]
        qq[:, 0] = c[:, iqx[0]]
        qq[:, 1] = c[:, iqx[1]]
        qq[:, 2] = c[:, iqx[2]]
        qq[:, 3] = c[:, iqx[3]]
        q0 = -qq[:, 1].copy()
        q3 = -qq[:, 2].copy()
        qq[:, 1] = qq[:, 0]
        qq[:, 2] = qq[:, 3]
        qq[:, 0] = q0
        qq[:, 3] = q3
        q_len = np.linalg.norm(qq, axis=1, keepdims=True)
        q_len = np.maximum(q_len, 1e-8)
        qq /= q_len
        vm = valid[s:e]
        vm[:] = True
        vm &= np.isfinite(p).all(axis=1)
        vm &= np.isfinite(sh).all(axis=1)
        vm &= np.isfinite(op)
        vm &= np.isfinite(sc).all(axis=1)
        vm &= np.isfinite(qq).all(axis=1)
        vm &= sc.max(axis=1) > 0.0
    num_sh = 1
    if num_rest > 0:
        num_sh = max(1, min(int(np.sqrt(num_rest // 3 + 1)), 4))
    return (positions, normals, sh_coeffs, opacity, scales,
            quaternions, num_sh, valid)


def load_ply_gaussian_splat(path: str) -> Optional[GaussianSplatData]:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            header_lines = []
            while True:
                line = f.readline()
                if not line:
                    return None
                decoded = line.decode("ascii", errors="ignore").strip()
                header_lines.append(decoded)
                if decoded == "end_header":
                    break

            vertex_count, properties, fmt = _parse_header(header_lines)

            prop_names = [p[1] for p in properties]
            has_normals = "nx" in prop_names

            if fmt == "binary_little_endian":
                dt = np.dtype([(p[1], _ply_type(p[0])) for p in properties])
                blob = f.read(vertex_count * dt.itemsize)
                raw = np.frombuffer(blob, dtype=dt)
                parsed = _parse_splat_columns(raw, prop_names, has_normals)
                if parsed is None:
                    try:
                        dt32 = np.dtype([(nm, np.float32) for nm in prop_names])
                        raw32 = np.empty(vertex_count, dtype=dt32)
                        for nm in prop_names:
                            raw32[nm] = raw[nm].astype(np.float32)
                        parsed = _parse_splat_columns(raw32, prop_names, has_normals)
                    except (ValueError, TypeError, KeyError):
                        parsed = None
                    if parsed is None:
                        return None
                (positions, normals, sh_coeffs, opacity, scales,
                 quaternions, num_sh, valid) = parsed
                if not bool(valid.all()):
                    if not bool(valid.any()):
                        return None
                    positions = np.ascontiguousarray(positions[valid])
                    normals = np.ascontiguousarray(normals[valid])
                    sh_coeffs = np.ascontiguousarray(sh_coeffs[valid])
                    opacity = np.ascontiguousarray(opacity[valid])
                    scales = np.ascontiguousarray(scales[valid])
                    quaternions = np.ascontiguousarray(quaternions[valid])
                return GaussianSplatData(
                    positions=positions,
                    normals=normals,
                    sh_coeffs=sh_coeffs,
                    opacity=opacity,
                    scales=scales,
                    quaternions=quaternions,
                    num_sh=num_sh,
                )
            elif fmt == "binary_big_endian":
                dt = np.dtype([(p[1], _ply_type(p[0])) for p in properties])
                raw = np.frombuffer(f.read(vertex_count * dt.itemsize), dtype=dt)
                raw = raw.astype(dt.newbyteorder("<"))
            else:
                dt = np.dtype([(p[1], _ply_type(p[0])) for p in properties])
                body = f.read().decode("ascii", errors="ignore")
                n_cols = len(properties)
                needed = vertex_count * n_cols
                raw = None
                try:
                    flat = np.fromstring(body, dtype=np.float32, sep=" ")
                    if flat.size >= needed:
                        cols = flat[:needed].reshape(vertex_count, n_cols)
                        raw = np.empty(vertex_count, dtype=dt)
                        for i, (_, name) in enumerate(properties):
                            raw[name] = cols[:, i]
                except Exception:
                    raw = None
                if raw is None:
                    lines = body.splitlines()
                    raw = np.zeros(vertex_count, dtype=dt)
                    for r in range(vertex_count):
                        vals = lines[r].split() if r < len(lines) else []
                        for i, (_, name) in enumerate(properties):
                            v = vals[i] if i < len(vals) else "0"
                            t = _ply_type(properties[i][0])
                            if t == np.uint8:
                                raw[name][r] = int(v)
                            elif t in (np.int16, np.int32):
                                raw[name][r] = int(v)
                            else:
                                raw[name][r] = float(v)

            positions = np.column_stack([raw["x"].astype(np.float32),
                                          raw["y"].astype(np.float32),
                                          raw["z"].astype(np.float32)])

            if has_normals:
                normals = np.column_stack([raw["nx"].astype(np.float32),
                                            raw["ny"].astype(np.float32),
                                            raw["nz"].astype(np.float32)])
            else:
                normals = np.zeros_like(positions)

            dc = np.column_stack([raw["f_dc_0"].astype(np.float32),
                                   raw["f_dc_1"].astype(np.float32),
                                   raw["f_dc_2"].astype(np.float32)])
            dc = dc * SH_C0 + 0.5

            rest_keys = [k for k in prop_names if k.startswith("f_rest_")]
            if len(rest_keys) > 45:
                rest_keys = rest_keys[:45]
            num_rest = len(rest_keys)
            if num_rest > 0:
                rest = np.column_stack([raw[k].astype(np.float32) for k in rest_keys])
            else:
                rest = np.zeros((vertex_count, 0), dtype=np.float32)

            sh_coeffs = np.concatenate([dc, rest], axis=1)

            logit = raw["opacity"].astype(np.float32)
            opacity = 1.0 / (1.0 + np.exp(-logit))

            scales = np.exp(np.column_stack([raw["scale_0"].astype(np.float32),
                                              raw["scale_1"].astype(np.float32),
                                              raw["scale_2"].astype(np.float32)]))

            quaternions = np.column_stack([raw["rot_1"].astype(np.float32),
                                            raw["rot_2"].astype(np.float32),
                                            raw["rot_3"].astype(np.float32),
                                            raw["rot_0"].astype(np.float32)])
            q_len = np.linalg.norm(quaternions, axis=1, keepdims=True)
            q_len = np.maximum(q_len, 1e-8)
            quaternions = quaternions / q_len

            num_sh = 1
            rest_per_sh = 3
            if num_rest > 0:
                num_sh_approx = int(np.sqrt(num_rest // rest_per_sh + 1))
                num_sh = max(1, min(num_sh_approx, 4))

            valid = np.isfinite(positions).all(axis=1)
            valid &= np.isfinite(sh_coeffs).all(axis=1)
            valid &= np.isfinite(opacity)
            valid &= np.isfinite(scales).all(axis=1)
            valid &= np.isfinite(quaternions).all(axis=1)
            valid &= scales.max(axis=1) > 0.0
            if not bool(valid.all()):
                if not bool(valid.any()):
                    return None
                positions = np.ascontiguousarray(positions[valid])
                normals = np.ascontiguousarray(normals[valid])
                sh_coeffs = np.ascontiguousarray(sh_coeffs[valid])
                opacity = np.ascontiguousarray(opacity[valid])
                scales = np.ascontiguousarray(scales[valid])
                quaternions = np.ascontiguousarray(quaternions[valid])
                vertex_count = positions.shape[0]

            try:
                from core.assets.sog_loader import _apply_z180
                _apply_z180(positions, quaternions, sh_coeffs)
            except Exception:
                pass

            return GaussianSplatData(
                positions=positions,
                normals=normals,
                sh_coeffs=sh_coeffs,
                opacity=opacity,
                scales=scales,
                quaternions=quaternions,
                num_sh=num_sh,
            )
    except Exception:
        return None
