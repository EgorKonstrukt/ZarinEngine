# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import html as html_mod
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Iterable

PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"
PYPI_SEARCH_URL = "https://pypi.org/search/?q={query}"
PYPI_PROJECT_URL = "https://pypi.org/project/{name}/"
USER_AGENT = "ZarinEngine-PackageManager/1.0 (+https://github.com/anomalyco/opencode)"
HTTP_TIMEOUT = 12.0
_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXTRAS_RE = re.compile(r"\[([^\]]*)\]")
_SNIPPET_NAME_RE = re.compile(r"package-snippet__name[^>]*>\s*([^<]+?)\s*<", re.I)
_SNIPPET_VER_RE = re.compile(r"package-snippet__version[^>]*>\s*v?([^<]+?)\s*<", re.I)
_SNIPPET_DESC_RE = re.compile(r"package-snippet__description[^>]*>\s*([^<]+?)\s*<", re.I)


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


_EXTRA_MARKER_RE = re.compile(r"extra\s*==", re.I)
_SIMPLE_HREF_RE = re.compile(r'<a\s[^>]*href="[^"]*/simple/([^/"]+)/?"[^>]*>', re.I)
INDEX_CACHE_TTL = 24 * 3600
INDEX_URL = "https://pypi.org/simple/"


def _index_cache_path() -> str:
    base = os.path.join(os.path.expanduser("~"), ".zarin", "pypi_cache")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, "simple_names.txt")


class SimpleIndex:
    def __init__(self):
        self._entries: list[tuple[str, str]] | None = None

    def cache_path(self) -> str:
        return _index_cache_path()

    def is_fresh(self) -> bool:
        path = self.cache_path()
        try:
            age = time.time() - os.path.getmtime(path)
            return os.path.isfile(path) and age < INDEX_CACHE_TTL
        except Exception:
            return False

    def _load(self, refresh: bool = False) -> list[tuple[str, str]]:
        if self._entries is not None and not refresh:
            return self._entries
        path = self.cache_path()
        if not refresh and self.is_fresh():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    names = [line.strip() for line in f if line.strip()]
                self._entries = [(normalize_name(n), n) for n in names]
                return self._entries
            except Exception:
                pass
        names = self._fetch()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(names))
        except Exception:
            pass
        self._entries = [(normalize_name(n), n) for n in names]
        return self._entries

    def names(self, refresh: bool = False) -> list[str]:
        return [display for _, display in self._load(refresh)]

    def _fetch(self) -> list[str]:
        text = http_get_text(INDEX_URL, timeout=120.0)
        found = {html_mod.unescape(n) for n in _SIMPLE_HREF_RE.findall(text)}
        return sorted(found, key=str.lower)

    def search(self, query: str, limit: int = 60, refresh: bool = False) -> list[str]:
        q = normalize_name(query)
        raw = (query or "").strip().lower()
        if not q and not raw:
            return []
        exact = []
        prefix = []
        partial = []
        for key, display in self._load(refresh):
            if key == q or display.lower() == raw:
                exact.append(display)
            elif key.startswith(q):
                prefix.append(display)
            elif q and q in key:
                partial.append(display)
        return (exact + prefix + partial)[:limit]


def requirement_is_optional(req: Requirement) -> bool:
    return bool(_EXTRA_MARKER_RE.search(req.marker or ""))


def requirement_map(packages: Iterable[PackageInfo],
                    include_extras: bool = False) -> dict[str, list[Requirement]]:
    out: dict[str, list[Requirement]] = {}
    for p in packages:
        reqs = [parse_requirement(r) for r in p.requires]
        if not include_extras:
            reqs = [r for r in reqs if not requirement_is_optional(r)]
        out[p.key] = reqs
    return out


def build_dependency_tree(packages: Iterable[PackageInfo],
                          reverse: bool = False,
                          roots: Iterable[str] | None = None,
                          include_extras: bool = False,
                          dedupe: bool = True,
                          max_depth: int = 64) -> list[TreeNode]:
    pkgs = list(packages)
    by_key = {p.key: p for p in pkgs}
    reqs = requirement_map(pkgs, include_extras=include_extras)
    expanded: set[str] = set()
    if reverse:
        parents: dict[str, list[tuple[str, Requirement]]] = {k: [] for k in by_key}
        for parent_key, rlist in reqs.items():
            for req in rlist:
                if req.key in parents:
                    parents[req.key].append((parent_key, req))
        roots_keys = [normalize_name(r) for r in roots] if roots else sorted(by_key.keys())
        def build(key: str, path: set[str], as_root: bool = False) -> TreeNode:
            p = by_key.get(key)
            node = TreeNode(
                name=p.name if p else key,
                version=p.version if p else "",
                installed=p is not None,
            )
            if key in path:
                node.cyclic = True
                return node
            if not as_root and dedupe and key in expanded:
                node.shared = True
                return node
            expanded.add(key)
            if len(path) >= max_depth:
                return node
            nxt = path | {key}
            for parent_key, req in parents.get(key, []):
                child = build(parent_key, nxt)
                child.spec = req.spec
                child.extras = req.extras
                child.marker = req.marker
                node.children.append(child)
            return node
        return [build(k, set(), True) for k in roots_keys if k in by_key]
    roots_keys = [normalize_name(r) for r in roots] if roots else None
    if roots_keys is None:
        referenced = set()
        for rlist in reqs.values():
            for req in rlist:
                if req.key in by_key:
                    referenced.add(req.key)
        roots_keys = [k for k in sorted(by_key.keys()) if k not in referenced]
    def build_fwd(key: str, path: set[str], as_root: bool = False) -> TreeNode:
        p = by_key.get(key)
        node = TreeNode(
            name=p.name if p else key,
            version=p.version if p else "",
            installed=p is not None,
        )
        if key in path:
            node.cyclic = True
            return node
        if not as_root and dedupe and key in expanded:
            node.shared = True
            return node
        expanded.add(key)
        if len(path) >= max_depth:
            return node
        nxt = path | {key}
        for req in reqs.get(key, []):
            target = by_key.get(req.key)
            child = build_fwd(req.key, nxt)
            child.spec = req.spec
            child.extras = req.extras
            child.marker = req.marker
            if target is None:
                child.missing = True
                child.installed = False
                child.version = ""
                child.name = req.name or child.name
            node.children.append(child)
        return node
    return [build_fwd(k, set(), True) for k in roots_keys]


def http_get_json(url: str, timeout: float = HTTP_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, timeout: float = HTTP_TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


class PyPiClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._info: dict[str, dict] = {}
        self._versions: dict[str, list[str]] = {}
        self._search: dict[str, list[dict]] = {}
        self._errors: dict[str, str] = {}

    def project(self, name: str, refresh: bool = False) -> dict:
        key = normalize_name(name)
        with self._lock:
            if not refresh and key in self._info:
                return self._info[key]
        url = PYPI_JSON_URL.format(name=urllib.parse.quote(key))
        data = http_get_json(url)
        with self._lock:
            self._info[key] = data
            self._errors.pop(key, None)
        return data

    def cached_project(self, name: str) -> dict | None:
        with self._lock:
            return self._info.get(normalize_name(name))

    def latest(self, name: str) -> str:
        try:
            info = self.project(name).get("info") or {}
            return str(info.get("version") or "")
        except Exception:
            return ""

    def versions(self, name: str, include_pre: bool = False) -> list[str]:
        key = normalize_name(name)
        with self._lock:
            cached = self._versions.get(key)
        if cached is not None and not include_pre:
            return cached
        try:
            data = self.project(name)
        except Exception:
            return cached or []
        releases = data.get("releases") or {}
        out = []
        for ver, files in releases.items():
            if not include_pre and _is_prerelease(ver):
                continue
            usable = [f for f in (files or []) if not str(f.get("yanked", False)).lower() == "true"]
            if usable:
                out.append(ver)
        out.sort(key=_version_tuple, reverse=True)
        with self._lock:
            self._versions[key] = out
        return out

    def metadata(self, name: str) -> dict:
        data = self.project(name)
        info = data.get("info") or {}
        urls = data.get("urls") or []
        return {
            "name": info.get("name") or name,
            "version": info.get("version") or "",
            "summary": info.get("summary") or "",
            "author": info.get("author") or info.get("author_email") or "",
            "license": info.get("license") or "",
            "home_page": info.get("home_page") or "",
            "project_url": info.get("project_url") or PYPI_PROJECT_URL.format(name=urllib.parse.quote(normalize_name(name))),
            "requires_python": info.get("requires_python") or "",
            "requires_dist": [str(r) for r in (info.get("requires_dist") or [])],
            "keywords": info.get("keywords") or "",
            "yanked": bool(urls and all(str(u.get("yanked", False)).lower() == "true" for u in urls)),
        }

    def search(self, query: str) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        with self._lock:
            cached = self._search.get(q.lower())
        if cached is not None:
            return cached
        results: list[dict] = []
        try:
            data = self.project(q)
            info = data.get("info") or {}
            results.append({
                "name": info.get("name") or q,
                "version": info.get("version") or "",
                "summary": info.get("summary") or "",
                "exact": True,
            })
        except Exception:
            pass
        try:
            url = PYPI_SEARCH_URL.format(query=urllib.parse.quote(q))
            html = http_get_text(url)
            names = _SNIPPET_NAME_RE.findall(html)
            vers = _SNIPPET_VER_RE.findall(html)
            descs = _SNIPPET_DESC_RE.findall(html)
            seen = {normalize_name(r["name"]) for r in results}
            for i, n in enumerate(names):
                key = normalize_name(n)
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "name": n.strip(),
                    "version": vers[i].strip() if i < len(vers) else "",
                    "summary": descs[i].strip() if i < len(descs) else "",
                    "exact": False,
                })
        except Exception as e:
            with self._lock:
                self._errors[q.lower()] = str(e)
        with self._lock:
            self._search[q.lower()] = results
        return results

    def error_for(self, query: str) -> str:
        with self._lock:
            return self._errors.get(query.lower(), "")


def _is_prerelease(version: str) -> bool:
    return bool(re.search(r"(a|b|rc|dev|alpha|beta)\d*$", str(version or ""), re.I))


def fetch_latest_versions(names: Iterable[str],
                          client: PyPiClient | None = None,
                          workers: int = 10,
                          on_result: Callable[[str, str], None] | None = None) -> dict[str, str]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    client = client or PyPiClient()
    names = [n for n in dict.fromkeys(names) if n]
    out: dict[str, str] = {}
    if not names:
        return out
    def work(name: str):
        return name, client.latest(name)
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures = [pool.submit(work, n) for n in names]
        for fut in as_completed(futures):
            try:
                name, latest = fut.result()
            except Exception:
                continue
            if latest:
                out[name] = latest
                if on_result is not None:
                    on_result(name, latest)
    return out


def parse_outdated_json(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    start = text.find("[")
    if start < 0:
        return out
    try:
        data = json.loads(text[start:])
    except Exception:
        return out
    for entry in data or []:
        name = str(entry.get("name") or "")
        latest = str(entry.get("latest_version") or "")
        if name and latest:
            out[normalize_name(name)] = latest
    return out


def check_outdated(timeout: float = 240.0) -> tuple[dict[str, str], str]:
    code, out = run_pip_capture(["list", "--outdated", "--format=json"], timeout=timeout)
    if code != 0:
        return {}, out
    return parse_outdated_json(out), out


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
