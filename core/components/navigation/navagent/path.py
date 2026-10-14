# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from typing import Optional
from core.maths.math3d import Vec3
from core.navigation import NavWorld


class NavAgentPathMixin:

    def _ensure_nav_world(self):
        if self._nav_world:
            return True
        scene = self.entity._scene if self.entity else None
        if not scene:
            return False
        nw = NavWorld(self.nav_resolution, self.nav_world_size)
        nw.set_scene(scene)
        padding = self.agent_padding if self.agent_padding > 0 else self.agent_radius
        if self.flying:
            nw.dilate_for_agent(padding)
        try:
            ent = self.entity
            if ent is not None:
                try:
                    eid = ent.id
                except Exception:
                    eid = id(ent)
                nw.ignore_entity(eid, True)
        except Exception:
            pass
        self._nav_world = nw
        return True


    def _request_path(self):
        if self._pending_req_id is not None:
            return
        if not self._ensure_nav_world():
            return
        tr = self.transform
        if not tr:
            return
        start = tr.local_position
        end = self._get_target_position()
        if end is None:
            return
        self._nav_world.rebuild_grid()
        padding = self.agent_padding if self.agent_padding > 0 else None
        if self.flying:
            self._nav_world.dilate_for_agent(padding if padding is not None else self.agent_radius)
        radius, height, climb, slope = self._effective_nav_params()
        req_id = self._nav_world.find_path_gpu_deferred(
            start, end, radius, height, self.flying,
            climb, slope, padding
        )
        self._pending_req_id = req_id


    def _poll_path_result(self):
        if self._pending_req_id is None:
            return
        result = self._nav_world.poll_result(self._pending_req_id)
        if result is None:
            return
        self._pending_req_id = None
        self._blocked_frames = 0
        if len(result) == 0:
            self._fail_streak = min(self._fail_streak + 1, 6)
            self._path = result
            self._path_index = 0
            return
        self._fail_streak = 0
        try:
            keep_old = False
            if len(self._path) >= 2 and self._path_index < len(self._path):
                goal_now = self._get_target_position()
                if goal_now is not None and self._last_path_goal is not None:
                    dx = goal_now.x - self._last_path_goal[0]
                    dy = goal_now.y - self._last_path_goal[1]
                    dz = goal_now.z - self._last_path_goal[2]
                    same_goal = dx * dx + dy * dy + dz * dz < 0.04
                else:
                    same_goal = goal_now is None and self._last_path_goal is None
                gid_now = id(self._nav_world._grid._grid)
                if same_goal and self._path_grid_gid == gid_now:
                    tr0 = self.transform
                    if tr0 is not None:
                        pos0 = tr0.local_position
                        keep_old = True
                        prev = pos0
                        for wp in self._path[self._path_index:]:
                            if not self._nav_world.has_los(prev, wp, self.flying):
                                keep_old = False
                                break
                            prev = wp
            if keep_old:
                return
        except Exception:
            pass
        self._path = result
        try:
            goal_now = self._get_target_position()
            if goal_now is not None:
                self._last_path_goal = (goal_now.x, goal_now.y, goal_now.z)
            else:
                self._last_path_goal = None
            self._path_grid_gid = id(self._nav_world._grid._grid)
        except Exception:
            pass
        if len(result) >= 2:
            tr = self.transform
            if tr:
                try:
                    pos = tr.local_position
                    far = 1
                    for k in range(1, len(result)):
                        if self._nav_world.has_los(pos, result[k], self.flying):
                            far = k
                        else:
                            break
                    self._path_index = far
                except Exception:
                    self._path_index = 1
            else:
                self._path_index = 1
        else:
            self._path_index = 0


    def _get_target_position(self) -> Optional[Vec3]:
        if self.target_entity_id:
            scene = self.entity._scene if self.entity else None
            if scene:
                target_ent = scene.get_entity(self.target_entity_id)
                if target_ent:
                    target_tr = target_ent.transform
                    if target_tr:
                        return target_tr.position
        return Vec3(self.target_x, self.target_y, self.target_z)


    def gizmo_lines(self) -> list[tuple[Vec3, Vec3, list[float]]]:
        lines = []
        path_color = [0.2, 0.8, 1.0, 1.0]
        target_color = [1.0, 0.8, 0.2, 1.0]
        agent_color = [0.2, 1.0, 0.6, 0.5]

        if self.show_path_cells and self._nav_world:
            rects = self._nav_world.get_path_rects()
            if rects:
                for rct in rects:
                    aabb = rct.world_aabb(self._nav_world._grid)
                    depth_color = [0.1, 0.8, 0.3, 0.3]
                    corners = [
                        Vec3(aabb.min.x, aabb.min.y, aabb.min.z),
                        Vec3(aabb.max.x, aabb.min.y, aabb.min.z),
                        Vec3(aabb.max.x, aabb.max.y, aabb.min.z),
                        Vec3(aabb.min.x, aabb.max.y, aabb.min.z),
                        Vec3(aabb.min.x, aabb.min.y, aabb.max.z),
                        Vec3(aabb.max.x, aabb.min.y, aabb.max.z),
                        Vec3(aabb.max.x, aabb.max.y, aabb.max.z),
                        Vec3(aabb.min.x, aabb.max.y, aabb.max.z),
                    ]
                    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
                    for a, b in edges:
                        lines.append((corners[a], corners[b], depth_color))
            else:
                aabbs = self._nav_world.get_path_aabbs()
                for aabb, depth in aabbs:
                    alpha = max(0.15, 1.0 - depth * 0.12)
                    depth_color = [0.2 + depth * 0.1, 0.9 - depth * 0.08, 0.4 + depth * 0.05, alpha]
                    corners = [
                        Vec3(aabb.min.x, aabb.min.y, aabb.min.z),
                        Vec3(aabb.max.x, aabb.min.y, aabb.min.z),
                        Vec3(aabb.max.x, aabb.max.y, aabb.min.z),
                        Vec3(aabb.min.x, aabb.max.y, aabb.min.z),
                        Vec3(aabb.min.x, aabb.min.y, aabb.max.z),
                        Vec3(aabb.max.x, aabb.min.y, aabb.max.z),
                        Vec3(aabb.max.x, aabb.max.y, aabb.max.z),
                        Vec3(aabb.min.x, aabb.max.y, aabb.max.z),
                    ]
                    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
                    for a, b in edges:
                        lines.append((corners[a], corners[b], depth_color))

        tr = self.transform
        if tr:
            pos = tr.local_position
            r = self.agent_radius
            h = self.agent_height
            segments = 16
            for i in range(segments):
                theta1 = 2.0 * math.pi * i / segments
                theta2 = 2.0 * math.pi * (i + 1) / segments
                x1 = pos.x + r * math.cos(theta1)
                z1 = pos.z + r * math.sin(theta1)
                x2 = pos.x + r * math.cos(theta2)
                z2 = pos.z + r * math.sin(theta2)
                y_top = pos.y + h
                y_bot = pos.y
                lines.append((Vec3(x1, y_bot, z1), Vec3(x2, y_bot, z2), agent_color))
                lines.append((Vec3(x1, y_top, z1), Vec3(x2, y_top, z2), agent_color))
                lines.append((Vec3(x1, y_bot, z1), Vec3(x1, y_top, z1), agent_color))

        target_pos = Vec3(self.target_x, self.target_y, self.target_z)
        s = 0.5
        lines.append((target_pos + Vec3(-s, 0, -s), target_pos + Vec3(s, 0, s), target_color))
        lines.append((target_pos + Vec3(s, 0, -s), target_pos + Vec3(-s, 0, s), target_color))
        lines.append((target_pos + Vec3(0, -s, 0), target_pos + Vec3(0, s, 0), target_color))

        for i in range(len(self._path) - 1):
            a = self._path[i]
            b = self._path[i + 1]
            alpha = 1.0 - i / max(len(self._path), 1)
            lines.append((a, b, [path_color[0], path_color[1], path_color[2], alpha]))

        if self._path and self._path_index < len(self._path):
            wp = self._path[self._path_index]
            wp_color = [0.0, 1.0, 0.0, 1.0]
            ws = 0.3
            lines.append((wp + Vec3(-ws, 0, -ws), wp + Vec3(ws, 0, ws), wp_color))
            lines.append((wp + Vec3(ws, 0, -ws), wp + Vec3(-ws, 0, ws), wp_color))

        return lines

