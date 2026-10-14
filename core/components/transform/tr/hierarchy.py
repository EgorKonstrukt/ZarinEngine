# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.components.transform.tr.component import TransformBase
try:
    from core._ecs_batch import batch_update_from_transforms as _batch_from_transforms
    from core._ecs_batch import batch_update_flat as _batch_flat
except ImportError:
    _batch_from_transforms = None
    _batch_flat = None
try:
    from core._ecs_batch import batch_update_from_transforms_soa as _batch_from_soa
except ImportError:
    _batch_from_soa = None
class TransformHierarchyBase(TransformBase):
    __slots__ = ()
    def _mark_dirty(self):
        if self._dirty:
            return
        ent = self._entity
        if ent is None:
            self._dirty = True
            return
        children = ent._children
        if not children:
            self._dirty = True
            scene = ent._scene
            if scene is not None:
                scene._dirty_roots.add(self)
                scene._spatial_dirty = True
                scene._transform_version_pending = True
            return
        scene = ent._scene
        if scene is None:
            stack = [self]
            pop = stack.pop
            push = stack.append
            while stack:
                t = pop()
                if t._dirty:
                    continue
                t._dirty = True
                e = t._entity
                if e is None:
                    continue
                for child in e._children:
                    ct = child._transform
                    if ct is not None and not ct._dirty:
                        push(ct)
            return
        dirty_add = scene._dirty_roots.add
        stack = [self]
        pop = stack.pop
        push = stack.append
        while stack:
            t = pop()
            if t._dirty:
                continue
            t._dirty = True
            e = t._entity
            if e is None:
                continue
            dirty_add(t)
            for child in e._children:
                ct = child._transform
                if ct is not None and not ct._dirty:
                    push(ct)
        scene._spatial_dirty = True
        scene._transform_version_pending = True
    @staticmethod
    def batch_update_world_matrices(transforms: list):
        n = len(transforms)
        if n == 0:
            return
        bft = _batch_from_transforms
        if bft is not None:
            for t in transforms:
                if t._world_target is not None:
                    for u in transforms:
                        u._update_world_matrix()
                    return
            bft(transforms)
            for t in transforms:
                if t._dirty:
                    continue
                e = t._entity
                if e is None:
                    continue
                sc = e._scene
                if sc is None:
                    continue
                slot = t._soa
                if slot >= 0 and slot < sc._soa_cap:
                    sc._soa_world[slot] = t._world_matrix._d
            return
        for t in transforms:
            t._update_world_matrix()
    @staticmethod
    def mark_many_dirty(transforms: list):
        n = len(transforms)
        if n == 0:
            return
        stack = []
        stack_append = stack.append
        for t in transforms:
            if not t._dirty:
                stack_append(t)
        pop = stack.pop
        while stack:
            t = pop()
            if t._dirty:
                continue
            t._dirty = True
            ent = t._entity
            if ent is None:
                continue
            sc = ent._scene
            if sc is not None:
                sc._dirty_roots.add(t)
                sc._spatial_dirty = True
                sc._transform_version_pending = True
            children = ent._children
            for child in children:
                ct = child._transform
                if ct is not None and not ct._dirty:
                    stack_append(ct)
