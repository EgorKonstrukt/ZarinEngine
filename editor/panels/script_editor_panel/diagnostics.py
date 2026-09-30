# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import ast
import re


class Diagnostic:
    def __init__(self, line: int, col: int, end_col: int, message: str, kind: str, code: str = ""):
        self.line = line
        self.col = col
        self.end_col = end_col
        self.message = message
        self.kind = kind
        self.code = code

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "col": self.col,
            "end_col": self.end_col,
            "message": self.message,
            "kind": self.kind,
            "code": self.code,
        }


def _hash() -> str:
    return chr(35)


def _collect_used_names(tree: ast.AST) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            pass
    return used


def _unused_imports(tree: ast.AST, used: set[str]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                full = alias.name
                local = alias.asname if alias.asname else full.split(".")[0]
                if local not in used:
                    ln = (node.lineno or 1) - 1
                    col = node.col_offset or 0
                    out.append(Diagnostic(ln, col, col + len(local) + 7, "imported but unused: " + local, "warning", "unused-import"))
        elif isinstance(node, ast.ImportFrom):
            if node.names is not None:
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname if alias.asname else alias.name
                    if local not in used:
                        ln = (node.lineno or 1) - 1
                        col = node.col_offset or 0
                        out.append(Diagnostic(ln, col, col + len(local) + 7, "imported but unused: " + local, "warning", "unused-import"))
    return out


def _bare_except_warnings(tree: ast.AST) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                ln = (node.lineno or 1) - 1
                col = node.col_offset or 0
                out.append(Diagnostic(ln, col, col + 6, "bare except BH001", "warning", "bare-except"))
    return out


def _none_compare_warnings(tree: ast.AST) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)):
                    is_none = False
                    if isinstance(comp, ast.Constant) and comp.value is None:
                        is_none = True
                    if isinstance(node.left, ast.Constant) and node.left.value is None:
                        is_none = True
                    if is_none:
                        ln = (node.lineno or 1) - 1
                        col = node.col_offset or 0
                        out.append(Diagnostic(ln, col, col + 8, "comparison to None should use is or is not", "warning", "none-compare"))
                        break
    return out


def analyze_text(text: str, filename: str = "") -> tuple[list[Diagnostic], list[Diagnostic]]:
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []
    try:
        tree = ast.parse(text, filename or "<editor>")
    except SyntaxError as e:
        ln = (e.lineno or 1) - 1
        col = (e.offset or 1) - 1
        if col < 0:
            col = 0
        end_col = col + 4
        try:
            if e.text:
                end_col = max(col + 1, len(e.text.rstrip(chr(10))) - len(e.text.lstrip()) + 2)
        except Exception:
            pass
        msg = str(e.msg) if e.msg else "syntax error"
        errors.append(Diagnostic(ln, col, end_col, msg, "error", "syntax"))
        return errors, warnings
    except Exception as e:
        errors.append(Diagnostic(0, 0, 1, str(e), "error", "parse"))
        return errors, warnings
    try:
        used = _collect_used_names(tree)
        warnings.extend(_unused_imports(tree, used))
        warnings.extend(_bare_except_warnings(tree))
        warnings.extend(_none_compare_warnings(tree))
    except Exception:
        pass
    try:
        lines = text.splitlines()
        for idx, ln in enumerate(lines):
            if len(ln) > 120:
                warnings.append(Diagnostic(idx, 120, len(ln), "line too long (" + str(len(ln)) + " > 120)", "warning", "line-too-long"))
            if ln != ln.rstrip(" \t"):
                warnings.append(Diagnostic(idx, len(ln.rstrip(" \t")), len(ln), "trailing whitespace", "warning", "trailing-whitespace"))
            s = ln.strip()
            if s.startswith("import ") and ".." in s:
                warnings.append(Diagnostic(idx, 0, len(ln), "relative import looks suspicious", "warning", "import"))
    except Exception:
        pass
    warnings.sort(key=lambda d: (d.line, d.col))
    return errors, warnings


def count_kinds(errors: list[Diagnostic], warnings: list[Diagnostic]) -> tuple[int, int]:
    return len(errors), len(warnings)


def by_line(diags: list[Diagnostic]) -> dict[int, list[Diagnostic]]:
    m: dict[int, list[Diagnostic]] = {}
    for d in diags:
        m.setdefault(d.line, []).append(d)
    return m
