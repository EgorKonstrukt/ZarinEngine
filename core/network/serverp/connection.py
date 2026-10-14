# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import asyncio
import socket
import time
import uuid
from typing import Optional
from core.foundation.logger import Logger
from core.network.protocol import MessageType, make_msg, PROTOCOL_VERSION
from .base import CollabClientInfo, _COLORS, _ServerBase


class CollabServer(_ServerBase):
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            sock = writer.get_extra_info("socket")
            if sock is not None:
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass
        except Exception:
            pass
        addr = writer.get_extra_info("peername", ("unknown", 0))
        try:
            addr_str = f"{addr[0]}:{addr[1]}"
        except Exception:
            addr_str = "unknown"
        peer_id = None
        try:
            msg_type, data = await self._read_frame(reader)
            if msg_type != MessageType.JOIN:
                try:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                except Exception:
                    pass
                return
            async with self._lock:
                if len(self._clients) >= self._max_clients:
                    try:
                        writer.write(make_msg(MessageType.NET_KICK, {"reason": "server_full"}))
                        await writer.drain()
                    except Exception:
                        pass
                    try:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except Exception:
                            pass
                    except Exception:
                        pass
                    return
            if not self._auth_ok(data):
                try:
                    writer.write(make_msg(MessageType.AUTH_FAIL, {"reason": "auth"}))
                    await writer.drain()
                except Exception:
                    pass
                try:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                except Exception:
                    pass
                return
            try:
                client_version = int(data.get("version", 1))
            except Exception:
                client_version = 1
            if client_version > PROTOCOL_VERSION + 2:
                try:
                    writer.write(make_msg(MessageType.AUTH_FAIL, {"reason": "version"}))
                    await writer.drain()
                except Exception:
                    pass
                try:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                except Exception:
                    pass
                return
            name = str(data.get("name", f"User_{len(self._clients)+1}"))[:32] or "User"
            peer_id = f"peer_{uuid.uuid4().hex[:12]}"
            color = _COLORS[self._color_idx % len(_COLORS)]
            self._color_idx += 1
            info = CollabClientInfo(reader, writer, peer_id, name, color, addr_str)
            async with self._lock:
                self._clients[peer_id] = info
            join_data = {"id": peer_id, "name": name, "color": color}
            await self._broadcast_and_drain(MessageType.PEER_JOINED, join_data, exclude=peer_id)
            current_peers = [
                {"id": c.peer_id, "name": c.name, "color": c.color}
                for c in list(self._clients.values())
            ]
            stored_scene = self._scene_data or data.get("scene")
            init_data = {
                "your_id": peer_id,
                "your_color": color,
                "peers": current_peers,
                "scene": stored_scene,
                "version": int(PROTOCOL_VERSION),
                "room": self._room,
            }
            try:
                writer.write(make_msg(MessageType.JOINED, init_data))
                await writer.drain()
            except Exception:
                async with self._lock:
                    self._clients.pop(peer_id, None)
                return
            if self._scene_data is None and data.get("scene"):
                self._scene_data = data.get("scene")
            Logger.info(f"Collab peer joined: {name} ({addr_str}) as {peer_id}")
            await self._client_loop(info)
        except (asyncio.IncompleteReadError, ConnectionResetError, ValueError):
            pass
        except Exception as e:
            Logger.error(f"Collab client error: {e}")
        finally:
            if peer_id:
                async with self._lock:
                    existed = peer_id in self._clients
                    if existed:
                        del self._clients[peer_id]
                if existed:
                    self._broadcast(MessageType.LEAVE, {"id": peer_id}, exclude=peer_id)
                try:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                except Exception:
                    pass
            Logger.info(f"Collab peer left: {peer_id}")

    async def _client_loop(self, info: CollabClientInfo):
        reader = info.reader
        while self._running:
            try:
                msg_type, data = await self._read_frame(reader)
                info.last_seen = time.monotonic()
                if not self._check_rate(info):
                    continue
                await self._route_message(info, msg_type, data)
            except (asyncio.IncompleteReadError, ConnectionResetError, ValueError, asyncio.TimeoutError):
                break
            except Exception:
                continue

    async def _route_message(self, info: CollabClientInfo, msg_type: int, data: dict):
        if not isinstance(data, dict):
            return
        if msg_type == MessageType.CURSOR:
            data["id"] = info.peer_id
            self._broadcast(MessageType.CURSOR_UPDATE, data, exclude=info.peer_id)
        elif msg_type == MessageType.CAMERA:
            data["id"] = info.peer_id
            self._broadcast(MessageType.CAMERA_UPDATE, data, exclude=info.peer_id)
        elif msg_type == MessageType.ENTITY_CREATE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.ENTITY_CREATED, data, exclude=info.peer_id)
        elif msg_type == MessageType.ENTITY_DELETE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.ENTITY_DELETED, data, exclude=info.peer_id)
        elif msg_type == MessageType.TRANSFORM_UPDATE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.TRANSFORM_UPDATED, data, exclude=info.peer_id)
        elif msg_type == MessageType.SELECTION:
            data["id"] = info.peer_id
            self._broadcast(MessageType.SELECTION_UPDATE, data, exclude=info.peer_id)
        elif msg_type == MessageType.COMPONENT_UPDATE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.COMPONENT_UPDATED, data, exclude=info.peer_id)
        elif msg_type == MessageType.COMPONENT_ADD:
            data["id"] = info.peer_id
            self._broadcast(MessageType.COMPONENT_ADDED, data, exclude=info.peer_id)
        elif msg_type == MessageType.COMPONENT_REMOVE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.COMPONENT_REMOVED, data, exclude=info.peer_id)
        elif msg_type == MessageType.PING:
            timestamp = data.get("t", 0)
            try:
                info.writer.write(make_msg(MessageType.PONG, {"t": timestamp}))
                await info.writer.drain()
            except Exception:
                pass
        elif msg_type == MessageType.PLAY_MODE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.PLAY_MODE, data, exclude=info.peer_id)
        elif msg_type == MessageType.GIZMO_STATE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.GIZMO_STATE_UPDATE, data, exclude=info.peer_id)
        elif msg_type == MessageType.SCENE_SNAPSHOT_REQ:
            scene = self._scene_data
            if scene:
                snap_data = {"scene": scene, "requesting_id": info.peer_id}
                try:
                    info.writer.write(make_msg(MessageType.SCENE_SNAPSHOT, snap_data))
                    await info.writer.drain()
                except Exception:
                    pass
        elif msg_type == MessageType.ASSET_LIST_REQ:
            data["id"] = info.peer_id
            self._broadcast(MessageType.ASSET_LIST_REQ, data, exclude=info.peer_id)
        elif msg_type == MessageType.ASSET_LIST:
            data["id"] = info.peer_id
            target = str(data.get("target", ""))
            if target:
                await self._send_to_one(target, MessageType.ASSET_LIST, data)
            else:
                self._broadcast(MessageType.ASSET_LIST, data, exclude=info.peer_id)
        elif msg_type == MessageType.ASSET_SYNC:
            data["id"] = info.peer_id
            target = str(data.get("target", ""))
            if target:
                await self._send_to_one(target, MessageType.ASSET_SYNC, data)
            else:
                self._broadcast(MessageType.ASSET_SYNC, data, exclude=info.peer_id)
        elif msg_type == MessageType.ASSET_WATCH:
            data["id"] = info.peer_id
            self._broadcast(MessageType.ASSET_WATCH, data, exclude=info.peer_id)
        elif msg_type == MessageType.ASSET_DELETE:
            data["id"] = info.peer_id
            self._broadcast(MessageType.ASSET_DELETE, data, exclude=info.peer_id)
        elif msg_type == MessageType.ASSET_REQUEST:
            data["id"] = info.peer_id
            target = str(data.get("target", ""))
            if target:
                await self._send_to_one(target, MessageType.ASSET_REQUEST, data)
            else:
                self._broadcast(MessageType.ASSET_REQUEST, data, exclude=info.peer_id)
        elif msg_type == MessageType.CHUNK:
            data["id"] = info.peer_id
            target = str(data.get("target", ""))
            if target:
                await self._send_to_one(target, MessageType.CHUNK, data)
            else:
                self._broadcast(MessageType.CHUNK, data, exclude=info.peer_id)
        elif msg_type == MessageType.ROOM_INFO:
            try:
                info.writer.write(make_msg(MessageType.ROOM_INFO, {"room": self._room, "locked": bool(self._password), "peers": len(self._clients), "version": int(PROTOCOL_VERSION)}))
                await info.writer.drain()
            except Exception:
                pass
        else:
            data["id"] = info.peer_id
            self._broadcast(msg_type, data, exclude=info.peer_id)
