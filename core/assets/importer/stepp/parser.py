# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import re


_ENTITY_RE = re.compile(r"#(\d+)\s*=")
_NUMBER_RE = re.compile(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class StepModel:
    __slots__ = ("entities", "schema")

    def __init__(self):
        self.entities: dict[int, tuple[str, list]] = {}
        self.schema: str = ""


def _strip_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "'":
                if i + 1 < n and text[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                in_str = False
            i += 1
            continue
        if c == "'":
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _data_sections(text: str) -> list[str]:
    up = text.upper()
    sections: list[str] = []
    pos = 0
    while True:
        start = up.find("DATA;", pos)
        if start < 0:
            return sections
        depth = 0
        i = start + 5
        n = len(text)
        in_str = False
        while i < n:
            c = text[i]
            if in_str:
                if c == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        i += 2
                        continue
                    in_str = False
                i += 1
                continue
            if c == "'":
                in_str = True
                i += 1
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == ";" and depth == 0:
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if up[j:j + 6] == "ENDSEC":
                    sections.append(text[start + 5:i])
                    pos = i + 1
                    break
            i += 1
        else:
            return sections


class _Cursor:
    __slots__ = ("text", "pos", "end")

    def __init__(self, text: str, pos: int, end: int):
        self.text = text
        self.pos = pos
        self.end = end


def _skip_ws(cur: _Cursor):
    t = cur.text
    while cur.pos < cur.end and t[cur.pos] in " \t\r\n":
        cur.pos += 1


def _parse_value(cur: _Cursor):
    _skip_ws(cur)
    t = cur.text
    if cur.pos >= cur.end:
        return None
    c = t[cur.pos]
    if c == "'":
        return _parse_string(cur)
    if c == "(":
        return _parse_list(cur)
    if c == "#":
        cur.pos += 1
        m = _NUMBER_RE.match(t, cur.pos, cur.end)
        ident = int(m.group(0)) if m else 0
        cur.pos = m.end() if m else cur.pos
        return ("ref", ident)
    if c == "$":
        cur.pos += 1
        return None
    if c == "*":
        cur.pos += 1
        return ("omit",)
    if c == ".":
        end = t.find(".", cur.pos + 1, cur.end)
        if end < 0:
            cur.pos = cur.end
            return ("enum", "")
        val = t[cur.pos + 1:end]
        cur.pos = end + 1
        return ("enum", val)
    m = _NUMBER_RE.match(t, cur.pos, cur.end)
    if m:
        tok = m.group(0)
        cur.pos = m.end()
        if "." in tok or "e" in tok or "E" in tok:
            try:
                return float(tok)
            except ValueError:
                return 0.0
        try:
            return int(tok)
        except ValueError:
            return 0
    w = _WORD_RE.match(t, cur.pos, cur.end)
    if w:
        word = w.group(0)
        cur.pos = w.end()
        _skip_ws(cur)
        if cur.pos < cur.end and t[cur.pos] == "(":
            cur.pos += 1
            _skip_ws(cur)
            if cur.pos < cur.end and t[cur.pos] == "(":
                inner = _parse_list(cur)
            else:
                inner = _parse_value(cur)
            _skip_ws(cur)
            if cur.pos < cur.end and t[cur.pos] == ")":
                cur.pos += 1
            return ("typed", word.upper(), inner)
        return ("name", word.upper())
    cur.pos += 1
    return None


def _parse_string(cur: _Cursor) -> str:
    t = cur.text
    cur.pos += 1
    parts: list[str] = []
    while cur.pos < cur.end:
        c = t[cur.pos]
        if c == "'":
            if cur.pos + 1 < cur.end and t[cur.pos + 1] == "'":
                parts.append("'")
                cur.pos += 2
                continue
            cur.pos += 1
            break
        parts.append(c)
        cur.pos += 1
    return "".join(parts)


def _parse_list_contents(cur: _Cursor) -> list:
    out: list = []
    while True:
        _skip_ws(cur)
        if cur.pos >= cur.end:
            break
        if cur.text[cur.pos] == ")":
            cur.pos += 1
            break
        if cur.text[cur.pos] == ",":
            cur.pos += 1
            continue
        out.append(_parse_value(cur))
    return out


def _parse_list(cur: _Cursor) -> list:
    cur.pos += 1
    return _parse_list_contents(cur)


def _parse_complex_groups(body: str):
    cur = _Cursor(body, 1, len(body))
    parts: list[tuple[str, list]] = []
    while True:
        _skip_ws(cur)
        if cur.pos >= cur.end:
            break
        if body[cur.pos] == ")":
            break
        m = _WORD_RE.match(body, cur.pos, cur.end)
        if not m:
            cur.pos += 1
            continue
        name = m.group(0).upper()
        cur.pos = m.end()
        _skip_ws(cur)
        if cur.pos < cur.end and body[cur.pos] == "(":
            cur.pos += 1
            parts.append((name, _parse_list_contents(cur)))
        else:
            parts.append((name, []))
    if not parts:
        return "", []
    return "complex", parts


def _parse_record(body: str):
    body = body.strip()
    if body.startswith("("):
        return _parse_complex_groups(body)
    m = _WORD_RE.match(body, 0)
    if not m:
        return "", []
    name = m.group(0).upper()
    cur = _Cursor(body, m.end(), len(body))
    _skip_ws(cur)
    if cur.pos < len(body) and body[cur.pos] == "(":
        args = _parse_list(cur)
    else:
        args = []
    return name, args


def parse_step_file(path: str):
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= 0 or size > 512 * 1024 * 1024:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None
    if "ISO-10303-21" not in text[:512].upper() and "ISO-10303-21" not in text[:4096].upper():
        return None
    text = _strip_comments(text)
    up = text.upper()
    schema = ""
    hs = up.find("FILE_SCHEMA")
    if hs >= 0:
        he = text.find(";", hs)
        schema = text[hs:he if he >= 0 else hs + 256]
    model = StepModel()
    model.schema = schema
    for section in _data_sections(text):
        for m in _ENTITY_RE.finditer(section):
            ident = int(m.group(1))
            i = m.end()
            n = len(section)
            depth = 0
            in_str = False
            while i < n:
                c = section[i]
                if in_str:
                    if c == "'":
                        if i + 1 < n and section[i + 1] == "'":
                            i += 2
                            continue
                        in_str = False
                    i += 1
                    continue
                if c == "'":
                    in_str = True
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                elif c == ";" and depth == 0:
                    break
                i += 1
            body = section[m.end():i].strip()
            name, args = _parse_record(body)
            if name:
                model.entities[ident] = (name, args)
    if not model.entities:
        return None
    return model


def entity_of(model: StepModel, ident: int):
    try:
        return model.entities.get(int(ident))
    except (TypeError, ValueError):
        return None


def parts_of(ent) -> list:
    try:
        if ent is not None and isinstance(ent, tuple) and len(ent) == 2 and ent[0] == "complex":
            return list(ent[1])
        if ent is not None and isinstance(ent, tuple) and len(ent) == 2:
            return [(ent[0], ent[1])]
    except (TypeError, ValueError, IndexError):
        pass
    return []


def first_part(model: StepModel, value, *names):
    ent = deref(model, value)
    for pn, pa in parts_of(ent):
        if pn in names:
            return pn, pa
    return None, None


def deref(model: StepModel, value, _depth: int = 0):
    seen = 0
    while isinstance(value, tuple) and len(value) == 2 and value[0] == "ref" and seen < 8:
        ent = entity_of(model, value[1])
        if ent is None:
            return None
        value = ent
        seen += 1
    return value


def as_float(value, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            return float(value)
    except (TypeError, ValueError):
        pass
    return default


def as_enum(value) -> str:
    try:
        if isinstance(value, tuple) and len(value) == 2 and value[0] == "enum":
            return str(value[1]).upper()
        if isinstance(value, tuple) and len(value) == 2 and value[0] == "name":
            return str(value[1]).upper()
        if isinstance(value, str):
            return value.upper()
    except (TypeError, ValueError, IndexError):
        pass
    return ""


def is_true(value) -> bool:
    return as_enum(value) in ("T", "TRUE")
