# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from typing import Optional
from core.maths.math3d import Vec3


def _nav_sig(self, entity, tr, cols):
    from .nav_world import NavWorld as _O
    return _O._nav_sig(self, entity, tr, cols)

def _rb_begin(self, grid, key, sv):
    from .nav_world import NavWorld as _O
    return _O._rb_begin(self, grid, key, sv)

def _rb_process_entity(self, grid, job, entity):
    from .nav_world import NavWorld as _O
    return _O._rb_process_entity(self, grid, job, entity)

def _rb_pump(self, grid, job, budget: float) -> bool:
    from .nav_world import NavWorld as _O
    return _O._rb_pump(self, grid, job, budget)

def _rb_finish(self, grid, job, key, sv) -> bool:
    from .nav_world import NavWorld as _O
    return _O._rb_finish(self, grid, job, key, sv)

def _maybe_pump_rebuild(self, grid, key, sv, budget: float):
    from .nav_world import NavWorld as _O
    return _O._maybe_pump_rebuild(self, grid, key, sv, budget)

def _poll_rebuild(self, grid) -> bool:
    from .nav_world import NavWorld as _O
    return _O._poll_rebuild(self, grid)

def _is_grid_current(self) -> bool:
    from .nav_world import NavWorld as _O
    return _O._is_grid_current(self)

def wait_grid_ready(self, timeout: float = 30.0) -> bool:
    from .nav_world import NavWorld as _O
    return _O.wait_grid_ready(self, timeout)

def _rebuild_grid(self):
    from .nav_world import NavWorld as _O
    return _O._rebuild_grid(self)

def _box_obb_tuple(self, comp, tr):
    from .nav_world import NavWorld as _O
    return _O._box_obb_tuple(self, comp, tr)

def _box_aligned(self, q) -> bool:
    from .nav_world import NavWorld as _O
    return _O._box_aligned(self, q)

def ignore_entity(self, eid, ignore: bool = True):
    from .nav_world import NavWorld as _O
    return _O.ignore_entity(self, eid, ignore)

def _entity_nav_key(self, entity):
    from .nav_world import NavWorld as _O
    return _O._entity_nav_key(self, entity)

def _collider_comps(self, entity):
    from .nav_world import NavWorld as _O
    return _O._collider_comps(self, entity)

def _world_matrix_rows(self, tr):
    from .nav_world import NavWorld as _O
    return _O._world_matrix_rows(self, tr)

def _fp_entry(self, entity, grid, cs, hw, rr, ignore):
    from .nav_world import NavWorld as _O
    return _O._fp_entry(self, entity, grid, cs, hw, rr, ignore)

def _entity_descs(self, entity, grid):
    from .nav_world import NavWorld as _O
    return _O._entity_descs(self, entity, grid)

def _drive_rebuild_pump(self):
    from .nav_world import NavWorld as _O
    return _O._drive_rebuild_pump(self)

def _poll_dynamics(self) -> bool:
    from .nav_world import NavWorld as _O
    return _O._poll_dynamics(self)

def _submit_raster(self, grid, changed: dict, now: float):
    from .nav_world import NavWorld as _O
    return _O._submit_raster(self, grid, changed, now)

def _get_collider_world_aabb(self, comp) -> Optional[AABB]:
    from .nav_world import NavWorld as _O
    return _O._get_collider_world_aabb(self, comp)

def rebuild_grid(self):
    from .nav_world import NavWorld as _O
    return _O.rebuild_grid(self)

def dilate_for_agent(self, radius: float):
    from .nav_world import NavWorld as _O
    return _O.dilate_for_agent(self, radius)