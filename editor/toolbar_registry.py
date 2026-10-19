# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

_DEFS: Dict[str, dict] = {}


def define_toolbar_item(item_id: str, config_key: str, default: Any, kind: str = "check", options: Optional[list] = None, mirror_keys: Optional[list] = None) -> dict:
    try:
        entry = _DEFS.get(item_id)
        if entry is None:
            entry = {"item_id": item_id, "config_key": config_key, "default": default, "kind": kind, "options": list(options) if options else None, "mirror_keys": list(mirror_keys) if mirror_keys else []}
            _DEFS[item_id] = entry
        else:
            entry["config_key"] = config_key
            entry["default"] = default
            entry["kind"] = kind
            entry["options"] = list(options) if options else None
            entry["mirror_keys"] = list(mirror_keys) if mirror_keys else []
        return entry
    except Exception:
        return {"item_id": item_id, "config_key": config_key, "default": default, "kind": kind, "options": options, "mirror_keys": list(mirror_keys) if mirror_keys else []}


def get_toolbar_defs() -> List[dict]:
    try:
        return [dict(v) for v in _DEFS.values()]
    except Exception:
        return []


def ensure_toolbar_defaults(cfg) -> None:
    try:
        for entry in list(_DEFS.values()):
            try:
                key = entry.get("config_key", "")
                if not key:
                    continue
                if not cfg.has(key):
                    try:
                        cfg.set(key, entry.get("default"), notify=False)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


class ToolbarRegistry:
    def __init__(self, mw=None):
        self._mw = mw
        self._bindings: Dict[str, dict] = {}
        self._loading = False

    @property
    def loading(self) -> bool:
        return self._loading

    def bind(self, item_id: str, get_value: Callable[[], Any], set_value: Callable[[Any], None], apply: Optional[Callable[[Any, Any], None]] = None) -> None:
        try:
            self._bindings[item_id] = {"get": get_value, "set": set_value, "apply": apply}
        except Exception:
            pass

    def unbind(self, item_id: str) -> None:
        try:
            self._bindings.pop(item_id, None)
        except Exception:
            pass

    def bound_ids(self) -> List[str]:
        try:
            return list(self._bindings.keys())
        except Exception:
            return []

    def _cfg(self):
        try:
            from core.config.config import get_global_config
            return get_global_config()
        except Exception:
            return None

    def _def_for(self, item_id: str) -> Optional[dict]:
        try:
            return _DEFS.get(item_id)
        except Exception:
            return None

    def store(self, item_id: str, value: Any) -> None:
        try:
            if self._loading:
                return
            entry = self._def_for(item_id)
            if entry is None:
                return
            cfg = self._cfg()
            if cfg is None:
                return
            cfg.set(entry["config_key"], value, notify=False)
            for mirror in entry.get("mirror_keys", []) or []:
                try:
                    cfg.set(mirror, value, notify=False)
                except Exception:
                    pass
            cfg.save()
        except Exception:
            pass

    def save(self) -> None:
        try:
            cfg = self._cfg()
            if cfg is None:
                return
            for item_id, binding in list(self._bindings.items()):
                try:
                    entry = self._def_for(item_id)
                    if entry is None:
                        continue
                    get_fn = binding.get("get")
                    if not callable(get_fn):
                        continue
                    value = get_fn()
                    cfg.set(entry["config_key"], value, notify=False)
                    for mirror in entry.get("mirror_keys", []) or []:
                        try:
                            cfg.set(mirror, value, notify=False)
                        except Exception:
                            pass
                except Exception:
                    pass
            cfg.save()
        except Exception:
            pass

    def load(self) -> None:
        try:
            cfg = self._cfg()
            if cfg is None:
                return
            self._loading = True
            try:
                for item_id, binding in list(self._bindings.items()):
                    try:
                        entry = self._def_for(item_id)
                        if entry is None:
                            continue
                        set_fn = binding.get("set")
                        if not callable(set_fn):
                            continue
                        value = cfg.get(entry["config_key"], entry.get("default"))
                        set_fn(value)
                    except Exception:
                        pass
            finally:
                self._loading = False
        except Exception:
            try:
                self._loading = False
            except Exception:
                pass

    def apply(self, mw=None) -> None:
        try:
            target = mw if mw is not None else self._mw
            cfg = self._cfg()
            if cfg is None or target is None:
                return
            for item_id, binding in list(self._bindings.items()):
                try:
                    entry = self._def_for(item_id)
                    if entry is None:
                        continue
                    fn = binding.get("apply")
                    if not callable(fn):
                        continue
                    value = cfg.get(entry["config_key"], entry.get("default"))
                    fn(target, value)
                except Exception:
                    pass
        except Exception:
            pass

    def save_ids(self, item_ids: list) -> None:
        try:
            cfg = self._cfg()
            if cfg is None:
                return
            wanted = set(item_ids or [])
            for item_id, binding in list(self._bindings.items()):
                try:
                    if wanted and item_id not in wanted:
                        continue
                    entry = self._def_for(item_id)
                    if entry is None:
                        continue
                    get_fn = binding.get("get")
                    if not callable(get_fn):
                        continue
                    value = get_fn()
                    cfg.set(entry["config_key"], value, notify=False)
                    for mirror in entry.get("mirror_keys", []) or []:
                        try:
                            cfg.set(mirror, value, notify=False)
                        except Exception:
                            pass
                except Exception:
                    pass
            cfg.save()
        except Exception:
            pass

    def load_ids(self, item_ids: list) -> None:
        try:
            cfg = self._cfg()
            if cfg is None:
                return
            wanted = set(item_ids or [])
            self._loading = True
            try:
                for item_id, binding in list(self._bindings.items()):
                    try:
                        if wanted and item_id not in wanted:
                            continue
                        entry = self._def_for(item_id)
                        if entry is None:
                            continue
                        set_fn = binding.get("set")
                        if not callable(set_fn):
                            continue
                        value = cfg.get(entry["config_key"], entry.get("default"))
                        set_fn(value)
                    except Exception:
                        pass
            finally:
                self._loading = False
        except Exception:
            try:
                self._loading = False
            except Exception:
                pass

    def apply_ids(self, item_ids: list, mw=None) -> None:
        try:
            target = mw if mw is not None else self._mw
            cfg = self._cfg()
            if cfg is None or target is None:
                return
            wanted = set(item_ids or [])
            for item_id, binding in list(self._bindings.items()):
                try:
                    if wanted and item_id not in wanted:
                        continue
                    entry = self._def_for(item_id)
                    if entry is None:
                        continue
                    fn = binding.get("apply")
                    if not callable(fn):
                        continue
                    value = cfg.get(entry["config_key"], entry.get("default"))
                    fn(target, value)
                except Exception:
                    pass
        except Exception:
            pass

    def apply_one(self, item_id: str, mw=None, value: Any = None) -> None:
        try:
            target = mw if mw is not None else self._mw
            if target is None:
                return
            binding = self._bindings.get(item_id)
            if not binding:
                return
            fn = binding.get("apply")
            if not callable(fn):
                return
            if value is None:
                try:
                    cfg = self._cfg()
                    entry = self._def_for(item_id)
                    if cfg is not None and entry is not None:
                        value = cfg.get(entry["config_key"], entry.get("default"))
                    else:
                        value = binding["get"]()
                except Exception:
                    return
            fn(target, value)
        except Exception:
            pass

    def sync_key(self, key: str, mw=None) -> None:
        try:
            target = mw if mw is not None else self._mw
            cfg = self._cfg()
            if cfg is None:
                return
            self._loading = True
            try:
                for item_id, binding in list(self._bindings.items()):
                    try:
                        entry = self._def_for(item_id)
                        if entry is None:
                            continue
                        keys = [entry.get("config_key")] + list(entry.get("mirror_keys", []) or [])
                        if key not in keys:
                            continue
                        set_fn = binding.get("set")
                        if not callable(set_fn):
                            continue
                        value = cfg.get(entry["config_key"], entry.get("default"))
                        set_fn(value)
                    except Exception:
                        pass
            finally:
                self._loading = False
            for item_id, binding in list(self._bindings.items()):
                try:
                    entry = self._def_for(item_id)
                    if entry is None:
                        continue
                    keys = [entry.get("config_key")] + list(entry.get("mirror_keys", []) or [])
                    if key not in keys:
                        continue
                    fn = binding.get("apply")
                    if callable(fn) and target is not None:
                        value = cfg.get(entry["config_key"], entry.get("default"))
                        fn(target, value)
                except Exception:
                    pass
        except Exception:
            try:
                self._loading = False
            except Exception:
                pass


def get_toolbar_registry(mw) -> ToolbarRegistry:
    try:
        reg = getattr(mw, "_toolbar_registry", None)
        if isinstance(reg, ToolbarRegistry):
            return reg
    except Exception:
        pass
    reg = ToolbarRegistry(mw)
    try:
        mw._toolbar_registry = reg
    except Exception:
        pass
    return reg


def define_builtin_toolbar_items() -> None:
    define_toolbar_item("gizmo_mode", "toolbar.gizmo_mode", "translate", kind="mode", options=["none", "translate", "rotate", "scale"])
    define_toolbar_item("gizmo_space", "toolbar.gizmo_space", "world", kind="combo", options=["world", "local"])
    define_toolbar_item("multigizmo_enabled", "gizmo.multigizmo_enabled", False, kind="check")
    define_toolbar_item("multigizmo_alignment", "gizmo.multigizmo_alignment", "local", kind="combo", options=["local", "world", "view", "custom"])
    define_toolbar_item("multigizmo_orientation_lock", "gizmo.multigizmo_orientation_lock", False, kind="check")
    define_toolbar_item("multigizmo_visible", "gizmo.multigizmo_visible", True, kind="check")
    define_toolbar_item("render_mode", "toolbar.render_mode", "shaded", kind="mode", options=["shaded", "shaded_wireframe", "flat"])
    define_toolbar_item("camera_projection", "toolbar.camera_projection", "perspective", kind="combo", options=["perspective", "orthographic"])
    define_toolbar_item("camera_2d", "toolbar.camera_2d", False, kind="check")
    define_toolbar_item("skybox", "toolbar.skybox", True, kind="check", mirror_keys=["rendering.show_skybox"])
    define_toolbar_item("effects", "toolbar.effects", True, kind="check")
    define_toolbar_item("grid", "toolbar.grid", True, kind="check", mirror_keys=["rendering.show_grid"])
    define_toolbar_item("snap", "toolbar.snap", True, kind="check")
    define_toolbar_item("snap_translate", "toolbar.snap_translate", 0.25, kind="spin")
    define_toolbar_item("snap_rotate", "toolbar.snap_rotate", 15.0, kind="spin")
    define_toolbar_item("snap_scale", "toolbar.snap_scale", 0.25, kind="spin")
    define_toolbar_item("gizmo_visible", "toolbar.gizmo_visible", True, kind="check")
    define_toolbar_item("nav_mode", "camera.nav_mode", "fly", kind="combo", options=["fly", "orbit"])
    define_toolbar_item("time_scale", "engine.time_scale", 1.0, kind="spin")


define_builtin_toolbar_items()
