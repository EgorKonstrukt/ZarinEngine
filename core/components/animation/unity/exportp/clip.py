# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.components.animation.animation_clip import AnimationClip
from core.foundation.curve import TangentMode

_INDENT = "  "


def _f(value: float) -> str:
    if value != value:
        return "0"
    if value in (float("inf"), float("-inf")):
        return "1." + chr(35) + "INF"
    return "%.8g" % value


def _key_scalar(kd: dict, sub_indent: int = 6) -> str:
    v = kd["value"]
    in_w = kd.get("inWeight", 0.33333334)
    out_w = kd.get("outWeight", 0.33333334)
    d = _INDENT * sub_indent
    f = _INDENT * (sub_indent - 2)
    return (
        f"{f}- serializedVersion: 3\n"
        f"{d}time: {_f(kd['time'])}\n"
        f"{d}value: {_f(v)}\n"
        f"{d}inSlope: {_f(kd['inSlope'])}\n"
        f"{d}outSlope: {_f(kd['outSlope'])}\n"
        f"{d}tangentMode: 0\n"
        f"{d}weightedMode: 0\n"
        f"{d}inWeight: {_f(in_w)}\n"
        f"{d}outWeight: {_f(out_w)}\n"
    )


def _key_vector(kd: dict, comps: str, sub_indent: int = 6) -> str:
    parts_v = ", ".join(f"{c}: {_f(kd['value'][c])}" for c in comps)
    parts_in = ", ".join(f"{c}: {_f(kd['inSlope'][c])}" for c in comps)
    parts_out = ", ".join(f"{c}: {_f(kd['outSlope'][c])}" for c in comps)
    parts_w = ", ".join(f"{c}: 0.33333334" for c in comps)
    d = _INDENT * sub_indent
    f = _INDENT * (sub_indent - 2)
    return (
        f"{f}- serializedVersion: 3\n"
        f"{d}time: {_f(kd['time'])}\n"
        f"{d}value: {{{parts_v}}}\n"
        f"{d}inSlope: {{{parts_in}}}\n"
        f"{d}outSlope: {{{parts_out}}}\n"
        f"{d}tangentMode: 0\n"
        f"{d}weightedMode: 0\n"
        f"{d}inWeight: {{{parts_w}}}\n"
        f"{d}outWeight: {{{parts_w}}}\n"
    )


def _slopes(key, prev, nxt):
    if key.tangent_mode == TangentMode.CONSTANT:
        return float("inf"), float("inf")
    if key.tangent_mode == TangentMode.FREE:
        return key.in_tangent, key.out_tangent
    if prev is not None and nxt is not None:
        chord = (nxt.value - prev.value) / max(nxt.time - prev.time, 1e-10)
        return chord, chord
    if prev is not None:
        s = (key.value - prev.value) / max(key.time - prev.time, 1e-10)
        return s, s
    if nxt is not None:
        s = (nxt.value - key.value) / max(nxt.time - key.time, 1e-10)
        return s, s
    return 0.0, 0.0


def _group_vector_curves(clip: AnimationClip, base: str) -> list:
    rows: dict = {}
    order: list = []
    for (bone_path, prop), curve in clip.bone_curves.items():
        if not prop.startswith(base + "."):
            continue
        chan = prop[len(base) + 1:]
        if chan not in ("x", "y", "z"):
            continue
        if bone_path not in rows:
            rows[bone_path] = {
                "times": {},
                "curves": {c: None for c in ("x", "y", "z")},
            }
            order.append(bone_path)
        rows[bone_path]["curves"][chan] = curve
        for k in curve.keys:
            rows[bone_path]["times"][round(k.time, 7)] = True
    items = []
    for bone_path in order:
        row = rows[bone_path]
        times = sorted(row["times"])
        keys = []
        for t in times:
            value = {}
            in_slope = {}
            out_slope = {}
            for c, curve in row["curves"].items():
                if curve is None:
                    value[c] = 0.0
                    in_slope[c] = 0.0
                    out_slope[c] = 0.0
                    continue
                k = curve.find_key(t)
                value[c] = k.value if k is not None else 0.0
                if k is not None:
                    idx = curve.keys.index(k)
                    prev = curve.keys[idx - 1] if idx > 0 else None
                    nxt = curve.keys[idx + 1] if idx + 1 < len(curve.keys) else None
                    sl, sr = _slopes(k, prev, nxt)
                    in_slope[c] = sl
                    out_slope[c] = sr
                else:
                    in_slope[c] = 0.0
                    out_slope[c] = 0.0
            keys.append({"time": t, "value": value, "inSlope": in_slope, "outSlope": out_slope})
        items.append({"path": bone_path, "keys": keys})
    return [it for it in items if it["keys"]]


def _rotation_block(clip: AnimationClip) -> str:
    items = []
    for (bone_path, prop), curve in clip.bone_rotation_curves.items():
        keys = []
        for k in curve.keys:
            v = k.value
            keys.append({
                "time": k.time,
                "value": {"x": v[0], "y": v[1], "z": v[2], "w": v[3]},
                "inSlope": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0},
                "outSlope": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0},
            })
        if not keys:
            continue
        items.append((bone_path, keys))
    block = ""
    for bone_path, keys in items:
        block += (
            f"{_INDENT}- curve:\n"
            f"{_INDENT * 4}serializedVersion: 2\n"
            f"{_INDENT * 4}m_Curve:\n"
        )
        for kd in keys:
            block += _key_vector(kd, "xyzw", sub_indent=6)
        block += f"{_INDENT}  path: {bone_path}\n"
    return block


def _float_block(clip: AnimationClip) -> str:
    block = ""
    used_vector = set()
    for base in ("Transform/local_position", "Transform/local_scale", "Transform/local_euler_angles"):
        for prop in clip.curves:
            if prop.startswith(base + "."):
                used_vector.add(prop)
    for prop, curve in clip.curves.items():
        if prop in used_vector:
            continue
        if prop in clip.rotation_curves:
            continue
        if any(prop.startswith(b + ".") for b in
               ("Transform/local_position", "Transform/local_scale",
                "Transform/local_euler_angles")):
            continue
        annotation = clip.annotations.get(prop, {})
        bone_path = clip.curve_targets.get(prop, "") or annotation.get("bone_path", "")
        class_id = int(annotation.get("class_id") or 0)
        keys = []
        for i, k in enumerate(curve.keys):
            idx = i
            prev = curve.keys[idx - 1] if idx > 0 else None
            nxt = curve.keys[idx + 1] if idx + 1 < len(curve.keys) else None
            sl, sr = _slopes(k, prev, nxt)
            keys.append({
                "time": k.time,
                "value": k.value,
                "inSlope": sl,
                "outSlope": sr,
            })
        if not keys:
            continue
        block += (
            f"{_INDENT}- serializedVersion: 2\n"
            f"{_INDENT * 2}curve:\n"
            f"{_INDENT * 4}serializedVersion: 2\n"
            f"{_INDENT * 4}m_Curve:\n"
        )
        for kd in keys:
            block += _key_scalar(kd, sub_indent=6)
        block += (
            f"{_INDENT}  path: {bone_path}\n"
            f"{_INDENT}  classID: {class_id}\n"
            f"{_INDENT}  script: {{fileID: 0}}\n"
        )
    return block


def clip_to_unity_yaml(clip: AnimationClip) -> str:
    position_items = _group_vector_curves(clip, "Transform/local_position")
    scale_items = _group_vector_curves(clip, "Transform/local_scale")
    euler_items = _group_vector_curves(clip, "Transform/local_euler_angles")

    def render_vector(items) -> str:
        if not items:
            return "[]\n"
        out = "\n"
        for it in items:
            out += f"{_INDENT}- curve:\n"
            out += f"{_INDENT * 4}serializedVersion: 2\n"
            out += f"{_INDENT * 4}m_Curve:\n"
            for kd in it["keys"]:
                out += _key_vector(kd, "xyz", sub_indent=6)
            out += f"{_INDENT}  path: {it['path']}\n"
        return out

    rotation = _rotation_block(clip) or "[]\n"
    text = "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
    text += "--- !u!74 &7400000\nAnimationClip:\n"
    text += (
        f"{_INDENT}m_ObjectHideFlags: 0\n"
        f"{_INDENT}m_CorrespondingSourceObject: {{fileID: 0}}\n"
        f"{_INDENT}m_PrefabInstance: {{fileID: 0}}\n"
        f"{_INDENT}m_PrefabAsset: {{fileID: 0}}\n"
        f"{_INDENT}m_Name: {clip.name}\n"
        f"{_INDENT}serializedVersion: 6\n"
        f"{_INDENT}m_Legacy: 0\n"
        f"{_INDENT}m_Compressed: 0\n"
        f"{_INDENT}m_UseHighQualityCurve: 1\n"
        f"{_INDENT}m_RotationCurves: {rotation}"
        f"{_INDENT}m_CompressedRotationCurves: []\n"
        f"{_INDENT}m_EulerCurves: {render_vector(euler_items)}"
        f"{_INDENT}m_PositionCurves: {render_vector(position_items)}"
        f"{_INDENT}m_ScaleCurves: {render_vector(scale_items)}"
        f"{_INDENT}m_FloatCurves: {_float_block(clip) or '[]'}\n"
        f"{_INDENT}m_PPtrCurves: []\n"
        f"{_INDENT}m_AnimationClipSettings:\n"
        f"{_INDENT * 2}m_AdditiveReferencePoseClip: {{fileID: 0}}\n"
        f"{_INDENT * 2}m_AdditiveReferencePoseTime: 0\n"
        f"{_INDENT * 2}m_StartTime: 0\n"
        f"{_INDENT * 2}m_StopTime: {_f(clip.length)}\n"
        f"{_INDENT * 2}m_OrientationOffsetY: 0\n"
        f"{_INDENT * 2}m_Level: 0\n"
        f"{_INDENT * 2}m_CycleOffset: 0\n"
        f"{_INDENT * 2}m_HasAdditiveReferencePose: 0\n"
        f"{_INDENT * 2}m_LoopTime: {1 if clip.loop else 0}\n"
        f"{_INDENT * 2}m_LoopBlend: 0\n"
        f"{_INDENT * 2}m_LoopBlendOrientation: 0\n"
        f"{_INDENT * 2}m_LoopBlendPositionY: 0\n"
        f"{_INDENT * 2}m_LoopBlendPositionXZ: 0\n"
        f"{_INDENT * 2}m_KeepOriginalOrientation: 0\n"
        f"{_INDENT * 2}m_KeepOriginalPositionY: 1\n"
        f"{_INDENT * 2}m_KeepOriginalPositionXZ: 0\n"
        f"{_INDENT * 2}m_HeightFromFeet: 0\n"
        f"{_INDENT * 2}m_Mirror: 0\n"
    )
    if clip.events:
        text += f"{_INDENT}m_Events:\n"
        for e in clip.events:
            text += (
                f"{_INDENT * 2}- time: {_f(e.time)}\n"
                f"{_INDENT * 4}functionName: {e.function_name}\n"
                f"{_INDENT * 4}data: {e.string_parameter}\n"
                f"{_INDENT * 4}objectReferenceParameter: {{fileID: 0}}\n"
                f"{_INDENT * 4}floatParameter: {_f(e.float_parameter)}\n"
                f"{_INDENT * 4}intParameter: {e.int_parameter}\n"
                f"{_INDENT * 4}messageOptions: 0\n"
            )
    else:
        text += f"{_INDENT}m_Events: []\n"
    return text
