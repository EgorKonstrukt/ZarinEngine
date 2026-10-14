# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import os
import ctypes
import numpy as np
from asyncio import Future
from typing import Optional, Callable
from core.ecs.pool import asset as _get_asset_pool
from core.assets.importer.ctypes_types import aiString
from core.assets.importer.assimp import _get_dll
def _read_material_name(scene, mat_idx):
    try:
        if not scene.mMaterials or mat_idx >= scene.mNumMaterials or mat_idx < 0:
            return ""
        dll = _get_dll()
        if not hasattr(dll, "aiGetMaterialString"):
            return ""
        mats = ctypes.cast(scene.mMaterials, ctypes.POINTER(ctypes.c_void_p))
        s = aiString()
        dll.aiGetMaterialString(ctypes.c_void_p(mats[mat_idx]), b"?mat.name", 0, 0, ctypes.byref(s))
        return s.data.decode("utf-8", "ignore")[:s.length]
    except Exception:
        return ""
def load_gif_frames(path: str) -> list[np.ndarray]:
    from PIL import Image
    gif = Image.open(path)
    frames = []
    try:
        while True:
            frame = gif.copy().convert("RGBA")
            frames.append(np.array(frame, dtype=np.uint8))
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass
    if not frames:
        raise ValueError(f"No frames found in GIF: {path}")
    return frames
def gif_frames_to_flipbook(frames: list[np.ndarray], cols: int = None, rows: int = None) -> tuple[np.ndarray, int, int]:
    n = len(frames)
    if cols is None and rows is None:
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
    elif cols is None:
        cols = int(np.ceil(n / rows))
    elif rows is None:
        rows = int(np.ceil(n / cols))
    total = cols * rows
    fh, fw = frames[0].shape[:2]
    sheet = np.zeros((fh * rows, fw * cols, 4), dtype=np.uint8)
    for i in range(total):
        cx = (i % cols) * fw
        cy = (i // cols) * fh
        src = frames[i] if i < n else frames[-1]
        sheet[cy:cy + fh, cx:cx + fw] = src
    return sheet, cols, rows
def import_gif_to_flipbook(gif_path: str, output_path: str = None, cols: int = None, rows: int = None) -> tuple[int, int, int]:
    frames = load_gif_frames(gif_path)
    sheet, cols_out, rows_out = gif_frames_to_flipbook(frames, cols, rows)
    if output_path is None:
        base = os.path.splitext(gif_path)[0]
        output_path = base + "_flipbook.png"
    from PIL import Image
    Image.fromarray(sheet).save(output_path)
    return cols_out, rows_out, len(frames)
def import_gif_to_flipbook_async(gif_path: str, callback: Callable[[Optional[tuple[int, int, int]]], None] = None, output_path: str = None, cols: int = None, rows: int = None) -> Future:
    fut = _get_asset_pool().submit(import_gif_to_flipbook, gif_path, output_path, cols, rows)
    def _done(f):
        try:
            result = f.result()
            if callback:
                callback(result)
        except Exception:
            if callback:
                callback(None)
    fut.add_done_callback(_done)
    return fut
