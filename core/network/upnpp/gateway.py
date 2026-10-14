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
