# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import array
import wave

import numpy as np


def _fmt(song) -> str:
    return str(getattr(song, "file_extension", "mod") or "mod").lower().strip(".")


def _wave_to_float(smp) -> np.ndarray:
    try:
        if getattr(smp, "is_16bit", False):
            return np.asarray(smp.waveform, dtype=np.float32) / 32768.0
        return np.asarray(smp.waveform, dtype=np.float32) / 128.0
    except Exception:
        return np.zeros(0, dtype=np.float32)


def _float_to_array(floats: np.ndarray, is_16bit: bool) -> array.array:
    data = np.clip(np.nan_to_num(floats, nan=0.0, posinf=1.0, neginf=-1.0), -1.0, 1.0)
    if is_16bit:
        return array.array("h", np.clip(np.round(data * 32767.0), -32768, 32767).astype(np.int16))
    return array.array("b", np.clip(np.round(data * 127.0), -128, 127).astype(np.int8))


def _natural_rate(song, smp) -> int:
    f = _fmt(song)
    if f == "s3m":
        return max(1, int(getattr(smp, "c2spd", 8363) or 8363))
    if f == "xm":
        try:
            rel = int(getattr(smp, "relative_note", 0) or 0)
            fine = int(getattr(smp, "finetune", 0) or 0)
            return max(1, int(8363.0 * 2.0 ** (rel / 12.0 + fine / (128.0 * 12.0))))
        except Exception:
            return 8363
    try:
        return max(1, int(song._get_effective_sample_rate(smp, "C-5")))
    except Exception:
        return 8287


def _resample(x: np.ndarray, in_rate: int, out_rate: int) -> np.ndarray:
    if in_rate == out_rate or len(x) == 0:
        return x
    n_out = max(1, round(len(x) * out_rate / in_rate))
    pos = np.linspace(0, len(x) - 1, num=n_out)
    i0 = pos.astype(np.int64)
    i1 = np.clip(i0 + 1, 0, len(x) - 1)
    frac = (pos - i0).astype(np.float32)
    return (x[i0] * (1.0 - frac) + x[i1] * frac).astype(np.float32)


def _write_wav(path: str, floats: np.ndarray, rate: int) -> None:
    pcm = _float_to_array(floats, True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(max(1, int(rate)))
        wf.writeframes(pcm.tobytes())


def _read_wav(path: str):
    with wave.open(path, "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = max(1, wf.getframerate())
        frames = wf.readframes(wf.getnframes())
    if not frames or sw == 0:
        return np.zeros(0, dtype=np.float32), rate
    if sw == 1:
        a = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        data = (a - 128.0) / 128.0
    elif sw == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 3:
        raw = np.frombuffer(frames, dtype=np.uint8).astype(np.uint32)
        vals = raw[0::3] | (raw[1::3] << 8) | (raw[2::3] << 16)
        vals = np.where(vals >= 0x800000, vals - 0x1000000, vals)
        data = vals.astype(np.float32) / 8388608.0
    else:
        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    if nch > 1:
        data = data[: (len(data) // nch) * nch].reshape(-1, nch).mean(axis=1)
    return np.ascontiguousarray(data, dtype=np.float32), rate
