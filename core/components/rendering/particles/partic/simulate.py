# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3
from core.components.rendering.particles.partic.component import PARTICLE_DTYPE
from core.components.rendering.particles.partic.component import SimulationSpace


def _build_curve_cache(curve_list) -> Optional[tuple]:
    if not curve_list or len(curve_list) < 2:
        return None
    arr = np.array(curve_list, dtype=np.float32)
    return arr[:, 0], arr[:, 1]

def _build_gradient_cache(grad) -> Optional[tuple]:
    if not grad:
        return None
    if isinstance(grad, (list, tuple)):
        stops = sorted(grad, key=lambda s: s[0])
        c_t = np.array([s[0] for s in stops], dtype=np.float32)
        c_v = np.array([s[1][:3] for s in stops], dtype=np.float32).reshape(-1, 3)
        a_t = np.array([s[0] for s in stops], dtype=np.float32)
        a_v = np.array([s[1][3] if len(s[1]) > 3 else 1.0 for s in stops], dtype=np.float32)
        return c_t, c_v, a_t, a_v
    ck = grad.get("color_keys", [(0, [1, 1, 1]), (1, [1, 1, 1])])
    ak = grad.get("alpha_keys", [(0, 1.0), (1, 1.0)])
    c_t = np.array([k[0] for k in ck], dtype=np.float32)
    c_v = np.array([k[1] for k in ck], dtype=np.float32).reshape(-1, 3)
    a_t = np.array([k[0] for k in ak], dtype=np.float32)
    a_v = np.array([k[1] for k in ak], dtype=np.float32)
    return c_t, c_v, a_t, a_v

def _sample_curve(keys_t: np.ndarray, keys_v: np.ndarray, t: float) -> float:
    nk = len(keys_t)
    t_clamped = max(keys_t[0], min(keys_t[-1], t))
    lo, hi = 0, nk - 2
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if keys_t[mid] <= t_clamped:
            lo = mid
        else:
            hi = mid - 1
    idx = lo if lo < nk - 1 else nk - 2
    dt = keys_t[idx + 1] - keys_t[idx]
    seg = (t_clamped - keys_t[idx]) / (dt if dt > 1e-10 else 1e-10)
    return keys_v[idx] + (keys_v[idx + 1] - keys_v[idx]) * seg

def _presample_curve(curve_cache: Optional[tuple], num_samples: int = 16) -> np.ndarray:
    out = np.ones(num_samples, dtype=np.float32)
    if curve_cache is None:
        return out
    keys_t, keys_v = curve_cache
    for i in range(num_samples):
        t = i / (num_samples - 1)
        out[i] = _sample_curve(keys_t, keys_v, t)
    return out

def _presample_gradient(grad_cache: Optional[tuple], num_samples: int = 16) -> tuple:
    cr = np.ones(num_samples, dtype=np.float32)
    cg = np.ones(num_samples, dtype=np.float32)
    cb = np.ones(num_samples, dtype=np.float32)
    alpha = np.ones(num_samples, dtype=np.float32)
    if grad_cache is None:
        return cr, cg, cb, alpha
    c_t, c_v, a_t, a_v = grad_cache
    nk = len(c_t)
    for i in range(num_samples):
        t = i / (num_samples - 1)
        t_clamped = max(c_t[0], min(c_t[-1], t))
        lo, hi = 0, nk - 2
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if c_t[mid] <= t_clamped:
                lo = mid
            else:
                hi = mid - 1
        idx = lo if lo < nk - 1 else nk - 2
        dt = c_t[idx + 1] - c_t[idx]
        seg = (t_clamped - c_t[idx]) / (dt if dt > 1e-10 else 1e-10)
        cr[i] = c_v[idx, 0] + (c_v[idx + 1, 0] - c_v[idx, 0]) * seg
        cg[i] = c_v[idx, 1] + (c_v[idx + 1, 1] - c_v[idx, 1]) * seg
        cb[i] = c_v[idx, 2] + (c_v[idx + 1, 2] - c_v[idx, 2]) * seg
    for i in range(num_samples):
        t = i / (num_samples - 1)
        t_clamped = max(a_t[0], min(a_t[-1], t))
        lo, hi = 0, len(a_t) - 2
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if a_t[mid] <= t_clamped:
                lo = mid
            else:
                hi = mid - 1
        idx = lo if lo < len(a_t) - 1 else len(a_t) - 2
        dt = a_t[idx + 1] - a_t[idx]
        seg = (t_clamped - a_t[idx]) / (dt if dt > 1e-10 else 1e-10)
        alpha[i] = a_v[idx] + (a_v[idx + 1] - a_v[idx]) * seg
    return cr, cg, cb, alpha


class ParticleSimulateMixin:
    def _ensure_arrays(self):
        if self._particles is not None and len(self._particles) >= 1:
            return
        n = min(self.max_particles, self._INITIAL_CAPACITY)
        self._particles = np.zeros(n, dtype=PARTICLE_DTYPE)
        self._particles['meta'][:, 3] = 0.0
        self._free_stack = np.arange(n, dtype=np.int32)
        self._free_top = n
        self._alive_mask = np.zeros(n, dtype=np.bool_)
        self._particle_count = 0
        self._alive_count = 0

    def _grow_capacity(self):
        old_cap = len(self._particles) if self._particles is not None else 0
        new_cap = min(self.max_particles, max(old_cap * 2, self._INITIAL_CAPACITY))
        if new_cap <= old_cap:
            return
        new_particles = np.zeros(new_cap, dtype=PARTICLE_DTYPE)
        new_particles[:old_cap] = self._particles
        new_particles['meta'][old_cap:, 3] = 0.0
        self._particles = new_particles
        new_free = np.arange(old_cap, new_cap, dtype=np.int32)
        self._free_stack = np.concatenate([self._free_stack, new_free])
        self._free_top += new_cap - old_cap
        new_mask = np.zeros(new_cap, dtype=np.bool_)
        new_mask[:old_cap] = self._alive_mask
        self._alive_mask = new_mask

    def on_start(self):
        self._ensure_arrays()

    def on_enable(self):
        if not self._started:
            self._time = -self.start_delay
            self._started = True
            self._stopped = False
            self._emit_accum = 0.0
            self._burst_index = 0
            self._prewarmed = False
            self._ensure_arrays()

    def on_disable(self):
        self._stop()

    def _stop(self):
        self._stopped = True

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
        self._last_dt = dt
        self._last_delta_pos = delta_pos
        if self.simulation_space == SimulationSpace.LOCAL:
            wm = t.world_matrix._d
            self._local_to_world = wm[:3, :3].astype(np.float32)
            self._local_position = np.array([current_pos.x, current_pos.y, current_pos.z], dtype=np.float32)
        else:
            self._local_to_world = None
            self._local_position = None
        self._emit_particles(dt, delta_pos)
        if self._time >= self.duration:
            if self.looping:
                self._time = 0.0
                self._burst_index = 0
            else:
                self._stopped = True

    def replenish_free_list(self, dead_indices: np.ndarray):
        n = len(dead_indices)
        if n == 0:
            return
        self._free_stack[self._free_top:self._free_top + n] = dead_indices.astype(np.int32)
        self._free_top += n
        for idx in dead_indices:
            self._alive_mask[idx] = False
        self._particle_count -= n
        self._alive_count -= n

    def get_compute_params(self, dt: float, delta_pos: Vec3) -> dict:
        dx = delta_pos.x if self.simulation_space == SimulationSpace.LOCAL else 0.0
        dy = delta_pos.y if self.simulation_space == SimulationSpace.LOCAL else 0.0
        dz = delta_pos.z if self.simulation_space == SimulationSpace.LOCAL else 0.0
        params = {
            'dt': dt,
            'gravity': -9.81 * self.gravity_modifier,
            'simulation_space': self.simulation_space.value,
            'emitter_delta': (dx, dy, dz),
            'num_particles': len(self._particles) if self._particles is not None else 0,
            'size_enabled': self.size_over_lifetime_enabled,
            'color_enabled': self.color_over_lifetime_enabled,
            'rotation_enabled': self.rotation_over_lifetime_enabled,
            'velocity_enabled': self.velocity_over_lifetime_enabled,
        }
        if self.size_over_lifetime_enabled:
            if self._curve_cache_x is None:
                cx = self.size_over_lifetime_curve_x or self.size_over_lifetime_curve or [(0,1),(1,1)]
                self._curve_cache_x = _build_curve_cache(cx)
            params['size_curve'] = _presample_curve(self._curve_cache_x)
        if self.color_over_lifetime_enabled:
            if self._gradient_cache is None:
                grad = self.color_over_lifetime_gradient or {
                    "alpha_keys": [(0,1),(1,0)],
                    "color_keys": [(0,[1,1,1]),(1,[1,1,1])]
                }
                self._gradient_cache = _build_gradient_cache(grad)
            cr, cg, cb, ca = _presample_gradient(self._gradient_cache)
            params['color_curve_r'] = cr
            params['color_curve_g'] = cg
            params['color_curve_b'] = cb
            params['alpha_curve'] = ca
        if self.rotation_over_lifetime_enabled:
            params['angular_velocity'] = math.radians(self.rotation_over_lifetime_angular_velocity)
        if self.velocity_over_lifetime_enabled:
            params['vel_linear'] = tuple(self.velocity_over_lifetime_linear or [0,0,0])
            params['vel_orbital'] = tuple(self.velocity_over_lifetime_orbital or [0,0,0])
        return params

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
        self._prewarmed = False

    def pause(self):
        self._stopped = True

    def stop(self):
        self._stopped = True
        self._started = False
        self._time = 0.0
        self._emit_accum = 0.0
        self._burst_index = 0
        self._prewarmed = False
        if self._particles is not None:
            n = len(self._particles)
            self._particles['meta'][:, 3] = 0.0
            self._alive_count = 0
            self._particle_count = 0
            self._free_stack = np.arange(n, dtype=np.int32)
            self._free_top = n
            self._alive_mask[:] = False

    def clear(self):
        if self._particles is not None:
            n = len(self._particles)
            self._particles['meta'][:, 3] = 0.0
            self._alive_count = 0
            self._particle_count = 0
            self._free_stack = np.arange(n, dtype=np.int32)
            self._free_top = n
            self._alive_mask[:] = False
        self._prewarmed = False

    def on_destroy(self):
        self.stop()
