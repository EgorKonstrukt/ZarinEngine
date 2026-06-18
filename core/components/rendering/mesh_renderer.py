from __future__ import annotations
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
@ComponentRegistry.register
class MeshRenderer(Component):
    _icon = "MeshRenderer.png"
    _gizmo_icon_color = (160, 160, 160)
    _gizmo_icon_label = "M"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("material_path", "Material", FieldType.RESOURCE_PATH, file_filter="Material (*.mat)"),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
            InspectorField("receive_shadows", "Receive Shadows", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.material_path: str = ""
        self.cast_shadows: bool = True
        self.receive_shadows: bool = True
    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"material_path": self.material_path, "cast_shadows": self.cast_shadows, "receive_shadows": self.receive_shadows})
        return d
    @classmethod
    def deserialize(cls, data: dict) -> MeshRenderer:
        mr = cls()
        mr.enabled = data.get("enabled", True)
        mr.material_path = data.get("material_path", "")
        mr.cast_shadows = data.get("cast_shadows", True)
        mr.receive_shadows = data.get("receive_shadows", True)
        return mr
