# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
from typing import Optional
from core.ecs import GizmoPrimitive
from core.maths.math3d import Mat4
from core.config.config import get_global_config


try:
    from core._skinning import compute_skinning_buffer_cy
    _HAS_SKINNING_CY = True
except ImportError:
    _HAS_SKINNING_CY = False


try:
    from core._skinning import soa_skin_compose as _soa_skin_cy
    _HAS_SOA_CY = True
except ImportError:
    _HAS_SOA_CY = False


class _ArmatureSkin:
    def _bone_world_positions(self) -> list:
        n = len(self.bone_names)
        scene = self._entity._scene if self._entity else None
        positions = []
        for i in range(n):
            ent = None
            if scene is not None and i < len(self.bone_entity_ids) and self.bone_entity_ids[i]:
                ent = scene.get_entity(self.bone_entity_ids[i])
            if ent is not None and ent.transform is not None:
                wm = ent.transform.world_matrix._d
                positions.append((float(wm[3, 0]), float(wm[3, 1]), float(wm[3, 2])))
            else:
                positions.append(None)
        return positions

    def _append_joint_cross(self, s_list, e_list, c_list, p, size, color):
        x, y, z = p
        s_list.append([x - size, y, z]); e_list.append([x + size, y, z])
        s_list.append([x, y - size, z]); e_list.append([x, y + size, z])
        s_list.append([x, y, z - size]); e_list.append([x, y, z + size])
        for _ in range(3):
            c_list.append(color)

    def gizmo(self):
        if not get_global_config().get("gizmo.show_armature_bones", True):
            return []
        from core.engine.eng import Engine
        engine = Engine.instance()
        if engine:
            vp = getattr(engine, 'viewport', None)
            if vp is not None:
                selected = getattr(vp, '_selected_entities', None)
                if selected is not None:
                    selected_ids = {e.id for e in selected}
                    armature_id = self._entity.id if self._entity else None
                    bone_ids = set(self.bone_entity_ids)
                    if armature_id is not None and armature_id not in selected_ids and not bone_ids.intersection(selected_ids):
                        return []
                else:
                    return []
        n = len(self.bone_names)
        if n == 0:
            return []
        positions = self._bone_world_positions()
        parents = self.bone_parents
        bone_color = self._gizmo_bone_color
        root_color = self._gizmo_root_color
        s_list, e_list, c_list = [], [], []
        for i in range(n):
            p = positions[i]
            if p is None:
                continue
            pi = parents[i] if i < len(parents) else -1
            if pi >= 0 and pi < n and positions[pi] is not None:
                pp = positions[pi]
                s_list.append([pp[0], pp[1], pp[2]])
                e_list.append([p[0], p[1], p[2]])
                c_list.append(bone_color)
                self._append_joint_cross(s_list, e_list, c_list, p, 0.03, bone_color)
            else:
                self._append_joint_cross(s_list, e_list, c_list, p, 0.06, root_color)
        if not s_list:
            return []
        starts = np.array(s_list, dtype=np.float32)
        ends = np.array(e_list, dtype=np.float32)
        colors = np.array(c_list, dtype=np.float32)
        return [GizmoPrimitive(starts, ends, colors)]

    def bone_world_matrices(self, scene, renderer_world: Mat4) -> list[np.ndarray]:
        n = len(self.bone_offset_matrices)
        out: list[np.ndarray] = []
        inv = renderer_world.inverted()
        for i in range(n):
            ent = None
            if i < len(self.bone_entity_ids) and self.bone_entity_ids[i]:
                ent = scene.get_entity(self.bone_entity_ids[i])
            if ent is not None and ent.transform is not None:
                rel = (ent.transform.world_matrix * inv)._d
            else:
                rel = np.eye(4, dtype=np.float32)
            off = self.bone_offset_matrices[i]
            out.append((off @ rel).astype(np.float32))
        return out

    def _soa_bone_offsets(self) -> Optional[np.ndarray]:
        cur = self._bone_offsets_f64
        if cur is not None and len(cur) == len(self.bone_offset_matrices):
            return cur
        try:
            stacked = np.stack([np.asarray(m, dtype=np.float64).reshape(4, 4) for m in self.bone_offset_matrices])
        except Exception:
            return None
        self._bone_offsets_f64 = stacked
        return stacked

    def _soa_bone_slots(self, scene) -> Optional[np.ndarray]:
        try:
            ids = tuple(self.bone_entity_ids)
        except Exception:
            return None
        if not ids or scene is None:
            return None
        try:
            epoch = scene._soa_epoch
            cap = scene._soa_cap
        except Exception:
            return None
        cached = self._bone_slots
        if (cached is not None and self._bone_slots_scene is scene
                and self._bone_slots_epoch == epoch
                and self._bone_slots_ids == ids and len(cached) == len(ids)):
            return cached
        slots = np.empty(len(ids), dtype=np.intp)
        for i, bid in enumerate(ids):
            slot = -1
            if bid:
                try:
                    ent = scene.get_entity(bid)
                except Exception:
                    ent = None
                if ent is not None:
                    try:
                        tr = ent.transform
                    except Exception:
                        tr = None
                    if tr is not None and not getattr(tr, "_dirty", False):
                        try:
                            s = tr._soa
                        except Exception:
                            s = -1
                        if s is not None and 0 <= s < cap:
                            slot = int(s)
                        else:
                            return None
                    else:
                        return None
            slots[i] = slot
        if bool((slots < 0).any()):
            return None
        self._bone_slots = slots
        self._bone_slots_epoch = epoch
        self._bone_slots_scene = scene
        self._bone_slots_ids = ids
        return slots

    def _soa_scratch_for(self, n: int) -> Optional[tuple]:
        cur = self._soa_scratch
        if cur is not None and cur[0].shape[0] == n:
            return cur
        try:
            w16 = np.empty((n, 16), dtype=np.float64)
            rel = np.empty((n, 4, 4), dtype=np.float64)
            skin = np.empty((n, 4, 4), dtype=np.float64)
            flat = np.empty((n, 16), dtype=np.float32)
        except Exception:
            return None
        bufs = (w16, rel, skin, flat)
        self._soa_scratch = bufs
        return bufs

    def _soa_skinning(self, scene, renderer_world: Mat4) -> Optional[tuple[np.ndarray, int]]:
        slots = self._soa_bone_slots(scene)
        if slots is None:
            return None
        try:
            world = scene._soa_world
            cap = scene._soa_cap
        except Exception:
            return None
        if int(slots.max()) >= cap:
            return None
        off = self._soa_bone_offsets()
        if off is None or len(off) != len(slots):
            return None
        bufs = self._soa_scratch_for(len(slots))
        if bufs is None:
            return None
        try:
            w16, rel, skin, flat = bufs
            inv_d = np.ascontiguousarray(renderer_world.inverted()._d, dtype=np.float64)
            if _HAS_SOA_CY:
                try:
                    if (world.dtype == np.float64 and world.flags.c_contiguous
                            and world.ndim == 3 and world.shape[1] == 4 and world.shape[2] == 4
                            and off.dtype == np.float64 and off.flags.c_contiguous
                            and inv_d.shape == (4, 4)):
                        _soa_skin_cy(world, slots, off, inv_d, rel, flat)
                        return flat, int(len(slots))
                except Exception:
                    pass
            np.take(world.reshape(-1, 16), slots, axis=0, out=w16)
            np.matmul(w16.reshape(-1, 4, 4), inv_d, out=rel)
            np.matmul(off, rel, out=skin)
            flat[:] = skin.reshape(-1, 16)
            return flat, int(len(slots))
        except Exception:
            return None

    def compute_skinning_buffer(self, scene, renderer_world: Mat4) -> tuple[np.ndarray, int]:
        n = len(self.bone_offset_matrices)
        if n == 0:
            return np.empty((0, 16), dtype=np.float32), 0
        try:
            soa = self._soa_skinning(scene, renderer_world)
        except Exception:
            soa = None
        if soa is not None:
            return soa
        if _HAS_SKINNING_CY:
            flat, n_bones, new_inv_cache, new_inv_key = compute_skinning_buffer_cy(
                self.bone_offset_matrices, self.bone_entity_ids,
                scene, renderer_world, self._inv_cache, self._inv_cache_key)
            self._inv_cache = new_inv_cache
            self._inv_cache_key = new_inv_key
            return flat, n_bones
        if self._skin_flat is None or self._skin_flat_size < n:
            self._skin_flat = np.zeros((n, 16), dtype=np.float32)
            self._skin_flat_size = n
            self._skin_mat = np.empty((4, 4), dtype=np.float32)
        flat = self._skin_flat
        inv_d = renderer_world.inverted()._d
        skin_mat = self._skin_mat
        bone_offsets = self.bone_offset_matrices
        bone_ids = self.bone_entity_ids
        for i in range(n):
            ent = None
            if scene is not None and i < len(bone_ids) and bone_ids[i]:
                ent = scene.get_entity(bone_ids[i])
            if ent is not None and ent.transform is not None:
                rel = ent.transform.world_matrix._d @ inv_d
                np.matmul(bone_offsets[i], rel, out=skin_mat)
                flat[i] = skin_mat.ravel()
            else:
                flat[i] = 0.0
                flat[i, 0] = 1.0
                flat[i, 5] = 1.0
                flat[i, 10] = 1.0
                flat[i, 15] = 1.0
        return flat, n
