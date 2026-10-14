# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
from typing import Optional
from core.physics import PhysicsProcess, PhysicsScene
from core.physics.shapep import find_shapes_info
from core.foundation.logger import Logger
_RAD = math.radians
class PhysicsSyncMixin:
    def _body_with_slot(self, entity, tr) -> Optional[dict]:
        return self._body_with_slot_in_process(entity, tr, self._physics_process)
    def _body_with_slot_in_process(self, entity, tr, proc: PhysicsProcess) -> Optional[dict]:
        rb = entity._components.get("Rigidbody")
        rb2d = entity._components.get("Rigidbody2D")
        try:
            from core.components.physics.soft_body import SoftBody
            soft = entity.get_component(SoftBody)
            if soft is not None and getattr(soft, "enabled", True):
                return None
        except Exception:
            pass
        shapes = find_shapes_info(entity, tr)
        if not shapes:
            return None
        shape_info = shapes[0]
        is_2d = rb2d is not None
        lp = tr._local_pos
        q = tr._local_rot
        if is_2d:
            pos = (lp.x, lp.y, 0.0)
            sz = 2.0 * math.asin(max(-1.0, min(1.0, q.z)))
            rot = (0.0, 0.0, sz)
            mass = 0.0 if rb2d.is_kinematic else rb2d.mass
            is_kinematic = rb2d.is_kinematic
        else:
            pos = (lp.x, lp.y, lp.z)
            euler = tr.local_euler_angles
            rot = (_RAD(euler.x), _RAD(euler.y), _RAD(euler.z))
            mass = 0.0 if rb.is_kinematic else rb.mass
            is_kinematic = rb.is_kinematic
        slot = proc.alloc_slot()
        proc.entity_slot_map[entity.id] = slot
        self._cache_version += 1
        return {"slot": slot, "entity_id": entity.id, "is_2d": is_2d, "shape_type": shape_info["type"], "shape_params": shape_info["params"], "shapes": shapes, "position": pos, "rotation": rot, "mass": mass, "friction": shape_info.get("friction", 0.6), "restitution": shape_info.get("restitution", 0.0), "is_trigger": shape_info.get("is_trigger", False), "is_kinematic": is_kinematic, "collision_layer": shape_info.get("layer", 0), "collision_mask": shape_info.get("mask", 0xFFFF)}
    def _get_entity_layer(self, entity) -> int:
        for comp in entity.get_all_components():
            if hasattr(comp, "layer"):
                return int(getattr(comp, "layer", 0))
        return 0
    def _get_soft_sync_helper(self):
        if self._soft_sync_helper is None:
            try:
                self._soft_sync_helper = PhysicsScene(None)
            except Exception:
                return None
        return self._soft_sync_helper
    def _clear_soft_remote(self):
        for eid in list(self._soft_remote.keys()):
            self._drop_soft_remote(eid)
        self._soft_remote.clear()
        self._soft_over_cap_warned.clear()
    def _drop_soft_remote(self, entity_id: str):
        info = self._soft_remote.pop(entity_id, None)
        if info is None:
            return
        try:
            proc = info.get("proc")
            slot = info.get("slot", -1)
            if proc is not None and slot is not None and slot >= 0:
                try:
                    proc.entity_soft_slot_map.pop(entity_id, None)
                except Exception:
                    pass
                try:
                    proc.free_soft_slot(slot)
                except Exception:
                    pass
                try:
                    if proc.is_alive():
                        proc.send({"type": "remove_bodies", "entity_ids": [entity_id]})
                except Exception:
                    pass
        except Exception:
            pass
    def _build_soft_dict(self, entity, tr, soft, proc, slot=None, reuse_mesh=None) -> Optional[dict]:
        from core.components.rendering.renderers.mesh_filter import MeshFilter
        from core.components.physics.meshcol import load_collision_geometry
        mf = entity.get_component(MeshFilter)
        mesh_path = (mf.mesh_path or "") if mf else ""
        if not mesh_path:
            Logger.warning(str("SoftBody") + " needs MeshFilter mesh")
            return None
        verts_b, indices_b = (None, None)
        if reuse_mesh is not None:
            try:
                verts_b, indices_b = reuse_mesh
            except Exception:
                verts_b, indices_b = (None, None)
        if verts_b is None or indices_b is None:
            try:
                verts, indices, _k = load_collision_geometry(mesh_path)
            except Exception:
                verts, indices = None, None
            if verts is None or indices is None or len(verts) < 3:
                Logger.warning(str("SoftBody mesh unreadable"))
                return None
            try:
                verts_b = np.ascontiguousarray(verts, dtype=np.float32).tobytes()
                indices_b = np.ascontiguousarray(np.asarray(indices).reshape(-1), dtype=np.int64).tobytes()
            except Exception:
                return None
        if slot is None:
            try:
                slot = proc.alloc_soft_slot()
            except Exception as e:
                Logger.warning(str("SoftBody no free slot"))
                return None
            try:
                proc.entity_soft_slot_map[entity.id] = slot
            except Exception:
                pass
        lp = tr._local_pos
        s = tr.local_scale
        euler = tr.local_euler_angles
        bend = soft.bend_mode.value if hasattr(soft.bend_mode, "value") else str(soft.bend_mode)
        pin = soft.pin_mode.value if hasattr(soft.pin_mode, "value") else str(soft.pin_mode)
        return {"entity_id": entity.id, "slot": int(slot), "verts_b": verts_b, "indices_b": indices_b, "scale": (float(s.x), float(s.y), float(s.z)), "position": (float(lp._x), float(lp._y), float(lp._z)), "rotation": (_RAD(euler.x), _RAD(euler.y), _RAD(euler.z)), "mass": float(soft.mass), "compliance": float(soft.compliance), "bend_mode": str(bend), "pressure": float(soft.pressure), "damping": float(soft.damping), "iterations": int(soft.iterations), "gravity_factor": float(soft.gravity_scale), "friction": float(soft.material_friction), "restitution": float(soft.material_bounciness), "vertex_radius": float(soft.vertex_radius), "max_velocity": float(soft.max_velocity), "max_vertices": int(soft.max_vertices), "pin_mode": str(pin), "pin_fraction": float(soft.pin_fraction), "double_sided": bool(soft.double_sided), "update_com": bool(soft.update_com), "layer": int(soft.layer), "mask": int(soft.mask) & 0xFFFFFFFF, "mesh_path": mesh_path}
    def _track_soft_dict(self, entity, soft, tr, proc, slot: int, d: dict):
        try:
            sig = PhysicsScene._soft_sig(entity, soft, tr)
        except Exception:
            sig = None
        try:
            pose = PhysicsScene._soft_applied_pose(tr)
        except Exception:
            pose = None
        try:
            pinned = str(d.get("pin_mode", "none")).lower() in ("top", "bottom")
        except Exception:
            pinned = False
        self._soft_remote[entity.id] = {"slot": int(slot), "proc": proc, "sig": sig, "count": -1, "pending": True, "layer": int(d.get("layer", 0)), "mask": int(d.get("mask", 0xFFFF)) & 0xFFFFFFFF, "mass": float(d.get("mass", 1.0)), "max_velocity": float(d.get("max_velocity", 50.0)), "pinned": bool(pinned), "radius": float(d.get("vertex_radius", 0.05)), "mesh_path": d.get("mesh_path", ""), "scale": (float(d["scale"][0]), float(d["scale"][1]), float(d["scale"][2])), "max_vertices": int(d.get("max_vertices", 0)), "mesh_b": (d.get("verts_b"), d.get("indices_b"))}
        if pose is not None:
            try:
                soft._soft_applied_pose = pose
            except Exception:
                pass
    def _collect_soft_dicts(self, scene, proc) -> list:
        from core.components.physics.soft_body import SoftBody
        out = []
        try:
            entities = scene.get_all_entities()
        except Exception:
            return out
        for entity in entities:
            try:
                if entity.id in self._soft_remote:
                    continue
                soft = entity.get_component(SoftBody)
                if soft is None or not getattr(soft, "enabled", True):
                    continue
                tr = entity._components.get("Transform")
                if tr is None:
                    continue
                d = self._build_soft_dict(entity, tr, soft, proc)
                if d is None:
                    continue
                self._track_soft_dict(entity, soft, tr, proc, d["slot"], d)
                out.append(d)
            except Exception:
                continue
        return out
    def _harvest_soft_created(self, proc, scene, results):
        if not results:
            return
        try:
            entities = scene._entities
        except Exception:
            return
        from core.components.physics.soft_body import SoftBody
        for r in results:
            try:
                items = r.get("soft_created", None) if isinstance(r, dict) else None
            except Exception:
                continue
            if not items:
                continue
            for item in items:
                try:
                    eid = item.get("entity_id")
                    info = self._soft_remote.get(eid)
                    if info is None or info.get("proc") is not proc:
                        continue
                    if not item.get("ok"):
                        Logger.warning(str("SoftBody worker creation failed"))
                        self._drop_soft_remote(eid)
                        continue
                    entity = entities.get(eid)
                    if entity is None:
                        self._drop_soft_remote(eid)
                        continue
                    soft = entity.get_component(SoftBody)
                    if soft is None:
                        self._drop_soft_remote(eid)
                        continue
                    verts = np.frombuffer(item["verts_b"], dtype=np.float32).reshape(-1, 3).copy()
                    faces = np.frombuffer(item["faces_b"], dtype=np.int32).astype(np.int64, copy=True)
                    if len(verts) < 3 or int(item.get("count", 0)) <= 0:
                        self._drop_soft_remote(eid)
                        continue
                    soft._soft_verts = np.ascontiguousarray(verts, dtype=np.float32)
                    soft._soft_faces = np.ascontiguousarray(faces, dtype=np.int64)
                    info["count"] = int(item["count"])
                    info["pending"] = False
                    try:
                        info["radius"] = max(float(item.get("radius", info["radius"])), 1e-4)
                    except Exception:
                        pass
                except Exception:
                    continue
    def _soft_remote_check_update(self, entity, soft, tr, info, proc) -> bool:
        try:
            sig = PhysicsScene._soft_sig(entity, soft, tr)
        except Exception:
            sig = None
        try:
            dirty = bool(getattr(tr, "_physics_dirty", False))
        except Exception:
            dirty = False
        pose_moved = False
        if dirty:
            try:
                cur = PhysicsScene._soft_applied_pose(tr)
            except Exception:
                cur = None
            if cur is None:
                try:
                    tr._physics_dirty = False
                except Exception:
                    pass
            else:
                try:
                    prev = getattr(soft, "_soft_applied_pose", None)
                except Exception:
                    prev = None
                if prev is None:
                    pose_moved = True
                else:
                    try:
                        dp = abs(cur[0] - prev[0]) + abs(cur[1] - prev[1]) + abs(cur[2] - prev[2])
                        dq = 1.0 - abs(cur[3] * prev[3] + cur[4] * prev[4] + cur[5] * prev[5] + cur[6] * prev[6])
                        ds = abs(cur[7] - prev[7]) + abs(cur[8] - prev[8]) + abs(cur[9] - prev[9])
                    except Exception:
                        dp, dq, ds = 0.0, 0.0, 0.0
                    pose_moved = (dp > 1e-6 or dq > 1e-8 or ds > 1e-9)
        if (sig is not None and sig != info.get("sig")) or pose_moved:
            try:
                from core.components.rendering.renderers.mesh_filter import MeshFilter
                mf = entity.get_component(MeshFilter)
                mesh_path = (mf.mesh_path or "") if mf else ""
            except Exception:
                mesh_path = info.get("mesh_path", "")
            reuse = None
            try:
                if mesh_path and mesh_path == info.get("mesh_path"):
                    reuse = info.get("mesh_b")
            except Exception:
                reuse = None
            d = self._build_soft_dict(entity, tr, soft, proc, slot=info["slot"], reuse_mesh=reuse)
            if d is None:
                info["sig"] = sig
                try:
                    tr._physics_dirty = False
                except Exception:
                    pass
                return False
            try:
                proc.send({"type": "update_soft_body", "soft": d})
            except Exception:
                return False
            info["sig"] = sig
            info["pending"] = True
            for k in ("layer", "mask", "mass", "max_velocity", "mesh_path", "max_vertices"):
                try:
                    if k in ("mask",):
                        info[k] = int(d.get(k, info.get(k, 0xFFFF))) & 0xFFFFFFFF
                    elif k in ("layer", "max_vertices"):
                        info[k] = int(d.get(k, info.get(k, 0)))
                    elif k in ("mass", "max_velocity"):
                        info[k] = float(d.get(k, info.get(k, 1.0)))
                    else:
                        info[k] = d.get(k, info.get(k))
                except Exception:
                    pass
            try:
                info["pinned"] = str(d.get("pin_mode", "none")).lower() in ("top", "bottom")
                sc = d.get("scale", info.get("scale", (1.0, 1.0, 1.0)))
                info["scale"] = (float(sc[0]), float(sc[1]), float(sc[2]))
                info["mesh_b"] = (d.get("verts_b"), d.get("indices_b"))
            except Exception:
                pass
            try:
                tr._physics_dirty = False
            except Exception:
                pass
            return True
        if dirty:
            try:
                tr._physics_dirty = False
            except Exception:
                pass
        return False
    def _sync_soft_remote_entity(self, proc, entity, soft, tr, info, helper):
        slot = info.get("slot", -1)
        try:
            sbuf = proc.soft_shared
        except Exception:
            return None
        try:
            count = sbuf.read_count(slot)
        except Exception:
            return None
        if count <= 0:
            if count < 0 and entity.id not in self._soft_over_cap_warned:
                self._soft_over_cap_warned.add(entity.id)
                Logger.warning(str("SoftBody vertex cap exceeded"))
            return None
        if info.get("count", -1) != count:
            return None
        try:
            data = sbuf.read_soft(slot)
        except Exception:
            return None
        if data is None:
            return None
        world, pos, quat, vel = data
        if world is None or len(world) != count:
            return None
        try:
            helper._soft_apply_com(entity, soft, tr, None, com=(pos, quat))
        except Exception:
            pass
        try:
            invW = PhysicsScene._entity_frame_inv(tr)
        except Exception:
            invW = None
        if invW is None:
            return None
        try:
            w4 = np.ones((len(world), 4), dtype=np.float64)
            w4[:, :3] = np.asarray(world, dtype=np.float64)
            local = (w4 @ invW)[:, :3].astype(np.float32)
        except Exception:
            return None
        if not np.all(np.isfinite(local)):
            return None
        try:
            helper._sync_soft_mesh(entity.id, soft, local)
        except Exception:
            return None
        return data
    def _sync_soft_remote(self, proc, scene, dt: float, pending_results) -> dict:
        vels: dict = {}
        try:
            self._harvest_soft_created(proc, scene, pending_results)
        except Exception:
            pass
        try:
            tracked = [(eid, info) for eid, info in self._soft_remote.items() if info.get("proc") is proc]
        except Exception:
            return vels
        if not tracked:
            return vels
        try:
            helper = self._get_soft_sync_helper()
        except Exception:
            helper = None
        if helper is None:
            return vels
        try:
            entities = scene._entities
        except Exception:
            return vels
        from core.components.physics.soft_body import SoftBody
        try:
            step_dt = max(float(dt), 1e-6)
        except Exception:
            step_dt = 1.0 / 60.0
        datas = {}
        for eid, info in tracked:
            try:
                entity = entities.get(eid)
                if entity is None or not getattr(entity, "_active", True):
                    continue
                soft = entity.get_component(SoftBody)
                if soft is None or not getattr(soft, "enabled", True):
                    continue
                tr = entity._components.get("Transform")
                if tr is None:
                    continue
                try:
                    if self._soft_remote_check_update(entity, soft, tr, info, proc):
                        continue
                except Exception:
                    pass
                data = self._sync_soft_remote_entity(proc, entity, soft, tr, info, helper)
                if data is not None:
                    datas[eid] = (data, info)
            except Exception:
                continue
        if len(datas) >= 2:
            try:
                items = []
                for eid, (data, info) in datas.items():
                    world, _pos, _quat, vel = data
                    v = np.asarray(world, dtype=np.float64)
                    c = v.mean(axis=0)
                    bmin = v.min(axis=0)
                    bmax = v.max(axis=0)
                    try:
                        r = max(float(info.get("radius", 0.05)), 1e-4)
                    except Exception:
                        r = 0.05
                    items.append({"key": eid, "center": (float(c[0]), float(c[1]), float(c[2])), "aabb_min": (float(bmin[0]) - r, float(bmin[1]) - r, float(bmin[2]) - r), "aabb_max": (float(bmax[0]) + r, float(bmax[1]) + r, float(bmax[2]) + r), "velocity": (float(vel[0]), float(vel[1]), float(vel[2])), "pinned": bool(info.get("pinned", False)), "mass": float(info.get("mass", 1.0)), "max_velocity": float(info.get("max_velocity", 50.0)), "layer": int(info.get("layer", 0)), "mask": int(info.get("mask", 0xFFFF))})
                out = PhysicsScene._soft_separation_corrections(items, step_dt)
                for k, vv in out.items():
                    vels[k] = (float(vv[0]), float(vv[1]), float(vv[2]))
            except Exception:
                pass
        return vels
