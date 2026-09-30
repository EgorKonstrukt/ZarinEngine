# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def find_import_block(lines: list[str]) -> tuple[int, int] | None:
    start = -1
    end = -1
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("import ") or s.startswith("from "):
            if start < 0:
                start = idx
            end = idx
        elif start >= 0:
            if s == "":
                continue
            break
    if start < 0 or end <= start:
        return None
    first = lines[start] if 0 <= start < len(lines) else ""
    if "__future__" in first and end > start + 1:
        start = start + 1
        if end <= start:
            return None
    return (start, end)


def find_indent_block(lines: list[str], line: int) -> tuple[int, int] | None:
    if line < 0 or line >= len(lines):
        return None
    s = lines[line].strip()
    if not (s.startswith("import ") or s.startswith("from ") or s.startswith("class ") or s.startswith("def ") or s.startswith("try:")):
        return None
    base = len(lines[line]) - len(lines[line].lstrip())
    j = line + 1
    while j < len(lines):
        lj = lines[j]
        if lj.strip() == "":
            j += 1
            continue
        ind = len(lj) - len(lj.lstrip())
        if ind <= base:
            break
        j += 1
    if j - 1 > line:
        return (line, j - 1)
    return None


def placeholder_for(first_line: str) -> str:
    if "import" in first_line:
        return "import ..."
    return "..."
