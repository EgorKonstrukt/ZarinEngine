# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os


MODEL_EXTS = frozenset({
    ".obj", ".fbx", ".stl", ".gltf", ".glb", ".usdz",
    ".dae", ".blend", ".3ds", ".x", ".lwo",
    ".stp", ".step",
})

MODEL_FILE_FILTER = "Models (*.obj *.fbx *.stl *.gltf *.glb *.usdz *.dae *.blend *.3ds *.x *.lwo *.stp *.step)"


def is_model_file(path: str) -> bool:
    try:
        return os.path.splitext(path or "")[1].lower() in MODEL_EXTS
    except Exception:
        return False


def model_tab_title(path: str) -> str:
    try:
        base = os.path.splitext(os.path.basename(path or ""))[0] or "Model"
    except Exception:
        base = "Model"
    return "Model: " + base


def default_scene_path_for_model(model_path: str) -> str:
    try:
        d = os.path.dirname(os.path.abspath(model_path))
        base = os.path.splitext(os.path.basename(model_path))[0]
        return os.path.join(d, base + ".zpes")
    except Exception:
        return ""


def export_obj(path: str, positions, indices, normals=None, uvs=None) -> bool:
    try:
        import numpy as np
    except Exception:
        return False
    try:
        pos = np.asarray(positions, dtype=np.float64).reshape(-1, 3) + 0.0
        idx = np.asarray(indices, dtype=np.int64).reshape(-1, 3)
    except Exception:
        return False
    if pos.shape[0] == 0 or idx.shape[0] == 0:
        return False
    try:
        nrm = np.asarray(normals, dtype=np.float64).reshape(-1, 3) if normals is not None else None
        if nrm is not None and nrm.shape[0] != pos.shape[0]:
            nrm = None
    except Exception:
        nrm = None
    try:
        uv = np.asarray(uvs, dtype=np.float64).reshape(-1, 2) if uvs is not None else None
        if uv is not None and uv.shape[0] != pos.shape[0]:
            uv = None
    except Exception:
        uv = None
    try:
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("o " + os.path.splitext(os.path.basename(path))[0] + "\n")
            for p in pos:
                f.write("v " + repr(float(p[0])) + " " + repr(float(p[1])) + " " + repr(float(p[2])) + "\n")
            if uv is not None:
                for t in uv:
                    f.write("vt " + repr(float(t[0])) + " " + repr(float(t[1])) + "\n")
            if nrm is not None:
                for n in nrm:
                    f.write("vn " + repr(float(n[0])) + " " + repr(float(n[1])) + " " + repr(float(n[2])) + "\n")
            has_uv = uv is not None
            has_n = nrm is not None
            for tri in idx:
                parts = []
                for vi in tri:
                    v = int(vi) + 1
                    if has_uv and has_n:
                        parts.append(str(v) + "/" + str(v) + "/" + str(v))
                    elif has_uv:
                        parts.append(str(v) + "/" + str(v))
                    elif has_n:
                        parts.append(str(v) + "//" + str(v))
                    else:
                        parts.append(str(v))
                f.write("f " + " ".join(parts) + "\n")
        return True
    except Exception:
        return False


def import_data_to_arrays(import_data):
    try:
        import numpy as np
    except Exception:
        return None
    try:
        verts = np.asarray(getattr(import_data, "vertices", []), dtype=np.float32).reshape(-1, 3)
        idx = np.asarray(getattr(import_data, "indices", []), dtype=np.int64).reshape(-1, 3)
        if verts.shape[0] == 0 or idx.shape[0] == 0:
            return None
        try:
            norms = np.asarray(getattr(import_data, "normals", []), dtype=np.float32).reshape(-1, 3)
            if norms.shape[0] != verts.shape[0]:
                norms = None
        except Exception:
            norms = None
        try:
            uvs = np.asarray(getattr(import_data, "uvs", []), dtype=np.float32).reshape(-1, 2)
            if uvs.shape[0] != verts.shape[0]:
                uvs = None
        except Exception:
            uvs = None
        return verts, idx, norms, uvs
    except Exception:
        return None
