# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.assets.physics_material import PhysicsMaterial, PhysicCombineMode


def default_physics_material_dict() -> dict:
    return {
        "path": "",
        "dynamic_friction": 0.6,
        "static_friction": 0.6,
        "bounciness": 0.0,
        "friction_combine": PhysicCombineMode.AVERAGE.value,
        "bounce_combine": PhysicCombineMode.AVERAGE.value,
    }


def resolve_physics_material(comp) -> dict:
    try:
        fallback_friction = float(getattr(comp, "material_friction", 0.6))
    except Exception:
        fallback_friction = 0.6
    try:
        fallback_bounce = float(getattr(comp, "material_bounciness", 0.0))
    except Exception:
        fallback_bounce = 0.0
    if fallback_friction != fallback_friction or fallback_friction < 0.0:
        fallback_friction = 0.6
    if fallback_bounce != fallback_bounce or fallback_bounce < 0.0:
        fallback_bounce = 0.0
    try:
        path = getattr(comp, "physic_material", "") or ""
    except Exception:
        path = ""
    if isinstance(path, str) and path:
        try:
            mat = PhysicsMaterial.load_cached(path)
        except Exception:
            mat = None
        if mat is not None:
            return {
                "path": path,
                "dynamic_friction": float(mat.dynamic_friction),
                "static_friction": float(mat.static_friction),
                "bounciness": float(mat.bounciness),
                "friction_combine": PhysicCombineMode.coerce(mat.friction_combine).value,
                "bounce_combine": PhysicCombineMode.coerce(mat.bounce_combine).value,
            }
    return {
        "path": "",
        "dynamic_friction": fallback_friction,
        "static_friction": fallback_friction,
        "bounciness": fallback_bounce,
        "friction_combine": PhysicCombineMode.AVERAGE.value,
        "bounce_combine": PhysicCombineMode.AVERAGE.value,
    }


PRIMITIVE_SHAPE_TYPES = ("box", "sphere", "capsule", "cylinder")

_HALF_SQRT2 = 0.7071067811865476
_CAPSULE_PART_QUAT = {
    0: (0.0, 0.0, _HALF_SQRT2, _HALF_SQRT2),
    1: (0.0, 0.0, 0.0, 1.0),
    2: (_HALF_SQRT2, 0.0, 0.0, _HALF_SQRT2),
}
_PYBULLET_CAPSULE_EULER = {
    0: (0.0, 1.5707963267948966, 0.0),
    1: (-1.5707963267948966, 0.0, 0.0),
    2: (0.0, 0.0, 0.0),
}


def capsule_part_quat(direction: int) -> tuple[float, float, float, float]:
    try:
        return _CAPSULE_PART_QUAT[int(direction) % 3]
    except Exception:
        return (0.0, 0.0, 0.0, 1.0)


def capsule_section_height(radius: float, height: float) -> tuple[float, float]:
    r = max(float(radius), 1e-4)
    try:
        h = max(float(height) - 2.0 * r, 1e-4)
    except Exception:
        h = 1e-4
    return r, h


def capsule_volume(radius: float, height: float) -> float:
    import math
    r, h = capsule_section_height(radius, height)
    return math.pi * r * r * h + 4.0 / 3.0 * math.pi * r ** 3


def part_volume(shape_type: str, params: dict) -> float:
    import math
    try:
        if shape_type == "box":
            s = params.get("size", [1, 1, 1])
            return max(float(s[0]) * float(s[1]) * float(s[2]), 1e-9)
        if shape_type == "sphere":
            r = max(float(params.get("radius", 0.5)), 1e-4)
            return 4.0 / 3.0 * math.pi * r ** 3
        if shape_type == "capsule":
            return max(capsule_volume(float(params.get("radius", 0.5)), float(params.get("height", 2.0))), 1e-9)
        if shape_type == "cylinder":
            r = max(float(params.get("radius", 0.5)), 1e-4)
            h = max(float(params.get("height", 1.0)), 1e-4)
            return math.pi * r * r * h
    except Exception:
        pass
    return 1.0


def part_center(shape_type: str, params: dict) -> list[float]:
    c = params.get("center", [0.0, 0.0, 0.0])
    try:
        return [float(c[0]), float(c[1]), float(c[2])]
    except Exception:
        return [0.0, 0.0, 0.0]
