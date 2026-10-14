# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
from core.foundation.logger import Logger


def create_soft_body_in_solver(solver, *, vertices, indices, scale_xyz, pos_xyz, euler_rad_xyz, params, entity_id=""):
    try:
        sx, sy, sz = float(scale_xyz[0]), float(scale_xyz[1]), float(scale_xyz[2])
        lv = (np.asarray(vertices).reshape(-1, 3).astype(np.float64)
              * np.array([sx, sy, sz], dtype=np.float64)).astype(np.float32)
        if not np.all(np.isfinite(lv)):
            return None, 0, None, None
        p = params or {}
        bend = p.get("bend_mode", "distance")
        bend = bend.value if hasattr(bend, "value") else str(bend)
        pin = p.get("pin_mode", "none")
        pin = pin.value if hasattr(pin, "value") else str(pin)
        sid = solver.create_soft_body(
            entity_id=entity_id,
            vertices=lv,
            indices=np.asarray(indices).reshape(-1),
            position=(float(pos_xyz[0]), float(pos_xyz[1]), float(pos_xyz[2])),
            rotation=(float(euler_rad_xyz[0]), float(euler_rad_xyz[1]), float(euler_rad_xyz[2])),
            mass=p.get("mass", 1.0),
            compliance=p.get("compliance", 0.001),
            bend_mode=bend,
            pressure=p.get("pressure", 0.0),
            damping=p.get("damping", 0.1),
            iterations=p.get("iterations", 10),
            gravity_factor=p.get("gravity_factor", 1.0),
            friction=p.get("friction", 0.6),
            restitution=p.get("restitution", 0.0),
            vertex_radius=p.get("vertex_radius", 0.05),
            max_velocity=p.get("max_velocity", 500.0),
            max_vertices=p.get("max_vertices", 0),
            pin_mode=pin,
            pin_fraction=p.get("pin_fraction", 0.1),
            double_sided=p.get("double_sided", True),
            update_com=p.get("update_com", True),
            collision_layer=p.get("layer", 0),
            collision_mask=p.get("mask", 0xFFFF),
        )
    except Exception as e:
        Logger.warning(f"[SoftBody] '{entity_id}' creation exception: {e}")
        return None, 0, None, None
    if sid is None or sid >= 0:
        Logger.warning(f"[SoftBody] '{entity_id}' solver returned invalid id: {sid}")
        return None, 0, None, None
    try:
        n = solver.get_soft_body_count(sid)
    except Exception:
        n = 0
    if not n or n <= 0:
        Logger.warning(f"[SoftBody] '{entity_id}' solver returned 0 vertices, removing")
        try:
            solver.remove_soft_body(sid)
        except Exception:
            pass
        return None, 0, None, None
    try:
        geom = solver.get_soft_body_geometry(sid)
    except Exception:
        geom = None
    sverts, sfaces = None, None
    if geom is not None:
        try:
            sverts, sfaces = geom
        except Exception:
            sverts, sfaces = None, None
    return sid, int(n), sverts, sfaces


class EventsMixin:
    def _separate_soft_bodies(self, dt: float):
        try:
            items = list(self._entity_to_soft.items())
        except Exception:
            return
        if len(items) < 2:
            return
        infos = []
        for entity_id, sid in items:
            try:
                entity = self._get_entity(entity_id)
            except Exception:
                continue
            if entity is None:
                continue
            try:
                active = bool(entity._active)
            except Exception:
                active = True
            if not active:
                continue
            try:
                soft = self._soft_component(entity)
            except Exception:
                continue
            if soft is None:
                continue
            try:
                sample = self._solver.get_soft_body_sample(sid)
            except Exception:
                continue
            if not sample:
                continue
            try:
                lay = int(getattr(soft, "layer", 0))
                msk = int(getattr(soft, "mask", 0xFFFF)) & 0xFFFFFFFF
            except Exception:
                lay = 0
                msk = 0xFFFF
            try:
                maxv = float(getattr(soft, "max_velocity", 50.0))
            except Exception:
                maxv = 50.0
            infos.append({
                "key": entity_id,
                "center": sample.get("center", (0.0, 0.0, 0.0)),
                "aabb_min": sample.get("aabb_min", (0.0, 0.0, 0.0)),
                "aabb_max": sample.get("aabb_max", (0.0, 0.0, 0.0)),
                "velocity": sample.get("velocity", (0.0, 0.0, 0.0)),
                "pinned": bool(sample.get("pinned", False)),
                "mass": sample.get("mass", 1.0),
                "max_velocity": maxv,
                "layer": lay,
                "mask": msk,
            })
        try:
            out = EventsMixin._soft_separation_corrections(infos, dt)
        except Exception:
            return
        for key, vel in out.items():
            try:
                sid = self._entity_to_soft.get(key)
                if sid is None:
                    continue
                self._solver.set_soft_body_velocity(sid, vel)
            except Exception:
                pass

    @staticmethod
    def _soft_separation_corrections(items, dt: float):
        out = {}
        try:
            step_dt = max(float(dt), 1e-6)
        except Exception:
            step_dt = 1.0 / 60.0
        try:
            n = len(items)
        except Exception:
            return out
        if n < 2:
            return out
        vel = {}
        for it in items:
            try:
                v = it.get("velocity", (0.0, 0.0, 0.0))
                vel[it["key"]] = [float(v[0]), float(v[1]), float(v[2])]
            except Exception:
                continue
        changed = set()
        for i in range(n):
            for j in range(i + 1, n):
                try:
                    a = items[i]
                    b = items[j]
                    ka = a["key"]
                    kb = b["key"]
                    if ka not in vel or kb not in vel:
                        continue
                    cat_a = (1 << (int(a.get("layer", 0)) & 31)) & 0xFFFFFFFF
                    cat_b = (1 << (int(b.get("layer", 0)) & 31)) & 0xFFFFFFFF
                    if (int(a.get("mask", 0xFFFF)) & cat_b) == 0 or (int(b.get("mask", 0xFFFF)) & cat_a) == 0:
                        continue
                    if bool(a.get("pinned", False)) and bool(b.get("pinned", False)):
                        continue
                    amn = a["aabb_min"]
                    amx = a["aabb_max"]
                    bmn = b["aabb_min"]
                    bmx = b["aabb_max"]
                    ox = min(float(amx[0]), float(bmx[0])) - max(float(amn[0]), float(bmn[0]))
                    oy = min(float(amx[1]), float(bmx[1])) - max(float(amn[1]), float(bmn[1]))
                    oz = min(float(amx[2]), float(bmx[2])) - max(float(amn[2]), float(bmn[2]))
                except Exception:
                    continue
                if not (ox == ox and oy == oy and oz == oz):
                    continue
                if ox <= 0.0 or oy <= 0.0 or oz <= 0.0:
                    continue
                try:
                    ca = a["center"]
                    cb = b["center"]
                    if ox <= oy and ox <= oz:
                        nx, ny, nz = (1.0, 0.0, 0.0) if float(cb[0]) >= float(ca[0]) else (-1.0, 0.0, 0.0)
                        overlap = ox
                    elif oy <= oz:
                        nx, ny, nz = (0.0, 1.0, 0.0) if float(cb[1]) >= float(ca[1]) else (0.0, -1.0, 0.0)
                        overlap = oy
                    else:
                        nx, ny, nz = (0.0, 0.0, 1.0) if float(cb[2]) >= float(ca[2]) else (0.0, 0.0, -1.0)
                        overlap = oz
                    va = vel[ka]
                    vb = vel[kb]
                    rvx = float(vb[0]) - float(va[0])
                    rvy = float(vb[1]) - float(va[1])
                    rvz = float(vb[2]) - float(va[2])
                    vn = rvx * nx + rvy * ny + rvz * nz
                    bias = overlap / step_dt * 0.15
                    if vn >= bias:
                        continue
                    corr = bias - vn
                    try:
                        ma = max(float(a.get("mass", 1.0)), 1e-6)
                        mb = max(float(b.get("mass", 1.0)), 1e-6)
                    except Exception:
                        ma, mb = 1.0, 1.0
                    ima = 0.0 if bool(a.get("pinned", False)) else 1.0 / ma
                    imb = 0.0 if bool(b.get("pinned", False)) else 1.0 / mb
                    denom = ima + imb
                    if denom <= 0.0:
                        continue
                    wa = ima / denom
                    wb = imb / denom
                    try:
                        maxv = max(float(a.get("max_velocity", 50.0)), 1.0)
                        corr = min(corr, maxv)
                    except Exception:
                        pass
                    va[0] -= nx * corr * wa
                    va[1] -= ny * corr * wa
                    va[2] -= nz * corr * wa
                    vb[0] += nx * corr * wb
                    vb[1] += ny * corr * wb
                    vb[2] += nz * corr * wb
                    changed.add(ka)
                    changed.add(kb)
                except Exception:
                    continue
        for k in changed:
            try:
                v = vel.get(k)
                if v is None:
                    continue
                out[k] = (float(v[0]), float(v[1]), float(v[2]))
            except Exception:
                pass
        return out

    def _has_collision_listeners(self) -> bool:
        if not self._scene:
            return False
        sig = self._listener_signature()
        if sig != self._collision_listener_sig:
            self._collision_listener_sig = sig
            self._collision_scripts_checked = False
            self._has_collision_scripts = False
        if self._collision_scripts_checked:
            return self._has_collision_scripts
        self._collision_scripts_checked = True
        for entity in self._scene.get_all_entities():
            for comp in entity._components.values():
                if type(comp).__name__ == "ScriptComponent":
                    inst = comp._py_instance if hasattr(comp, "_py_instance") else None
                    if inst is None:
                        continue
                    if (hasattr(inst, "on_collision_enter") or
                        hasattr(inst, "on_collision_stay") or
                        hasattr(inst, "on_collision_exit")):
                        self._has_collision_scripts = True
                        return True
                elif hasattr(comp, "on_collision_enter"):
                    self._has_collision_scripts = True
                    return True
        return False

    def _listener_signature(self) -> tuple:
        entities = self._scene._entities
        count = 0
        for ent in entities.values():
            count += len(ent._components)
        return (len(entities), count)

    def _process_collision_events(self):
        from core.components import ScriptComponent
        if not self._has_collision_listeners():
            self._prev_frame_contacts.clear()
            return
        raw = self._solver.get_collision_events()
        current: set[frozenset[int]] = set()
        forces: dict[frozenset[int], float] = {}
        for ev in raw:
            ba, bb = ev["body_a"], ev["body_b"]
            if ba < 0 or bb < 0:
                continue
            pair = frozenset([ba, bb])
            current.add(pair)
            force = float(ev.get("force", 0.0) or 0.0)
            forces[pair] = max(forces.get(pair, 0.0), force)
        entered = current - self._prev_frame_contacts
        exited = self._prev_frame_contacts - current
        stayed = current & self._prev_frame_contacts

        def _dispatch(pairs, callback_name):
            for pair in pairs:
                bodies = list(pair)
                e0 = self._body_to_entity.get(bodies[0], "")
                e1 = self._body_to_entity.get(bodies[1], "")
                if not e0 or not e1:
                    continue
                force = forces.get(pair, 0.0)
                for sc in self._get_entity(e0).get_components(ScriptComponent):
                    inst = sc._py_instance
                    if inst and hasattr(inst, callback_name):
                        try:
                            if getattr(sc, "_py_collision_arity", {}).get(callback_name, 1) >= 2:
                                getattr(inst, callback_name)(e1, force)
                            else:
                                getattr(inst, callback_name)(e1)
                        except Exception as ex:
                            Logger.error(f"Script {callback_name} error: {ex}")
                for sc in self._get_entity(e1).get_components(ScriptComponent):
                    inst = sc._py_instance
                    if inst and hasattr(inst, callback_name):
                        try:
                            if getattr(sc, "_py_collision_arity", {}).get(callback_name, 1) >= 2:
                                getattr(inst, callback_name)(e0, force)
                            else:
                                getattr(inst, callback_name)(e0)
                        except Exception as ex:
                            Logger.error(f"Script {callback_name} error: {ex}")

        def _dispatch_components(pairs, callback_name):
            for pair in pairs:
                bodies = list(pair)
                e0 = self._body_to_entity.get(bodies[0], "")
                e1 = self._body_to_entity.get(bodies[1], "")
                if not e0 or not e1:
                    continue
                force = forces.get(pair, 0.0)
                self._invoke_component_collision(self._get_entity(e0), e1, callback_name, force)
                self._invoke_component_collision(self._get_entity(e1), e0, callback_name, force)
        _dispatch(entered, "on_collision_enter")
        _dispatch(exited, "on_collision_exit")
        _dispatch(stayed, "on_collision_stay")
        _dispatch_components(entered, "on_collision_enter")
        _dispatch_components(exited, "on_collision_exit")
        _dispatch_components(stayed, "on_collision_stay")
        self._prev_frame_contacts = current

    def _invoke_component_collision(self, entity, other_eid: str, callback_name: str, force: float):
        if not entity:
            return
        from core.components import ScriptComponent
        for comp in entity.get_all_components():
            if isinstance(comp, ScriptComponent):
                continue
            if hasattr(comp, callback_name):
                try:
                    getattr(comp, callback_name)(other_eid, force)
                except Exception as ex:
                    Logger.error(f"Component {callback_name} error: {ex}")

    def get_collision_events(self) -> list[dict]:
        return self._solver.get_collision_events()
