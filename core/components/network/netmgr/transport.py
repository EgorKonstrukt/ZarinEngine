# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
from core.ecs import Entity


class NetworkManagerTransportMixin:

    @property
    def is_server(self) -> bool:
        try:
            from core.network.transp import get_transport
            return get_transport().is_server
        except Exception:
            return False

    @property
    def is_client(self) -> bool:
        try:
            from core.network.transp import get_transport
            return get_transport().is_client
        except Exception:
            return False

    @property
    def is_connected(self) -> bool:
        try:
            from core.network.transp import get_transport
            return get_transport().is_connected
        except Exception:
            return False

    @property
    def local_id(self) -> int:
        try:
            from core.network.transp import get_transport
            return get_transport().local_id
        except Exception:
            return -1

    @property
    def peer_count(self) -> int:
        try:
            from core.network.transp import get_transport
            return get_transport().peer_count
        except Exception:
            return 0

    def host(self, port: int | None = None, max_players: int | None = None):
        p = int(port) if port is not None else int(self.port)
        mp = int(max_players) if max_players is not None else int(self.max_players)
        mp = max(1, min(64, mp))
        self.max_players = mp
        try:
            from core.network.transp import get_transport
            from core.foundation.logger import Logger
            ok = get_transport().host("0.0.0.0", p, max_players=mp)
            if ok:
                self._next_net_id = 1
                self._net_to_entity.clear()
                self._entity_to_net.clear()
                self._register_existing()
                Logger.info(f"NetworkManager hosting on {p} max_players={mp}")
            else:
                from core.foundation.logger import Logger as _L
                _L.error(f"NetworkManager host failed on {p}")
            return bool(ok)
        except Exception as e:
            try:
                from core.foundation.logger import Logger as _L2
                _L2.error(f"NetworkManager host exception: {e}")
            except Exception:
                pass
            return False

    def connect(self, address: str | None = None, port: int | None = None, name: str | None = None):
        addr = str(address) if address is not None else str(self.host_address)
        p = int(port) if port is not None else int(self.port)
        n = str(name) if name is not None else "Player"
        try:
            from core.network.transp import get_transport
            ok = get_transport().connect(addr, p, n)
            self._net_to_entity.clear()
            self._entity_to_net.clear()
            return bool(ok)
        except Exception:
            return False

    def disconnect(self):
        try:
            from core.network.transp import get_transport
            get_transport().disconnect()
        except Exception:
            pass
        self._net_to_entity.clear()
        self._entity_to_net.clear()

    def despawn(self, net_id: int):
        ident_nid = int(net_id)
        ent = self._find_entity_by_net_id(ident_nid)
        if ent is None:
            return
        scene = self._get_scene()
        ident = ent.get_component_by_name("NetworkIdentity")
        if ident is not None and not self.is_server and not ident.is_owner:
            return
        if self.is_server:
            try:
                from core.network.transp import get_transport
                from core.network.protocol import MessageType
                get_transport().broadcast(MessageType.NET_DESPAWN, {"net_id": ident_nid})
            except Exception:
                pass
        elif self.is_client:
            try:
                from core.network.transp import get_transport
                from core.network.protocol import MessageType
                get_transport().send(MessageType.NET_DESPAWN, {"net_id": ident_nid})
                return
            except Exception:
                pass
        self._net_to_entity.pop(ident_nid, None)
        self._entity_to_net.pop(ent.id, None)
        if scene:
            try:
                scene.remove_entity(ent.id)
            except Exception:
                pass

    def despawn_entity(self, entity: Entity):
        ident = entity.get_component_by_name("NetworkIdentity")
        if ident is None or ident.net_id < 0:
            scene = self._get_scene()
            if scene:
                try:
                    scene.remove_entity(entity.id)
                except Exception:
                    pass
            return
        self.despawn(int(ident.net_id))

    def send_rpc(self, net_id: int, method: str, args: dict | None = None, target: int | None = None):
        payload = {"net_id": int(net_id), "method": str(method), "args": dict(args) if args else {}, "t": time.time()}
        if target is not None:
            payload["target"] = int(target)
        try:
            from core.network.transp import get_transport
            from core.network.protocol import MessageType
            if target is not None and self.is_server:
                get_transport().send_to(int(target), MessageType.NET_RPC, payload)
            elif self.is_server or target is None:
                get_transport().broadcast(MessageType.NET_RPC, payload)
            else:
                get_transport().send(MessageType.NET_RPC, payload)
        except Exception:
            pass

    def _sync_new_peer(self, peer_id: int):
        if not self.is_server:
            return
        scene = self._get_scene()
        if scene is None:
            return
        try:
            from core.network.transp import get_transport
            from core.network.protocol import MessageType
            t = get_transport()
            for nid, eid in list(self._net_to_entity.items()):
                ent = scene.get_entity(eid)
                if ent is None:
                    continue
                ident = ent.get_component_by_name("NetworkIdentity")
                owner = ident.owner_id if ident else -1
                payload = {"net_id": nid, "owner_id": owner, "prefab_id": ident.prefab_id if ident else "", "entity": ent.serialize()}
                t.send_to(peer_id, MessageType.NET_SPAWN, payload)
        except Exception:
            pass
