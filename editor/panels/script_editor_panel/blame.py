# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import re
import time


def parse_blame_output(blame_text: str) -> dict[int, dict]:
    data: dict[int, dict] = {}
    if not blame_text or not blame_text.strip():
        return data
    for raw in blame_text.strip().splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t")
        if len(parts) < 3:
            continue
        try:
            rev_info = parts[0].strip()
            author = parts[1].strip() if len(parts) > 1 else ""
            line_part = parts[2].strip() if len(parts) > 2 else ""
            time_str = parts[3].strip() if len(parts) > 3 else ""
            m = re.search(r"(\d+)\)", line_part)
            if not m:
                first_tok = line_part.split()
                if not first_tok:
                    continue
                num = int(first_tok[0])
            else:
                num = int(m.group(1))
            ln = num - 1
            if not author:
                continue
            short = rev_info.split()[0] if rev_info else ""
            data[ln] = {
                "author": author,
                "short": short[:7] if short else "",
                "time_str": time_str,
                "email": "",
                "message": "",
            }
        except Exception:
            continue
    return data


def enrich_with_log(blame_data: dict[int, dict], git) -> dict[int, dict]:
    if not blame_data:
        return blame_data
    try:
        commits = git.log(80)
        by_short: dict[str, dict] = {}
        for c in commits:
            try:
                by_short[c.get("short", "")] = c
                h = c.get("hash", "")
                if h:
                    by_short[h[:7]] = c
            except Exception:
                continue
        for ln, info in blame_data.items():
            try:
                short = info.get("short", "")
                c = by_short.get(short)
                if c:
                    info["message"] = c.get("message", "")
                    info["email"] = c.get("email", "")
                    ts = c.get("time", 0)
                    if ts and not info.get("time_str"):
                        info["time_str"] = time.strftime("%d.%m.%Y %H:%M", time.localtime(ts))
            except Exception:
                continue
    except Exception:
        pass
    return blame_data


def format_label(info: dict) -> str:
    try:
        author = info.get("author", "")
        when = info.get("time_str", "")
        msg = info.get("message", "")
        if author and when and msg:
            return author + ", " + when + " " + chr(8226) + " " + msg
        if author and when:
            return author + ", " + when
        if author and msg:
            return author + " " + chr(8226) + " " + msg
        return author
    except Exception:
        return ""
