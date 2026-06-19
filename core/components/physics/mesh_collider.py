from __future__ import annotations
from enum import Enum
from core.math3d import Vec3
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField


class CollisionMode(Enum):
    AUTO = "auto"
    MESH = "mesh"
    CONVEX_HULL = "convex_hull"
    BOX = "box"
    SPHERE = "sphere"


@ComponentRegistry.register
class MeshCollider(Component):
    _icon = "MeshCollider.png"
    _gizmo_icon_color = (200, 80, 80)
    _gizmo_icon_label = "C"
    _show_gizmo_icon: bool = False

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("mesh_path", "Mesh", FieldType.RESOURCE_PATH, file_filter="Collision Meshes (*.obj *.stl *.gltf *.glb)"),
            InspectorField("collision_mode", "Collision Mode", FieldType.ENUM, enum_class=CollisionMode),
            InspectorField("max_vertices", "Max Vertices", FieldType.INT, min_val=0, max_val=100000, step=100, decimals=0),
            InspectorField("is_trigger", "Is Trigger", FieldType.BOOL),
            InspectorField("layer", "Layer", FieldType.LAYER),
            InspectorField("mask", "Collision Mask", FieldType.LAYER_MASK),
        ]

    def __init__(self):
        super().__init__()
        self.layer: int = 0
        self.mask: int = 0xFFFF
        self.center: Vec3 = Vec3.zero()
        self.mesh_path: str = ""
        self.collision_mode: CollisionMode = CollisionMode.AUTO
        self.max_vertices: int = 2000
        self.is_trigger: bool = False
        self.material_friction: float = 0.6
        self.material_bounciness: float = 0.0

    @property
    def scaled_center(self) -> Vec3:
        tr = self.transform
        s = tr.local_scale if tr else Vec3.one()
        c = self.center if isinstance(self.center, Vec3) else Vec3(*self.center)
        return Vec3(c.x * s.x, c.y * s.y, c.z * s.z)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "center": self.center.to_list(), "mesh_path": self.mesh_path,
            "collision_mode": self.collision_mode.value,
            "max_vertices": self.max_vertices,
            "is_trigger": self.is_trigger,
            "friction": self.material_friction,
            "bounciness": self.material_bounciness,
            "layer": self.layer, "mask": self.mask,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> MeshCollider:
        mc = cls()
        mc.enabled = data.get("enabled", True)
        mc.center = Vec3(*data.get("center", [0, 0, 0]))
        mc.mesh_path = data.get("mesh_path", "")
        mc.collision_mode = CollisionMode(data.get("collision_mode", "auto"))
        mc.max_vertices = data.get("max_vertices", 2000)
        mc.is_trigger = data.get("is_trigger", False)
        mc.material_friction = data.get("friction", 0.6)
        mc.material_bounciness = data.get("bounciness", 0.0)
        mc.layer = data.get("layer", 0)
        mc.mask = data.get("mask", 0xFFFF)
        return mc
