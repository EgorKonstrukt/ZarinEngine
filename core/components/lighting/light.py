from __future__ import annotations
from enum import Enum
import math
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.math3d import Vec3
class LightType(Enum):
    DIRECTIONAL = "directional"
    POINT = "point"
    SPOT = "spot"
@ComponentRegistry.register
class Light(Component):
    _icon = "Light.png"
    _gizmo_icon_color = (255, 220, 50)
    _gizmo_icon_label = "L"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("light_type", "Type", FieldType.ENUM, enum_class=LightType),
            InspectorField("procedural_sky_lighting", "Procedural Sky Lighting", FieldType.BOOL),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("intensity", "Intensity", FieldType.FLOAT, min_val=0.0, max_val=1000.0, step=0.1, decimals=3),
            InspectorField("range", "Range", FieldType.FLOAT, min_val=0.0, max_val=10000.0, step=0.5, decimals=2),
            InspectorField("spot_angle", "Spot Angle", FieldType.FLOAT, min_val=1.0, max_val=179.0, step=1.0, decimals=1),
            InspectorField("cast_shadows", "Cast Shadows", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.light_type: LightType = LightType.DIRECTIONAL
        self.color: list[float] = [1.0, 1.0, 1.0]
        self.intensity: float = 1.0
        self.procedural_sky_lighting: bool = False
        self.range: float = 10.0
        self.spot_angle: float = 30.0
        self.spot_inner_angle: float = 20.0
        self.cast_shadows: bool = True

    @staticmethod
    def compute_sun_light(sun_dir: Vec3) -> tuple[list[float], float]:
        elevation = sun_dir.y
        if elevation <= 0.0:
            night = max(0.0, min(1.0, -elevation * 2.0))
            moonlight = 0.02 * (1.0 - night * 0.75)
            return [0.3, 0.35, 0.55], moonlight
        t = elevation
        warm = pow(1.0 - t, 4.0)
        sun_color = [
            1.0,
            0.95 * (1.0 - warm) + 0.3 * warm,
            0.85 * (1.0 - warm) + 0.05 * warm,
        ]
        intensity = 1.2 * (1.0 - math.exp(-t * 4.0))
        return sun_color, intensity

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "light_type": self.light_type.value, "color": self.color,
            "intensity": self.intensity, "range": self.range,
            "spot_angle": self.spot_angle, "spot_inner_angle": self.spot_inner_angle,
            "cast_shadows": self.cast_shadows,
            "procedural_sky_lighting": self.procedural_sky_lighting,
        })
        return d
    @classmethod
    def deserialize(cls, data: dict) -> Light:
        l = cls()
        l.enabled = data.get("enabled", True)
        l.light_type = LightType(data.get("light_type", "directional"))
        l.color = data.get("color", [1.0,1.0,1.0])
        l.intensity = data.get("intensity", 1.0)
        l.procedural_sky_lighting = data.get("procedural_sky_lighting", False)
        l.range = data.get("range", 10.0)
        l.spot_angle = data.get("spot_angle", 30.0)
        l.spot_inner_angle = data.get("spot_inner_angle", 20.0)
        l.cast_shadows = data.get("cast_shadows", True)
        return l
