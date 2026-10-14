# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
from typing import Optional
from core.components.rendering.deform.blendshapes import BlendShapes
class EvictMixin:
    def _refresh_soft_snapshot_meshes(self, scene=None, snap=None) -> None:
        try:
            if scene is not None:
                try:
                    if not scene._component_indices.get("SoftBody"):
                        return
                except Exception:
                    pass
            if snap is None:
                snap = self._snap_cache
            if snap is None:
                return
            renderable = getattr(snap, "renderable", None)
            if not renderable:
                return
            from core.components.physics.soft_body import SoftBody
            for entry in renderable:
                try:
                    ent = entry[0]
                    if ent is None:
                        continue
                    try:
                        soft = ent.get_component(SoftBody)
                    except Exception:
                        soft = None
                    if soft is None or not getattr(soft, "enabled", True):
                        continue
                    ov = getattr(soft, "_render_mesh", None)
                    if ov is None:
                        continue
                    try:
                        needs = bool(getattr(soft, "_soft_needs_rebuild", False))
                    except Exception:
                        needs = False
                    if needs:
                        try:
                            src = getattr(ov, "_soft_src", None)
                        except Exception:
                            src = None
                        if src is not None:
                            try:
                                rebuilt = self._soft_override_mesh(ent, src)
                            except Exception:
                                rebuilt = None
                            if rebuilt is not None:
                                ov = rebuilt
                    if entry[2] is not ov:
                        entry[2] = ov
                    self._soft_upload_if_dirty(ov)
                except Exception:
                    continue
        except Exception:
            pass
    def _release_morph_cache(self, ent_id=None):
        try:
            if ent_id is None:
                for clone in self._morph_cache.values():
                    try:
                        clone.release()
                    except Exception:
                        pass
                self._morph_cache.clear()
                self._morph_sig.clear()
                return
            clone = self._morph_cache.pop(ent_id, None)
            self._morph_sig.pop(ent_id, None)
            if clone is not None:
                try:
                    clone.release()
                except Exception:
                    pass
        except Exception:
            pass
    def _morphed_mesh(self, ent, mesh):
        try:
            bs = ent.get_component(BlendShapes)
        except Exception:
            return mesh
        if bs is None or not getattr(bs, "enabled", True):
            return mesh
        if mesh is None or not getattr(mesh, "has_blendshapes", False):
            return mesh
        try:
            if len(getattr(bs, "shapes", [])) != int(getattr(mesh, "blendshape_count", 0)):
                bs.sync_with_mesh(mesh)
            else:
                want = list(getattr(mesh, "blendshape_names", []) or [])
                got = [str(s.get("name", "")) for s in bs.shapes]
                if want != got:
                    bs.sync_with_mesh(mesh)
        except Exception:
            pass
        try:
            w = bs.weights_vector(mesh)
        except Exception:
            return mesh
        if not any(v != 0.0 for v in w):
            self._release_morph_cache(getattr(ent, "id", None))
            return mesh
        try:
            sig = (id(mesh), int(getattr(mesh, "_gpu_version", 0)), tuple(float(v) for v in w))
        except Exception:
            return mesh
        eid = getattr(ent, "id", None)
        if eid is not None:
            if self._morph_sig.get(eid) == sig:
                cached = self._morph_cache.get(eid)
                if cached is not None:
                    return cached
        try:
            clone = mesh.make_morphed_clone(w, self._ctx, self._default_prog, self._outline_prog)
        except Exception:
            return mesh
        if eid is not None:
            old = self._morph_cache.get(eid)
            if old is not None and old is not clone:
                try:
                    old.release()
                except Exception:
                    pass
            self._morph_cache[eid] = clone
            self._morph_sig[eid] = sig
        return clone
    def _soft_override_mesh(self, ent, mesh):
        from core.components.physics.soft_body import SoftBody
        soft = ent.get_component(SoftBody)
        if soft is None or not getattr(soft, "enabled", True):
            return None
        try:
            n_full = int(len(mesh.vertices) // 3)
        except Exception:
            return None
        if n_full <= 0:
            return None
        sv = getattr(soft, "_soft_verts", None)
        try:
            sim_rest = np.ascontiguousarray(sv, dtype=np.float32).reshape(-1, 3) if sv is not None else None
        except Exception:
            sim_rest = None
        use_skin = sim_rest is not None and len(sim_rest) >= 3
        tr = ent.transform
        try:
            sc = tr.local_scale if tr is not None else None
            sxs, sys, szs = (float(sc.x), float(sc.y), float(sc.z)) if sc is not None else (1.0, 1.0, 1.0)
        except Exception:
            sxs, sys, szs = 1.0, 1.0, 1.0
        if use_skin and (abs(sxs) < 1e-6 or abs(sys) < 1e-6 or abs(szs) < 1e-6):
            use_skin = False
        if not use_skin and sim_rest is not None and len(sim_rest) >= 3:
            try:
                soft._soft_use_skin = False
            except Exception:
                pass
            n_c = int(len(sim_rest))
            ov = getattr(soft, "_render_mesh", None)
            if ov is None or getattr(ov, "_soft_src", None) is not mesh or getattr(ov, "_soft_n", -1) != n_c:
                try:
                    from core.foundation.logger import Logger
                    Logger.info(f"[SoftBody] override['{getattr(ent,'name',ent)}'] building ov n={n_c} (prev={getattr(ov,'_soft_n','-')})")
                except Exception:
                    pass
                from core.renderer.meshd import MeshData
                if ov is None:
                    ov = MeshData()
                try:
                    ov.vertices = np.ascontiguousarray(sim_rest, dtype=np.float32).copy().reshape(-1)
                    ov.normals = np.zeros_like(ov.vertices)
                    ov.uvs = np.zeros((n_c * 2,), dtype=np.float32)
                    ov.sub_mesh_ranges = []
                    ov.sub_mesh_names = []
                    sf = getattr(soft, "_soft_faces", None)
                    if sf is not None and len(sf) >= 3:
                        ov.indices = np.ascontiguousarray(sf, dtype=np.uint32).copy()
                    else:
                        ov.indices = np.ascontiguousarray(mesh.indices, dtype=np.uint32).copy()
                    try:
                        flat = np.asarray(ov.indices).reshape(-1)
                        ov._soft_faces = flat.astype(np.int64) if flat.size % 3 == 0 else None
                    except Exception:
                        ov._soft_faces = None
                    ov.compute_aabb()
                    ov.build_gl(self._ctx, self._default_prog)
                    if self._outline_prog:
                        try:
                            ov.build_outline_vao(self._ctx, self._outline_prog)
                        except Exception:
                            pass
                except Exception:
                    return None
                ov._soft_src = mesh
                ov._soft_n = n_c
                ov._soft_ctx = self._ctx
                ov._soft_prog = self._default_prog
                ov._soft_dirty = False
                try:
                    ov._soft_version = int(getattr(ov, "_soft_version", 0) or 0) + 1
                except Exception:
                    pass
                try:
                    soft._soft_needs_rebuild = False
                except Exception:
                    pass
                soft._render_mesh = ov
            else:
                self._soft_upload_if_dirty(ov)
            return ov
        skin_ok = False
        if use_skin:
            try:
                e_idx = getattr(soft, "_soft_skin_idx", None)
                e_w = getattr(soft, "_soft_skin_w", None)
                e_nsim = int(getattr(soft, "_soft_skin_nsim", -1))
                e_nfull = int(getattr(soft, "_soft_skin_nfull", -1))
                e_sc = tuple(getattr(soft, "_soft_skin_scale", ()))
                skin_ok = (
                    e_idx is not None and e_w is not None
                    and getattr(e_idx, "shape", (0, 0)) == (n_full, 4)
                    and getattr(e_w, "shape", (0, 0)) == (n_full, 4)
                    and e_nsim == len(sim_rest) and e_nfull == n_full
                    and getattr(soft, "_soft_skin_mesh", None) is mesh
                    and len(e_sc) == 3
                    and abs(e_sc[0] - sxs) < 1e-9 and abs(e_sc[1] - sys) < 1e-9 and abs(e_sc[2] - szs) < 1e-9
                )
            except Exception:
                skin_ok = False
        ov = getattr(soft, "_render_mesh", None)
        try:
            need_rebuild = bool(getattr(soft, "_soft_needs_rebuild", False))
        except Exception:
            need_rebuild = False
        if ov is None or getattr(ov, "_soft_src", None) is not mesh or getattr(ov, "_soft_n", -1) != n_full or need_rebuild or (use_skin and not skin_ok):
            try:
                from core.foundation.logger import Logger
                Logger.info(f"[SoftBody] override['{getattr(ent,'name',ent)}'] building ov n={n_full} (prev={getattr(ov,'_soft_n','-')})")
            except Exception:
                pass
            from core.renderer.meshd import MeshData
            if ov is None:
                ov = MeshData()
            try:
                rrest = np.ascontiguousarray(mesh.vertices, dtype=np.float32).reshape(-1, 3)
                if use_skin and not skin_ok:
                    try:
                        s0 = sim_rest / np.array([sxs, sys, szs], dtype=np.float32)
                        s0 = np.ascontiguousarray(s0, dtype=np.float32)
                        e_idx, e_w = self._soft_build_skin(rrest, s0, 4)
                        soft._soft_skin_idx = e_idx
                        soft._soft_skin_w = e_w
                        soft._soft_skin_nsim = int(len(sim_rest))
                        soft._soft_skin_nfull = int(n_full)
                        soft._soft_skin_scale = (sxs, sys, szs)
                        soft._soft_skin_mesh = mesh
                        soft._soft_use_skin = True
                        skin_ok = True
                    except Exception:
                        skin_ok = False
                        try:
                            soft._soft_use_skin = False
                        except Exception:
                            pass
                if use_skin and skin_ok:
                    try:
                        latest = np.ascontiguousarray(getattr(soft, "_soft_latest_local", None), dtype=np.float32).reshape(-1, 3)
                    except Exception:
                        latest = None
                    try:
                        src = latest if latest is not None and len(latest) == len(sim_rest) else sim_rest / np.array([sxs, sys, szs], dtype=np.float32)
                    except Exception:
                        src = sim_rest
                    ov.vertices = np.ascontiguousarray(self._soft_apply_skin(src, soft._soft_skin_idx, soft._soft_skin_w).reshape(-1))
                    ov.normals = np.zeros_like(ov.vertices)
                else:
                    ov.vertices = np.ascontiguousarray(mesh.vertices, dtype=np.float32).copy()
                    if getattr(mesh, "normals", None) is not None and len(mesh.normals) == len(mesh.vertices):
                        ov.normals = np.ascontiguousarray(mesh.normals, dtype=np.float32).copy()
                    else:
                        ov.normals = np.zeros_like(ov.vertices)
                if getattr(mesh, "uvs", None) is not None and len(mesh.uvs) > 0:
                    try:
                        ov.uvs = np.ascontiguousarray(mesh.uvs, dtype=np.float32).copy()
                    except Exception:
                        ov.uvs = np.zeros((n_full * 2,), dtype=np.float32)
                else:
                    ov.uvs = np.zeros((n_full * 2,), dtype=np.float32)
                ov.indices = np.ascontiguousarray(mesh.indices, dtype=np.uint32).copy()
                ov.sub_mesh_ranges = list(getattr(mesh, "sub_mesh_ranges", []))
                ov.sub_mesh_names = list(getattr(mesh, "sub_mesh_names", []))
                try:
                    flat = np.asarray(ov.indices).reshape(-1)
                    ov._soft_faces = flat.astype(np.int64) if flat.size % 3 == 0 else None
                except Exception:
                    ov._soft_faces = None
                ov.compute_aabb()
                ov.build_gl(self._ctx, self._default_prog)
                if self._outline_prog:
                    try:
                        ov.build_outline_vao(self._ctx, self._outline_prog)
                    except Exception:
                        pass
            except Exception:
                return None
            ov._soft_src = mesh
            ov._soft_n = n_full
            ov._soft_ctx = self._ctx
            ov._soft_prog = self._default_prog
            ov._soft_dirty = False
            try:
                ov._soft_version = int(getattr(ov, "_soft_version", 0) or 0) + 1
            except Exception:
                pass
            try:
                soft._soft_needs_rebuild = False
            except Exception:
                pass
            soft._render_mesh = ov
        else:
            self._soft_upload_if_dirty(ov)
        return ov
    def _soft_build_skin(self, render_rest, sim_rest, k):
        import numpy as np
        R = np.ascontiguousarray(render_rest, dtype=np.float32)
        S = np.ascontiguousarray(sim_rest, dtype=np.float32)
        n_full = int(len(R))
        n_sim = int(len(S))
        kk = max(1, min(int(k), n_sim))
        idx = np.empty((n_full, kk), dtype=np.int32)
        w = np.empty((n_full, kk), dtype=np.float32)
        s2 = np.ascontiguousarray((S * S).sum(axis=1, dtype=np.float32).reshape(1, -1))
        try:
            step = max(512, min(4096, (64 * 1024 * 1024) // max(1, n_sim * 4)))
        except Exception:
            step = 1024
        for a in range(0, n_full, step):
            b = min(n_full, a + step)
            Rs = np.ascontiguousarray(R[a:b])
            r2 = np.ascontiguousarray((Rs * Rs).sum(axis=1, dtype=np.float32).reshape(-1, 1))
            d2 = r2 + s2 - 2.0 * (Rs @ S.T)
            np.maximum(d2, 0.0, out=d2)
            part = np.argpartition(d2, kth=kk - 1, axis=1)[:, :kk]
            rows = np.arange(b - a)[:, None]
            dk = d2[rows, part]
            order = np.argsort(dk, axis=1, kind="stable")
            sel = part[rows, order]
            ds = dk[rows, order].astype(np.float64)
            inv = 1.0 / (ds + 1e-8)
            inv /= inv.sum(axis=1, keepdims=True)
            idx[a:b] = sel.astype(np.int32)
            w[a:b] = inv.astype(np.float32)
        return idx, w
    def _soft_apply_skin(self, sim_pos, idx, w):
        import numpy as np
        L = np.ascontiguousarray(sim_pos, dtype=np.float32)
        ii = np.asarray(idx, dtype=np.int64)
        ww = np.ascontiguousarray(w, dtype=np.float32)
        out = np.zeros((len(ii), 3), dtype=np.float32)
        for c in range(ii.shape[1]):
            out += ww[:, c:c + 1] * L[ii[:, c]]
        return out
