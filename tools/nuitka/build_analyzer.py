# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_SOLVERS = ("culverin", "pybullet", "physx")
_SOLVER_NATIVES = {
    "culverin": ("culverin",),
    "pybullet": ("pybullet", "pybullet_data"),
    "physx": ("ovphysx",),
}
_DEV_MODULES = (
    "Cython",
    "cython",
    "setuptools",
    "distutils",
    "pytest",
    "_pytest",
    "nuitka",
    "tkinter",
)
_QT_UNUSED = (
    "PySide6.QtMultimedia",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtCharts",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtTextToSpeech",
)


def _normalize_solver(name) -> str:
    try:
        from physics_solvers.registry import normalize
    except Exception:
        normalize = None
    if normalize is not None:
        try:
            return normalize(name)
        except Exception:
            pass
    try:
        key = str(name).strip().lower()
    except Exception:
        return "culverin"
    return key if key in _SOLVERS else "culverin"


def _chosen_solver() -> str:
    try:
        from .config import PHYSICS_CHOICE
    except Exception:
        PHYSICS_CHOICE = None
    if PHYSICS_CHOICE:
        return _normalize_solver(PHYSICS_CHOICE)
    try:
        raw = (ROOT / "ProjectSettings.json").read_text(encoding="utf-8")
    except Exception:
        return "culverin"
    try:
        data = json.loads(raw)
    except Exception:
        return "culverin"
    try:
        solver = data.get("physics", {}).get("solver", "culverin")
    except Exception:
        return "culverin"
    return _normalize_solver(solver)


def analyze(verbose=False) -> dict:
    chosen = _chosen_solver()
    modules = list(_DEV_MODULES)
    packages = ["tests", "tools"]
    packages.extend(_QT_UNUSED)
    for solver in _SOLVERS:
        if solver == chosen:
            continue
        packages.append("physics_solvers." + solver + "_solver")
        for native in _SOLVER_NATIVES.get(solver, ()):
            packages.append(native)
    if verbose:
        print(f"analyzer: solver={chosen} modules={len(modules)} packages={len(packages)}")
    return {"module_nofollow": modules, "package_nofollow": packages}
