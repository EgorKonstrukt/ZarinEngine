# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional
from core.ecs import Entity


class NetworkManagerSyncMixin:

    def spawn_entity(self, entity: Entity, owner_id: int | None = None) -> int:
        scene = self._get_scene()
        if scene is None or entity is None:
            return -1
        if entity._scene is None:
            try:
                scene.add_entity(entity)
            except Exception:
                pass
        ident = entity.get_component_by_name("NetworkIdentity")
        if ident is None:
            from core.components.network.network_identity import NetworkIdentity
            ident = NetworkIdentity()
            entity.add_component(ident)
        if ident.net_id >= 0:
            return int(ident.net_id)
        if self.is_server:
            nid = self._alloc_net_id()
            ident.net_id = nid
            ident.network_id = nid
            ident.owner_id = int(owner_id) if owner_id is not None else int(self.local_id)
            ident._refresh_is_local()
            self._net_to_entity[nid] = entity.id
            self._entity_to_net[entity.id] = nid
            payload = {"net_id": nid, "owner_id": ident.owner_id, "prefab_id": ident.prefab_id, "entity": entity.serialize()}
            try:
                from core.network.transp import get_transport
                from core.network.protocol import MessageType
                get_transport().broadcast(MessageType.NET_SPAWN, payload)
            except Exception:
                pass
            return nid
        else:
            if not self.is_connected:
                return -1
            payload = {"prefab_id": ident.prefab_id, "entity": entity.serialize(), "requester": int(self.local_id)}
            try:
                from core.network.transp import get_transport
                from core.network.protocol import MessageType
                get_transport().send(MessageType.NET_SPAWN_REQUEST, payload)
            except Exception:
                pass
            return -1

    def spawn_prefab(self, prefab_path: str, pos=None, rot=None, owner_id: int | None = None):
        scene = self._get_scene()
        if scene is None:
            return None
        prefab_path = str(prefab_path).replace("\\", "/")
        if not self.is_server and self.is_connected:
            ident_tmp = None
            entity_tmp = None
            payload_entity = None
            if prefab_path.endswith(".zpep"):
                try:
                    from core.ecs.prefabp import Prefab
                    from core.ecs import ComponentRegistry as CR
                    prefab = Prefab.load(prefab_path)
                    if prefab is not None:
                        spawned = prefab.instantiate(scene, CR)
                        if spawned:
                            entity_tmp = spawned[0]
                            for extra in spawned[1:]:
                                try:
                                    scene.remove_entity(extra.id)
                                except Exception:
                                    pass
                            payload_entity = entity_tmp.serialize()
                            scene.remove_entity(entity_tmp.id)
                except Exception:
                    pass
            if payload_entity is None:
                try:
                    from core.ecs import Entity as _E
                    from core.components.transform.tr import Transform as _T
                    from core.maths.math3d import Vec3 as _V, Quat as _Q
                    tmp = _E("SpawnReq")
                    t = _T()
                    if pos is not None:
                        if isinstance(pos, _V):
                            t.local_position = pos
                        elif isinstance(pos, (list, tuple)):
                            t.local_position = _V(float(pos[0]), float(pos[1]), float(pos[2]))
                    payload_entity = tmp.serialize()
                except Exception:
                    payload_entity = {"id": "tmp"}
            try:
                from core.network.transp import get_transport
                from core.network.protocol import MessageType
                get_transport().send(MessageType.NET_SPAWN_REQUEST, {"prefab_id": prefab_path, "entity": payload_entity, "requester": int(self.local_id), "pos": list(pos.to_list()) if hasattr(pos, "to_list") else pos, "rot": list(rot.to_list()) if hasattr(rot, "to_list") else rot})
            except Exception:
                pass
            return None
        entity: Optional[Entity] = None
        if prefab_path.endswith(".zpep"):
            try:
                from core.ecs.prefabp import Prefab
                from core.ecs import ComponentRegistry
                prefab = Prefab.load(prefab_path)
                if prefab is not None:
                    spawned = prefab.instantiate(scene, ComponentRegistry)
                    if spawned:
                        entity = spawned[0]
                        for extra in spawned[1:]:
                            pass
                else:
                    entity = scene.create_entity("Spawned")
                    from core.components.transform.tr import Transform
                    from core.maths.math3d import Vec3, Quat
                    t = Transform()
                    if pos is not None:
                        if isinstance(pos, Vec3):
                            t.local_position = pos
                        else:
                            t.local_position = Vec3(float(pos[0]), float(pos[1]), float(pos[2]))
                    if rot is not None and hasattr(t, "local_rotation"):
                        if isinstance(rot, Quat):
                            t.local_rotation = rot
                        else:
                            try:
                                t.local_rotation = Quat(float(rot[0]), float(rot[1]), float(rot[2]), float(rot[3]))
                            except Exception:
                                pass
                    entity.add_component(t)
            except Exception:
                entity = scene.create_entity("Spawned")
                try:
                    from core.components.transform.tr import Transform
                    from core.maths.math3d import Vec3, Quat
                    t = Transform()
                    if pos is not None:
                        if isinstance(pos, Vec3):
                            t.local_position = pos
                        else:
                            t.local_position = Vec3(float(pos[0]), float(pos[1]), float(pos[2]))
                    entity.add_component(t)
                except Exception:
                    pass
        else:
            entity = scene.create_entity("Spawned")
            try:
                from core.components.transform.tr import Transform
                from core.maths.math3d import Vec3
                t = Transform()
                if pos is not None:
                    if isinstance(pos, Vec3):
                        t.local_position = pos
                    else:
                        t.local_position = Vec3(float(pos[0]), float(pos[1]), float(pos[2]))
                entity.add_component(t)
            except Exception:
                pass
        if entity is None:
            return None
        ident = entity.get_component_by_name("NetworkIdentity")
        if ident is None:
            from core.components.network.network_identity import NetworkIdentity
            ident = NetworkIdentity()
            ident.prefab_id = prefab_path
            entity.add_component(ident)
        else:
            ident.prefab_id = prefab_path
        if pos is not None and entity.transform is not None:
            try:
                from core.maths.math3d import Vec3, Quat
                tr = entity.transform
                if isinstance(pos, Vec3):
                    tr.local_position = pos
                elif isinstance(pos, (list, tuple)):
                    tr.local_position = Vec3(float(pos[0]), float(pos[1]), float(pos[2]))
                if rot is not None:
                    if isinstance(rot, Quat):
                        tr.local_rotation = rot
                    elif isinstance(rot, (list, tuple)):
                        tr.local_rotation = Quat(float(rot[0]), float(rot[1]), float(rot[2]), float(rot[3]))
            except Exception:
                pass
        nid = self.spawn_entity(entity, owner_id=owner_id)
        if nid < 0 and not self.is_server:
            try:
                scene.remove_entity(entity.id)
            except Exception:
                pass
            return None
        return entity

    def _handle_spawn(self, data: dict):
        if self.is_server and int(data.get("_sender", -1)) != 0 and int(data.get("_sender", -1)) != self.local_id:
            return
        scene = self._get_scene()
        if scene is None:
            return
        net_id = int(data.get("net_id", -1))
        if net_id < 0:
            return
        if net_id in self._net_to_entity:
            return
        if net_id >= 1000000:
            return
        owner_id = int(data.get("owner_id", data.get("_sender", -1)))
        prefab_id = str(data.get("prefab_id", ""))[:256]
        entity_data = data.get("entity")
        ent: Optional[Entity] = None
        if entity_data:
            try:
                from core.ecs import ComponentRegistry
                ent = Entity.deserialize(dict(entity_data), ComponentRegistry)
                if ent.id in scene._entities:
                    return
                scene.add_entity(ent)
            except Exception:
                return
        else:
            return
        ident = ent.get_component_by_name("NetworkIdentity")
        if ident is None:
            from core.components.network.network_identity import NetworkIdentity
            ident = NetworkIdentity()
            ent.add_component(ident)
        ident.net_id = net_id
        ident.network_id = net_id
        ident.owner_id = owner_id
        ident.prefab_id = prefab_id
        ident._refresh_is_local()
        self._net_to_entity[net_id] = ent.id
        self._entity_to_net[ent.id] = net_id
        if net_id >= self._next_net_id:
            self._next_net_id = net_id + 1

    def _handle_despawn(self, data: dict):
        sender = int(data.get("_sender", -1))
        net_id = int(data.get("net_id", -1))
        ent = self._find_entity_by_net_id(net_id)
        if ent is None:
            return
        if not self.is_server and sender != 0 and sender != -1:
            ident = ent.get_component_by_name("NetworkIdentity")
            if ident is not None and ident.owner_id != sender:
                return
        scene = self._get_scene()
        self._net_to_entity.pop(net_id, None)
        self._entity_to_net.pop(ent.id, None)
        if scene:
            try:
                scene.remove_entity(ent.id)
            except Exception:
                pass

    def _handle_spawn_request(self, data: dict):
        if not self.is_server:
            return
        requester = int(data.get("requester", data.get("_sender", -1)))
        if requester < 0:
            return
        prefab_id = str(data.get("prefab_id", ""))[:256]
        entity_data = data.get("entity")
        scene = self._get_scene()
        if scene is None:
            return
        if not prefab_id and not entity_data:
            return
        ent: Optional[Entity] = None
        if entity_data:
            try:
                from core.ecs import ComponentRegistry
                ent = Entity.deserialize(dict(entity_data), ComponentRegistry)
                if ent.id in scene._entities:
                    ent._id = str(scene._generate_id()) if hasattr(scene, "_generate_id") else ent.id
                scene.add_entity(ent)
                try:
                    from core.maths.math3d import Vec3, Quat
                    pos = data.get("pos")
                    rot = data.get("rot")
                    if pos is not None and ent.transform is not None:
                        if isinstance(pos, (list, tuple)) and len(pos) == 3:
                            ent.transform.local_position = Vec3(float(pos[0]), float(pos[1]), float(pos[2]))
                    if rot is not None and ent.transform is not None:
                        if isinstance(rot, (list, tuple)) and len(rot) == 4:
                            ent.transform.local_rotation = Quat(float(rot[0]), float(rot[1]), float(rot[2]), float(rot[3]))
                except Exception:
                    pass
            except Exception:
                return
        else:
            ent = self.spawn_prefab(prefab_id, owner_id=requester)
            if ent is None:
                return
            return
        ident = ent.get_component_by_name("NetworkIdentity")
        if ident is None:
            from core.components.network.network_identity import NetworkIdentity
            ident = NetworkIdentity()
            ent.add_component(ident)
        nid = self._alloc_net_id()
        ident.net_id = nid
        ident.network_id = nid
        ident.owner_id = requester
        ident.prefab_id = prefab_id
        ident._refresh_is_local()
        self._net_to_entity[nid] = ent.id
        self._entity_to_net[ent.id] = nid
        payload = {"net_id": nid, "owner_id": requester, "prefab_id": prefab_id, "entity": ent.serialize()}
        try:
            from core.network.transp import get_transport
            from core.network.protocol import MessageType
            get_transport().broadcast(MessageType.NET_SPAWN, payload)
        except Exception:
            pass

    def _handle_rpc(self, data: dict):
        net_id = int(data.get("net_id", -1))
        method = str(data.get("method", ""))[:64]
        if not method:
            return
        args = data.get("args", {})
        if not isinstance(args, dict):
            return
        target = data.get("target", None)
        if target is not None:
            try:
                from core.network.transp import get_transport
                if int(target) != int(get_transport().local_id):
                    return
            except Exception:
                pass
        rpc_type = str(data.get("rpc_type", ""))
        if rpc_type == "server" and not self.is_server:
            ent = self._find_entity_by_net_id(net_id)
            if ent is None:
                return
            from core.network.rpc import invoke_rpc
            invoke_rpc(ent, method, args, sender=int(data.get("_sender", -1)))
            return
        if rpc_type == "client" and self.is_server:
            return
        ent = self._find_entity_by_net_id(net_id)
        if ent is None:
            return
        from core.network.rpc import invoke_rpc
        invoke_rpc(ent, method, args, sender=int(data.get("_sender", -1)))

    def _handle_owner_change(self, data: dict):
        net_id = int(data.get("net_id", -1))
        ent = self._find_entity_by_net_id(net_id)
        if ent is None:
            return
        ident = ent.get_component_by_name("NetworkIdentity")
        if ident is None:
            return
        sender = int(data.get("_sender", -1))
        if "requester" in data:
            if not self.is_server:
                return
            requester = int(data.get("requester", -1))
            ident.apply_owner_change(requester)
            try:
                from core.network.transp import get_transport
                from core.network.protocol import MessageType
                get_transport().broadcast(MessageType.NET_OWNER_CHANGE, {"net_id": net_id, "owner_id": requester})
            except Exception:
                pass
        else:
            if not self.is_server and sender != 0:
                return
            new_owner = int(data.get("owner_id", -1))
            ident.apply_owner_change(new_owner)
