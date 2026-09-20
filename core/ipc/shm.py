# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import struct
import uuid
from multiprocessing import shared_memory
from typing import Optional
import numpy as np


MAGIC = 0x5A41524E
HEADER_FMT = "<I Q I I f f I I 32x"
HEADER_SIZE = 64
FLOATS_PER_ENTITY = 10
DEFAULT_CAPACITY = 4096


def _total_size(capacity: int) -> int:
    return HEADER_SIZE + capacity * FLOATS_PER_ENTITY * 4


class TransformShm:
    def __init__(self, name: str = "", capacity: int = DEFAULT_CAPACITY):
        if not name:
            name = "zarin_shm_" + uuid.uuid4().hex[:12]
        self._name = name
        self._capacity = int(capacity)
        self._shm: Optional[shared_memory.SharedMemory] = None
        self._arr: Optional[np.ndarray] = None
        self._own = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def capacity(self) -> int:
        return self._capacity

    def create(self) -> "TransformShm":
        self._shm = shared_memory.SharedMemory(name=self._name, create=True, size=_total_size(self._capacity))
        self._own = True
        self._map()
        self.set_header(0, 0, 0.0, 0.0, 0)
        return self

    def attach(self, name: str = "", capacity: int = 0) -> "TransformShm":
        if name:
            self._name = name
        if capacity:
            self._capacity = int(capacity)
        self._shm = shared_memory.SharedMemory(name=self._name)
        try:
            magic, _ver, _cnt, cap, _fps, _tps, _play, _seq = struct.unpack_from(HEADER_FMT, self._shm.buf, 0)
            if magic == MAGIC and cap >= 1 and cap <= 65536:
                self._capacity = int(cap)
        except Exception:
            pass
        self._map()
        return self

    def _map(self) -> None:
        buf = self._shm.buf
        self._arr = np.ndarray((self._capacity, FLOATS_PER_ENTITY), dtype=np.float32, buffer=buf[HEADER_SIZE:HEADER_SIZE + self._capacity * FLOATS_PER_ENTITY * 4])

    def _header(self) -> tuple:
        return struct.unpack_from(HEADER_FMT, self._shm.buf, 0)

    def set_header(self, version: int, count: int, fps: float, tps: float, play: int) -> None:
        struct.pack_into(HEADER_FMT, self._shm.buf, 0, MAGIC, int(version), int(count), int(self._capacity), float(fps), float(tps), int(play), 0)

    def get_header(self) -> dict:
        magic, version, count, capacity, fps, tps, play, _seq = struct.unpack_from(HEADER_FMT, self._shm.buf, 0)
        return {"magic": magic, "version": int(version), "count": int(count), "capacity": int(capacity), "fps": float(fps), "tps": float(tps), "play": int(play)}

    def get_version(self) -> int:
        return int(struct.unpack_from("<Q", self._shm.buf, 4)[0])

    def set_version(self, v: int) -> None:
        struct.pack_into("<Q", self._shm.buf, 4, int(v))

    def write_row(self, slot: int, px: float, py: float, pz: float, qx: float, qy: float, qz: float, qw: float, sx: float, sy: float, sz: float) -> None:
        row = self._arr[slot]
        row[0] = px
        row[1] = py
        row[2] = pz
        row[3] = qx
        row[4] = qy
        row[5] = qz
        row[6] = qw
        row[7] = sx
        row[8] = sy
        row[9] = sz

    def read_row(self, slot: int) -> tuple:
        row = self._arr[slot]
        return (float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), float(row[6]), float(row[7]), float(row[8]), float(row[9]))

    def array(self) -> np.ndarray:
        return self._arr

    def close(self) -> None:
        try:
            if self._shm is not None:
                self._shm.close()
        except Exception:
            pass
        self._shm = None
        self._arr = None

    def unlink(self) -> None:
        try:
            if self._shm is not None:
                self._shm.unlink()
        except Exception:
            pass
