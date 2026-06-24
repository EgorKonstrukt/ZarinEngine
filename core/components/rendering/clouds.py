from __future__ import annotations
import time
import numpy as np
import moderngl
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.math3d import Mat4
from core.components.lighting.light import Light


@ComponentRegistry.register
class Cloud(Component):
    _icon = "Cloud.png"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("material_path", "Cloud Material", FieldType.RESOURCE_PATH, file_filter="Shader (*.shader)"),
            InspectorField("coverage", "Coverage", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
            InspectorField("density", "Density", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.01, decimals=2),
            InspectorField("speed", "Wind Speed", FieldType.FLOAT, min_val=0.0, max_val=5.0, step=0.01, decimals=3),
            InspectorField("height", "Height", FieldType.FLOAT, min_val=0.0, max_val=500.0, step=1.0, decimals=1),
            InspectorField("thickness", "Thickness", FieldType.FLOAT, min_val=0.0, max_val=200.0, step=1.0, decimals=1),
            InspectorField("scale", "Noise Scale", FieldType.FLOAT, min_val=0.001, max_val=1.0, step=0.001, decimals=3),
            InspectorField("opacity", "Opacity", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
        ]

    def __init__(self):
        super().__init__()
        self.material_path: str = "core/shaders/Clouds.shader"
        self.coverage: float = 0.5
        self.density: float = 1.0
        self.speed: float = 0.1
        self.height: float = 50.0
        self.thickness: float = 20.0
        self.scale: float = 0.02
        self.opacity: float = 0.9

    def render_clouds(self, ctx, shaders, view_mat, proj_mat, dir_light, cam_pos, quad_mesh):
        cloud_prog = shaders.get_or_compile(self.material_path) if shaders else None
        if not cloud_prog:
            return
        if dir_light:
            dl, dt = dir_light
            sun_dir_obj = -dt.forward
            if "_SunDirection" in cloud_prog:
                cloud_prog["_SunDirection"].write(np.array([sun_dir_obj.x, sun_dir_obj.y, sun_dir_obj.z], dtype=np.float32).tobytes())
            if "_SunColor" in cloud_prog:
                if dl.procedural_sky_lighting:
                    sc, si = Light.compute_sun_light(-dt.forward)
                    cloud_prog["_SunColor"].write(np.array(sc, dtype=np.float32).tobytes())
                    if "_SunIntensity" in cloud_prog:
                        cloud_prog["_SunIntensity"].value = si
                else:
                    cloud_prog["_SunColor"].write(np.array(dl.color, dtype=np.float32).tobytes())
                    if "_SunIntensity" in cloud_prog:
                        cloud_prog["_SunIntensity"].value = dl.intensity
        if "u_time" in cloud_prog:
            cloud_prog["u_time"].value = time.time()
        if "u_cam_pos" in cloud_prog:
            cloud_prog["u_cam_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        vp = proj_mat * view_mat
        inv_vp = vp.inverted()
        if "u_inv_view_proj" in cloud_prog:
            cloud_prog["u_inv_view_proj"].write(inv_vp.to_f32().tobytes())
        for prop_name in ("_Coverage", "_Density", "_Speed", "_Height", "_Thickness", "_Scale", "_Opacity"):
            if prop_name in cloud_prog:
                val = getattr(self, prop_name.lower().lstrip("_"))
                cloud_prog[prop_name].value = val
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        ctx.disable(moderngl.CULL_FACE)
        ctx.disable(moderngl.DEPTH_TEST)
        quad_mesh.render(cloud_prog)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        ctx.disable(moderngl.BLEND)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "material_path": self.material_path,
            "coverage": self.coverage,
            "density": self.density,
            "speed": self.speed,
            "height": self.height,
            "thickness": self.thickness,
            "scale": self.scale,
            "opacity": self.opacity,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> Cloud:
        c = cls()
        c.enabled = data.get("enabled", True)
        c.material_path = data.get("material_path", "core/shaders/Clouds.shader")
        c.coverage = data.get("coverage", 0.5)
        c.density = data.get("density", 1.0)
        c.speed = data.get("speed", 0.1)
        c.height = data.get("height", 50.0)
        c.thickness = data.get("thickness", 20.0)
        c.scale = data.get("scale", 0.02)
        c.opacity = data.get("opacity", 0.9)
        return c
