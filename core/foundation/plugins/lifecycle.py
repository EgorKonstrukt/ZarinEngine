# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.foundation.logger import Logger


def _parse_version(text) -> tuple:
    out = []
    cur = ""
    for ch in str(text).strip():
        if ch.isdigit():
            cur += ch
        else:
            if cur:
                out.append(int(cur))
                cur = ""
            if ch.isalnum():
                out.append(ch.lower())
    if cur:
        out.append(int(cur))
    return tuple(out)


def _compare_versions(a, b) -> int:
    pa = _parse_version(a)
    pb = _parse_version(b)
    for x, y in zip(pa, pb):
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return -1 if x < y else 1
        if isinstance(x, int):
            return -1
        if isinstance(y, int):
            return 1
        return -1 if str(x) < str(y) else 1
    if len(pa) == len(pb):
        return 0
    longer = pa if len(pa) > len(pb) else pb
    sign = 1 if len(pa) > len(pb) else -1
    for x in longer[min(len(pa), len(pb)):]:
        if x != 0 and x != "":
            return sign
    return 0


def _split_spec(spec: str) -> list:
    ops = []
    for part in str(spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        for op in ("==", "!=", ">=", "<=", "~=", ">", "<", "="):
            if part.startswith(op):
                ops.append((op, part[len(op):].strip()))
                break
        else:
            ops.append(("==", part))
    return ops


def _compatible_release(version, want) -> bool:
    if _compare_versions(version, want) < 0:
        return False
    wp = _parse_version(want)
    prefix = wp[:-1] if len(wp) > 1 else wp
    vp = _parse_version(version)
    return tuple(vp[:len(prefix)]) == tuple(prefix)


def _spec_satisfied(spec, version) -> bool:
    if not spec:
        return True
    for op, want in _split_spec(spec):
        if op in ("==", "=") and want.endswith(".*"):
            prefix = _parse_version(want[:-2])
            vp = _parse_version(version)
            if tuple(vp[:len(prefix)]) != tuple(prefix):
                return False
            continue
        c = _compare_versions(version, want)
        if op == "==" or op == "=":
            ok = c == 0
        elif op == "!=":
            ok = c != 0
        elif op == ">=":
            ok = c >= 0
        elif op == "<=":
            ok = c <= 0
        elif op == ">":
            ok = c > 0
        elif op == "<":
            ok = c < 0
        elif op == "~=":
            ok = _compatible_release(version, want)
        else:
            return False
        if not ok:
            return False
    return True


def _pep508_name(spec: str) -> str:
    s = str(spec or "").split(";")[0].strip()
    name = ""
    for ch in s:
        if ch.isalnum() or ch in "-_.":
            name += ch
        else:
            break
    return name


def _split_requirement(spec: str):
    s = str(spec or "").split(";")[0].strip()
    name = _pep508_name(s)
    rest = s[len(name):].strip()
    if rest.startswith("["):
        end = rest.find("]")
        rest = rest[end + 1:].strip() if end != -1 else ""
    return name, rest


def _split_plugin_require(req):
    if isinstance(req, dict):
        return str(req.get("name", "")), str(req.get("version", ""))
    s = str(req or "")
    name = _pep508_name(s)
    return name, s[len(name):].strip()


def _normalize_dist_name(name: str) -> str:
    out = []
    for ch in str(name or "").lower():
        out.append("-" if ch in "-_." else ch)
    collapsed = []
    for ch in out:
        if ch == "-" and collapsed and collapsed[-1] == "-":
            continue
        collapsed.append(ch)
    return "".join(collapsed).strip("-")


def _installed_dist_version(name: str):
    try:
        from importlib import metadata as _md
        return _md.version(_normalize_dist_name(name))
    except Exception:
        return None


class LifecycleMixin:
    def shutdown_all(self):
        for name in reversed(self._load_order):
            p = self._plugins.get(name)
            if p:
                try:
                    p.shutdown()
                except Exception as e:
                    Logger.error(f"Error shutting down plugin '{name}': {e}", e)

    def _notify_all(self, method_name: str, *args):
        for p in self.get_all():
            try:
                getattr(p, method_name)(*args)
            except Exception as e:
                Logger.error(f"Plugin {method_name} error: {e}", e)

    def notify_scene_loaded(self, scene):
        self._notify_all("on_scene_loaded", scene)

    def notify_scene_unloaded(self, scene):
        self._notify_all("on_scene_unloaded", scene)

    def notify_project_opened(self):
        for p in self.get_all():
            try:
                p.on_project_opened()
            except Exception as e:
                Logger.error(f"Plugin on_project_opened error: {e}", e)

    def notify_main_window_ready(self, window):
        self._notify_all("on_main_window_ready", window)

    def notify_play_start(self):
        self._notify_all("on_play_start")

    def notify_play_stop(self):
        self._notify_all("on_play_stop")
