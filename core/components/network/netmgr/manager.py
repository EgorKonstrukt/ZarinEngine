# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from core.ecs import Component, ComponentRegistry, Entity, Scene
from core.components.inspector_meta import FieldType, InspectorField
from core.components.network.netmgr.transport import NetworkManagerTransportMixin
from core.components.network.netmgr.sync import NetworkManagerSyncMixin


@ComponentRegistry.register
class NetworkManager(NetworkManagerTransportMixin, NetworkManagerSyncMixin, Component):
    _icon = "NetworkManager.png"
    _gizmo_icon_color = (255, 200, 50)
    _gizmo_icon_label = "M"
    _instance: Optional[NetworkManager] = None

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Network Manager", FieldType.HEADER),
            InspectorField("port", "Port", FieldType.INT, min_val=1024, max_val=65535),
            InspectorField("max_players", "Max Players", FieldType.INT, min_val=1, max_val=64),
            InspectorField("server_name", "Server Name", FieldType.STRING),
            InspectorField("host_address", "Host Address", FieldType.STRING),
            InspectorField("player_prefab", "Player Prefab", FieldType.RESOURCE_PATH, file_filter="Prefab (*.zpep)"),
            InspectorField("auto_spawn_player", "Auto Spawn Player", FieldType.BOOL),
            InspectorField("tick_rate", "Tick Rate", FieldType.FLOAT, min_val=1.0, max_val=60.0),
            InspectorField("show_debug", "Show Debug", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.port: int = 7777
        self.max_players: int = 16
        self.server_name: str = "Zarin Server"
        self.host_address: str = "127.0.0.1"
        self.player_prefab: str = ""
        self.auto_spawn_player: bool = True
        self.tick_rate: float = 20.0
        self.show_debug: bool = False
        self._next_net_id: int = 1
        self._net_to_entity: dict[int, str] = {}
        self._entity_to_net: dict[str, int] = {}
        self._pending_spawn_requests: list[dict] = []

    @classmethod
    def get(cls) -> Optional[NetworkManager]:
        if cls._instance is not None:
            return cls._instance
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            if eng and eng.scene:
                for e in eng.scene.get_all_entities():
                    c = e.get_component_by_name("NetworkManager")
                    if c is not None:
                        return c
        except Exception:
            pass
        return None

    def _get_scene(self) -> Optional[Scene]:
        ent = self._entity
        if ent is not None and ent._scene is not None:
            return ent._scene
        try:
            from core.engine.eng import Engine
            eng = Engine.instance()
            if eng:
                return eng.scene
        except Exception:
            pass
        return None

    def _register_existing(self):
        scene = self._get_scene()
        if scene is None:
            return
        for e in scene.get_all_entities():
            ident = e.get_component_by_name("NetworkIdentity")
            if ident is not None and ident.net_id >= 0:
                self._net_to_entity[int(ident.net_id)] = e.id
                self._entity_to_net[e.id] = int(ident.net_id)
                if ident.net_id >= self._next_net_id:
                    self._next_net_id = int(ident.net_id) + 1

    def _alloc_net_id(self) -> int:
        nid = int(self._next_net_id)
        self._next_net_id += 1
        return nid

    def _find_entity_by_net_id(self, net_id: int) -> Optional[Entity]:
        eid = self._net_to_entity.get(int(net_id))
        if eid is not None:
            scene = self._get_scene()
            if scene:
                ent = scene.get_entity(eid)
                if ent is not None:
                    return ent
        scene = self._get_scene()
        if scene is None:
            return None
        for e in scene.get_all_entities():
            ident = e.get_component_by_name("NetworkIdentity")
            if ident is not None and int(ident.net_id) == int(net_id):
                self._net_to_entity[int(net_id)] = e.id
                self._entity_to_net[e.id] = int(net_id)
                return e
        return None

    def on_awake(self):
        NetworkManager._instance = self
        self._register_existing()

    def on_destroy(self):
        if NetworkManager._instance is self:
            NetworkManager._instance = None

    def on_update(self, dt: float):
        if NetworkManager._instance is None:
            NetworkManager._instance = self
        try:
            from core.network.transp import get_transport
            from core.network.protocol import MessageType
            t = get_transport()
            msgs = t.poll()
            for msg_type, data in msgs:
                if msg_type == MessageType.NET_SPAWN:
                    self._handle_spawn(data)
                elif msg_type == MessageType.NET_DESPAWN:
                    self._handle_despawn(data)
                elif msg_type == MessageType.NET_SPAWN_REQUEST:
                    self._handle_spawn_request(data)
                elif msg_type == MessageType.NET_TRANSFORM:
                    nid = int(data.get("net_id", -1))
                    ent = self._find_entity_by_net_id(nid)
                    if ent:
                        comp = ent.get_component_by_name("NetworkTransform")
                        if comp:
                            comp.apply_snapshot(data)
                elif msg_type == MessageType.NET_RIGIDBODY:
                    nid = int(data.get("net_id", -1))
                    ent = self._find_entity_by_net_id(nid)
                    if ent:
                        comp = ent.get_component_by_name("NetworkRigidbody")
                        if comp:
                            comp.apply_snapshot(data)
                elif msg_type == MessageType.NET_ANIMATOR:
                    nid = int(data.get("net_id", -1))
                    ent = self._find_entity_by_net_id(nid)
                    if ent:
                        comp = ent.get_component_by_name("NetworkAnimator")
                        if comp:
                            comp.apply_snapshot(data)
                elif msg_type == MessageType.NET_RPC:
                    if "rpc" in data:
                        try:
                            from core.engine.eng import Engine
                            eng = Engine.instance()
                            if eng:
                                plug = eng.plugin_manager.get_plugin("NetworkPlugin") if hasattr(eng, "plugin_manager") else None
                                if plug and hasattr(plug, "_dispatch_rpc"):
                                    plug._dispatch_rpc(data)
                                    continue
                        except Exception:
                            pass
                    self._handle_rpc(data)
                elif msg_type == MessageType.NET_OWNER_CHANGE:
                    self._handle_owner_change(data)
                elif msg_type == MessageType.NET_VARIABLES:
                    nid = int(data.get("net_id", -1))
                    ent = self._find_entity_by_net_id(nid)
                    if ent:
                        comp = ent.get_component_by_name("NetworkVariables")
                        if comp:
                            comp.apply_snapshot(data)
                        else:
                            vars_data = data.get("vars", data.get("data", {}))
                            if isinstance(vars_data, dict):
                                for comp_key, props in vars_data.items():
                                    c = ent.get_component_by_name(comp_key)
                                    if c and isinstance(props, dict):
                                        for k, v in props.items():
                                            try:
                                                setattr(c, k, v)
                                            except Exception:
                                                pass
                elif msg_type == MessageType.NET_KICK:
                    self.disconnect()
                elif msg_type == MessageType.PEER_JOINED:
                    pid = int(data.get("id", -1))
                    if self.is_server and pid >= 0:
                        self._sync_new_peer(pid)
                        if self.auto_spawn_player and self.player_prefab:
                            pos = None
                            try:
                                from core.maths.math3d import Vec3
                                import random
                                pos = Vec3(float(random.uniform(-2, 2)), 0.0, float(random.uniform(-2, 2)))
                            except Exception:
                                pos = None
                            self.spawn_prefab(self.player_prefab, pos=pos, owner_id=pid)
                elif msg_type == MessageType.LEAVE:
                    nid = int(data.get("id", -1))
                    to_remove = []
                    for net_id, eid in list(self._net_to_entity.items()):
                        ent = self._find_entity_by_net_id(net_id)
                        if ent:
                            ident = ent.get_component_by_name("NetworkIdentity")
                            if ident and ident.owner_id == nid:
                                to_remove.append(net_id)
                    for net_id in to_remove:
                        self.despawn(net_id)
                elif msg_type == MessageType.JOINED:
                    pass
        except Exception:
            pass

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "port": self.port,
            "max_players": self.max_players,
            "server_name": self.server_name,
            "host_address": self.host_address,
            "player_prefab": self.player_prefab,
            "auto_spawn_player": self.auto_spawn_player,
            "tick_rate": self.tick_rate,
            "show_debug": self.show_debug,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> NetworkManager:
        inst = cls()
        inst.enabled = data.get("enabled", True)
        inst.port = int(data.get("port", 7777))
        inst.max_players = int(data.get("max_players", 16))
        inst.server_name = str(data.get("server_name", "Zarin Server"))
        inst.host_address = str(data.get("host_address", "127.0.0.1"))
        inst.player_prefab = str(data.get("player_prefab", ""))
        inst.auto_spawn_player = bool(data.get("auto_spawn_player", True))
        inst.tick_rate = float(data.get("tick_rate", 20.0))
        inst.show_debug = bool(data.get("show_debug", False))
        return inst
