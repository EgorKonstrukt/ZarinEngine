# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


def compute_usages(text: str, lines: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    if len(text) > 500000 or len(lines) > 6000:
        return out
    defs: dict[str, list[int]] = {}
    for idx, ln in enumerate(lines):
        if len(ln) < 6:
            continue
        s = ln.strip()
        if s.startswith("class "):
            name = s[6:].split(":")[0].split("(")[0].strip()
            if name:
                if len(defs) > 300:
                    break
                defs.setdefault(name, []).append(idx)
    if not defs:
        return out
    import re as _re
    try:
        pat = _re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
        counts: dict[str, int] = {}
        for m in pat.finditer(text):
            w = m.group(0)
            if w in defs:
                counts[w] = counts.get(w, 0) + 1
                if len(counts) > 2000:
                    break
    except Exception:
        return out
    for name, lst in defs.items():
        cnt = counts.get(name, 0) - len(lst)
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
    if len(lines) > 6000:
        return out
    count = 0
    for idx, ln in enumerate(lines):
        if len(ln) < 4:
            continue
        s = ln.strip()
        if not s.startswith("def "):
            continue
        count += 1
        if count > 250:
            break
        branches = 0
        if " if " in ln:
            branches += 1
        if " for " in ln:
            branches += 1
        if " while " in ln:
            branches += 1
        if " try:" in ln:
            branches += 1
        if " except" in ln:
            branches += 1
        if " and " in ln:
            branches += 1
        if " or " in ln:
            branches += 1
        depth = len(ln) - len(ln.lstrip())
        j = idx + 1
        end = idx + 60
        if end > len(lines):
            end = len(lines)
        while j < end:
            lj = lines[j]
            if lj.strip() == "":
                j += 1
                continue
            d2 = len(lj) - len(lj.lstrip())
            if d2 <= depth:
                break
            if lj.startswith(" " * (depth + 4)) or lj.startswith("\t"):
                if "if " in lj or "for " in lj or "while " in lj or "try:" in lj or "except" in lj:
                    branches += 1
                    if branches > 12:
                        break
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
