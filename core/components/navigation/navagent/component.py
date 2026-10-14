# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from core.ecs import Component, ComponentRegistry
from core.maths.math3d import Vec3
from core.components.inspector_meta import FieldType, InspectorField
from core.navigation import NavWorld
from core.components.navigation.navagent.path import NavAgentPathMixin
from core.components.navigation.navagent.steering import NavAgentSteeringMixin


@ComponentRegistry.register
class NavAgent(NavAgentSteeringMixin, NavAgentPathMixin, Component):
    _icon = "NavAgent.png"
    _gizmo_icon_color = (60, 180, 255)
    _gizmo_icon_label = "N"
    _gizmo_pass = "nav"
    _inspector_buttons = [
        ("_btn_set_target", "Set Target"),
        ("_btn_stop", "Stop"),
    ]


    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Agent", FieldType.HEADER),
            InspectorField("agent_radius", "Agent Radius", FieldType.FLOAT, min_val=0.01, max_val=100.0, step=0.1),
            InspectorField("agent_height", "Agent Height", FieldType.FLOAT, min_val=0.01, max_val=100.0, step=0.1),
            InspectorField("agent_padding", "Wall Padding", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.1),
            InspectorField("max_climb", "Max Climb", FieldType.FLOAT, min_val=0.0, max_val=100.0, step=0.1),
            InspectorField("max_slope", "Max Slope", FieldType.FLOAT, min_val=0.0, max_val=89.0, step=1.0),
            InspectorField("", "Movement", FieldType.HEADER),
            InspectorField("max_speed", "Max Speed", FieldType.FLOAT, min_val=0.0, max_val=1000.0, step=0.1),
            InspectorField("max_angular_speed", "Angular Speed", FieldType.FLOAT, min_val=0.0, max_val=1000.0, step=1.0),
            InspectorField("use_physical_controller", "Physical Controller", FieldType.BOOL),
            InspectorField("flying", "Flying Mode", FieldType.BOOL),
            InspectorField("auto_move", "Auto Move", FieldType.BOOL),
            InspectorField("show_path_cells", "Show Path Cells", FieldType.BOOL),
            InspectorField("", "Target", FieldType.HEADER),
            InspectorField("target_x", "Target X", FieldType.FLOAT, min_val=-10000.0, max_val=10000.0, step=0.1),
            InspectorField("target_y", "Target Y", FieldType.FLOAT, min_val=-10000.0, max_val=10000.0, step=0.1),
            InspectorField("target_z", "Target Z", FieldType.FLOAT, min_val=-10000.0, max_val=10000.0, step=0.1),
            InspectorField("target_entity_id", "Target Entity", FieldType.GAMEOBJECT),
            InspectorField("", "Navigation", FieldType.HEADER),
            InspectorField("repath_interval", "Repath Interval", FieldType.FLOAT, min_val=0.0, max_val=60.0, step=0.1),
            InspectorField("arrival_distance", "Arrival Distance", FieldType.FLOAT, min_val=0.01, max_val=100.0, step=0.1),
            InspectorField("nav_resolution", "Nav Resolution", FieldType.INT, min_val=8, max_val=1024, step=1),
            InspectorField("nav_world_size", "Nav World Size", FieldType.FLOAT, min_val=10.0, max_val=10000.0, step=10.0),
        ]

    def __init__(self):
        super().__init__()
        self.agent_radius: float = 0.5
        self.agent_height: float = 2.0
        self.agent_padding: float = 0.0
        self.max_climb: float = 0.5
        self.max_slope: float = 45.0
        self.max_speed: float = 5.0
        self.max_angular_speed: float = 360.0
        self.use_physical_controller: bool = True
        self.flying: bool = False
        self.auto_move: bool = False
        self.show_path_cells: bool = False
        self.target_x: float = 0.0
        self.target_y: float = 0.0
        self.target_z: float = 0.0
        self.target_entity_id: str = ""
        self.repath_interval: float = 1.0
        self.arrival_distance: float = 0.5
        self.nav_resolution: int = 512
        self.nav_world_size: float = 500.0

        self._path: list[Vec3] = []
        self._path_index: int = 0
        self._repath_timer: float = 0.0
        self._nav_world: NavWorld = None
        self._last_nav_grid_version: int = -1
        self._pending_req_id: Optional[str] = None
        self._blocked_frames: int = 0
        self._fail_streak: int = 0
        self._last_path_goal = None
        self._path_grid_gid = None
        self._last_cc = None
        self._cc_fixed_seen: int = -1
        self._cc_stall_time: float = 0.0
        self._cc_dead: bool = False

    def on_start(self):
        self._repath_timer = 0.0
        if self.auto_move:
            self._request_path()

    def set_target(self, pos: Vec3):
        self.target_entity_id = ""
        self.target_x = pos.x
        self.target_y = pos.y
        self.target_z = pos.z
        self.auto_move = True
        self._pending_req_id = None
        self._blocked_frames = 0
        self._fail_streak = 0
        self._repath_timer = self.repath_interval
        if self._ensure_nav_world():
            start = self.transform.local_position if self.transform else pos
            self._nav_world.rebuild_grid()
            padding = self.agent_padding if self.agent_padding > 0 else None
            if self.flying:
                self._nav_world.dilate_for_agent(padding if padding is not None else self.agent_radius)
            radius, height, climb, slope = self._effective_nav_params()
            req_id = self._nav_world.find_path_gpu_deferred(
                start, pos, radius, height, self.flying,
                climb, slope, padding
            )
            self._pending_req_id = req_id

    def set_target_entity(self, entity) -> bool:
        if entity is None:
            return False
        tr = entity.transform
        if tr is None:
            return False
        self.target_entity_id = entity.id
        self.target_x = tr.position.x
        self.target_y = tr.position.y
        self.target_z = tr.position.z
        self.auto_move = True
        self._repath_timer = self.repath_interval
        return True

    def stop(self):
        self.auto_move = False
        self._path = []
        self._path_index = 0
        self._pending_req_id = None
        self._blocked_frames = 0
        self._fail_streak = 0
        self._cc_fixed_seen = -1
        self._cc_stall_time = 0.0
        self._cc_dead = False
        self._set_cc_drive(None, None)

    def _btn_set_target(self):
        tr = self.transform
        if tr:
            pos = tr.local_position + Vec3(5, 0, 0)
            self.set_target(pos)

    def _btn_stop(self):
        self.stop()

    def has_path(self) -> bool:
        return len(self._path) > 0 and self._path_index < len(self._path)

    @property
    def current_path(self) -> list[Vec3]:
        return list(self._path)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "agent_radius": self.agent_radius,
            "agent_height": self.agent_height,
            "agent_padding": self.agent_padding,
            "max_climb": self.max_climb,
            "max_slope": self.max_slope,
            "max_speed": self.max_speed,
            "max_angular_speed": self.max_angular_speed,
            "use_physical_controller": self.use_physical_controller,
            "flying": self.flying,
            "auto_move": self.auto_move,
            "show_path_cells": self.show_path_cells,
            "target_entity_id": self.target_entity_id,
            "target_x": self.target_x,
            "target_y": self.target_y,
            "target_z": self.target_z,
            "repath_interval": self.repath_interval,
            "arrival_distance": self.arrival_distance,
            "nav_resolution": self.nav_resolution,
            "nav_world_size": self.nav_world_size,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> NavAgent:
        na = cls()
        na.enabled = data.get("enabled", True)
        na.agent_radius = data.get("agent_radius", 0.5)
        na.agent_height = data.get("agent_height", 2.0)
        na.agent_padding = data.get("agent_padding", 0.0)
        na.max_climb = data.get("max_climb", 0.5)
        na.max_slope = data.get("max_slope", 45.0)
        na.max_speed = data.get("max_speed", 5.0)
        na.max_angular_speed = data.get("max_angular_speed", 360.0)
        na.use_physical_controller = data.get("use_physical_controller", True)
        na.flying = data.get("flying", False)
        na.auto_move = data.get("auto_move", False)
        na.show_path_cells = data.get("show_path_cells", False)
        na.target_entity_id = data.get("target_entity_id", "")
        na.target_x = data.get("target_x", 0.0)
        na.target_y = data.get("target_y", 0.0)
        na.target_z = data.get("target_z", 0.0)
        na.repath_interval = data.get("repath_interval", 1.0)
        na.arrival_distance = data.get("arrival_distance", 0.5)
        na.nav_resolution = data.get("nav_resolution", 512)
        na.nav_world_size = data.get("nav_world_size", 500.0)
        return na
