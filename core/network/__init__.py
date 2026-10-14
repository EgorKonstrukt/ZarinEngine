# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from core.network.protocol import MessageType, make_msg, parse_msg, FRAME_HEADER_SIZE, PROTOCOL_VERSION, CHUNK_SIZE, generate_room_code, normalize_room, hash_password, make_invite, parse_invite, build_direct_invite, build_relay_invite, normalize_relay_url, is_relay_url
from core.network.serverp import CollabServer
from core.network.client import CollabClient
from core.network.collab import CollaborationManager, get_lan_ips, get_public_ip
from core.network.transp import Transport, GameServer, GameClient, get_transport

try:
    from core.network.relayp import RelayServer, RelayClient
except Exception:
    RelayServer = None
    RelayClient = None

try:
    from core.network.upnpp import UpnpGateway, UpnpMapper, discover_gateways, get_external_ip as upnp_external_ip, UPNP_AVAILABLE
except Exception:
    UpnpGateway = None
    UpnpMapper = None
    discover_gateways = None
    upnp_external_ip = None
    UPNP_AVAILABLE = False

__all__ = [
    "MessageType", "make_msg", "parse_msg", "FRAME_HEADER_SIZE",
    "PROTOCOL_VERSION", "CHUNK_SIZE",
    "generate_room_code", "normalize_room", "hash_password",
    "make_invite", "parse_invite", "build_direct_invite", "build_relay_invite",
    "normalize_relay_url", "is_relay_url",
    "CollabServer", "CollabClient", "CollaborationManager",
    "get_lan_ips", "get_public_ip",
    "RelayServer", "RelayClient",
    "UpnpGateway", "UpnpMapper", "discover_gateways", "upnp_external_ip", "UPNP_AVAILABLE",
    "Transport", "GameServer", "GameClient", "get_transport",
]
