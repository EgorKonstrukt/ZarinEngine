# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import hashlib
import os
import socket
import urllib.request
def _compute_hash(path: str) -> str:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()
def _scan_assets_dir(assets_dir: str) -> dict[str, dict]:
    result = {}
    if not os.path.isdir(assets_dir):
        return result
    for root, dirs, files in os.walk(assets_dir):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, assets_dir)
            try:
                size = os.path.getsize(full)
                mtime = os.path.getmtime(full)
            except Exception:
                continue
            result[rel] = {"size": size, "mtime": mtime, "hash": ""}
    return result
def get_lan_ips() -> list[str]:
    out: list[str] = []
    try:
        hn = socket.gethostname()
        try:
            _, _, addrs = socket.gethostbyname_ex(hn)
            for a in addrs:
                if a and not a.startswith("127.") and a not in out:
                    out.append(a)
        except Exception:
            pass
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip not in out:
                out.append(ip)
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass
    except Exception:
        pass
    return out
def get_public_ip(timeout: float = 4.0) -> str:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ZarinEngine"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ip = r.read().decode("utf-8", errors="ignore").strip()
                if ip and len(ip) < 64 and "." in ip:
                    return ip
        except Exception:
            continue
    return ""
