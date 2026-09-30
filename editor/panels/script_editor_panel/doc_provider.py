# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import builtins
import inspect
import keyword
import re


def _topics() -> dict:
    try:
        import pydoc_data.topics as _t
        return _t.topics
    except Exception:
        return {}


def _clean_topic(text: str) -> str:
    try:
        lines = text.splitlines()
        out: list[str] = []
        for ln in lines:
            s = ln.rstrip()
            if s.strip() == "*" * len(s.strip()) and len(s.strip()) > 2:
                continue
            if s.strip().startswith("===") or s.strip().startswith("---"):
                continue
            out.append(s)
        return chr(10).join(out).strip()
    except Exception:
        return text


def lookup_topic(word: str) -> tuple[str, str] | None:
    if not word:
        return None
    topics = _topics()
    key = word.strip()
    if key in topics:
        try:
            body = _clean_topic(str(topics[key]))
            return ("keyword " + key, body)
        except Exception:
            pass
    low = key.lower()
    if low in topics:
        try:
            body = _clean_topic(str(topics[low]))
            return ("keyword " + low, body)
        except Exception:
            pass
    return None


def lookup_builtin(word: str) -> tuple[str, str] | None:
    if not word:
        return None
    try:
        obj = getattr(builtins, word, None)
        if obj is not None:
            try:
                doc = inspect.getdoc(obj)
            except Exception:
                doc = None
            if doc:
                try:
                    sig = ""
                    try:
                        sig = str(inspect.signature(obj))
                    except Exception:
                        sig = ""
                    title = word + sig if sig else word
                    return (title, doc)
                except Exception:
                    return (word, doc)
    except Exception:
        pass
    return None


def lookup_exception(word: str) -> tuple[str, str] | None:
    if not word:
        return None
    try:
        obj = getattr(builtins, word, None)
        if obj is None:
            import builtins as _b
            obj = getattr(_b, word, None)
        if isinstance(obj, type) and issubclass(obj, BaseException):
            doc = inspect.getdoc(obj)
            if doc:
                return (word, doc)
    except Exception:
        pass
    return None


def lookup_pydoc(word: str) -> tuple[str, str] | None:
    if not word:
        return None
    try:
        import pydoc as _pd
        try:
            doc = _pd.render_doc(word)
        except Exception:
            return None
        if doc and "No Python documentation found" not in doc:
            first = doc.splitlines()[0] if doc.splitlines() else word
            return (first.strip()[:160], doc.strip()[:6000])
    except Exception:
        pass
    return None


def get_documentation(word: str) -> tuple[str, str] | None:
    if not word or not word.strip():
        return None
    w = word.strip()
    if keyword.iskeyword(w):
        r = lookup_topic(w)
        if r is not None:
            return r
    r = lookup_exception(w)
    if r is not None:
        return r
    r = lookup_builtin(w)
    if r is not None:
        return r
    r = lookup_topic(w)
    if r is not None:
        return r
    r = lookup_pydoc(w)
    if r is not None:
        return r
    return None


def word_at(text_line: str, column: int) -> str:
    if not text_line:
        return ""
    n = len(text_line)
    if column < 0:
        column = 0
    if column >= n:
        column = max(0, n - 1)
    if not (text_line[column].isalnum() or text_line[column] == "_"):
        return ""
    s = column
    while s >= 0 and (text_line[s].isalnum() or text_line[s] == "_"):
        s -= 1
    s += 1
    e = column
    while e < n and (text_line[e].isalnum() or text_line[e] == "_"):
        e += 1
    return text_line[s:e]


def is_doc_trigger(word: str) -> bool:
    if not word:
        return False
    if keyword.iskeyword(word):
        return True
    if hasattr(builtins, word):
        return True
    topics = _topics()
    if word in topics or word.lower() in topics:
        return True
    return False
