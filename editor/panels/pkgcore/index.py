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
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, Iterable

from .core import _version_tuple
from .core import normalize_name

PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"
PYPI_SEARCH_URL = "https://pypi.org/search/?q={query}"
PYPI_PROJECT_URL = "https://pypi.org/project/{name}/"
USER_AGENT = "ZarinEngine-PackageManager/1.0 (+https://github.com/anomalyco/opencode)"
HTTP_TIMEOUT = 12.0
_SNIPPET_NAME_RE = re.compile(r"package-snippet__name[^>]*>\s*([^<]+?)\s*<", re.I)
_SNIPPET_VER_RE = re.compile(r"package-snippet__version[^>]*>\s*v?([^<]+?)\s*<", re.I)
_SNIPPET_DESC_RE = re.compile(r"package-snippet__description[^>]*>\s*([^<]+?)\s*<", re.I)
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
