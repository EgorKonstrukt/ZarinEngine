# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def compute_usages(text: str, lines: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    defs: dict[str, list[int]] = {}
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("class "):
            name = s[6:].split(":")[0].split("(")[0].strip()
            if name:
                defs.setdefault(name, []).append(idx)
    for name, lst in defs.items():
        cnt = text.count(name) - len(lst)
        if cnt < 0:
            cnt = 0
        for li in lst:
            if cnt == 0:
                out[li] = "no usages"
            elif cnt == 1:
                out[li] = "1 usage"
            else:
                out[li] = str(cnt) + " usages"
    return out


def compute_complexity(lines: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if not s.startswith("def "):
            continue
        branches = 0
        for kw in (" if ", " for ", " while ", " try:", " except", " and ", " or ", " with "):
            if kw in ln:
                branches += 1
        depth = len(ln) - len(ln.lstrip())
        j = idx + 1
        while j < len(lines) and j < idx + 80:
            lj = lines[j]
            if lj.strip() == "":
                j += 1
                continue
            d2 = len(lj) - len(lj.lstrip())
            if d2 <= depth:
                break
            for kw in ("if ", "for ", "while ", "try:", "except", " and ", " or "):
                if kw in lj:
                    branches += 1
            j += 1
        pct = min(92, 12 + branches * 7)
        unit = chr(37)
        if branches <= 4:
            out[idx] = "low complexity (" + str(pct) + unit + ")"
        elif branches <= 8:
            out[idx] = "moderate complexity (" + str(pct) + unit + ")"
        else:
            out[idx] = "high complexity (" + str(pct) + unit + ")"
    return out
