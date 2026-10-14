# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import asyncio
import threading
import time
import uuid
from typing import Optional
import msgpack
from core.foundation.logger import Logger
from core.network.protocol import PROTOCOL_VERSION, normalize_room
from .relay import _RELAY_COLORS, _Room, _RoomPeer, _route_pair


class RelayServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765, max_rooms: int = 256, max_peers_per_room: int = 32):
        self._host = str(host or "0.0.0.0")
        self._port = int(port)
        self._max_rooms = max(1, int(max_rooms))
        self._max_peers = max(1, int(max_peers_per_room))
        self._rooms: dict[str, _Room] = {}
        self._ws_server = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    @property
    def running(self) -> bool:
        return bool(self._running)

    @property
    def room_count(self) -> int:
        return len(self._rooms)

    def peer_count(self, room: str = "") -> int:
        if room:
            r = self._rooms.get(normalize_room(room))
            return len(r.peers) if r else 0
        total = 0
        for r in self._rooms.values():
            total += len(r.peers)
        return total

    def start_sync(self, timeout: float = 5.0) -> bool:
        if self._running:
            return True
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=timeout)
        return bool(self._running)

    def stop_sync(self):
        self._running = False
        lp = self._loop
        if lp is not None and lp.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self._async_stop(), lp)
                try:
                    fut.result(timeout=3.0)
                except Exception:
                    pass
            except Exception:
                pass
            try:
                lp.call_soon_threadsafe(lp.stop)
            except Exception:
                pass
        th = self._thread
        if th is not None and th.is_alive():
            try:
                th.join(timeout=3.0)
            except Exception:
                pass
        self._thread = None
        self._loop = None

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_start())
            self._ready.set()
            self._loop.run_forever()
        except Exception as e:
            Logger.error(f"RelayServer error: {e}")
            self._ready.set()

    async def _async_start(self):
        from websockets.asyncio.server import serve
        self._ws_server = await serve(
            self._handle_ws,
            self._host,
            self._port,
            max_size=8 * 1024 * 1024,
            ping_interval=20.0,
            ping_timeout=20.0,
        )
        self._running = True
        Logger.info(f"RelayServer listening on {self._host}:{self._port}")

    async def _async_stop(self):
        self._running = False
        if self._ws_server is not None:
            try:
                self._ws_server.close()
                await self._ws_server.wait_closed()
            except Exception:
                pass
            self._ws_server = None
        Logger.info("RelayServer stopped")

    async def _send(self, ws, obj: dict):
        try:
            raw = msgpack.packb(obj, use_bin_type=True)
            await ws.send(raw)
        except Exception:
            pass

    async def _handle_ws(self, ws):
        peer_id: Optional[str] = None
        room_code = ""
        try:
            async for raw in ws:
                try:
                    if isinstance(raw, str):
                        raw = raw.encode("utf-8")
                    obj = msgpack.unpackb(raw, raw=False)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                op = str(obj.get("op", ""))
                if op == "create" or op == "join":
                    if peer_id is not None:
                        continue
                    room_code = normalize_room(obj.get("room", ""))
                    if not room_code:
                        await self._send(ws, {"op": "fail", "reason": "room"})
                        break
                    token = str(obj.get("token", ""))
                    name = str(obj.get("name", "User"))[:32] or "User"
                    try:
                        ver = int(obj.get("version", 1))
                    except Exception:
                        ver = 1
                    if ver > int(PROTOCOL_VERSION) + 2:
                        await self._send(ws, {"op": "fail", "reason": "version"})
                        break
                    room = self._rooms.get(room_code)
                    if room is None:
                        if len(self._rooms) >= self._max_rooms:
                            await self._send(ws, {"op": "fail", "reason": "busy"})
                            break
                        room = _Room(room_code, token)
                        self._rooms[room_code] = room
                    if room.token and token != room.token:
                        await self._send(ws, {"op": "fail", "reason": "auth"})
                        break
                    if len(room.peers) >= self._max_peers:
                        await self._send(ws, {"op": "fail", "reason": "server_full"})
                        break
                    peer_id = f"peer_{uuid.uuid4().hex[:12]}"
                    color = _RELAY_COLORS[room.color_idx % len(_RELAY_COLORS)]
                    room.color_idx += 1
                    peer = _RoomPeer(peer_id, name, list(color), ws)
                    room.peers[peer_id] = peer
                    peers = [{"id": p.peer_id, "name": p.name, "color": p.color} for p in room.peers.values()]
                    await self._send(ws, {"op": "welcomed", "your_id": peer_id, "your_color": list(color), "peers": peers, "room": room_code, "version": int(PROTOCOL_VERSION)})
                    notice = {"op": "peer_joined", "id": peer_id, "name": name, "color": list(color)}
                    for pid, p in list(room.peers.items()):
                        if pid == peer_id:
                            continue
                        try:
                            await self._send(p.ws, notice)
                        except Exception:
                            pass
                    Logger.info(f"Relay peer {name} joined room {room_code} as {peer_id}")
                elif op == "data":
                    if peer_id is None or not room_code:
                        continue
                    room = self._rooms.get(room_code)
                    if room is None:
                        continue
                    peer = room.peers.get(peer_id)
                    if peer is None:
                        continue
                    peer.last_seen = time.monotonic()
                    try:
                        t = int(obj.get("t", 0))
                    except Exception:
                        continue
                    d = obj.get("d", {})
                    if not isinstance(d, dict):
                        continue
                    to = str(obj.get("to", "") or d.get("target", ""))
                    out_type = _route_pair(t)
                    payload = dict(d)
                    payload["id"] = peer_id
                    envelope = {"op": "data", "from": peer_id, "t": int(out_type), "d": payload}
                    if to and to in room.peers:
                        try:
                            await self._send(room.peers[to].ws, envelope)
                        except Exception:
                            pass
                    else:
                        for pid, p in list(room.peers.items()):
                            if pid == peer_id:
                                continue
                            try:
                                await self._send(p.ws, envelope)
                            except Exception:
                                pass
                elif op == "ping":
                    await self._send(ws, {"op": "pong", "t": obj.get("t", 0)})
                elif op == "leave":
                    break
        except Exception:
            pass
        finally:
            if peer_id and room_code:
                room = self._rooms.get(room_code)
                if room is not None and peer_id in room.peers:
                    try:
                        del room.peers[peer_id]
                    except Exception:
                        pass
                    notice = {"op": "peer_left", "id": peer_id}
                    for pid, p in list(room.peers.items()):
                        try:
                            await self._send(p.ws, notice)
                        except Exception:
                            pass
                    if not room.peers and (time.monotonic() - room.created) > 60.0:
                        try:
                            del self._rooms[room_code]
                        except Exception:
                            pass
                Logger.info(f"Relay peer left: {peer_id}")


def run_relay_server_blocking(host="0.0.0.0", port=8765):
    srv = RelayServer(host, port)
    ok = srv.start_sync()
    print(f"Relay listening on {host}:{port} ok={ok}", flush=True)
    try:
        import time as _t
        while srv.running:
            _t.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop_sync()


if __name__ == "__main__":
    import argparse as _ap
    _pa = _ap.ArgumentParser()
    _pa.add_argument("--host", default="0.0.0.0")
    _pa.add_argument("--port", type=int, default=8765)
    _a = _pa.parse_args()
    run_relay_server_blocking(_a.host, _a.port)
