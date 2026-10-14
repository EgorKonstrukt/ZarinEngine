# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from plugins.vr_plugin.components.xr_haptics import XRHaptics
from plugins.vr_plugin.components.xrinter.interactors import XRBaseInteractor, XRRayInteractor, XRDirectInteractor
from plugins.vr_plugin.components.xrinter.interactables import XRBaseInteractable, XRGrabInteractable


def _layer_match(a: str, b: str) -> bool:
    if not a or a == "Default" or not b or b == "Default":
        return True
    return a == b


def update_interaction(scene, dt: float, manager=None):
    if scene is None:
        return
    interactors = []
    interactables = []
    for e in scene.get_all_entities():
        if not e.active:
            continue
        inter = e.get_component(XRBaseInteractor)
        if inter is not None and inter.enabled:
            interactors.append(inter)
        inter2 = e.get_component(XRGrabInteractable)
        if inter2 is None:
            inter2 = e.get_component(XRBaseInteractable)
        if inter2 is not None and inter2.enabled:
            interactables.append(inter2)
    try:
        from plugins.vr_plugin import vr_core
    except Exception:
        return
    max_dist = manager.max_raycast_distance if manager is not None else 50.0
    for inter in interactors:
        idx = inter.controller_index()
        if inter.select_on == "Trigger":
            pressed = vr_core._vr_state.controllers[idx].trigger
            threshold = 0.6
        else:
            pressed = vr_core._vr_state.controllers[idx].grip
            threshold = 0.5
        is_pressed = pressed > threshold
        prev = getattr(inter, "_was_pressed", False)
        just_pressed = is_pressed and not prev
        just_released = (not is_pressed) and prev
        inter._was_pressed = is_pressed
        target = _resolve_target(inter, interactables, vr_core, max_dist)
        if target is not None and target is not inter._hover:
            if inter._hover is not None:
                inter._hover.on_hover_exited(inter)
                inter._hover._hovered_by = None
            inter._hover = target
            target._hovered_by = inter
            target.on_hover_entered(inter)
            if inter.enable_haptic_on_hover:
                inter.entity.get_component(XRHaptics) if inter.entity else None
                _haptic(inter, 0.3, 0.04)
        elif target is None and inter._hover is not None:
            inter._hover.on_hover_exited(inter)
            inter._hover._hovered_by = None
            inter._hover = None
        if just_pressed and target is not None:
            inter._selected = target
            target._selected_by = inter
            target.on_select_entered(inter)
            _haptic(inter, 1.0, 0.06)
        if just_released and inter._selected is not None:
            inter._selected.on_select_exited(inter)
            inter._selected._selected_by = None
            inter._selected = None


def _haptic(inter, amp, dur):
    try:
        from plugins.vr_plugin.components.xr_haptics import XRHaptics
        hap = inter.entity.get_component(XRHaptics) if inter.entity else None
        if hap is not None:
            hap.SendHapticImpulse(amplitude=amp, duration=dur)
        else:
            from plugins.vr_plugin import vr_core
            vr_core.trigger_haptic(inter.controller_index(), amplitude=amp, duration_s=dur)
    except Exception:
        pass


def _resolve_target(inter, interactables, vr_core, max_dist):
    candidates = [it for it in interactables if _layer_match(inter.interaction_layers, it.interaction_layers)]
    if isinstance(inter, XRRayInteractor):
        ray = inter.get_ray()
        if ray is None:
            return None
        origin, fwd = ray
        ent, hit, dist = vr_core.raycast_scene(origin, fwd, max_dist)
        if ent is not None:
            for it in candidates:
                if it.entity is ent:
                    return it
        return None
    pose = inter.get_pose()
    if pose is None:
        return None
    pos = pose[0]
    radius = getattr(inter, "reach_radius", 0.15) if isinstance(inter, XRDirectInteractor) else getattr(inter, "poke_radius", 0.05)
    best = None
    best_d = float("inf")
    for it in candidates:
        tr = it.entity.transform if it.entity else None
        if tr is None:
            continue
        p = tr.position
        d = math.sqrt((p.x-pos[0])**2 + (p.y-pos[1])**2 + (p.z-pos[2])**2)
        if d < radius and d < best_d:
            best_d = d
            best = it
    return best
