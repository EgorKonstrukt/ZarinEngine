# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from enum import Enum
from typing import Optional
from core.ecs import Component
from core.maths.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField


class ShapeType(Enum):
    CONE = "cone"
    SPHERE = "sphere"
    HEMISPHERE = "hemisphere"
    BOX = "box"
    CIRCLE = "circle"

class ParticleRenderMode(Enum):
    BILLBOARD = "billboard"
    STRETCHED_BILLBOARD = "stretched_billboard"

class SimulationSpace(Enum):
    LOCAL = "local"
    WORLD = "world"

class ParticleSortMode(Enum):
    NONE = "none"
    BY_DISTANCE = "by_distance"
    BY_AGE = "by_age"

PARTICLE_DTYPE = np.dtype([
    ('position', np.float32, 4),
    ('velocity', np.float32, 4),
    ('color', np.float32, 4),
    ('meta', np.float32, 4),
    ('lifetime', np.float32, 4),
    ('start_color', np.float32, 4),
    ('start_meta', np.float32, 4),
])


class ParticleSystemBase(Component):
    _icon = "ParticleSystem.png"
    _allow_multiple = False
    _gizmo_icon_color = (255, 160, 50)
    _gizmo_icon_label = "P"
    _gizmo_cache_attrs = ("shape_type", "shape_radius", "shape_arc", "shape_angle",
                          "shape_length", "shape_box")
    _gizmo_pass = "particle"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Emission", FieldType.HEADER),
            InspectorField("duration", "Duration", FieldType.FLOAT, min_val=0.01, max_val=300.0, step=0.1, decimals=2),
            InspectorField("looping", "Looping", FieldType.BOOL),
            InspectorField("prewarm", "Prewarm", FieldType.BOOL),
            InspectorField("start_delay", "Start Delay", FieldType.FLOAT, min_val=0.0, max_val=60.0, step=0.1, decimals=2),
            InspectorField("", "Start", FieldType.HEADER),
            InspectorField("start_lifetime", "Start Lifetime", FieldType.FLOAT, min_val=0.01, max_val=300.0, step=0.1, decimals=2),
            InspectorField("start_lifetime_min", "Lifetime Min", FieldType.FLOAT, min_val=0.0, max_val=300.0, step=0.1, decimals=2),
            InspectorField("start_lifetime_max", "Lifetime Max", FieldType.FLOAT, min_val=0.0, max_val=300.0, step=0.1, decimals=2),
            InspectorField("start_speed", "Start Speed", FieldType.FLOAT, min_val=0.0, max_val=1000.0, step=0.1, decimals=2),
            InspectorField("start_speed_min", "Speed Min", FieldType.FLOAT, min_val=0.0, max_val=1000.0, step=0.1, decimals=2),
            InspectorField("start_speed_max", "Speed Max", FieldType.FLOAT, min_val=0.0, max_val=1000.0, step=0.1, decimals=2),
            InspectorField("start_size", "Start Size", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.01, decimals=3),
            InspectorField("start_size_min", "Size Min", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.01, decimals=3),
            InspectorField("start_size_max", "Size Max", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.01, decimals=3),
            InspectorField("start_rotation", "Start Rotation", FieldType.FLOAT, min_val=0.0, max_val=360.0, step=1.0, decimals=1),
            InspectorField("flip_rotation", "Flip Rotation", FieldType.FLOAT, min_val=0.0, max_val=360.0, step=1.0, decimals=1),
            InspectorField("inherit_velocity", "Inherit Velocity", FieldType.FLOAT, min_val=0.0, max_val=1.0, step=0.01, decimals=2),
            InspectorField("gravity_modifier", "Gravity Modifier", FieldType.FLOAT, min_val=0.0, max_val=10.0, step=0.01, decimals=3),
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("simulation_space", "Simulation Space", FieldType.ENUM, enum_class=SimulationSpace),
            InspectorField("max_particles", "Max Particles", FieldType.INT, min_val=1, max_val=10000000, step=1, decimals=0),
            InspectorField("rate_over_time", "Rate over Time", FieldType.FLOAT, min_val=0.0, max_val=100000.0, step=1.0, decimals=1),
            InspectorField("shape_type", "Shape", FieldType.ENUM, enum_class=ShapeType),
            InspectorField("shape_angle", "Shape Angle", FieldType.FLOAT, min_val=0.0, max_val=360.0, step=1.0, decimals=1),
            InspectorField("shape_radius", "Shape Radius", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.1, decimals=2),
            InspectorField("", "Rendering", FieldType.HEADER),
            InspectorField("render_mode", "Render Mode", FieldType.ENUM, enum_class=ParticleRenderMode),
            InspectorField("material_path", "Material", FieldType.RESOURCE_PATH, file_filter="Material (*.mat)"),
            InspectorField("sort_mode", "Sort Mode", FieldType.ENUM, enum_class=ParticleSortMode),
            InspectorField("sorting_fudge", "Sorting Fudge", FieldType.FLOAT, min_val=-100.0, max_val=100.0, step=0.1, decimals=2),
            InspectorField("", "Flipbook", FieldType.HEADER),
            InspectorField("flipbook_columns", "Flipbook Columns", FieldType.INT, min_val=1, max_val=100, step=1, decimals=0),
            InspectorField("flipbook_rows", "Flipbook Rows", FieldType.INT, min_val=1, max_val=100, step=1, decimals=0),
            InspectorField("flipbook_fps", "Flipbook FPS", FieldType.FLOAT, min_val=0.0, max_val=120.0, step=1.0, decimals=1),
            InspectorField("", "General", FieldType.HEADER),
            InspectorField("size_over_lifetime_enabled", "Size over Lifetime", FieldType.BOOL),
            InspectorField("size_over_lifetime_curve", "Size Curve", FieldType.CURVE, toggle_field="size_over_lifetime_enabled"),
            InspectorField("color_over_lifetime_enabled", "Color over Lifetime", FieldType.BOOL),
            InspectorField("color_over_lifetime_gradient", "Color Gradient", FieldType.GRADIENT, toggle_field="color_over_lifetime_enabled"),
            InspectorField("rotation_over_lifetime_enabled", "Rotation over Lifetime", FieldType.BOOL),
            InspectorField("velocity_over_lifetime_enabled", "Velocity over Lifetime", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.duration: float = 5.0
        self.looping: bool = True
        self.prewarm: bool = False
        self.start_delay: float = 0.0
        self.start_lifetime: float = 5.0
        self.start_lifetime_min: float = 0.0
        self.start_lifetime_max: float = 0.0
        self.start_speed: float = 5.0
        self.start_speed_min: float = 0.0
        self.start_speed_max: float = 0.0
        self.start_size: float = 1.0
        self.start_size_min: float = 0.0
        self.start_size_max: float = 0.0
        self.start_color: list[float] = None
        self.start_rotation: float = 0.0
        self.flip_rotation: float = 0.0
        self.inherit_velocity: float = 0.0
        self.gravity_modifier: float = 0.0
        self.simulation_space: SimulationSpace = SimulationSpace.LOCAL
        self.max_particles: int = 1000
        self.rate_over_time: float = 10.0
        self.rate_over_distance: float = 0.0
        self.bursts: list[dict] = None
        self.shape_type: ShapeType = ShapeType.CONE
        self.shape_angle: float = 25.0
        self.shape_radius: float = 1.0
        self.shape_length: float = 5.0
        self.shape_box: list[float] = None
        self.shape_arc: float = 360.0
        self.render_mode: ParticleRenderMode = ParticleRenderMode.BILLBOARD
        self.material_path: str = ""
        self.texture_path: str = ""
        self.sort_mode: ParticleSortMode = ParticleSortMode.NONE
        self.sorting_fudge: float = 0.0
        self.flipbook_columns: int = 1
        self.flipbook_rows: int = 1
        self.flipbook_fps: float = 0.0
        self.size_over_lifetime_enabled: bool = False
        self.size_over_lifetime_curve: list[list[float]] = None
        self.size_over_lifetime_curve_x: list[list[float]] = None
        self.size_over_lifetime_curve_y: list[list[float]] = None
        self.color_over_lifetime_enabled: bool = False
        self.color_over_lifetime_gradient: dict = None
        self.rotation_over_lifetime_enabled: bool = False
        self.rotation_over_lifetime_angular_velocity: float = 0.0
        self.velocity_over_lifetime_enabled: bool = False
        self.velocity_over_lifetime_linear: list[float] = None
        self.velocity_over_lifetime_orbital: list[float] = None
        self._time: float = 0.0
        self._particle_count: int = 0
        self._alive_count: int = 0
        self._emit_accum: float = 0.0
        self._distance_accum: float = 0.0
        self._prewarmed: bool = False
        self._started: bool = False
        self._stopped: bool = False
        self._burst_index: int = 0
        self._prev_position: Vec3 = None
        self._last_delta_pos: Vec3 = Vec3.zero()
        self._emitter_velocity: np.ndarray = None
        self._local_to_world: np.ndarray = None
        self._local_position: np.ndarray = None
        self._particles: Optional[np.ndarray] = None
        self._free_stack: Optional[np.ndarray] = None
        self._free_top: int = 0
        self._last_dt: float = 0.016
        self._alive_mask: Optional[np.ndarray] = None
        self._start_color_arr: Optional[np.ndarray] = None
        self._curve_cache_x: Optional[tuple] = None
        self._curve_cache_y: Optional[tuple] = None
        self._gradient_cache: Optional[tuple] = None

    def _invalidate_caches(self):
        self._curve_cache_x = None
        self._curve_cache_y = None
        self._gradient_cache = None
        self._start_color_arr = None

    _INITIAL_CAPACITY = 1024

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "duration": self.duration,
            "looping": self.looping,
            "prewarm": self.prewarm,
            "start_delay": self.start_delay,
            "start_lifetime": self.start_lifetime,
            "start_lifetime_min": self.start_lifetime_min,
            "start_lifetime_max": self.start_lifetime_max,
            "start_speed": self.start_speed,
            "start_speed_min": self.start_speed_min,
            "start_speed_max": self.start_speed_max,
            "start_size": self.start_size,
            "start_size_min": self.start_size_min,
            "start_size_max": self.start_size_max,
            "start_color": self.start_color or [1,1,1,1],
            "start_rotation": self.start_rotation,
            "flip_rotation": self.flip_rotation,
            "inherit_velocity": self.inherit_velocity,
            "gravity_modifier": self.gravity_modifier,
            "simulation_space": self.simulation_space.value,
            "max_particles": self.max_particles,
            "rate_over_time": self.rate_over_time,
            "rate_over_distance": self.rate_over_distance,
            "bursts": self.bursts or [],
            "shape_type": self.shape_type.value,
            "shape_angle": self.shape_angle,
            "shape_radius": self.shape_radius,
            "shape_length": self.shape_length,
            "shape_box": self.shape_box or [1,1,1],
            "shape_arc": self.shape_arc,
            "render_mode": self.render_mode.value,
            "material_path": self.material_path,
            "texture_path": self.texture_path,
            "sort_mode": self.sort_mode.value,
            "sorting_fudge": self.sorting_fudge,
            "flipbook_columns": self.flipbook_columns,
            "flipbook_rows": self.flipbook_rows,
            "flipbook_fps": self.flipbook_fps,
            "size_over_lifetime_enabled": self.size_over_lifetime_enabled,
            "size_over_lifetime_curve": self.size_over_lifetime_curve or [[0,1],[1,1]],
            "size_over_lifetime_curve_x": self.size_over_lifetime_curve_x or [[0,1],[1,1]],
            "size_over_lifetime_curve_y": self.size_over_lifetime_curve_y or [[0,1],[1,1]],
            "color_over_lifetime_enabled": self.color_over_lifetime_enabled,
            "color_over_lifetime_gradient": self.color_over_lifetime_gradient if self.color_over_lifetime_gradient is not None else {
                "alpha_keys": [[0, 1], [1, 0]],
                "color_keys": [[0, [1, 1, 1]], [1, [1, 1, 1]]]
            },
            "rotation_over_lifetime_enabled": self.rotation_over_lifetime_enabled,
            "rotation_over_lifetime_angular_velocity": self.rotation_over_lifetime_angular_velocity,
            "velocity_over_lifetime_enabled": self.velocity_over_lifetime_enabled,
            "velocity_over_lifetime_linear": self.velocity_over_lifetime_linear or [0,0,0],
            "velocity_over_lifetime_orbital": self.velocity_over_lifetime_orbital or [0,0,0],
        })
        return d

    @classmethod
    def deserialize(cls, data: dict):
        ps = cls()
        ps.enabled = data.get("enabled", True)
        ps.duration = data.get("duration", 5.0)
        ps.looping = data.get("looping", True)
        ps.prewarm = data.get("prewarm", False)
        ps.start_delay = data.get("start_delay", 0.0)
        ps.start_lifetime = data.get("start_lifetime", 5.0)
        ps.start_lifetime_min = data.get("start_lifetime_min", 0.0)
        ps.start_lifetime_max = data.get("start_lifetime_max", 0.0)
        ps.start_speed = data.get("start_speed", 5.0)
        ps.start_speed_min = data.get("start_speed_min", 0.0)
        ps.start_speed_max = data.get("start_speed_max", 0.0)
        ps.start_size = data.get("start_size", 1.0)
        ps.start_size_min = data.get("start_size_min", 0.0)
        ps.start_size_max = data.get("start_size_max", 0.0)
        ps.start_color = data.get("start_color", [1,1,1,1])
        ps.start_rotation = data.get("start_rotation", 0.0)
        ps.flip_rotation = data.get("flip_rotation", 0.0)
        ps.inherit_velocity = data.get("inherit_velocity", 0.0)
        ps.gravity_modifier = data.get("gravity_modifier", 0.0)
        ps.simulation_space = SimulationSpace(data.get("simulation_space", "local"))
        ps.max_particles = data.get("max_particles", 1000)
        ps.rate_over_time = data.get("rate_over_time", 10.0)
        ps.rate_over_distance = data.get("rate_over_distance", 0.0)
        ps.bursts = data.get("bursts", [])
        ps.shape_type = ShapeType(data.get("shape_type", "cone"))
        ps.shape_angle = data.get("shape_angle", 25.0)
        ps.shape_radius = data.get("shape_radius", 1.0)
        ps.shape_length = data.get("shape_length", 5.0)
        ps.shape_box = data.get("shape_box", [1,1,1])
        ps.shape_arc = data.get("shape_arc", 360.0)
        ps.render_mode = ParticleRenderMode(data.get("render_mode", "billboard"))
        ps.material_path = data.get("material_path", "") or ""
        ps.texture_path = data.get("texture_path", "") or ""
        ps.sort_mode = ParticleSortMode(data.get("sort_mode", "none"))
        ps.sorting_fudge = data.get("sorting_fudge", 0.0)
        ps.flipbook_columns = data.get("flipbook_columns", 1)
        ps.flipbook_rows = data.get("flipbook_rows", 1)
        ps.flipbook_fps = data.get("flipbook_fps", 0.0)
        ps.size_over_lifetime_enabled = data.get("size_over_lifetime_enabled", False)
        ps.size_over_lifetime_curve = data.get("size_over_lifetime_curve", [[0,1],[1,1]])
        ps.size_over_lifetime_curve_x = data.get("size_over_lifetime_curve_x", None)
        ps.size_over_lifetime_curve_y = data.get("size_over_lifetime_curve_y", None)
        ps.color_over_lifetime_enabled = data.get("color_over_lifetime_enabled", False)
        ps.color_over_lifetime_gradient = data.get("color_over_lifetime_gradient", {
            "alpha_keys": [[0,1],[1,0]],
            "color_keys": [[0,[1,1,1]],[1,[1,1,1]]]
        })
        ps.rotation_over_lifetime_enabled = data.get("rotation_over_lifetime_enabled", False)
        ps.rotation_over_lifetime_angular_velocity = data.get("rotation_over_lifetime_angular_velocity", 0.0)
        ps.velocity_over_lifetime_enabled = data.get("velocity_over_lifetime_enabled", False)
        ps.velocity_over_lifetime_linear = data.get("velocity_over_lifetime_linear", [0,0,0])
        ps.velocity_over_lifetime_orbital = data.get("velocity_over_lifetime_orbital", [0,0,0])
        return ps
