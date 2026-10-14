# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from core.maths.math3d import Vec3
from core.components.rendering.particles.partic.component import ShapeType


class ParticleEmitMixin:
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
        if count > self._free_top:
            self._grow_capacity()
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
            self._start_color_arr = np.array(self.start_color or [1.0, 1.0, 1.0, 1.0], dtype=np.float32)
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
        if n > 1:
            phi = 0.6180339887498949
            offsets = np.mod(np.arange(n, dtype=np.float32) * phi, 1.0)
            lifetimes *= (0.925 + 0.15 * offsets)
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
        p['position'][idx_arr, :3] = pos
        p['velocity'][idx_arr, :3] = velocity
        p['color'][idx_arr] = sc
        p['meta'][idx_arr, 0] = size_val
        p['meta'][idx_arr, 1] = size_val
        p['meta'][idx_arr, 2] = rot
        p['meta'][idx_arr, 3] = 1.0
        p['lifetime'][idx_arr, 0] = lifetimes
        p['lifetime'][idx_arr, 1] = lifetimes
        p['start_color'][idx_arr] = sc
        p['start_meta'][idx_arr, 0] = size_val
        p['start_meta'][idx_arr, 1] = size_val
        p['start_meta'][idx_arr, 2] = rot
        self._alive_mask[idx_arr] = True
        self._particle_count += n
        self._alive_count += n

    def _emit_particles(self, dt: float, delta_pos: Vec3):
        if self._stopped:
            return
        if not self._prewarmed:
            self._prewarmed = True
            if self.rate_over_time > 0 and self.start_lifetime > 0:
                prewarm_n = int(self.rate_over_time * self.start_lifetime * 1.075)
                if prewarm_n > 0:
                    self._grow_capacity()
                    self._emit_accum = max(self._emit_accum, prewarm_n)
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
