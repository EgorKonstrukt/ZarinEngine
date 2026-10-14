# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import sys
import os
import ctypes
import numpy as np
from core.assets.importer.ctypes_types import aiMatrix4x4
from core.assets.importer.ctypes_types import aiNode
from core.assets.importer.ctypes_types import aiScene
from core.assets.importer.ctypes_types import aiString
from core.assets.importer.ctypes_types import _ai_matrix_to_np_full
if sys.platform == "win32":
    _ASSIMP_LIB_NAME = "assimp-vc143-mt.dll"
else:
    _ASSIMP_LIB_NAME = "libassimp.so.6.0.5"
def _find_project_root():
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(cur) == "core":
            return os.path.dirname(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = _find_project_root()
_DLL_PATH = os.path.join(_PROJECT_ROOT, _ASSIMP_LIB_NAME)
_dll = None
def _get_dll():
    global _dll
    if _dll is not None:
        return _dll
    candidates = [_DLL_PATH, _ASSIMP_LIB_NAME]
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetErrorMode(0x8007)
    for p in candidates:
        try:
            d = ctypes.CDLL(p)
            if hasattr(d, "aiImportFile"):
                d.aiImportFile.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
                d.aiImportFile.restype = ctypes.POINTER(aiScene)
                d.aiReleaseImport.argtypes = [ctypes.POINTER(aiScene)]
                if hasattr(d, "aiGetMaterialString"):
                    d.aiGetMaterialString.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                                      ctypes.c_uint, ctypes.c_uint,
                                                      ctypes.POINTER(aiString)]
                    d.aiGetMaterialString.restype = ctypes.c_uint
                _dll = d
                return d
        except Exception:
            pass
    raise RuntimeError("Assimp library not found")
def _read_name(field) -> str:
    try:
        buf = ctypes.string_at(ctypes.addressof(field), ctypes.sizeof(field))
    except Exception:
        return ""
    n = int.from_bytes(buf[0:4], "little")
    if n <= 0 or n > 1024:
        n = 0
    data = buf[4:4 + n] if n else b""
    return data.split(b"\x00")[0].decode("utf-8", "ignore")
def _decode_assimp_name(field) -> str:
    return _read_name(field)
def _build_node_map(node_ptr, parent_name, node_map):
    if not node_ptr:
        return
    node = ctypes.cast(node_ptr, ctypes.POINTER(aiNode)).contents
    node_name = _read_name(node.mName)
    try:
        local = _ai_matrix_to_np_full(node.mTransformation)
    except Exception:
        local = np.eye(4, dtype=np.float32)
    node_map[node_name] = (local, parent_name)
    children_ptr = ctypes.cast(node.mChildren, ctypes.POINTER(ctypes.c_void_p * node.mNumChildren))
    for i in range(node.mNumChildren):
        child_addr = children_ptr.contents[i]
        if child_addr:
            _build_node_map(child_addr, node_name, node_map)
def _node_world_zup(node_map, name):
    chain = []
    cur = name
    seen = set()
    while cur is not None and cur in node_map and cur not in seen:
        seen.add(cur)
        local, parent = node_map[cur]
        chain.append(local)
        cur = parent
    m = np.eye(4, dtype=np.float32)
    for part in chain:
        m = m @ part
    return m
