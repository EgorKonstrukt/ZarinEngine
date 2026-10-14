# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional
from core.gizmo.apiv.types import LineStyle
from core.gizmo.apiv.manager import GizmosManager


_gizmos_instance: Optional[GizmosManager] = None

def get_gizmos():
    return _gizmos_instance
def set_gizmos(gm):
    global _gizmos_instance
    _gizmos_instance = gm


_PASSTHROUGH = {
    'clear', 'clear_persistent', 'clear_unique', 'clear_tag', 'update', 'toggle',
    'set_transform', 'reset_transform', 'push_transform', 'pop_transform',
    'push_style', 'pop_style',
}

def _delegate(method, *a, **kw):
    if _gizmos_instance:
        getattr(_gizmos_instance, method)(*a, **kw)

class _GizmosMeta(type):
    def __getattr__(cls, name):
        if name.startswith('draw_') or name in _PASSTHROUGH:
            return lambda *a, **kw: _delegate(name, *a, **kw)
        if name.startswith('color_') or name in ('style',):
            fn = getattr(GizmosManager, name, None)
            if fn:
                return staticmethod(fn)
        if name in ('show_in_runtime',):
            if _gizmos_instance:
                return _gizmos_instance.show_in_runtime
            return True
        raise AttributeError(f"Gizmos has no attribute '{name}'")
    def __setattr__(cls, name, value):
        if name in ('show_in_runtime',) and _gizmos_instance is not None:
            _gizmos_instance.show_in_runtime = value
            return
        super().__setattr__(name, value)

class Gizmos(metaclass=_GizmosMeta):
    @staticmethod
    def style(**kw):
        if _gizmos_instance:
            return _gizmos_instance.style(**kw)
        from contextlib import nullcontext
        return nullcontext()
    @staticmethod
    def color_rgb(*a, **kw):
        return GizmosManager.color_rgb(*a, **kw)
    @staticmethod
    def color_hex(*a, **kw):
        return GizmosManager.color_hex(*a, **kw)
    @staticmethod
    def color_lerp(*a, **kw):
        return GizmosManager.color_lerp(*a, **kw)
    @staticmethod
    def color_random(*a, **kw):
        return GizmosManager.color_random(*a, **kw)
    @staticmethod
    def color_hsv(*a, **kw):
        return GizmosManager.color_hsv(*a, **kw)
    SOLID = LineStyle.SOLID
    DASHED = LineStyle.DASHED
    DOTTED = LineStyle.DOTTED
    HIDDEN = LineStyle.HIDDEN
