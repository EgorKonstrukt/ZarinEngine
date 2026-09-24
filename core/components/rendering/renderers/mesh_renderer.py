# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.ecs.ecs import Component, ComponentRegistry
from core.maths.math3d import Vec2
from core.components.inspector_meta import FieldType, InspectorField, ListElementField
@ComponentRegistry.register
class MeshRenderer(Component):
    _icon = "MeshRenderer.png"
    _gizmo_icon_color = (160, 160, 160)
    _gizmo_icon_label = "M"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Materials", FieldType.HEADER),
            InspectorField("materials", "Materials", FieldType.LIST, element_fields=[
                ListElementField("path", "Material", FieldType.RESOURCE_PATH, file_filter="Material (*.mat)"),
            ]),
            InspectorField("sprite_texture", "Sprite Texture", FieldType.RESOURCE_PATH, file_filter="Textures (*.png *.jpg *.jpeg *.bmp *.tga)"),
            InspectorField("", "UV", FieldType.HEADER),
            InspectorField("uv_scale", "UV Scale", FieldType.VEC2),
            InspectorField("uv_offset", "UV Offset", FieldType.VEC2),
            InspectorField("uv_scale_by_transform", "UV Scale by Transform", FieldType.BOOL),
            InspectorField("", "Shadows", FieldType.HEADER),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
            InspectorField("receive_shadows", "Receive Shadows", FieldType.BOOL),
            InspectorField("dynamic_reflections", "Dynamic Reflections", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.materials: list[dict] = [{"path": "assets/materials/ProBuilderPrototype.mat"}]
        self.sprite_texture: str = ""
        self.uv_scale: Vec2 = Vec2.one()
        self.uv_offset: Vec2 = Vec2.zero()
        self.uv_scale_by_transform: bool = False
        self.cast_shadows: bool = True
        self.receive_shadows: bool = True
        self.dynamic_reflections: bool = False

    def get_material_path(self, sub_mesh_index: int = 0) -> str:
        if sub_mesh_index < len(self.materials):
            return self.materials[sub_mesh_index].get("path", "")
        if self.materials:
            return self.materials[-1].get("path", "")
        return ""

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"materials": [dict(m) if isinstance(m, dict) else m for m in self.materials],
                  "sprite_texture": self.sprite_texture,
                  "uv_scale": self.uv_scale.to_list(),
                  "uv_offset": self.uv_offset.to_list(),
                  "uv_scale_by_transform": self.uv_scale_by_transform,
                  "cast_shadows": self.cast_shadows, "receive_shadows": self.receive_shadows,
                  "dynamic_reflections": self.dynamic_reflections})
        return d

    @classmethod
    def deserialize(cls, data: dict) -> MeshRenderer:
        mr = cls()
        mr.enabled = data.get("enabled", True)
        raw = data.get("materials")
        if raw:
            mr.materials = raw
        elif "material_path" in data:
            mr.materials = [{"path": data.get("material_path", "")}]
        else:
            mr.materials = [{"path": ""}]
        mr.sprite_texture = data.get("sprite_texture", "") or ""
        mr.uv_scale = Vec2(*data.get("uv_scale", [1, 1]))
        mr.uv_offset = Vec2(*data.get("uv_offset", [0, 0]))
        mr.uv_scale_by_transform = data.get("uv_scale_by_transform", False)
        mr.cast_shadows = data.get("cast_shadows", True)
        mr.receive_shadows = data.get("receive_shadows", True)
        mr.dynamic_reflections = data.get("dynamic_reflections", False)
        return mr
