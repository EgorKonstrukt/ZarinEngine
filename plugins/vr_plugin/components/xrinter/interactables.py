# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField


@ComponentRegistry.register
class XRBaseInteractable(Component):
    _icon = "XRInteractable.png"
    _gizmo_icon_color = (160, 255, 180)
    _gizmo_icon_label = "X"
    _show_gizmo_icon = True

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "XR Base Interactable", FieldType.HEADER),
            InspectorField("interaction_layers", "Interaction Layers", FieldType.STRING),
            InspectorField("select_on_hover", "Select Mode", FieldType.ENUM, enum_options=["Toggle", "Hold"]),
        ]

    def __init__(self):
        super().__init__()
        self.interaction_layers: str = "Default"
        self.select_on_hover: str = "Hold"
        self._hovered_by = None
        self._selected_by = None

    def on_update(self, dt: float):
        return

    def on_hover_entered(self, interactor):
        pass

    def on_hover_exited(self, interactor):
        pass

    def on_select_entered(self, interactor):
        pass

    def on_select_exited(self, interactor):
        pass

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"interaction_layers": self.interaction_layers, "select_on_hover": self.select_on_hover})
        return d

    @classmethod
    def deserialize(cls, data: dict) -> XRBaseInteractable:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.interaction_layers = data.get("interaction_layers", "Default")
        c.select_on_hover = data.get("select_on_hover", "Hold")
        return c


@ComponentRegistry.register
class XRGrabInteractable(XRBaseInteractable):
    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        fields = XRBaseInteractable._inspector_fields()
        fields.append(InspectorField("", "XR Grab Interactable", FieldType.HEADER))
        fields.append(InspectorField("attach_to_point", "Attach To Controller", FieldType.BOOL))
        fields.append(InspectorField("throw_smoothing", "Throw Smoothing", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.05, decimals=2))
        return fields

    def __init__(self):
        super().__init__()
        self.attach_to_point: bool = True
        self.throw_smoothing: float = 0.5
        self._original_parent = None
        self._original_local_pos = None
        self._original_local_rot = None
        self._vel_samples = []

    def on_select_entered(self, interactor):
        try:
            ent = self.entity
            tr = ent.transform
            self._original_parent = ent.parent
            self._original_local_pos = tr.local_position
            self._original_local_rot = tr.local_rotation
            if self.attach_to_point and interactor.entity is not None:
                ent.set_parent(interactor.entity, preserve_world=True)
                ent._is_static = False
            self._vel_samples = []
        except Exception:
            pass

    def on_select_exited(self, interactor):
        try:
            ent = self.entity
            if self._original_parent is not None:
                ent.set_parent(self._original_parent, preserve_world=True)
            elif ent.parent is not None:
                ent.set_parent(None, preserve_world=True)
            if self._original_local_pos is not None:
                ent.transform.local_position = self._original_local_pos
            if self._original_local_rot is not None:
                ent.transform.local_rotation = self._original_local_rot
        except Exception:
            pass

    @classmethod
    def deserialize(cls, data: dict) -> XRGrabInteractable:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.interaction_layers = data.get("interaction_layers", "Default")
        c.select_on_hover = data.get("select_on_hover", "Hold")
        c.attach_to_point = bool(data.get("attach_to_point", True))
        c.throw_smoothing = float(data.get("throw_smoothing", 0.5))
        return c
