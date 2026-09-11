# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Central registry of physics solver backends.

Single source of truth for the available physics engines, used by:
* plugins/physics_plugin.py (runtime solver selection),
* editor/settings_dialog.py (Project Settings dropdown),
* editor/build_dialog.py + build_nuitka.py (which solver to bake into a build).

Default solver: ``culverin`` (Culverin — Python bindings for Jolt Physics).
"""

from __future__ import annotations

import importlib.util

#: Default physics solver used for new projects and when nothing is configured.
DEFAULT_SOLVER = "culverin"

SOLVERS: dict[str, dict] = {
    "culverin": {
        "title": "Culverin (Jolt Physics)",
        "short": "Culverin",
        "engine": "Jolt Physics",
        "module": "physics_solvers.culverin_solver",
        "class_name": "CulverinSolver",
        "pip": "culverin",
        "default": True,
        "description": (
            "Default solver. Jolt Physics via the 'culverin' package: "
            "fast, deterministic rigid/soft bodies, recommended for most projects."
        ),
    },
    "pybullet": {
        "title": "PyBullet (Bullet Physics)",
        "short": "PyBullet",
        "engine": "Bullet Physics",
        "module": "physics_solvers.pybullet_solver",
        "class_name": "PyBulletSolver",
        "pip": "pybullet",
        "default": False,
        "description": (
            "Bullet Physics via 'pybullet'. Good compatibility with robotics "
            "tooling; needs 'pip install pybullet'."
        ),
    },
    "physx": {
        "title": "PhysX (NVIDIA)",
        "short": "PhysX",
        "engine": "NVIDIA PhysX",
        "module": "physics_solvers.physx_solver",
        "class_name": "PhysXSolver",
        "pip": "ovphysx",
        "default": False,
        "description": (
            "NVIDIA PhysX via 'ovphysx' (USD-based). GPU-capable; "
            "needs 'pip install ovphysx'."
        ),
    },
}


def choices() -> list[str]:
    """Solver keys in UI order (default first)."""
    keys = list(SOLVERS)
    keys.sort(key=lambda k: (not SOLVERS[k].get("default", False), k))
    return keys


def normalize(name: str | None) -> str:
    """Map any input to a valid solver key, falling back to the default."""
    if isinstance(name, str):
        key = name.strip().lower()
        if key in SOLVERS:
            return key
        # Accept titles like "Culverin (Jolt Physics)" or engine names.
        for k, info in SOLVERS.items():
            if key in (
                info.get("title", "").lower(),
                info.get("short", "").lower(),
                info.get("engine", "").lower(),
            ):
                return k
    return DEFAULT_SOLVER


def get_info(name: str | None = None) -> dict:
    """Metadata dict for a solver (default solver when omitted/unknown)."""
    return SOLVERS[normalize(name)]


def get_module_class(name: str | None = None) -> tuple[str, str]:
    """Return (module, class_name) for a solver."""
    info = get_info(name)
    return info["module"], info["class_name"]


def is_available(name: str | None = None) -> bool:
    """True if the solver's native package is importable."""
    pip_name = get_info(name).get("pip", "")
    if not pip_name:
        return True
    return importlib.util.find_spec(pip_name) is not None
