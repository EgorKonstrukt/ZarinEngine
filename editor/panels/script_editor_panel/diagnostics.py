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


def _single_pass(tree: ast.AST) -> tuple[set[str], list, list, list]:
    used: set[str] = set()
    imports: list = []
    bare: list = []
    none_cmp: list = []
    for node in ast.walk(tree):
        t = type(node).__name__
        if t == "Name":
            try:
                used.add(node.id)
            except Exception:
                pass
        elif t == "Import" or t == "ImportFrom":
            imports.append(node)
        elif t == "ExceptHandler":
            try:
                if node.type is None:
                    bare.append(node)
            except Exception:
                pass
        elif t == "Compare":
            try:
                has_none = False
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant) and comp.value is None:
                        has_none = True
                        break
                if not has_none and isinstance(node.left, ast.Constant) and node.left.value is None:
                    has_none = True
                if has_none:
                    for op in node.ops:
                        if isinstance(op, (ast.Eq, ast.NotEq)):
                            none_cmp.append(node)
                            break
            except Exception:
                pass
    return used, imports, bare, none_cmp


def analyze_text(text: str, filename: str = "") -> tuple[list[Diagnostic], list[Diagnostic]]:
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []
    if len(text) > 800000:
        try:
            tree = ast.parse(text, filename or "<editor>")
        except SyntaxError as e:
            ln = (e.lineno or 1) - 1
            col = (e.offset or 1) - 1
            if col < 0:
                col = 0
            errors.append(Diagnostic(ln, col, col + 4, str(e.msg) if e.msg else "syntax error", "error", "syntax"))
        except Exception as e:
            errors.append(Diagnostic(0, 0, 1, str(e)[:200], "error", "parse"))
        return errors, warnings
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
        errors.append(Diagnostic(0, 0, 1, str(e)[:200], "error", "parse"))
        return errors, warnings
    try:
        used, imports, bare, none_cmp = _single_pass(tree)
        for node in imports:
            try:
                if type(node).__name__ == "Import":
                    for alias in node.names:
                        full = alias.name
                        local = alias.asname if alias.asname else full.split(".")[0]
                        if local not in used:
                            ln = (node.lineno or 1) - 1
                            col = node.col_offset or 0
                            warnings.append(Diagnostic(ln, col, col + len(local) + 7, "imported but unused: " + local, "warning", "unused-import"))
                            if len(warnings) >= 200:
                                break
                else:
                    if node.names is not None:
                        for alias in node.names:
                            if alias.name == "*":
                                continue
                            local = alias.asname if alias.asname else alias.name
                            if local not in used:
                                ln = (node.lineno or 1) - 1
                                col = node.col_offset or 0
                                warnings.append(Diagnostic(ln, col, col + len(local) + 7, "imported but unused: " + local, "warning", "unused-import"))
                                if len(warnings) >= 200:
                                    break
            except Exception:
                continue
            if len(warnings) >= 200:
                break
        for node in bare:
            try:
                ln = (node.lineno or 1) - 1
                col = node.col_offset or 0
                warnings.append(Diagnostic(ln, col, col + 6, "bare except BH001", "warning", "bare-except"))
            except Exception:
                continue
        for node in none_cmp:
            try:
                ln = (node.lineno or 1) - 1
                col = node.col_offset or 0
                warnings.append(Diagnostic(ln, col, col + 8, "comparison to None should use is or is not", "warning", "none-compare"))
            except Exception:
                continue
    except Exception:
        pass
    try:
        lines = text.splitlines()
        n = len(lines)
        step = 1
        if n > 4000:
            step = 2
        for idx in range(0, n, step):
            ln = lines[idx]
            if len(ln) > 120:
                warnings.append(Diagnostic(idx, 120, len(ln), "line too long (" + str(len(ln)) + " > 120)", "warning", "line-too-long"))
                if len(warnings) >= 250:
                    break
            if ln.endswith(" ") or ln.endswith("\t"):
                try:
                    rs = len(ln.rstrip(" \t"))
                    warnings.append(Diagnostic(idx, rs, len(ln), "trailing whitespace", "warning", "trailing-whitespace"))
                    if len(warnings) >= 250:
                        break
                except Exception:
                    pass
    except Exception:
        pass
    try:
        warnings.sort(key=lambda d: (d.line, d.col))
    except Exception:
        pass
    if len(warnings) > 250:
        warnings = warnings[:250]
    return errors, warnings


def count_kinds(errors: list[Diagnostic], warnings: list[Diagnostic]) -> tuple[int, int]:
    return len(errors), len(warnings)


def by_line(diags: list[Diagnostic]) -> dict[int, list[Diagnostic]]:
    m: dict[int, list[Diagnostic]] = {}
    for d in diags:
        m.setdefault(d.line, []).append(d)
    return m
