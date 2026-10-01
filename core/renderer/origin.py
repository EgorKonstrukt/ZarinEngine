# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np


_origin_last_key = None
_origin_last_value = None


def origin_for(cam_pos, enabled=None):
    global _origin_last_key
    global _origin_last_value
    try:
        from core.renderer.precision import is_rtc_enabled
        flag = is_rtc_enabled() if enabled is None else bool(enabled)
    except Exception:
        flag = bool(enabled) if enabled is not None else False
    if not flag:
        return None
    try:
        cx = float(cam_pos.x)
        cy = float(cam_pos.y)
        cz = float(cam_pos.z)
    except Exception:
        try:
            arr = np.asarray(cam_pos.to_array(), dtype=np.float64).reshape(3)
            cx = float(arr[0])
            cy = float(arr[1])
            cz = float(arr[2])
        except Exception:
            return None
    key = (cx, cy, cz)
    if key == _origin_last_key:
        return _origin_last_value
    val = np.array([cx, cy, cz], dtype=np.float64)
    _origin_last_key = key
    _origin_last_value = val
    return val


def origin_from_view(view_mat, enabled=None):
    try:
        from core.renderer.precision import is_rtc_enabled
        flag = is_rtc_enabled() if enabled is None else bool(enabled)
    except Exception:
        flag = bool(enabled) if enabled is not None else False
    if not flag:
        return None
    try:
        d = view_mat._d.astype(np.float64)
        t = d[3, :3]
        c = -(d[:3, :3] @ t)
        return np.array([float(c[0]), float(c[1]), float(c[2])], dtype=np.float64)
    except Exception:
        return None


def relativize_positions(arr, origin):
    if origin is None:
        return arr
    try:
        a = np.asarray(arr, dtype=np.float64)
    except Exception:
        return arr
    try:
        if a.size == 0 or a.shape[-1] != 3:
            return arr
        o = np.asarray(origin, dtype=np.float64).reshape(3)
        return np.ascontiguousarray(a - o)
    except Exception:
        return arr


def relativize_chunk_f32(chunk, origin):
    if origin is None:
        return chunk
    try:
        a = np.asarray(chunk)
        if a.size == 0:
            return chunk
        if a.ndim == 2:
            stride = int(a.shape[1])
        else:
            stride = 16
        if stride < 16 or a.size % stride != 0:
            return chunk
        m = a.reshape(-1, stride).astype(np.float64)
        ox = float(origin[0])
        oy = float(origin[1])
        oz = float(origin[2])
        m[:, 12] -= ox
        m[:, 13] -= oy
        m[:, 14] -= oz
        return np.ascontiguousarray(m.astype(np.float32)).reshape(a.shape)
    except Exception:
        return chunk


def shifted_model(model_mat, origin):
    if origin is None:
        return model_mat
    try:
        d = model_mat._d.astype(np.float64)
        d[3, 0] -= float(origin[0])
        d[3, 1] -= float(origin[1])
        d[3, 2] -= float(origin[2])
        from core.maths.math3d import Mat4
        return Mat4(d)
    except Exception:
        return model_mat


def relativize_model_f32(model_mat, origin):
    if origin is None:
        try:
            return model_mat.to_f32()
        except Exception:
            return np.eye(4, dtype=np.float32).reshape(-1)
    try:
        d = model_mat._d
        out = d.astype(np.float32)
        out[3, 0] -= float(origin[0])
        out[3, 1] -= float(origin[1])
        out[3, 2] -= float(origin[2])
        return out.reshape(-1)
    except Exception:
        pass
    try:
        return shifted_model(model_mat, origin).to_f32()
    except Exception:
        try:
            return model_mat.to_f32()
        except Exception:
            return np.eye(4, dtype=np.float32).reshape(-1)


def relativize_models(mats, origin):
    if origin is None:
        return mats
    try:
        return [shifted_model(m, origin) for m in mats]
    except Exception:
        return mats


def shifted_vp(vp_mat, origin):
    if origin is None:
        return vp_mat
    try:
        d = vp_mat._d.astype(np.float64)
        ox = float(origin[0])
        oy = float(origin[1])
        oz = float(origin[2])
        d[3, :] += ox * d[0, :] + oy * d[1, :] + oz * d[2, :]
        from core.maths.math3d import Mat4
        return Mat4(d)
    except Exception:
        return vp_mat


def relativize_view_bytes(view_f32, origin):
    try:
        if isinstance(view_f32, (bytes, bytearray, memoryview)):
            base = np.frombuffer(view_f32, dtype=np.float32).astype(np.float32)
        else:
            base = np.asarray(view_f32, dtype=np.float32).reshape(-1)
    except Exception:
        try:
            return view_f32.tobytes()
        except Exception:
            return view_f32
    if origin is None or base.size < 16:
        return base.tobytes()
    try:
        out = base.copy()
        out[12] = 0.0
        out[13] = 0.0
        out[14] = 0.0
        return out.tobytes()
    except Exception:
        return base.tobytes()


def shift_vp_bytes(vp, origin):
    if origin is None:
        try:
            return vp.tobytes()
        except Exception:
            return vp
    try:
        if isinstance(vp, (bytes, bytearray, memoryview)):
            a = np.frombuffer(vp, dtype=np.float32).astype(np.float64).reshape(-1, 4, 4)
        else:
            a = np.asarray(vp, dtype=np.float64).reshape(-1, 4, 4).copy()
    except Exception:
        try:
            return vp.tobytes()
        except Exception:
            return vp
    try:
        ox = float(origin[0])
        oy = float(origin[1])
        oz = float(origin[2])
        a[:, 3, :] += ox * a[:, 0, :] + oy * a[:, 1, :] + oz * a[:, 2, :]
        return np.ascontiguousarray(a.astype(np.float32)).tobytes()
    except Exception:
        try:
            return vp.tobytes()
        except Exception:
            return vp


def shift_pos_bytes(blob, origin):
    if origin is None:
        return blob
    try:
        a = np.frombuffer(blob, dtype=np.float32).astype(np.float64).reshape(-1, 3)
    except Exception:
        return blob
    try:
        a[:, 0] -= float(origin[0])
        a[:, 1] -= float(origin[1])
        a[:, 2] -= float(origin[2])
        return np.ascontiguousarray(a.astype(np.float32)).tobytes()
    except Exception:
        return blob
