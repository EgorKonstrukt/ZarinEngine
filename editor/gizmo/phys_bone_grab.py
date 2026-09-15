# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from core.maths.math3d import Vec3
from editor.viewport.projection import screen_to_plane, world_to_screen


_HANDLE_PX = 16.0


class PhysBoneGrabGizmo:
    def __init__(self, viewport):
        self._vp = viewport
        self._dragging = False
        self._comp = None
        self._index = -1
        self._entity = None
        self._plane_point = None

    @property
    def dragging(self):
        return self._dragging

    @property
    def grab_entity(self):
        return self._entity

    def _iter_comps(self):
        vp = self._vp
        eng = getattr(vp, "_engine", None)
        scene = getattr(eng, "scene", None) if eng is not None else None
        if scene is None:
            return
        try:
            from core.components.physics.phys_bone import PhysBone
        except ImportError:
            return
        try:
            ents = scene.get_entities_with_component(PhysBone)
        except Exception:
            return
        for ent in ents:
            try:
                if not ent.active:
                    continue
                for comp in ent.get_components(PhysBone):
                    try:
                        if not comp.enabled:
                            continue
                        if not getattr(comp, "allow_grab", True):
                            continue
                        yield comp
                    except Exception:
                        continue
            except Exception:
                continue

    def _chain_points(self, comp):
        try:
            if not comp.ensure_built():
                return None
            nodes = comp._nodes
            if not nodes:
                return None
            pts = comp._pos if len(comp._pos) == len(nodes) else None
            if pts is None:
                pts = [nd.rest_world_pos for nd in nodes]
            return pts
        except Exception:
            return None

    def pick(self, lx, ly):
        best = None
        best_d = _HANDLE_PX + 1.0
        best_cam = float("inf")
        try:
            cam_pos = self._vp._cam.position
        except Exception:
            cam_pos = None
        for comp in self._iter_comps():
            pts = self._chain_points(comp)
            if not pts:
                continue
            for i, p in enumerate(pts):
                try:
                    if i == 0:
                        continue
                    sp = world_to_screen(self._vp, p)
                    if sp is None:
                        continue
                    d = math.hypot(sp[0] - lx, sp[1] - ly)
                    if d > best_d:
                        continue
                    cd = 0.0
                    if cam_pos is not None:
                        dx = p.x - cam_pos.x
                        dy = p.y - cam_pos.y
                        dz = p.z - cam_pos.z
                        cd = dx * dx + dy * dy + dz * dz
                    if d < best_d - 1e-9 or (abs(d - best_d) < 1e-9 and cd < best_cam):
                        best_d = d
                        best_cam = cd
                        best = (comp, i)
                except Exception:
                    continue
        return best

    def on_mouse_press(self, lx, ly):
        try:
            hit = self.pick(int(lx), int(ly))
            if hit is None:
                return False
            comp, idx = hit
            pts = self._chain_points(comp)
            if not pts:
                return False
            p = pts[idx]
            if not comp.debug_grab_begin(idx, Vec3(p.x, p.y, p.z)):
                return False
            self._comp = comp
            self._index = idx
            self._plane_point = Vec3(p.x, p.y, p.z)
            try:
                eid = comp.chain_entity_id(idx)
                eng = getattr(self._vp, "_engine", None)
                scene = getattr(eng, "scene", None) if eng is not None else None
                self._entity = scene.get_entity(eid) if scene is not None and eid else None
            except Exception:
                self._entity = None
            try:
                if not getattr(self._vp._engine, "play_mode", False):
                    comp.preview_step(1.0 / 60.0)
            except Exception:
                pass
            self._dragging = True
            return True
        except Exception:
            return False

    def on_mouse_move(self, lx, ly):
        try:
            if not self._dragging or self._comp is None:
                return False
            target = screen_to_plane(self._vp, int(lx), int(ly), self._plane_point)
            if not self._comp.debug_grab_move(target):
                return False
            try:
                if not getattr(self._vp._engine, "play_mode", False):
                    self._comp.preview_step(1.0 / 60.0)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def on_mouse_release(self):
        try:
            if not self._dragging:
                return
            comp = self._comp
            if comp is not None:
                try:
                    play = bool(getattr(self._vp._engine, "play_mode", False))
                except Exception:
                    play = False
                try:
                    comp.debug_grab_end(not play)
                except Exception:
                    pass
        except Exception:
            pass
        self._dragging = False
        self._comp = None
        self._index = -1
        self._entity = None
        self._plane_point = None
