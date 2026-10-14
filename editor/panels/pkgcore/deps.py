# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import json
import re
from typing import Iterable

from .core import PackageInfo
from .core import Requirement
from .core import TreeNode
from .core import normalize_name
from .core import parse_requirement
from .core import run_pip_capture

_EXTRA_MARKER_RE = re.compile(r"extra\s*==", re.I)


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
