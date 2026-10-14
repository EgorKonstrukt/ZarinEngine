# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.maths.math3d import Vec3
from core.audio.sys import AudioSystem, AudioSourceManager
from core.audio.efx import efx_available, reverb_enabled, is_aux_slot


class ReverbZoneSpatialMixin:
    def _zone_position(self):
        try:
            tr = self.transform
            if tr is None:
                return (0.0, 0.0, 0.0)
            p = tr.position
            return (float(p.x), float(p.y), float(p.z))
        except Exception:
            return (0.0, 0.0, 0.0)

    def compute_weight(self, src_pos) -> float:
        try:
            if self._is_off():
                return 0.0
            zone_pos = self._zone_position()
            dx = float(src_pos[0]) - float(zone_pos[0])
            dy = float(src_pos[1]) - float(zone_pos[1])
            dz = float(src_pos[2]) - float(zone_pos[2])
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        except Exception:
            return 0.0
        try:
            min_d = float(self.min_distance)
            max_d = float(self.max_distance)
        except Exception:
            return 0.0
        if max_d <= 0.0:
            return 0.0
        if min_d < 0.0:
            min_d = 0.0
        if max_d < min_d:
            max_d = min_d
        if dist <= min_d:
            return 1.0
        if dist >= max_d:
            return 0.0
        span = max_d - min_d
        if span <= 0.0001:
            return 1.0
        t = (dist - min_d) / span
        if t < 0.0:
            t = 0.0
        if t > 1.0:
            t = 1.0
        return 1.0 - t

    def _is_routable(self) -> bool:
        try:
            if not self._is_active():
                return False
            if not self._reverb_allowed():
                return False
            if self._is_off():
                return False
            if not bool(efx_available()):
                return False
            slot = int(getattr(self, "_slot_id", 0) or 0)
            if not slot:
                return False
            return bool(is_aux_slot(int(slot)))
        except Exception:
            return False

    @staticmethod
    def _current_frame() -> int:
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            if eng is not None and hasattr(eng, "_frame_count"):
                return int(eng._frame_count)
        except Exception:
            pass
        return -1

    @classmethod
    def update_routing(cls, force: bool = False):
        try:
            frame = cls._current_frame()
            if not force and frame >= 0 and int(cls._last_routing_frame) == int(frame):
                return
            if frame >= 0:
                cls._last_routing_frame = int(frame)
        except Exception:
            pass
        try:
            mgr = AudioSourceManager.instance()
        except Exception:
            mgr = None
        if mgr is None:
            return
        try:
            allowed = bool(reverb_enabled())
        except Exception:
            allowed = True
        try:
            has_efx = bool(efx_available())
        except Exception:
            has_efx = False
        if not allowed or not has_efx:
            try:
                for src_id in list(mgr.get_active_source_ids()):
                    try:
                        cur = int(mgr.get_source_aux_slot(int(src_id)))
                    except Exception:
                        continue
                    if cur == 0:
                        continue
                    owned = False
                    try:
                        for z in list(cls._instances):
                            try:
                                if int(getattr(z, "_slot_id", 0) or 0) == int(cur) and int(cur) != 0:
                                    owned = True
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass
                    if owned:
                        try:
                            mgr.set_source_aux_send(int(src_id), 0, 0, 0)
                        except Exception:
                            pass
            except Exception:
                pass
            return
        active = []
        try:
            for z in list(cls._instances):
                try:
                    if z._is_routable():
                        active.append(z)
                except Exception:
                    pass
        except Exception:
            pass
        if not active:
            try:
                for src_id in list(mgr.get_active_source_ids()):
                    try:
                        cur = int(mgr.get_source_aux_slot(int(src_id)))
                    except Exception:
                        continue
                    if cur == 0:
                        continue
                    owned = False
                    try:
                        for z in list(cls._instances):
                            try:
                                if int(getattr(z, "_slot_id", 0) or 0) == int(cur) and int(cur) != 0:
                                    owned = True
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass
                    if owned:
                        try:
                            mgr.set_source_aux_send(int(src_id), 0, 0, 0)
                        except Exception:
                            pass
                        try:
                            if hasattr(mgr, "_source_aux_gain"):
                                mgr._source_aux_gain[int(src_id)] = 0.0
                        except Exception:
                            pass
            except Exception:
                pass
            return
        try:
            sources = list(mgr.get_active_source_ids())
        except Exception:
            return
        for src_id in sources:
            try:
                pos = mgr.get_source_position(int(src_id))
            except Exception:
                continue
            if pos is None:
                continue
            best = None
            best_w = 0.0
            for z in active:
                try:
                    w = float(z.compute_weight(pos))
                except Exception:
                    w = 0.0
                if w > best_w:
                    best_w = w
                    best = z
            if best is None or best_w <= 0.001:
                try:
                    cur = int(mgr.get_source_aux_slot(int(src_id)))
                except Exception:
                    continue
                if cur == 0:
                    continue
                owned = False
                try:
                    for z in list(cls._instances):
                        try:
                            if int(getattr(z, "_slot_id", 0) or 0) == int(cur) and int(cur) != 0:
                                owned = True
                                break
                        except Exception:
                            pass
                except Exception:
                    pass
                if owned:
                    try:
                        mgr.set_source_aux_send(int(src_id), 0, 0, 0)
                    except Exception:
                        pass
                    try:
                        if hasattr(mgr, "_source_aux_gain"):
                            mgr._source_aux_gain[int(src_id)] = 0.0
                    except Exception:
                        pass
            else:
                try:
                    mgr.set_source_aux_send_weighted(int(src_id), int(best._slot_id), float(best_w), 0)
                except Exception:
                    pass

    @staticmethod
    def _get_listener_pos():
        try:
            audio_sys = AudioSystem.instance()
            if audio_sys:
                return audio_sys._listener_pos
        except Exception:
            pass
        return (0.0, 0.0, 0.0)

    def gizmo_lines(self):
        try:
            tr = self.transform
        except Exception:
            return []
        if not tr:
            return []
        try:
            pos = tr.position
            min_r = float(self.min_distance)
            max_r = float(self.max_distance)
        except Exception:
            return []
        lines = []
        segments = 24
        inner_color = [0.3, 0.5, 1.0, 0.6]
        outer_color = [0.2, 0.3, 0.8, 0.3]
        if min_r > 0.01:
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * min_r, math.sin(theta) * min_r)
                    elif axis_idx == 1:
                        pt = Vec3(math.cos(theta) * min_r, 0, math.sin(theta) * min_r)
                    else:
                        pt = Vec3(math.cos(theta) * min_r, math.sin(theta) * min_r, 0)
                    pts.append(pos + pt)
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], inner_color))
        if max_r > 0.01 and abs(max_r - min_r) > 0.01:
            for axis_idx in range(3):
                pts = []
                for i in range(segments + 1):
                    theta = 2.0 * math.pi * i / segments
                    if axis_idx == 0:
                        pt = Vec3(0, math.cos(theta) * max_r, math.sin(theta) * max_r)
                    elif axis_idx == 1:
                        pt = Vec3(math.cos(theta) * max_r, 0, math.sin(theta) * max_r)
                    else:
                        pt = Vec3(math.cos(theta) * max_r, math.sin(theta) * max_r, 0)
                    pts.append(pos + pt)
                for i in range(segments):
                    lines.append((pts[i], pts[i + 1], outer_color))
        return lines
