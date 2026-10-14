# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
try:
    from core._constraint_update import batch_update_constraints as _batch_constraints
except ImportError:
    _batch_constraints = None
try:
    from core._ik import batch_update_ik as _batch_ik
except ImportError:
    _batch_ik = None
try:
    from core._scene_query import fast_get_entities_with_component as _fast_get
    _HAS_FAST_QUERY = True
except ImportError:
    _fast_get = None
    _HAS_FAST_QUERY = False
try:
    from core._ecs_batch import batch_update_flat as _batch_flat
    from core._ecs_batch import batch_update_from_transforms as _batch_from_transforms
    from core._ecs_batch import collect_dirty_transforms as _collect_dirty
except ImportError:
    _batch_flat = None
    _batch_from_transforms = None
    _collect_dirty = None
try:
    from core._ecs_batch import batch_update_flat_soa as _batch_flat_soa
except ImportError:
    _batch_flat_soa = None
try:
    from core._ecs_batch import batch_update_from_transforms_soa as _batch_from_soa
except ImportError:
    _batch_from_soa = None
_UNSET = object()
_TRANSFORM_NAME = "Transform"


def _get_engine():
    try:
        from core.engine.eng import Engine
        return Engine.instance()
    except Exception:
        return None


def query_entities(scene, cls, sub_names: list) -> list:
    key = cls.__name__
    if _HAS_FAST_QUERY:
        exact = _fast_get(scene._component_indices, scene._entities, key, scene._render_version, scene._component_entity_frame_cache)
        if not sub_names:
            return exact
        seen: set[str] = set()
        merged: list = []
        for e in exact:
            if e.id not in seen:
                seen.add(e.id)
                merged.append(e)
        for sub_key in sub_names:
            try:
                sub_ents = _fast_get(scene._component_indices, scene._entities, sub_key, scene._render_version, scene._component_entity_frame_cache)
            except Exception:
                continue
            for e in sub_ents:
                if e.id not in seen:
                    seen.add(e.id)
                    merged.append(e)
        return merged
    s = scene._component_indices.get(key)
    ids: set[str] = set(s) if s else set()
    for sub_key in sub_names:
        sub = scene._component_indices.get(sub_key)
        if sub:
            ids.update(sub)
    if not ids:
        return []
    rv = scene._render_version
    cache_tag = (key, rv)
    cc = scene._component_entity_frame_cache
    cached = cc.get(cache_tag)
    if cached is not None:
        return cached
    ents = scene._entities
    result = [ents[eid] for eid in ids if eid in ents]
    cc[cache_tag] = result
    if len(cc) > 256:
        cc.clear()
        cc[cache_tag] = result
    return result


def cached_update_list(scene) -> list:
    if not scene._update_cache_valid:
        scene._update_list_cache = [c for c in scene._active_update_components if c.enabled]
        scene._update_cache_valid = True
    return scene._update_list_cache


def cached_fixed_list(scene) -> list:
    if not scene._fixed_cache_valid:
        scene._fixed_list_cache = [c for c in scene._active_fixed_components if c.enabled]
        scene._fixed_cache_valid = True
    return scene._fixed_list_cache


def partitioned_update(scene):
    if scene._update_partition_valid:
        return scene._update_constraints_cache, scene._update_iks_cache, scene._update_others_cache
    lst = cached_update_list(scene)
    CT = scene._CONSTRAINT_TYPES
    IK = scene._IK_TYPES
    cons = []
    iks = []
    others = []
    ac = cons.append
    ai = iks.append
    ao = others.append
    for c in lst:
        tn = type(c).__name__
        if tn in CT:
            ac(c)
        elif tn in IK:
            ai(c)
        else:
            ao(c)
    scene._update_constraints_cache = cons
    scene._update_iks_cache = iks
    scene._update_others_cache = others
    scene._update_partition_valid = True
    return cons, iks, others


def run_update(scene, dt: float):
    prof = scene._get_profiler()
    if prof is None:
        return
    prof.start("scene_update")
    log_error = None
    constraints, iks, others = partitioned_update(scene)
    if not constraints and not iks and not others:
        prof.stop("scene_update")
        return
    if constraints:
        with prof.scope("constraints"):
            if _batch_constraints is not None:
                try:
                    _batch_constraints(constraints, dt)
                except Exception as ex:
                    if log_error is None:
                        from core.foundation.logger import Logger
                        log_error = Logger.error
                    log_error(f"Constraint batch update error: {ex}")
            else:
                for c in constraints:
                    try:
                        c.on_update(dt)
                    except Exception as ex:
                        if log_error is None:
                            from core.foundation.logger import Logger
                            log_error = Logger.error
                        ent = c._entity
                        log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
    if others:
        with prof.scope("components"):
            for c in others:
                try:
                    c.on_update(dt)
                except Exception as ex:
                    if log_error is None:
                        from core.foundation.logger import Logger
                        log_error = Logger.error
                    ent = c._entity
                    log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
    if iks:
        with prof.scope("ik"):
            if _batch_ik is not None:
                try:
                    _batch_ik(iks, dt)
                except Exception as ex:
                    if log_error is None:
                        from core.foundation.logger import Logger
                        log_error = Logger.error
                    log_error(f"IK batch update error: {ex}")
                    for c in iks:
                        try:
                            c.on_update(dt)
                        except Exception as ex2:
                            if log_error is None:
                                from core.foundation.logger import Logger
                                log_error = Logger.error
                            ent = c._entity
                            log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex2}")
            else:
                for c in iks:
                    try:
                        c.on_update(dt)
                    except Exception as ex:
                        if log_error is None:
                            from core.foundation.logger import Logger
                            log_error = Logger.error
                        ent = c._entity
                        log_error(f"Update error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
    prof.stop("scene_update")


def run_fixed(scene, dt: float):
    prof = scene._get_profiler()
    if prof is None:
        return
    prof.start("scene_fixed_update")
    log_error = None
    for c in cached_fixed_list(scene):
        try:
            c.on_fixed_update(dt)
        except Exception as ex:
            if log_error is None:
                from core.foundation.logger import Logger
                log_error = Logger.error
            ent = c._entity
            log_error(f"FixedUpdate error in {ent._name if ent else '?'}/{type(c).__name__}: {ex}")
    prof.stop("scene_fixed_update")


def run_start(scene):
    prof = scene._get_profiler()
    if prof is None:
        return
    prof.start("scene_start")
    for e in list(scene._entities.values()):
        for c in e.get_all_components():
            try:
                c.on_start()
            except Exception as ex:
                from core.foundation.logger import Logger
                Logger.error(f"Start error: {ex}")
    prof.stop("scene_start")
