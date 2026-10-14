# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterable

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXTRAS_RE = re.compile(r"\[([^\]]*)\]")


@dataclass
class PackageInfo:
    name: str = ""
    version: str = ""
    summary: str = ""
    author: str = ""
    license: str = ""
    home_page: str = ""
    location: str = ""
    size: int = 0
    requires: list[str] = field(default_factory=list)
    latest: str = ""
    status: str = "unknown"
    editable: bool = False

    @property
    def key(self) -> str:
        return normalize_name(self.name)


@dataclass
class Requirement:
    raw: str = ""
    name: str = ""
    key: str = ""
    spec: str = ""
    extras: str = ""
    marker: str = ""

    @property
    def display(self) -> str:
        out = self.name
        if self.extras:
            out += f"[{self.extras}]"
        if self.spec:
            out += self.spec
        return out


@dataclass
class TreeNode:
    name: str = ""
    version: str = ""
    spec: str = ""
    extras: str = ""
    marker: str = ""
    installed: bool = True
    cyclic: bool = False
    missing: bool = False
    shared: bool = False
    children: list["TreeNode"] = field(default_factory=list)

    @property
    def note(self) -> str:
        parts = []
        if self.cyclic:
            parts.append("cycle")
        if self.shared:
            parts.append("shared")
        if self.missing or not self.installed:
            parts.append("not installed")
        if self.marker:
            parts.append(self.marker)
        return " · ".join(parts)


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def python_executable() -> str:
    return sys.executable or "python"


def python_version_label() -> str:
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def site_packages_path() -> str:
    try:
        import site
        paths = list(getattr(site, "getsitepackages", lambda: [])() or [])
        user = getattr(site, "getusersitepackages", lambda: "")()
        if user:
            paths.append(user)
        for p in paths:
            if os.path.isdir(p):
                return p
    except Exception:
        pass
    try:
        import sysconfig
        return sysconfig.get_path("purelib") or ""
    except Exception:
        return ""


def _pip_base_args() -> list[str]:
    return [python_executable(), "-m", "pip", "--disable-pip-version-check"]


def create_no_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def run_pip_streaming(args: Iterable[str],
                      on_line: Callable[[str], None] | None = None,
                      on_done: Callable[[int], None] | None = None,
                      cancel_event: threading.Event | None = None) -> int:
    cmd = _pip_base_args() + [str(a) for a in args]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=create_no_window_flag(),
    )
    try:
        for raw in proc.stdout:
            if cancel_event is not None and cancel_event.is_set():
                break
            if on_line is not None:
                on_line(raw.rstrip("\n"))
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
    if cancel_event is not None and cancel_event.is_set():
        try:
            proc.terminate()
        except Exception:
            pass
    code = proc.wait()
    if on_done is not None:
        on_done(code)
    return code


def run_pip_capture(args: Iterable[str], timeout: float = 180.0) -> tuple[int, str]:
    cmd = _pip_base_args() + [str(a) for a in args]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=create_no_window_flag(),
    )
    return proc.returncode, proc.stdout or ""


def parse_requirement(raw: str) -> Requirement:
    text = (raw or "").strip()
    req = Requirement(raw=text)
    m = _NAME_RE.match(text)
    if not m:
        req.name = text
        req.key = normalize_name(text)
        return req
    req.name = m.group(1)
    req.key = normalize_name(req.name)
    rest = text[m.end():]
    marker = ""
    if ";" in rest:
        rest, marker = rest.split(";", 1)
        req.marker = marker.strip()
    rest = rest.strip()
    em = _EXTRAS_RE.search(rest)
    if em:
        req.extras = em.group(1).strip()
        rest = (rest[:em.start()] + rest[em.end():]).strip()
    req.spec = rest.replace(" ", "")
    return req


def _dist_meta(dist, key: str) -> str:
    try:
        meta = dist.metadata
        val = meta.get(key) if meta is not None else None
        return (val or "").strip()
    except Exception:
        return ""


def _dist_size(dist) -> int:
    total = 0
    try:
        files = dist.files or []
        for f in files:
            try:
                p = dist.locate_file(f)
                if os.path.isfile(p):
                    total += os.path.getsize(p)
            except Exception:
                continue
    except Exception:
        return 0
    return total


def _dist_location(dist) -> str:
    try:
        for f in (dist.files or []):
            p = str(dist.locate_file(f))
            if p:
                return os.path.dirname(p)
    except Exception:
        pass
    try:
        return str(dist.locate_file("")) or ""
    except Exception:
        return ""


def _is_editable(dist) -> bool:
    try:
        direct = dist.read_text("direct_url.json") or ""
        if "editable" in direct or '"url": "file:' in direct:
            return True
    except Exception:
        pass
    try:
        path = str(getattr(dist, "_path", "") or "")
        return bool(path) and os.path.isdir(path) and not path.endswith(".dist-info")
    except Exception:
        return False


def list_installed(with_size: bool = True) -> list[PackageInfo]:
    from importlib import metadata as md
    out: dict[str, PackageInfo] = {}
    try:
        dists = list(md.distributions())
    except Exception:
        dists = []
    for dist in dists:
        try:
            name = dist.metadata["Name"]
        except Exception:
            name = None
        if not name:
            continue
        info = PackageInfo(
            name=name,
            version=str(dist.version or ""),
            summary=_dist_meta(dist, "Summary"),
            author=_dist_meta(dist, "Author") or _dist_meta(dist, "Author-email"),
            license=_dist_meta(dist, "License"),
            home_page=_dist_meta(dist, "Home-page") or _dist_meta(dist, "Project-URL"),
            location=_dist_location(dist),
            editable=_is_editable(dist),
        )
        try:
            reqs = list(dist.requires or [])
        except Exception:
            reqs = []
        info.requires = [r for r in (str(x) for x in reqs) if r.strip()]
        if with_size:
            info.size = _dist_size(dist)
        key = info.key
        prev = out.get(key)
        if prev is None or _version_tuple(info.version) > _version_tuple(prev.version):
            out[key] = info
    return sorted(out.values(), key=lambda p: p.name.lower())


def _version_tuple(v: str):
    parts = []
    for chunk in re.split(r"[.\-+]", str(v or "")):
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        else:
            parts.append((1, chunk))
    return tuple(parts)


def requirements_lines(packages: Iterable[PackageInfo], pinned: bool = True) -> list[str]:
    lines = []
    for p in sorted(packages, key=lambda x: x.name.lower()):
        if not p.name:
            continue
        if pinned and p.version:
            lines.append(f"{p.name}=={p.version}")
        else:
            lines.append(p.name)
    return lines


def write_requirements(path: str, packages: Iterable[PackageInfo], pinned: bool = True) -> str:
    lines = requirements_lines(packages, pinned)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def format_size(num: int) -> str:
    n = float(num or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def _as_specs(spec) -> list[str]:
    if spec is None:
        return []
    if isinstance(spec, str):
        text = spec.strip()
        return [text] if text else []
    return [str(s).strip() for s in spec if str(s).strip()]


def install_args(spec, upgrade: bool = False, no_deps: bool = False,
                 pre: bool = False, extra: Iterable[str] = ()) -> list[str]:
    args = ["install"]
    if upgrade:
        args.append("--upgrade")
    if no_deps:
        args.append("--no-deps")
    if pre:
        args.append("--pre")
    args.extend(extra)
    args.extend(_as_specs(spec))
    return args


def uninstall_args(name) -> list[str]:
    return ["uninstall", "-y", *_as_specs(name)]


def download_args(spec: str, dest: str, with_deps: bool = True, pre: bool = False) -> list[str]:
    args = ["download", "-d", dest]
    if not with_deps:
        args.append("--no-deps")
    if pre:
        args.append("--pre")
    args.append(spec)
    return args
