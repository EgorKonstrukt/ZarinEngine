# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCOPE = ("core", "editor", "plugins", "physics_solvers")


def mod_file(mod: str) -> str | None:
    rel = mod.replace(".", "/")
    cand = os.path.join(str(ROOT), rel + ".py")
    if os.path.isfile(cand):
        return cand
    cand = os.path.join(str(ROOT), rel, "__init__.py")
    if os.path.isfile(cand):
        return cand
    return None


def _is_tc_test(node) -> bool:
    t = node.test
    if isinstance(t, ast.Name) and t.id == "TYPE_CHECKING":
        return True
    if isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING":
        return True
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, mod: str, is_pkg: bool):
        self.mod = mod
        self.pkg = mod if is_pkg else (mod.rpartition(".")[0] if "." in mod else "")
        self.in_tc = False
        self.rt: set[str] = set()
        self.tc: set[str] = set()

    def visit_If(self, node):
        if _is_tc_test(node):
            old = self.in_tc
            self.in_tc = True
            for stmt in node.body:
                self.visit(stmt)
            self.in_tc = old
            for stmt in node.orelse:
                self.visit(stmt)
        else:
            self.generic_visit(node)

    def _add(self, dep: str):
        if dep:
            (self.tc if self.in_tc else self.rt).add(dep)

    def visit_Import(self, node):
        for a in node.names:
            self._add(a.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.level and node.level > 0:
            parts = self.pkg.split(".") if self.pkg else []
            if node.level - 1 <= len(parts):
                base = ".".join(parts[: len(parts) - node.level + 1])
                if node.module:
                    self._add(base + "." + node.module if base else node.module)
                else:
                    for a in node.names:
                        if a.name != "*":
                            self._add(base + "." + a.name if base else a.name)
        elif node.module:
            self._add(node.module)
        self.generic_visit(node)


def _module_deps(path: str, mod: str):
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
    except Exception:
        return set(), set()
    v = _Visitor(mod, os.path.basename(path) == "__init__.py")
    v.visit(tree)
    return v.rt, v.tc


def dead_editor_modules(seeds) -> list[str]:
    rt_seen: dict[str, bool] = {}
    tc_seen: dict[str, list] = {}
    stack = [(s, False) for s in seeds]
    while stack:
        mod, via_tc = stack.pop()
        if mod in rt_seen:
            continue
        if mod in tc_seen:
            if via_tc:
                continue
            deps = tc_seen.pop(mod)
            rt_seen[mod] = True
            for dep, tc in deps:
                stack.append((dep, tc))
            continue
        fp = mod_file(mod)
        if fp is None:
            continue
        try:
            rt, tc = _module_deps(fp, mod)
        except Exception:
            continue
        deps = [(d, True) for d in tc] + [(d, False) for d in rt]
        if via_tc:
            tc_seen[mod] = deps
        else:
            rt_seen[mod] = True
        for dep, tc in deps:
            if dep.split(".")[0] in SCOPE:
                stack.append((dep, tc or via_tc))
    return sorted(m for m in tc_seen if m.startswith("editor."))
