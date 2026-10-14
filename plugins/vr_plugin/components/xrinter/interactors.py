# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField


@ComponentRegistry.register
class XRInteractionManager(Component):
    _icon = "XRInteractionManager.png"
    _gizmo_icon_color = (200, 160, 255)
    _gizmo_icon_label = "IM"
    _show_gizmo_icon = True

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Interaction", FieldType.HEADER),
            InspectorField("enable_hover", "Enable Hover", FieldType.BOOL),
            InspectorField("max_raycast_distance", "Max Raycast Distance", FieldType.FLOAT, min_val=1.0, max_val=200.0, step=1.0, decimals=1),
        ]

    def __init__(self):
        super().__init__()
        self.enable_hover: bool = True
        self.max_raycast_distance: float = 50.0

    def on_update(self, dt: float):
        return

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"enable_hover": self.enable_hover, "max_raycast_distance": self.max_raycast_distance})
        return d

    @classmethod
    def deserialize(cls, data: dict) -> XRInteractionManager:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.enable_hover = bool(data.get("enable_hover", True))
        c.max_raycast_distance = float(data.get("max_raycast_distance", 50.0))
        return c


@ComponentRegistry.register
class XRBaseInteractor(Component):
    _icon = "XRInteractor.png"
    _gizmo_icon_color = (255, 220, 120)
    _gizmo_icon_label = "I"
    _show_gizmo_icon = True

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "XR Interactor", FieldType.HEADER),
            InspectorField("hand", "Hand", FieldType.ENUM, enum_options=["Left", "Right"]),
            InspectorField("interaction_layers", "Interaction Layers", FieldType.STRING),
            InspectorField("ray_length", "Ray Length", FieldType.FLOAT, min_val=0.5, max_val=100.0, step=0.5, decimals=1),
            InspectorField("select_on", "Select On", FieldType.ENUM, enum_options=["Trigger", "Grip"]),
            InspectorField("enable_haptic_on_hover", "Haptic On Hover", FieldType.BOOL),
        ]

    def __init__(self, hand: str = "Right"):
        super().__init__()
        self.hand: str = hand
        self.interaction_layers: str = "Default"
        self.ray_length: float = 10.0
        self.select_on: str = "Trigger"
        self.enable_haptic_on_hover: bool = True
        self._hover: object = None
        self._selected: object = None

    def on_update(self, dt: float):
        return

    def controller_index(self) -> int:
        return 0 if self.hand == "Left" else 1

    def get_ray(self):
        try:
            from plugins.vr_plugin import vr_core
            return vr_core.get_controller_ray(self.controller_index())
        except Exception:
            return None

    def get_pose(self):
        try:
            from plugins.vr_plugin import vr_core
            idx = self.controller_index()
            p = vr_core.get_controller_world_pos(idx)
            q = vr_core.get_controller_world_quat(idx)
            if p is None:
                return None
            return (p, q)
        except Exception:
            return None

    def gizmo_lines(self):
        try:
            if not self.enabled:
                return []
            ray = self.get_ray()
            if ray is None:
                return []
            origin, fwd = ray
            length = self.ray_length
            end = (origin[0]+fwd[0]*length, origin[1]+fwd[1]*length, origin[2]+fwd[2]*length)
            from core.maths.math3d import Vec3
            col = [0.2, 0.85, 1.0, 1.0] if self.hand == "Left" else [1.0, 0.35, 0.35, 1.0]
            return [(Vec3(*origin), Vec3(*end), col)]
        except Exception:
            return []

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "hand": self.hand, "interaction_layers": self.interaction_layers,
            "ray_length": self.ray_length, "select_on": self.select_on,
            "enable_haptic_on_hover": self.enable_haptic_on_hover,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> XRBaseInteractor:
        c = cls(hand=data.get("hand", "Right"))
        c.enabled = data.get("enabled", True)
        c.interaction_layers = data.get("interaction_layers", "Default")
        c.ray_length = float(data.get("ray_length", 10.0))
        c.select_on = data.get("select_on", "Trigger")
        c.enable_haptic_on_hover = bool(data.get("enable_haptic_on_hover", True))
        return c


@ComponentRegistry.register
class XRRayInteractor(XRBaseInteractor):
    def __init__(self, hand: str = "Right"):
        super().__init__(hand=hand)

    @classmethod
    def deserialize(cls, data: dict) -> XRRayInteractor:
        c = cls(hand=data.get("hand", "Right"))
        c.enabled = data.get("enabled", True)
        c.interaction_layers = data.get("interaction_layers", "Default")
        c.ray_length = float(data.get("ray_length", 10.0))
        c.select_on = data.get("select_on", "Trigger")
        c.enable_haptic_on_hover = bool(data.get("enable_haptic_on_hover", True))
        return c


@ComponentRegistry.register
class XRDirectInteractor(XRBaseInteractor):
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        fields = XRBaseInteractor._inspector_fields()
        fields.append(InspectorField("", "Direct", FieldType.HEADER))
        fields.append(InspectorField("reach_radius", "Reach Radius", FieldType.FLOAT, min_val=0.05, max_val=2.0, step=0.05, decimals=2))
        return fields

    def __init__(self, hand: str = "Right"):
        super().__init__(hand=hand)
        self.reach_radius: float = 0.15

    @classmethod
    def deserialize(cls, data: dict) -> XRDirectInteractor:
        c = cls(hand=data.get("hand", "Right"))
        c.enabled = data.get("enabled", True)
        c.interaction_layers = data.get("interaction_layers", "Default")
        c.ray_length = float(data.get("ray_length", 10.0))
        c.select_on = data.get("select_on", "Trigger")
        c.enable_haptic_on_hover = bool(data.get("enable_haptic_on_hover", True))
        c.reach_radius = float(data.get("reach_radius", 0.15))
        return c


@ComponentRegistry.register
class XRPokeInteractor(XRBaseInteractor):
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        fields = XRBaseInteractor._inspector_fields()
        fields.append(InspectorField("", "XR Poke Interactor", FieldType.HEADER))
        fields.append(InspectorField("poke_radius", "Poke Radius", FieldType.FLOAT, min_val=0.01, max_val=0.5, step=0.01, decimals=2))
        return fields

    def __init__(self, hand: str = "Right"):
        super().__init__(hand=hand)
        self.poke_radius: float = 0.05

    @classmethod
    def deserialize(cls, data: dict) -> XRPokeInteractor:
        c = cls(hand=data.get("hand", "Right"))
        c.enabled = data.get("enabled", True)
        c.interaction_layers = data.get("interaction_layers", "Default")
        c.ray_length = float(data.get("ray_length", 10.0))
        c.select_on = data.get("select_on", "Trigger")
        c.enable_haptic_on_hover = bool(data.get("enable_haptic_on_hover", True))
        c.poke_radius = float(data.get("poke_radius", 0.05))
        return c
