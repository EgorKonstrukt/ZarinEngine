# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import time
import numpy as np
from core.maths.math3d import Mat4, Vec3
from core.ecs import _GIZMO_PASSES, _GIZMO_PASS_ORDER
from core.gizmo.pipeline import GizmoPipeline
from editor.viewport.rend.helpers import _GIZMO_INST_CACHE, _FAST_COLLIDER_NAMES, _FAST_COL_CACHE, _FAST_COL_CACHE_MAX, _fast_buf, _collider_row
def _try_fast_colliders(scene):
    try:
        from core.components.physics.box_collider import BoxCollider
        from core.components.physics.sphere_collider import SphereCollider
        from core.components.physics.capsule_collider import CapsuleCollider
    except Exception:
        return None
    try:
        from core._render_batch import build_collider_gizmo_batch as _build
    except Exception:
        return None
    try:
        classes = (("box", BoxCollider), ("sphere", SphereCollider), ("capsule", CapsuleCollider))
    except Exception:
        return None
    try:
        rv = scene._render_version
    except Exception:
        rv = None
    try:
        sid = id(scene)
    except Exception:
        return None
    ent = _FAST_COL_CACHE.get(sid)
    if ent is not None and ent[0] is scene and ent[1] == rv:
        try:
            flushed = scene.peek_flushed_transforms() if hasattr(scene, "peek_flushed_transforms") else []
        except Exception:
            flushed = []
        try:
            overflow = bool(getattr(scene, "_flushed_overflow", False))
        except Exception:
            overflow = False
        shapes = ent[2]
        total = 0
        for _sh in shapes:
            total += _sh[2]
        if not overflow and flushed and total > 0 and len(flushed) * 4 < total:
            try:
                index = ent[3]
                dirty_rows = 0
                for t in flushed:
                    try:
                        lst = index.get(id(t))
                    except Exception:
                        lst = None
                    if not lst:
                        continue
                    for _si, _ri in lst:
                        try:
                            _shp, _params, _n, _rows, _tids = shapes[_si]
                        except Exception:
                            continue
                        try:
                            _tr, _comp = _rows[_ri]
                        except Exception:
                            continue
                        row = _collider_row(_shp, _tr, _comp)
                        if row is None:
                            continue
                        _params[_ri, 0] = row[0]
                        _params[_ri, 1] = row[1]
                        _params[_ri, 2] = row[2]
                        _params[_ri, 3] = row[3]
                        _params[_ri, 4] = row[4]
                        _params[_ri, 5] = row[5]
                        _params[_ri, 6] = row[6]
                        _params[_ri, 7] = row[7]
                        _params[_ri, 8] = row[8]
                        _params[_ri, 9] = row[9]
                        _params[_ri, 10] = row[10]
                        _params[_ri, 11] = row[11]
                        _params[_ri, 12] = row[12]
                        _params[_ri, 13] = row[13]
                        _params[_ri, 14] = row[14]
                        _params[_ri, 15] = row[15]
                        dirty_rows += 1
                if dirty_rows > 0:
                    out = []
                    for _shp, _params, _n, _rows, _tids in shapes:
                        try:
                            buf = _build(_params)
                        except Exception:
                            return None
                        out.append((_shp, buf, int(_n)))
                    try:
                        _FAST_COL_CACHE[sid] = (scene, rv, shapes, index, list(out))
                    except Exception:
                        pass
                    return out
                return list(ent[4])
            except Exception:
                pass
        elif not overflow and flushed is not None and len(flushed) == 0:
            try:
                return list(ent[4])
            except Exception:
                pass
    try:
        stage = _fast_buf()
        if stage is None:
            return None
    except Exception:
        return None
    out = []
    shapes = []
    index = {}
    for shape, cls in classes:
        try:
            ents = scene.get_entities_with_component(cls)
        except Exception:
            continue
        if not ents:
            continue
        try:
            del stage[:]
        except Exception:
            return None
        n = 0
        rows = []
        tids = []
        try:
            for ent in ents:
                try:
                    if not ent._active:
                        continue
                except Exception:
                    continue
                try:
                    lst = ent._type_map.get(cls)
                    if lst is None:
                        lst = ent.get_components(cls)
                        if not lst:
                            continue
                except Exception:
                    continue
                for comp in lst:
                    try:
                        tr = comp.transform
                        if not tr:
                            continue
                        row = _collider_row(shape, tr, comp)
                        if row is None:
                            continue
                        stage.extend(row)
                        rows.append((tr, comp))
                        tids.append(id(tr))
                        n += 1
                    except Exception:
                        continue
        except Exception:
            return None
        if n <= 0:
            continue
        try:
            params = np.frombuffer(stage, dtype=np.float64).reshape(n, 16)
            own = np.empty((n, 16), dtype=np.float64)
            own[:, :] = params
            del params
            buf = _build(own)
        except Exception:
            return None
        out.append((shape, buf, int(n)))
        shapes.append([shape, own, int(n), rows, tids])
    try:
        if len(_FAST_COL_CACHE) >= _FAST_COL_CACHE_MAX:
            _FAST_COL_CACHE.clear()
        idx = {}
        for _si, _sh in enumerate(shapes):
            _tids = _sh[4]
            for _ri, _tid in enumerate(_tids):
                _lst = idx.get(_tid)
                if _lst is None:
                    idx[_tid] = [(_si, _ri)]
                else:
                    _lst.append((_si, _ri))
        _FAST_COL_CACHE[sid] = (scene, rv, shapes, idx, list(out))
    except Exception:
        pass
    return out
def render_component_gizmos(vp, vp_mat: Mat4, fw: int = None, fh: int = None):
    scene = vp._engine.scene if vp._engine else None
    if not scene:
        return
    if fw is None or fh is None:
        try:
            _fw, _fh = vp._get_physical_dims()
            if fw is None:
                fw = _fw
            if fh is None:
                fh = _fh
        except Exception:
            if fw is None:
                fw = 1920
            if fh is None:
                fh = 1080
    try:
        cam_pos = vp._cam.position if vp._cam else Vec3(0, 0, 0)
    except Exception:
        cam_pos = Vec3(0, 0, 0)
    sel = getattr(vp, "_selected_entities", None)
    rv = None
    tv = None
    use_cache = False
    cached = None
    try:
        _play = bool(vp._engine and vp._engine.play_mode)
    except Exception:
        _play = False
    cacheable = (not sel) or _play
    if cacheable:
        try:
            rv = scene._render_version
            tv = scene._transform_version
        except Exception:
            rv = None
        if rv is not None:
            ent = _GIZMO_INST_CACHE.get(id(scene))
            if ent is not None and ent[0] is scene and ent[1] == rv and ent[2] == tv and time.perf_counter() - ent[3] < 2.0 and not ent[6]:
                use_cache = True
                cached = ent
                if len(_GIZMO_INST_CACHE) > 8:
                    _GIZMO_INST_CACHE.clear()
                    _GIZMO_INST_CACHE[id(scene)] = ent
    pipe = GizmoPipeline()
    pipe_col = GizmoPipeline() if not use_cache else None
    meshes = []
    _fast_cols = []
    for pass_name in _GIZMO_PASS_ORDER:
        if use_cache and pass_name == "collider":
            continue
        tgt = pipe_col if (pipe_col is not None and pass_name == "collider") else pipe
        _fast = None
        if pass_name == "collider" and pipe_col is not None:
            try:
                _fast = _try_fast_colliders(scene)
            except Exception:
                _fast = None
        if _fast is not None:
            try:
                _fast_cols.extend(_fast)
            except Exception:
                pass
            for ct in _GIZMO_PASSES.get(pass_name, []):
                try:
                    _cn = ct.__name__
                except Exception:
                    _cn = ""
                if _cn in _FAST_COLLIDER_NAMES:
                    try:
                        meshes.extend(ct.gizmo_collect_meshes(scene))
                    except Exception:
                        pass
                    continue
                ct.gizmo_collect(tgt, scene)
                try:
                    meshes.extend(ct.gizmo_collect_meshes(scene))
                except Exception:
                    pass
            continue
        for ct in _GIZMO_PASSES.get(pass_name, []):
            ct.gizmo_collect(tgt, scene)
            try:
                meshes.extend(ct.gizmo_collect_meshes(scene))
            except Exception:
                pass
    if use_cache:
        for shape_type, buf, n in cached[4]:
            try:
                vp._renderer.render_instanced_gizmo_lines(shape_type, buf, n, vp_mat, fw, fh, thickness_multiplier=1.0, cam_pos=cam_pos)
            except Exception:
                pass
    elif pipe_col is not None:
        try:
            col_lines = len(pipe_col._batches) > 0
        except Exception:
            col_lines = True
        try:
            col_data = pipe_col.get_instance_render_data()
        except Exception:
            col_data = []
        try:
            if _fast_cols:
                col_data = list(_fast_cols) + list(col_data)
        except Exception:
            pass
        if not col_lines and cacheable and rv is not None and col_data:
            try:
                if len(_GIZMO_INST_CACHE) > 8:
                    _GIZMO_INST_CACHE.clear()
                _GIZMO_INST_CACHE[id(scene)] = (scene, rv, tv, time.perf_counter(), col_data, None, False)
            except Exception:
                pass
        for shape_type, buf, n in col_data:
            try:
                vp._renderer.render_instanced_gizmo_lines(shape_type, buf, n, vp_mat, fw, fh, thickness_multiplier=1.0, cam_pos=cam_pos)
            except Exception:
                pass
        if col_lines:
            try:
                pipe._batches.extend(pipe_col._batches)
            except Exception:
                pass
    pipe.flush_and_render(vp, vp_mat, fw=fw, fh=fh)
    if meshes:
        vp._renderer.render_gizmo_meshes(meshes, vp_mat, cam_pos=cam_pos)
__all__ = ["_try_fast_colliders", "render_component_gizmos"]
