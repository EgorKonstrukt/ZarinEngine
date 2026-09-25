# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import re
import select
import socket
import threading
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urljoin, urlparse


UPNP_AVAILABLE = True
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SEARCH_TARGETS = (
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)
SOAP_ENV_OPEN = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
SOAP_ENV_CLOSE = "</s:Body></s:Envelope>"
FAULT_RE = re.compile(r"<errorCode>\s*(\d+)\s*</errorCode>", re.IGNORECASE)
FAULT_STR_RE = re.compile(r"<errorDescription>\s*([^<]*?)\s*</errorDescription>", re.IGNORECASE)


def _local_ip_for(remote_host: str) -> str:
    for target in (remote_host, "8.8.8.8"):
        if not target:
            continue
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2.0)
            s.connect((str(target), 1900))
            ip = str(s.getsockname()[0])
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        finally:
            try:
                if s is not None:
                    s.close()
            except Exception:
                pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return str(ip)
    except Exception:
        pass
    return ""


def _parse_ssdp_location(packet: bytes) -> str:
    try:
        text = packet.decode("latin-1", errors="ignore")
    except Exception:
        return ""
    for line in text.split("\r\n"):
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        if k.strip().lower() == "location":
            return v.strip()
    low = text.lower()
    idx = low.find("location:")
    if idx >= 0:
        end = text.find("\r\n", idx)
        return text[idx + 9:end if end >= 0 else len(text)].strip()
    return ""


def _fetch_xml(url: str, timeout: float = 6.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ZarinEngine", "Accept": "text/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def _iter_services(root: ET.Element):
    for el in root.iter():
        if el.tag.endswith("service"):
            yield el


def _child_text(service: ET.Element, name: str) -> str:
    for ch in service:
        if ch.tag.endswith(name):
            return (ch.text or "").strip()
    return ""


def _soap(control_url: str, service_type: str, action: str, args: dict, timeout: float = 8.0) -> tuple[int, str]:
    inner_args = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
    body = (
        '<?xml version="1.0"?>'
        + SOAP_ENV_OPEN
        + f'<u:{action} xmlns:u="{service_type}">{inner_args}</u:{action}>'
        + SOAP_ENV_CLOSE
    )
    data = body.encode("utf-8")
    req = urllib.request.Request(
        control_url,
        data=data,
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{service_type}#{action}"',
            "User-Agent": "ZarinEngine",
            "Content-Length": str(len(data)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.status or 200), r.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        try:
            return int(e.code), e.read().decode("utf-8", errors="ignore")
        except Exception:
            return int(getattr(e, "code", 500) or 500), ""
    except Exception as e:
        return -1, str(e)


def _fault_info(body: str) -> str:
    m = FAULT_RE.search(body or "")
    code = m.group(1) if m else ""
    ms = FAULT_STR_RE.search(body or "")
    desc = ms.group(1) if ms else ""
    if code and desc:
        return f"{code} {desc}"
    return code or desc


class UpnpGateway:
    def __init__(self, location: str, service_type: str, control_url: str, server: str = "", st: str = ""):
        self.location = str(location)
        self.service_type = str(service_type)
        self.control_url = str(control_url)
        self.server = str(server)
        self.st = str(st)
        try:
            self.host = str(urlparse(self.location).hostname or "")
        except Exception:
            self.host = ""

    def __repr__(self) -> str:
        return f"UpnpGateway({self.host} {self.service_type})"

    def get_external_ip(self, timeout: float = 8.0) -> str:
        status, body = _soap(self.control_url, self.service_type, "GetExternalIPAddress", {}, timeout=timeout)
        if status != 200:
            return ""
        m = re.search(r"<NewExternalIPAddress>\s*([^<]*?)\s*</NewExternalIPAddress>", body or "")
        return (m.group(1).strip() if m else "")

    def add_mapping(self, external_port: int, internal_port: int, internal_client: str, protocol: str = "TCP", description: str = "ZarinEngine", lease: int = 3600, timeout: float = 8.0) -> tuple[bool, str]:
        args = {
            "NewRemoteHost": "",
            "NewExternalPort": str(int(external_port)),
            "NewProtocol": str(protocol or "TCP").upper(),
            "NewInternalPort": str(int(internal_port)),
            "NewInternalClient": str(internal_client),
            "NewEnabled": "1",
            "NewPortMappingDescription": str(description or "ZarinEngine")[:64],
            "NewLeaseDuration": str(max(0, int(lease))),
        }
        status, body = _soap(self.control_url, self.service_type, "AddPortMapping", args, timeout=timeout)
        if status == 200:
            return True, ""
        return False, _fault_info(body) or f"http_{status}"

    def delete_mapping(self, external_port: int, protocol: str = "TCP", timeout: float = 8.0) -> tuple[bool, str]:
        args = {
            "NewRemoteHost": "",
            "NewExternalPort": str(int(external_port)),
            "NewProtocol": str(protocol or "TCP").upper(),
        }
        status, body = _soap(self.control_url, self.service_type, "DeletePortMapping", args, timeout=timeout)
        if status == 200:
            return True, ""
        info = _fault_info(body)
        if info.startswith("714"):
            return True, ""
        return False, info or f"http_{status}"

    def get_mapping(self, external_port: int, protocol: str = "TCP", timeout: float = 8.0) -> Optional[dict]:
        args = {
            "NewRemoteHost": "",
            "NewExternalPort": str(int(external_port)),
            "NewProtocol": str(protocol or "TCP").upper(),
        }
        status, body = _soap(self.control_url, self.service_type, "GetSpecificPortMappingEntry", args, timeout=timeout)
        if status != 200:
            return None
        out: dict = {}
        for key in ("NewInternalPort", "NewInternalClient", "NewEnabled", "NewPortMappingDescription", "NewLeaseDuration"):
            m = re.search(rf"<{key}>\s*([^<]*?)\s*</{key}>", body or "")
            out[key] = m.group(1).strip() if m else ""
        return out


def _services_from_device_xml(xml_text: str, base_url: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return found
    for svc in _iter_services(root):
        stype = _child_text(svc, "serviceType")
        curl = _child_text(svc, "controlURL")
        if not stype or not curl:
            continue
        if "WANIPConnection" in stype or "WANPPPConnection" in stype:
            found.append((stype, urljoin(base_url, curl)))
    return found


def _discovery_sources() -> list[str]:
    out: list[str] = []
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        for a in addrs:
            if a and not a.startswith("127.") and a not in out:
                try:
                    socket.inet_aton(a)
                    out.append(a)
                except Exception:
                    pass
    except Exception:
        pass
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2.0)
        s.connect(("8.8.8.8", 80))
        ip = str(s.getsockname()[0])
        if ip and not ip.startswith("127.") and ip not in out:
            out.append(ip)
    except Exception:
        pass
    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass
    return out


def _open_discovery_socket(source: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    except Exception:
        pass
    if source:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source))
        except Exception:
            pass
        try:
            sock.bind((source, 0))
        except Exception:
            try:
                sock.bind(("", 0))
            except Exception:
                pass
    else:
        try:
            sock.bind(("", 0))
        except Exception:
            pass
    sock.setblocking(False)
    return sock


def discover_gateways(timeout: float = 2.5, mx: int = 2) -> list[UpnpGateway]:
    locations: dict[str, dict] = {}
    socks: list = []
    try:
        sources = _discovery_sources()
        if not sources:
            sources = [""]
        for src in sources:
            try:
                socks.append(_open_discovery_socket(src))
            except Exception:
                pass
        if not socks:
            return []
        for target in SEARCH_TARGETS:
            msg = (
                "M-SEARCH * HTTP/1.1\r\n"
                f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                'MAN: "ns=01"; ns=01\r\n'
                f"MX: {max(1, int(mx))}\r\n"
                f"ST: {target}\r\n"
                "USER-AGENT: ZarinEngine UPnP\r\n"
                "\r\n"
            )
            raw = msg.encode("latin-1")
            for sock in socks:
                try:
                    sock.sendto(raw, (SSDP_ADDR, SSDP_PORT))
                except Exception:
                    pass
        deadline = time.time() + max(0.5, float(timeout))
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                ready, _, _ = select.select(socks, [], [], min(remaining, 0.5))
            except Exception:
                break
            if not ready:
                continue
            for sock in ready:
                try:
                    data, _ = sock.recvfrom(65535)
                except Exception:
                    continue
                loc = _parse_ssdp_location(data)
                if not loc or loc in locations:
                    continue
                try:
                    txt = data.decode("latin-1", errors="ignore")
                except Exception:
                    txt = ""
                server = ""
                st = ""
                for line in txt.split("\r\n"):
                    if ":" not in line:
                        continue
                    k, _, v = line.partition(":")
                    kl = k.strip().lower()
                    if kl == "server":
                        server = v.strip()
                    elif kl == "st":
                        st = v.strip()
                locations[loc] = {"server": server, "st": st}
                if len(locations) >= 10:
                    break
            if len(locations) >= 10:
                break
    except Exception:
        pass
    finally:
        for sock in socks:
            try:
                sock.close()
            except Exception:
                pass
    gateways: list[UpnpGateway] = []
    seen_ctrl: set[str] = set()
    for loc, meta in locations.items():
        try:
            xml_text = _fetch_xml(loc, timeout=6.0)
        except Exception:
            continue
        for stype, curl in _services_from_device_xml(xml_text, loc):
            if curl in seen_ctrl:
                continue
            seen_ctrl.add(curl)
            gateways.append(UpnpGateway(loc, stype, curl, str(meta.get("server", "")), str(meta.get("st", ""))))
    gateways.sort(key=lambda g: (0 if "WANIPConnection" in g.service_type else 1, g.host))
    return gateways


def get_external_ip(timeout: float = 8.0) -> str:
    try:
        for gw in discover_gateways(timeout=2.0):
            try:
                ip = gw.get_external_ip(timeout=timeout)
            except Exception:
                continue
            if ip:
                return ip
    except Exception:
        pass
    return ""


class UpnpMapper:
    def __init__(self, lease: int = 3600):
        self._lease = max(0, int(lease))
        self._mappings: dict[tuple[int, str], dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._gateway: Optional[UpnpGateway] = None
        self._gateway_error = ""
        self._external_ip = ""

    def _pick_gateway(self) -> Optional[UpnpGateway]:
        if self._gateway is not None:
            return self._gateway
        try:
            found = discover_gateways(timeout=2.5)
        except Exception as e:
            self._gateway_error = str(e)[:160]
            return None
        if not found:
            self._gateway_error = "no_igd"
            return None
        self._gateway = found[0]
        self._gateway_error = ""
        return self._gateway

    def _renew_loop(self):
        interval = min(1800.0, max(120.0, float(self._lease) / 2.0 if self._lease > 0 else 1800.0))
        while not self._stop.wait(interval):
            with self._lock:
                items = list(self._mappings.items())
            gw = self._gateway
            if gw is None or not items:
                continue
            for (ext, proto), info in items:
                try:
                    ok, _ = gw.add_mapping(
                        int(ext),
                        int(info.get("internal", ext)),
                        str(info.get("client", "")),
                        str(proto),
                        str(info.get("description", "ZarinEngine")),
                        self._lease,
                        timeout=8.0,
                    )
                    with self._lock:
                        if (ext, proto) in self._mappings:
                            self._mappings[(ext, proto)]["ok"] = bool(ok)
                except Exception:
                    pass

    def _ensure_thread(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._renew_loop, daemon=True)
            self._thread.start()

    def map_port(self, external: int, internal: Optional[int] = None, protocol: str = "TCP", description: str = "ZarinEngine", try_alternatives: bool = True, timeout: float = 10.0) -> dict:
        proto = str(protocol or "TCP").upper()
        if proto not in ("TCP", "UDP"):
            proto = "TCP"
        ext = max(1, min(65535, int(external)))
        intr = max(1, min(65535, int(internal if internal else ext)))
        gw = self._pick_gateway()
        if gw is None:
            return {"ok": False, "external": ext, "internal": intr, "protocol": proto, "external_ip": "", "error": self._gateway_error or "no_igd"}
        try:
            client = _local_ip_for(gw.host)
        except Exception:
            client = ""
        if not client:
            return {"ok": False, "external": ext, "internal": intr, "protocol": proto, "external_ip": "", "error": "no_local_ip"}
        candidates = [ext]
        if try_alternatives:
            candidates += [ext + i for i in range(1, 17) if ext + i <= 65535]
        last_err = ""
        for cand in candidates:
            try:
                existing = gw.get_mapping(cand, proto, timeout=timeout)
            except Exception:
                existing = None
            if existing and str(existing.get("NewInternalClient", "")) and (
                str(existing.get("NewInternalClient", "")) != client or str(existing.get("NewInternalPort", "")) != str(intr)
            ):
                last_err = "718 in_use"
                continue
            try:
                ok, err = gw.add_mapping(cand, intr, client, proto, description, self._lease, timeout=timeout)
            except Exception as e:
                ok, err = False, str(e)[:160]
            if ok:
                try:
                    ext_ip = gw.get_external_ip(timeout=timeout)
                except Exception:
                    ext_ip = ""
                self._external_ip = ext_ip or self._external_ip
                with self._lock:
                    self._mappings[(cand, proto)] = {
                        "internal": int(intr),
                        "client": str(client),
                        "description": str(description),
                        "external_ip": str(self._external_ip),
                        "ok": True,
                    }
                if self._lease > 0:
                    self._ensure_thread()
                return {"ok": True, "external": int(cand), "internal": int(intr), "protocol": proto, "external_ip": str(self._external_ip), "error": ""}
            last_err = err or "map_failed"
            if "718" not in str(last_err) and "725" not in str(last_err) and "in_use" not in str(last_err):
                break
        return {"ok": False, "external": ext, "internal": intr, "protocol": proto, "external_ip": "", "error": str(last_err)[:160]}

    def unmap_port(self, external: int, protocol: str = "TCP", timeout: float = 8.0) -> bool:
        proto = str(protocol or "TCP").upper()
        key = (int(external), proto)
        with self._lock:
            self._mappings.pop(key, None)
            empty = not self._mappings
        gw = self._gateway
        if gw is None:
            return False
        try:
            ok, _ = gw.delete_mapping(int(external), proto, timeout=timeout)
        except Exception:
            ok = False
        if empty:
            self._stop.set()
        return bool(ok)

    def unmap_all(self, timeout: float = 8.0) -> None:
        with self._lock:
            items = list(self._mappings.keys())
            self._mappings.clear()
        self._stop.set()
        gw = self._gateway
        if gw is None:
            return
        for ext, proto in items:
            try:
                gw.delete_mapping(int(ext), str(proto), timeout=timeout)
            except Exception:
                pass

    @property
    def gateway(self) -> Optional[UpnpGateway]:
        return self._gateway

    def tracked(self) -> list[tuple[int, str]]:
        with self._lock:
            return [(int(k[0]), str(k[1])) for k in self._mappings.keys()]

    def forget(self) -> None:
        with self._lock:
            self._mappings.clear()
        self._stop.set()

    def snapshot(self) -> dict:
        with self._lock:
            mappings = [
                {"external": int(k[0]), "protocol": str(k[1]), **{kk: vv for kk, vv in v.items()}}
                for k, v in self._mappings.items()
            ]
        return {
            "mappings": mappings,
            "external_ip": str(self._external_ip),
            "gateway": str(getattr(self._gateway, "host", "") or ""),
            "error": str(self._gateway_error),
        }

    def close(self) -> None:
        try:
            self.unmap_all()
        except Exception:
            pass
