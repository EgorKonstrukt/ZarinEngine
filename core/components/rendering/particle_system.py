from __future__ import annotations
import math
import numpy as np
from enum import Enum
from typing import Optional, Any, Tuple
from core.ecs import Component, ComponentRegistry
from core.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField

_numba_available = False

def njit(*args, **kwargs):
    if args and callable(args[0]):
        return args[0]
    def wrapper(f):
        return f
    return wrapper

prange = range

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
    ('position', np.float32, 3),
    ('velocity', np.float32, 3),
    ('color', np.float32, 4),
    ('size', np.float32, 2),
    ('rotation', np.float32),
    ('lifetime', np.float32),
    ('max_lifetime', np.float32),
    ('alive', np.int32),
    ('start_color', np.float32, 4),
    ('start_size', np.float32, 2),
    ('start_rotation', np.float32),
], align=True)

@njit(cache=True, fastmath=True)
def _sample_curve_numba(keys_t: np.ndarray, keys_v: np.ndarray, t_array: np.ndarray) -> np.ndarray:
    n = len(t_array)
    out = np.empty(n, dtype=np.float32)
    nk = len(keys_t)
    t_min, t_max = keys_t[0], keys_t[-1]
    for i in range(n):
        t = t_array[i]
        if t < t_min: t = t_min
        if t > t_max: t = t_max
        lo, hi = 0, nk - 2
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if keys_t[mid] <= t:
                lo = mid
            else:
                hi = mid - 1
        idx = lo if lo < nk - 1 else nk - 2
        dt = keys_t[idx + 1] - keys_t[idx]
        seg = (t - keys_t[idx]) / (dt if dt > 1e-10 else 1e-10)
        out[i] = keys_v[idx] + (keys_v[idx + 1] - keys_v[idx]) * seg
    return out

@njit(cache=True, fastmath=True)
def _sample_gradient_numba(
    c_keys_t: np.ndarray, c_keys_v: np.ndarray,
    a_keys_t: np.ndarray, a_keys_v: np.ndarray,
    t_array: np.ndarray
) -> np.ndarray:
    n = len(t_array)
    out = np.empty((n, 4), dtype=np.float32)
    nck = len(c_keys_t)
    nak = len(a_keys_t)
    ct_min, ct_max = c_keys_t[0], c_keys_t[-1]
    at_min, at_max = a_keys_t[0], a_keys_t[-1]
    for i in range(n):
        tc = t_array[i]
        if tc < ct_min: tc = ct_min
        if tc > ct_max: tc = ct_max
        lo, hi = 0, nck - 2
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if c_keys_t[mid] <= tc:
                lo = mid
            else:
                hi = mid - 1
        idx = lo if lo < nck - 1 else nck - 2
        dt = c_keys_t[idx + 1] - c_keys_t[idx]
        seg = (tc - c_keys_t[idx]) / (dt if dt > 1e-10 else 1e-10)
        for ch in range(3):
            out[i, ch] = c_keys_v[idx, ch] + (c_keys_v[idx + 1, ch] - c_keys_v[idx, ch]) * seg
        ta = t_array[i]
        if ta < at_min: ta = at_min
        if ta > at_max: ta = at_max
        lo2, hi2 = 0, nak - 2
        while lo2 < hi2:
            mid2 = (lo2 + hi2 + 1) >> 1
            if a_keys_t[mid2] <= ta:
                lo2 = mid2
            else:
                hi2 = mid2 - 1
        idx2 = lo2 if lo2 < nak - 1 else nak - 2
        dt2 = a_keys_t[idx2 + 1] - a_keys_t[idx2]
        seg2 = (ta - a_keys_t[idx2]) / (dt2 if dt2 > 1e-10 else 1e-10)
        out[i, 3] = a_keys_v[idx2] + (a_keys_v[idx2 + 1] - a_keys_v[idx2]) * seg2
    return out

@njit(cache=True, fastmath=True)
def _update_core(
    pos: np.ndarray, vel: np.ndarray, lt: np.ndarray, max_lt: np.ndarray,
    alive: np.ndarray, dt: float, gx: float, gy: float, gz: float,
    dx: float, dy: float, dz: float,
    do_local: bool
) -> np.ndarray:
    n = len(alive)
    died = np.zeros(n, dtype=np.int32)
    for i in range(n):
        if alive[i] != 1:
            continue
        lt[i] -= dt
        if lt[i] <= 0.0:
            alive[i] = 0
            died[i] = 1
            continue
        vel[i, 0] += gx * dt
        vel[i, 1] += gy * dt
        vel[i, 2] += gz * dt
        if do_local:
            pos[i, 0] += vel[i, 0] * dt + dx
            pos[i, 1] += vel[i, 1] * dt + dy
            pos[i, 2] += vel[i, 2] * dt + dz
        else:
            pos[i, 0] += vel[i, 0] * dt
            pos[i, 1] += vel[i, 1] * dt
            pos[i, 2] += vel[i, 2] * dt
    return died

def _build_curve_cache(curve_list) -> Optional[tuple]:
    if not curve_list or len(curve_list) < 2:
        return None
    arr = np.array(curve_list, dtype=np.float32)
    return arr[:, 0], arr[:, 1]

def _build_gradient_cache(grad: dict) -> Optional[tuple]:
    if not grad:
        return None
    ck = grad.get("color_keys", [(0, [1,1,1]), (1, [1,1,1])])
    ak = grad.get("alpha_keys", [(0, 1.0), (1, 1.0)])
    c_t = np.array([k[0] for k in ck], dtype=np.float32)
    c_v = np.array([k[1] for k in ck], dtype=np.float32).reshape(-1, 3)
    a_t = np.array([k[0] for k in ak], dtype=np.float32)
    a_v = np.array([k[1] for k in ak], dtype=np.float32)
    return c_t, c_v, a_t, a_v

@ComponentRegistry.register
class ParticleSystem(Component):
    _icon = "ParticleSystem.png"
    _allow_multiple = False
    _gizmo_icon_color = (255, 160, 50)
    _gizmo_icon_label = "P"

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("duration", "Duration", FieldType.FLOAT, min_val=0.01, max_val=300.0, step=0.1, decimals=2),
            InspectorField("looping", "Looping", FieldType.BOOL),
            InspectorField("prewarm", "Prewarm", FieldType.BOOL),
            InspectorField("start_delay", "Start Delay", FieldType.FLOAT, min_val=0.0, max_val=60.0, step=0.1, decimals=2),
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
            InspectorField("simulation_space", "Simulation Space", FieldType.ENUM, enum_class=SimulationSpace),
            InspectorField("max_particles", "Max Particles", FieldType.INT, min_val=1, max_val=100000, step=1, decimals=0),
            InspectorField("rate_over_time", "Rate over Time", FieldType.FLOAT, min_val=0.0, max_val=100000.0, step=1.0, decimals=1),
            InspectorField("shape_type", "Shape", FieldType.ENUM, enum_class=ShapeType),
            InspectorField("shape_angle", "Shape Angle", FieldType.FLOAT, min_val=0.0, max_val=360.0, step=1.0, decimals=1),
            InspectorField("shape_radius", "Shape Radius", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.1, decimals=2),
            InspectorField("render_mode", "Render Mode", FieldType.ENUM, enum_class=ParticleRenderMode),
            InspectorField("material_path", "Material", FieldType.RESOURCE_PATH, file_filter="Material (*.mat)"),
            InspectorField("sort_mode", "Sort Mode", FieldType.ENUM, enum_class=ParticleSortMode),
            InspectorField("sorting_fudge", "Sorting Fudge", FieldType.FLOAT, min_val=-100.0, max_val=100.0, step=0.1, decimals=2),
            InspectorField("flipbook_columns", "Flipbook Columns", FieldType.INT, min_val=1, max_val=100, step=1, decimals=0),
            InspectorField("flipbook_rows", "Flipbook Rows", FieldType.INT, min_val=1, max_val=100, step=1, decimals=0),
            InspectorField("flipbook_fps", "Flipbook FPS", FieldType.FLOAT, min_val=0.0, max_val=120.0, step=1.0, decimals=1),
            InspectorField("size_over_lifetime_enabled", "Size over Lifetime", FieldType.BOOL),
            InspectorField("size_over_lifetime_curve", "Size Curve", FieldType.CURVE, toggle_field="size_over_lifetime_enabled"),
            InspectorField("color_over_lifetime_enabled", "Color over Lifetime", FieldType.BOOL),
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
        self._started: bool = False
        self._stopped: bool = False
        self._burst_index: int = 0
        self._prev_position: Vec3 = None
        self._emitter_velocity: np.ndarray = None
        self._local_to_world: np.ndarray = None
        self._local_position: np.ndarray = None
        self._particles: Optional[np.ndarray] = None
        self._free_stack: Optional[np.ndarray] = None
        self._free_top: int = 0
        self._alive_mask: Optional[np.ndarray] = None
        self._vao: Optional[Any] = None
        self._vbo: Optional[Any] = None
        self._ibo: Optional[Any] = None
        self._curve_cache_x: Optional[tuple] = None
        self._curve_cache_y: Optional[tuple] = None
        self._gradient_cache: Optional[tuple] = None
        self._vel_linear: Optional[np.ndarray] = None
        self._vel_orbital: Optional[np.ndarray] = None
        self._start_color_arr: Optional[np.ndarray] = None

    def _invalidate_caches(self):
        self._curve_cache_x = None
        self._curve_cache_y = None
        self._gradient_cache = None
        self._vel_linear = None
        self._vel_orbital = None
        self._start_color_arr = None

    _RENDER_VERT_DTYPE = [
        ('position', np.float32, 3),
        ('color', np.float32, 4),
        ('texcoord', np.float32, 2),
        ('size', np.float32, 2),
        ('rotation', np.float32),
    ]

    def _ensure_arrays(self):
        n = self.max_particles
        if self._particles is None or len(self._particles) != n:
            self._particles = np.zeros(n, dtype=PARTICLE_DTYPE)
            self._particles['alive'] = 0
            self._free_stack = np.arange(n, dtype=np.int32)
            self._free_top = n
            self._alive_mask = np.zeros(n, dtype=np.bool_)
            self._particle_count = 0
            self._alive_count = 0
            self._render_verts = np.zeros(n * 4, dtype=self._RENDER_VERT_DTYPE)
            self._render_indices = np.zeros(n * 6, dtype=np.uint32)
            idx4 = np.arange(n, dtype=np.uint32) * 4
            self._render_indices[:] = (idx4[:, None] + np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)).ravel()

    def _get_curve_caches(self):
        if self._curve_cache_x is None:
            cx = self.size_over_lifetime_curve_x or self.size_over_lifetime_curve or [(0,1),(1,1)]
            cy = self.size_over_lifetime_curve_y or cx
            self._curve_cache_x = _build_curve_cache(cx)
            self._curve_cache_y = _build_curve_cache(cy)
        return self._curve_cache_x, self._curve_cache_y

    def _get_gradient_cache(self):
        if self._gradient_cache is None:
            grad = self.color_over_lifetime_gradient or {
                "alpha_keys": [(0,1),(1,0)],
                "color_keys": [(0,[1,1,1]),(1,[1,1,1])]
            }
            self._gradient_cache = _build_gradient_cache(grad)
        return self._gradient_cache

    def on_start(self):
        self._ensure_arrays()
        if self.prewarm:
            self._simulate_forward(self.start_lifetime)

    def _simulate_forward(self, time: float):
        steps = int(time / 0.02)
        t = self.transform
        if t and self.simulation_space == SimulationSpace.LOCAL:
            wm = t.world_matrix._d
            self._local_to_world = wm[:3, :3].astype(np.float32)
            pos = t.position
            self._local_position = np.array([pos.x, pos.y, pos.z], dtype=np.float32)
        for _ in range(steps):
            self._update_particles(0.02, Vec3.zero())
            self._emit_particles(0.02, Vec3.zero())

    def on_enable(self):
        if not self._started:
            self._time = -self.start_delay
            self._started = True
            self._stopped = False
            self._emit_accum = 0.0
            self._burst_index = 0
            self._ensure_arrays()

    def on_disable(self):
        self._stop()

    def _stop(self):
        self._stopped = True

    def _ranged(self, lo_attr, hi_attr, base_attr, n):
        lo, hi = getattr(self, lo_attr), getattr(self, hi_attr)
        if lo > 0 or hi > 0:
            lo = lo if lo > 0 else getattr(self, base_attr)
            hi = hi if hi > 0 else getattr(self, base_attr)
            lo, hi = min(lo, hi), max(lo, hi)
            return lo + (hi - lo) * np.random.random(n).astype(np.float32)
        return np.full(n, getattr(self, base_attr), dtype=np.float32)

    def _emit(self, count: int):
        self._ensure_arrays()
        n = min(count, self._free_top)
        if n == 0:
            return
        self._free_top -= n
        idx = self._free_stack[self._free_top:self._free_top + n].copy()
        idx_arr = idx
        shape = self.shape_type
        radius = self.shape_radius
        half_len = self.shape_length * 0.5
        arc_rad = math.radians(self.shape_arc)
        if self._start_color_arr is None:
            self._start_color_arr = np.array(self.start_color or [1.0,1.0,1.0,1.0], dtype=np.float32)
        rng = np.random.random(n).astype(np.float32)
        rng2 = np.random.random(n).astype(np.float32)
        rng3 = np.random.random(n).astype(np.float32)
        if shape == ShapeType.CONE:
            angle_rad = math.radians(self.shape_angle)
            base_r = radius * (1.0 - rng * math.tan(angle_rad))
            ang = rng2 * arc_rad
            r = base_r * np.sqrt(rng3)
            x = r * np.cos(ang)
            z = r * np.sin(ang)
            y = -half_len + np.random.random(n).astype(np.float32) * self.shape_length
            pos = np.column_stack([x, y, z])
            dv = np.column_stack([x, y + half_len, z])
            dlen = np.maximum(np.linalg.norm(dv, axis=1), 1e-8)
            velocity = dv / dlen[:, None]
        elif shape == ShapeType.SPHERE:
            theta = rng * arc_rad
            phi = rng2 * (math.pi * 2.0)
            r = radius * (rng3 ** (1.0/3.0))
            x = r * np.sin(theta) * np.cos(phi)
            y = r * np.sin(theta) * np.sin(phi)
            z = r * np.cos(theta)
            pos = np.column_stack([x, y, z])
            d = np.maximum(np.linalg.norm(pos, axis=1), 1e-8)
            velocity = pos / d[:, None]
        elif shape == ShapeType.HEMISPHERE:
            theta = rng * min(arc_rad, math.pi * 0.5)
            phi = rng2 * (math.pi * 2.0)
            r = radius * (rng3 ** (1.0/3.0))
            x = r * np.sin(theta) * np.cos(phi)
            y = r * np.cos(theta)
            z = r * np.sin(theta) * np.sin(phi)
            pos = np.column_stack([x, y, z])
            d = np.maximum(np.linalg.norm(pos, axis=1), 1e-8)
            velocity = pos / d[:, None]
        elif shape == ShapeType.BOX:
            bx = self.shape_box or [1, 1, 1]
            pos = np.column_stack([
                (rng - 0.5) * bx[0],
                (rng2 - 0.5) * bx[1],
                (rng3 - 0.5) * bx[2],
            ])
            velocity = np.broadcast_to(np.array([[0.0, 1.0, 0.0]], dtype=np.float32), (n, 3)).copy()
        else:
            r = radius * np.sqrt(rng)
            theta = rng2 * arc_rad
            x = r * np.cos(theta)
            z = r * np.sin(theta)
            pos = np.column_stack([x, np.zeros(n, dtype=np.float32), z])
            d = np.maximum(np.sqrt(x*x + z*z), 1e-8)
            velocity = np.column_stack([x/d, np.zeros(n), z/d])
        pos = pos.astype(np.float32)
        velocity = velocity.astype(np.float32)
        if self._local_to_world is not None:
            R = self._local_to_world
            RT = R.T
            pos = pos @ RT
            velocity = velocity @ RT
            if self._local_position is not None:
                pos += self._local_position
        if self.inherit_velocity > 0 and self._emitter_velocity is not None:
            velocity += (self.inherit_velocity * self._emitter_velocity)
        lifetimes = self._ranged('start_lifetime_min', 'start_lifetime_max', 'start_lifetime', n)
        size_val = self._ranged('start_size_min', 'start_size_max', 'start_size', n)
        sp_min, sp_max = self.start_speed_min, self.start_speed_max
        if sp_min > 0 or sp_max > 0:
            sp_lo = sp_min if sp_min > 0 else self.start_speed
            sp_hi = sp_max if sp_max > 0 else self.start_speed
            sp_lo, sp_hi = min(sp_lo, sp_hi), max(sp_lo, sp_hi)
            speed = sp_lo + (sp_hi - sp_lo) * np.random.random(n).astype(np.float32)
            velocity *= (speed / max(self.start_speed, 1e-6))[:, None]
        else:
            velocity *= self.start_speed
        rot = math.radians(self.start_rotation) + (np.random.random(n).astype(np.float32) - 0.5) * math.radians(self.flip_rotation)
        sc = self._start_color_arr
        p = self._particles
        p['position'][idx_arr] = pos
        p['velocity'][idx_arr] = velocity
        p['color'][idx_arr] = sc
        p['size'][idx_arr, 0] = size_val
        p['size'][idx_arr, 1] = size_val
        p['rotation'][idx_arr] = rot
        p['lifetime'][idx_arr] = lifetimes
        p['max_lifetime'][idx_arr] = lifetimes
        p['alive'][idx_arr] = 1
        p['start_color'][idx_arr] = sc
        p['start_size'][idx_arr, 0] = size_val
        p['start_size'][idx_arr, 1] = size_val
        p['start_rotation'][idx_arr] = rot
        self._alive_mask[idx_arr] = True
        self._particle_count += n
        self._alive_count += n

    def _emit_particles(self, dt: float, delta_pos: Vec3):
        if self._stopped:
            return
        if self.rate_over_time > 0:
            self._emit_accum += dt * self.rate_over_time
            count = int(self._emit_accum)
            if count > 0:
                self._emit(count)
                self._emit_accum -= count
        if self.rate_over_distance > 0:
            dist = delta_pos.length()
            self._distance_accum += dist
            n_units = int(self._distance_accum)
            if n_units > 0:
                self._emit(int(self.rate_over_distance) * n_units)
                self._distance_accum -= n_units
        if self.bursts:
            for burst in self.bursts:
                if abs(self._time - burst.get("time", 0.0)) < dt * 1.5:
                    self._emit(burst.get("count", 1))

    def _update_particles(self, dt: float, delta_pos: Vec3):
        if self._alive_count == 0:
            return
        p = self._particles
        alive_mask = self._alive_mask
        gx, gy, gz = 0.0, -9.81 * self.gravity_modifier, 0.0
        do_local = self.simulation_space == SimulationSpace.LOCAL
        dx = delta_pos.x if do_local else 0.0
        dy = delta_pos.y if do_local else 0.0
        dz = delta_pos.z if do_local else 0.0
        died = _update_core(
            p['position'], p['velocity'], p['lifetime'], p['max_lifetime'],
            p['alive'], dt, gx, gy, gz, dx, dy, dz, do_local
        )
        died_mask = died == 1
        if died_mask.any():
            died_idx = np.where(died_mask)[0].astype(np.int32)
            nd = len(died_idx)
            alive_mask[died_idx] = False
            self._free_stack[self._free_top:self._free_top + nd] = died_idx
            self._free_top += nd
            self._particle_count -= nd
            self._alive_count -= nd
        if self._alive_count == 0:
            return
        alive_idx = np.where(alive_mask)[0]
        if self.velocity_over_lifetime_enabled:
            if self._vel_linear is None:
                self._vel_linear = np.array(self.velocity_over_lifetime_linear or [0,0,0], dtype=np.float32)
            lx, ly, lz = self._vel_linear[0], self._vel_linear[1], self._vel_linear[2]
            if lx != 0 or ly != 0 or lz != 0:
                p['velocity'][alive_idx, 0] += lx * dt
                p['velocity'][alive_idx, 1] += ly * dt
                p['velocity'][alive_idx, 2] += lz * dt
            if self._vel_orbital is None:
                self._vel_orbital = np.array(self.velocity_over_lifetime_orbital or [0,0,0], dtype=np.float32)
            ox, oy, oz = self._vel_orbital[0], self._vel_orbital[1], self._vel_orbital[2]
            if ox != 0 or oy != 0 or oz != 0:
                orbital_v = np.cross(p['position'][alive_idx], self._vel_orbital)
                p['velocity'][alive_idx] += orbital_v * dt
        if self.size_over_lifetime_enabled:
            lt = p['lifetime'][alive_idx]
            max_lt = p['max_lifetime'][alive_idx]
            ratios = (1.0 - lt / np.maximum(max_lt, 1e-10)).astype(np.float32)
            cx_cache, cy_cache = self._get_curve_caches()
            if cx_cache:
                sx = _sample_curve_numba(cx_cache[0], cx_cache[1], ratios)
                p['size'][alive_idx, 0] = p['start_size'][alive_idx, 0] * sx
            if cy_cache:
                sy = _sample_curve_numba(cy_cache[0], cy_cache[1], ratios)
                p['size'][alive_idx, 1] = p['start_size'][alive_idx, 1] * sy
        if self.color_over_lifetime_enabled:
            lt = p['lifetime'][alive_idx]
            max_lt = p['max_lifetime'][alive_idx]
            ratios = (1.0 - lt / np.maximum(max_lt, 1e-10)).astype(np.float32)
            gc = self._get_gradient_cache()
            if gc:
                rgba = _sample_gradient_numba(gc[0], gc[1], gc[2], gc[3], ratios)
                sc = p['start_color'][alive_idx]
                p['color'][alive_idx, 0] = rgba[:, 0] * sc[:, 0]
                p['color'][alive_idx, 1] = rgba[:, 1] * sc[:, 1]
                p['color'][alive_idx, 2] = rgba[:, 2] * sc[:, 2]
                p['color'][alive_idx, 3] = rgba[:, 3] * sc[:, 3]
        if self.rotation_over_lifetime_enabled and self.rotation_over_lifetime_angular_velocity != 0:
            p['rotation'][alive_idx] += math.radians(self.rotation_over_lifetime_angular_velocity) * dt

    def on_update(self, dt: float):
        if not self.enabled or self._stopped:
            return
        if not self._started:
            self._time = -self.start_delay
            self._started = True
            self._stopped = False
            self._ensure_arrays()
        self._time += dt
        if self._time < 0:
            return
        t = self.transform
        if t is None:
            return
        prev = self._prev_position
        current_pos = t.position
        if prev is None:
            delta_pos = Vec3.zero()
            self._emitter_velocity = None
        else:
            delta_pos = current_pos - prev
            inv_dt = 1.0 / max(dt, 1e-6)
            self._emitter_velocity = np.array([delta_pos.x * inv_dt, delta_pos.y * inv_dt, delta_pos.z * inv_dt], dtype=np.float32)
        self._prev_position = current_pos
        if self.simulation_space == SimulationSpace.LOCAL:
            wm = t.world_matrix._d
            self._local_to_world = wm[:3, :3].astype(np.float32)
            self._local_position = np.array([current_pos.x, current_pos.y, current_pos.z], dtype=np.float32)
        else:
            self._local_to_world = None
            self._local_position = None
        self._emit_particles(dt, delta_pos)
        self._update_particles(dt, delta_pos if self.simulation_space == SimulationSpace.LOCAL else Vec3.zero())
        if self._time >= self.duration:
            if self.looping:
                self._time = 0.0
                self._burst_index = 0
            else:
                self._stopped = True

    def get_particle_count(self) -> int:
        return self._particle_count

    def get_alive_count(self) -> int:
        return self._alive_count

    def is_playing(self) -> bool:
        return not self._stopped and self._started

    def is_paused(self) -> bool:
        return self._stopped and self._started

    def is_stopped(self) -> bool:
        return self._stopped

    def play(self):
        if self._started and not self._stopped:
            return
        self._started = True
        self._stopped = False
        self._time = -self.start_delay
        self._emit_accum = 0.0
        self._burst_index = 0

    def pause(self):
        self._stopped = True

    def stop(self):
        self._stopped = True
        self._started = False
        self._time = 0.0
        self._emit_accum = 0.0
        self._burst_index = 0
        if self._particles is not None:
            n = self.max_particles
            self._particles['alive'] = 0
            self._alive_count = 0
            self._particle_count = 0
            self._free_stack = np.arange(n, dtype=np.int32)
            self._free_top = n
            self._alive_mask[:] = False

    def clear(self):
        if self._particles is not None:
            n = self.max_particles
            self._particles['alive'] = 0
            self._alive_count = 0
            self._particle_count = 0
            self._free_stack = np.arange(n, dtype=np.int32)
            self._free_top = n
            self._alive_mask[:] = False

    def get_particles_data(self) -> Optional[np.ndarray]:
        if self._alive_count == 0:
            return None
        return self._particles[self._particles['alive'] == 1]

    def build_render_data(self, camera_right: Vec3, camera_up: Vec3, camera_pos: Vec3 = None) -> Optional[tuple[np.ndarray, np.ndarray]]:
        n = self._alive_count
        if n == 0:
            return None
        p = self._particles
        alive_idx = np.where(self._alive_mask)[0]
        if self.sort_mode == ParticleSortMode.BY_DISTANCE and camera_pos is not None:
            cp = np.array([camera_pos.x, camera_pos.y, camera_pos.z], dtype=np.float32)
            diff = p['position'][alive_idx] - cp
            dist_sq = np.einsum('ij,ij->i', diff, diff)
            alive_idx = alive_idx[np.argsort(-dist_sq)]
        elif self.sort_mode == ParticleSortMode.BY_AGE:
            alive_idx = alive_idx[np.argsort(-p['lifetime'][alive_idx])]
        vn = n * 4
        verts = self._render_verts[:vn]
        idx_rpt = alive_idx.repeat(4)
        verts['position'] = p['position'][idx_rpt]
        verts['color'] = p['color'][idx_rpt]
        use_flipbook = (self.flipbook_fps > 0 and self.flipbook_fps <= 120
                        and self.flipbook_rows > 0 and self.flipbook_columns > 0)
        if use_flipbook:
            ages = p['max_lifetime'][alive_idx] - p['lifetime'][alive_idx]
            total_frames = self.flipbook_columns * self.flipbook_rows
            frame_idx = (ages * self.flipbook_fps).astype(np.int32) % total_frames
            col_idx = frame_idx % self.flipbook_columns
            row_idx = frame_idx // self.flipbook_columns
            inv_c = np.float32(1.0 / self.flipbook_columns)
            inv_r = np.float32(1.0 / self.flipbook_rows)
            u0 = col_idx * inv_c
            v0 = row_idx * inv_r
            u1 = u0 + inv_c
            v1 = v0 + inv_r
            uvs = np.empty((n, 4, 2), dtype=np.float32)
            uvs[:, 0, 0] = u0; uvs[:, 0, 1] = v0
            uvs[:, 1, 0] = u1; uvs[:, 1, 1] = v0
            uvs[:, 2, 0] = u1; uvs[:, 2, 1] = v1
            uvs[:, 3, 0] = u0; uvs[:, 3, 1] = v1
            verts['texcoord'] = uvs.reshape(vn, 2)
        else:
            verts['texcoord'][0:vn:4] = (0, 0)
            verts['texcoord'][1:vn:4] = (1, 0)
            verts['texcoord'][2:vn:4] = (1, 1)
            verts['texcoord'][3:vn:4] = (0, 1)
        verts['size'] = p['size'][idx_rpt]
        verts['rotation'] = p['rotation'][idx_rpt]
        return verts, self._render_indices[:n * 6]

    def gizmo_lines(self, color: list[float] | None = None) -> list[tuple[Vec3, Vec3, list[float]]]:
        if color is None:
            color = [0.8, 0.3, 0.8, 0.6]
        tr = self.transform
        if not tr:
            return []
        world_matrix = tr.world_matrix._d
        world_pos = tr.position
        R = world_matrix[:3, :3]
        lines: list[tuple[Vec3, Vec3, list[float]]] = []
        def local_to_world(v: Vec3) -> Vec3:
            vx, vy, vz = v.x, v.y, v.z
            return world_pos + Vec3(
                vx * R[0, 0] + vy * R[1, 0] + vz * R[2, 0],
                vx * R[0, 1] + vy * R[1, 1] + vz * R[2, 1],
                vx * R[0, 2] + vy * R[1, 2] + vz * R[2, 2],
            )
        shape = self.shape_type
        radius = self.shape_radius
        arc_rad = math.radians(self.shape_arc)
        segments = 24
        if shape == ShapeType.CONE:
            angle_rad = math.radians(self.shape_angle)
            half_len = self.shape_length * 0.5
            base_r = radius
            apex = local_to_world(Vec3(0, -half_len, 0))
            pts = []
            for i in range(segments + 1):
                theta = 2.0 * math.pi * i / segments
                pt = local_to_world(Vec3(math.cos(theta) * base_r, half_len, math.sin(theta) * base_r))
                pts.append(pt)
            for i in range(segments):
                lines.append((pts[i], pts[i + 1], color))
            lines.append((apex, pts[0], color))
            lines.append((apex, pts[segments // 4], color))
            lines.append((apex, pts[segments // 2], color))
            lines.append((apex, pts[3 * segments // 4], color))
            inner_r = base_r * (1.0 - math.tan(angle_rad)) if math.tan(angle_rad) < 1.0 else 0.0
            if inner_r > 0.01:
                inner_pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    pt = local_to_world(Vec3(math.cos(theta) * inner_r, -half_len, math.sin(theta) * inner_r))
                    inner_pts.append(pt)
                for i in range(segments):
                    lines.append((inner_pts[i], inner_pts[i + 1], color))
        elif shape == ShapeType.SPHERE:
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                    elif axis_idx == 1:
                        pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                    else:
                        pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                    pts.append(local_to_world(pt))
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], color))
            if arc_rad < math.pi * 2.0 - 0.01:
                arc_pts = []
                for i in range(segments + 1):
                    theta = arc_rad * i / segments
                    pt = Vec3(math.sin(theta) * radius, 0, math.cos(theta) * radius)
                    arc_pts.append(local_to_world(pt))
                for i in range(segments):
                    lines.append((arc_pts[i], arc_pts[i + 1], [0.8, 0.8, 0.2, 0.6]))
        elif shape == ShapeType.HEMISPHERE:
            ring_pts = []
            for i in range(segments + 1):
                theta = 2.0 * math.pi * i / segments
                pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                ring_pts.append(local_to_world(pt))
            for i in range(segments):
                lines.append((ring_pts[i], ring_pts[i + 1], color))
            for axis_idx in [0, 2]:
                pts = []
                for i in range(segments // 2 + 1):
                    theta = math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * radius, math.sin(theta) * radius)
                    else:
                        pt = Vec3(math.cos(theta) * radius, math.sin(theta) * radius, 0)
                    if pt.y < 0:
                        continue
                    pts.append(local_to_world(pt))
                for i in range(len(pts) - 1):
                    lines.append((pts[i], pts[i + 1], color))
            if arc_rad < math.pi * 2.0 - 0.01:
                arc_pts = []
                for i in range(segments + 1):
                    theta = arc_rad * i / segments
                    pt = Vec3(math.sin(theta) * radius, 0, math.cos(theta) * radius)
                    arc_pts.append(local_to_world(pt))
                for i in range(segments):
                    lines.append((arc_pts[i], arc_pts[i + 1], [0.8, 0.8, 0.2, 0.6]))
        elif shape == ShapeType.BOX:
            bx = self.shape_box or [1, 1, 1]
            hx, hy, hz = bx[0] * 0.5, bx[1] * 0.5, bx[2] * 0.5
            corners_local = [
                Vec3(-hx, -hy, -hz), Vec3(hx, -hy, -hz),
                Vec3(hx, hy, -hz), Vec3(-hx, hy, -hz),
                Vec3(-hx, -hy, hz), Vec3(hx, -hy, hz),
                Vec3(hx, hy, hz), Vec3(-hx, hy, hz),
            ]
            corners = [local_to_world(v) for v in corners_local]
            edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
            for a, b in edges:
                lines.append((corners[a], corners[b], color))
        else:
            pts = []
            for i in range(segments + 1):
                theta = arc_rad * i / segments
                pt = Vec3(math.cos(theta) * radius, 0, math.sin(theta) * radius)
                pts.append(local_to_world(pt))
            for i in range(segments):
                lines.append((pts[i], pts[i + 1], color))
            lines.append((world_pos, local_to_world(Vec3(0, 0, 0)), color))
        return lines

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
            "color_over_lifetime_gradient": self.color_over_lifetime_gradient or {
                "alpha_keys": [[0,1],[1,0]],
                "color_keys": [[0,[1,1,1]],[1,[1,1,1]]]
            },
            "rotation_over_lifetime_enabled": self.rotation_over_lifetime_enabled,
            "rotation_over_lifetime_angular_velocity": self.rotation_over_lifetime_angular_velocity,
            "velocity_over_lifetime_enabled": self.velocity_over_lifetime_enabled,
            "velocity_over_lifetime_linear": self.velocity_over_lifetime_linear or [0,0,0],
            "velocity_over_lifetime_orbital": self.velocity_over_lifetime_orbital or [0,0,0],
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> ParticleSystem:
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

    def on_destroy(self):
        self.stop()
        for attr in ('_vao', '_vbo', '_ibo'):
            obj = getattr(self, attr, None)
            if obj:
                try:
                    obj.release()
                except Exception:
                    pass


def import_gif_to_flipbook(gif_path: str, output_path: str = None, cols: int = None, rows: int = None) -> Tuple[int, int, int]:
    from core.asset_importer import import_gif_to_flipbook as _import
    return _import(gif_path, output_path, cols, rows)