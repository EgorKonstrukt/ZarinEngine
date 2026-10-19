# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
from core.renderer.origin import shift_vp_bytes
from .bind import prepare_shadow_flat, cull_flat, cull_flat_min, cull_flat_range_min, cull_flat_multi, collect_row_tr_ids, match_flushed_rows
class FlatMixin:
    def _ensure_model_pack_buf(self, needed_count: int):
        if self._model_pack_buf is not None and self._model_pack_buf_cap >= needed_count * 16:
            return
        cap = max(64, needed_count) * 16
        self._model_pack_buf = np.empty(cap, dtype=np.float32); self._model_pack_buf_cap = cap
    def _ensure_flat_cap(self, n: int):
        if n <= self._flat_cap:
            return
        cap = max(64, int(n * 1.5) + 8)
        self._flat_centers = np.empty((cap, 3), dtype=np.float64); self._flat_radii = np.empty(cap, dtype=np.float64)
        self._flat_mats = np.empty((cap, 16), dtype=np.float32); self._flat_mats_f64 = np.empty((cap, 4, 4), dtype=np.float64)
        self._flat_mesh_ids = np.empty(cap, dtype=np.uint64); self._flat_out = np.empty(cap, dtype=np.intp)
        self._flat_out_multi = np.zeros((4, cap), dtype=np.intp); self._flat_multi_counts = np.zeros(4, dtype=np.intp)
        self._cull_cen_buf = np.empty((cap, 3), dtype=np.float64); self._flat_row_tids = np.zeros(cap, dtype=np.uint64)
        self._partial_rows = np.empty(cap, dtype=np.intp); self._partial_which = np.empty(cap, dtype=np.intp)
        if self._flat_order is None or len(self._flat_order) < cap:
            self._flat_order = np.empty(cap, dtype=np.intp)
        self._flat_cap = cap
    def _flat_cache_valid(self, scene, renderable_shadow) -> bool:
        try:
            if self._flat_n <= 0:
                return False
            if renderable_shadow is not self._flat_src_list:
                return False
            if self._shadow_groups_cache is None:
                return False
            rv = scene._render_version if scene is not None else None; tv = scene._transform_version if scene is not None else None
            if (id(scene), rv, tv, len(renderable_shadow)) != self._flat_sig:
                return False
            return True
        except Exception:
            return False
    def _prepare_flat(self, renderable_shadow: list) -> int:
        n = len(renderable_shadow)
        if n == 0:
            self._flat_n = 0; self._flat_mesh_map = {}; self._flat_max_radius = 0.0
            return 0
        self._ensure_flat_cap(n)
        if prepare_shadow_flat is not None:
            try:
                prepare_shadow_flat(renderable_shadow, self._mesh_radius_cache, self._flat_centers, self._flat_radii, self._flat_mats, self._flat_mesh_ids); self._finish_flat_maps(renderable_shadow, n)
            except Exception:
                self._prepare_flat_numpy(renderable_shadow, n)
        else:
            self._prepare_flat_numpy(renderable_shadow, n)
        self._flat_n = n
        try:
            _ids = self._flat_mesh_ids
            _fp = (n, int(_ids[0]), int(_ids[n - 1]), int(np.sum(_ids[:n]))) if n > 0 else (0, 0, 0, 0)
            _same = _fp == getattr(self, "_flat_ids_sig", None)
            self._flat_ids_sig = _fp
            self._flat_ids_same = bool(_same)
            self._flat_prepared_list = renderable_shadow
            self._flat_prep_ver += 1
            if _same:
                self._flat_order_n = n
                self._flat_order_ver = self._flat_prep_ver
            else:
                self._refresh_flat_order(n)
        except Exception:
            try:
                self._flat_prep_ver += 1
                self._refresh_flat_order(n)
            except Exception:
                pass
        try:
            self._flat_max_radius = float(np.max(self._flat_radii[:n]))
        except Exception:
            pass
        try:
            tids = self._flat_row_tids
            if tids is None or len(tids) < n:
                tids = np.zeros(max(64, n), dtype=np.uint64); self._flat_row_tids = tids
            if collect_row_tr_ids is not None:
                collect_row_tr_ids(renderable_shadow, tids[:n])
            else:
                for i in range(n):
                    try:
                        tr = renderable_shadow[i][1]
                    except Exception:
                        tr = None
                    tids[i] = id(tr) if tr is not None else 0
        except Exception:
            try:
                self._flat_row_tids = np.zeros(0, dtype=np.uint64)
            except Exception:
                pass
        return n
    def _refresh_flat_order(self, n: int):
        try:
            if self._flat_order is None or len(self._flat_order) < n:
                self._flat_order = np.empty(max(64, n), dtype=np.intp)
            self._flat_order[:n] = np.argsort(self._flat_mesh_ids[:n], kind="stable"); self._flat_order_n = n; self._flat_order_ver = self._flat_prep_ver
        except Exception:
            try:
                self._flat_order_n = 0
            except Exception:
                pass
    def _iter_flat_groups_fast(self, vis: np.ndarray, mats: np.ndarray):
        try:
            n = self._flat_n
        except Exception:
            return
        try:
            total = len(vis)
        except Exception:
            return
        if n <= 0 or total <= 0:
            return
        try:
            if (self._flat_order is None or self._flat_order_n != n or self._flat_order_ver != self._flat_prep_ver or len(self._flat_order) < n):
                self._refresh_flat_order(n)
            order = self._flat_order
            if order is None or len(order) < n:
                return
            mask = np.zeros(n, dtype=np.bool_); mask[vis] = True
            ono = order[:n]; ovis = ono[mask[ono]]
            if len(ovis) == 0:
                return
            om = self._flat_mesh_ids[:n][ovis]; chg = np.nonzero(om[1:] != om[:-1])[0]; chg += 1
            gathered = mats[ovis]; mmap = self._flat_mesh_map; start = 0
            for _e in chg:
                e = int(_e); mesh = mmap.get(int(om[start]))
                if mesh is not None and e > start:
                    yield mesh, ovis[start:e], gathered[start:e]
                start = e
            mesh = mmap.get(int(om[start]))
            if mesh is not None and start < len(ovis):
                yield mesh, ovis[start:], gathered[start:]
        except Exception:
            return
    def _cull_flat_multi_rows(self, vp_list: list, min_list: list = None) -> list:
        try:
            active_count = len(vp_list); n = self._flat_n
        except Exception:
            return []
        if n <= 0 or active_count <= 0:
            return []
        try:
            need_cap = max(n, 64); out = self._flat_out_multi
            if out.shape[0] < active_count or out.shape[1] < need_cap:
                self._flat_out_multi = np.zeros((max(4, active_count), need_cap), dtype=np.intp); out = self._flat_out_multi
            cnt = self._flat_multi_counts
            if len(cnt) < active_count:
                self._flat_multi_counts = np.zeros(max(4, active_count), dtype=np.intp); cnt = self._flat_multi_counts
            buf = self._cull_cen_buf
            if buf is None or buf.shape[0] < need_cap:
                self._cull_cen_buf = np.empty((need_cap, 3), dtype=np.float64); buf = self._cull_cen_buf
        except Exception:
            return []
        try:
            _o = self._shadow_origin
        except Exception:
            _o = None
        cen = self._flat_centers[:n]; rad = self._flat_radii[:n]
        try:
            vps = np.ascontiguousarray(np.asarray(vp_list, dtype=np.float32))
        except Exception:
            return []
        if _o is None:
            cen_c = np.ascontiguousarray(cen, dtype=np.float64); rad_c = np.ascontiguousarray(rad, dtype=np.float64)
        else:
            try:
                ov = np.asarray(_o, dtype=np.float64).reshape(3); np.subtract(cen, ov, out=buf[:n])
                cen_c = np.ascontiguousarray(buf[:n], dtype=np.float64); rad_c = np.ascontiguousarray(rad, dtype=np.float64)
                svps = np.empty((active_count, 4, 4), dtype=np.float32)
                for k in range(active_count):
                    try:
                        svps[k] = np.frombuffer(shift_vp_bytes(vps[k], _o), dtype=np.float32).reshape(4, 4)
                    except Exception:
                        svps[k] = vps[k]
                vps = svps
            except Exception:
                cen_c = np.ascontiguousarray(cen, dtype=np.float64); rad_c = np.ascontiguousarray(rad, dtype=np.float64)
        try:
            mins = np.ascontiguousarray(np.asarray(min_list, dtype=np.float64)) if min_list is not None and len(min_list) == active_count else np.zeros(active_count, dtype=np.float64)
        except Exception:
            mins = np.zeros(active_count, dtype=np.float64)
        if cull_flat_multi is not None:
            try:
                cull_flat_multi(cen_c, rad_c, vps, mins, out[:active_count], cnt[:active_count]); return [int(cnt[k]) for k in range(active_count)]
            except Exception:
                pass
        res = []
        for k in range(active_count):
            try:
                c = self._cull_flat_count(np.ascontiguousarray(vps[k], dtype=np.float32))
            except Exception:
                c = 0
            try:
                np.copyto(out[k, :c], self._flat_out[:c])
            except Exception:
                pass
            res.append(int(c))
        return res
    def _finish_flat_maps(self, renderable_shadow: list, n: int):
        try:
            mesh_map: dict = {}; ids = self._flat_mesh_ids
            for i in range(n):
                mid = int(ids[i])
                if mid not in mesh_map:
                    try:
                        mesh_map[mid] = renderable_shadow[i][0]
                    except Exception:
                        pass
            self._flat_mesh_map = mesh_map
        except Exception:
            mesh_map = {}
            self._flat_mesh_map = mesh_map
    def _prepare_flat_numpy(self, renderable_shadow: list, n: int):
        centers = self._flat_centers; radii = self._flat_radii; mats = self._flat_mats
        M = self._flat_mats_f64[:n]; ids = self._flat_mesh_ids; rc = self._mesh_radius_cache
        if n == 0:
            return
        if len(rc) > 4096:
            try:
                rc.clear()
            except Exception:
                pass
        seen: dict = {}; order: list = []; code = np.empty(n, dtype=np.intp); bad_idx = []
        for i in range(n):
            entry = renderable_shadow[i]; mesh = entry[0]; mid = id(mesh); ids[i] = mid
            k = seen.get(mid)
            if k is None:
                k = len(order); seen[mid] = k; order.append(mesh)
            code[i] = k; tr = entry[1]
            if tr is None:
                bad_idx.append(i)
                try:
                    M[i] = 0.0
                except Exception:
                    pass
                continue
            try:
                M[i] = tr._world_matrix._d
            except Exception:
                try:
                    M[i] = tr.world_matrix._d
                except Exception:
                    bad_idx.append(i)
                    try:
                        M[i] = 0.0
                    except Exception:
                        pass
        centers[:n] = M[:, 3, :3]; col = M[:, :3, :]; ms = np.sqrt(np.einsum('nca,nca->na', col, col)).max(axis=1)
        uniq_r = np.empty(len(order), dtype=np.float64); mesh_map: dict = {}
        for k in range(len(order)):
            mesh = order[k]
            try:
                mesh_map[id(mesh)] = mesh
            except Exception:
                pass
            b = rc.get(mesh)
            if b is None:
                try:
                    b = float(mesh.bounding_radius)
                except Exception:
                    b = 1.0
                try:
                    rc[mesh] = b
                except Exception:
                    pass
            uniq_r[k] = b
        radii[:n] = ms * uniq_r[code]; mats[:n] = M.reshape(n, 16)
        if bad_idx:
            try:
                bi = np.asarray(bad_idx, dtype=np.intp)
            except Exception:
                bi = None
            if bi is not None:
                centers[bi, 0] = 1e30; centers[bi, 1] = 1e30; centers[bi, 2] = 1e30; radii[bi] = 0.0; mats[bi, :] = 0.0
        self._flat_mesh_map = mesh_map
    def _try_shadow_partial(self, scene, renderable_shadow):
        try:
            n = len(renderable_shadow)
        except Exception:
            return False
        if n == 0:
            return False
        try:
            if renderable_shadow is not self._flat_index_src or self._flat_index_n != n or self._flat_n != n:
                return False
            if not self._shadow_groups_cache:
                return False
            try:
                row_tids = self._flat_row_tids
                if row_tids is None or len(row_tids) < n:
                    return False
            except Exception:
                return False
            if scene is None or not hasattr(scene, "peek_flushed_transforms"):
                return False
            try:
                flushed = scene.peek_flushed_transforms()
            except Exception:
                return False
            if not flushed:
                return False
            try:
                if bool(getattr(scene, "_flushed_overflow", False)):
                    return False
            except Exception:
                pass
            if len(flushed) * 2 >= n:
                return False
            try:
                nf = len(flushed); fids = np.empty(nf, dtype=np.uint64); dlist = []
                for _fi, tr in enumerate(flushed):
                    try:
                        fids[_fi] = id(tr)
                    except Exception:
                        return False
                    try:
                        d = tr._world_matrix._d
                    except Exception:
                        try:
                            d = tr.world_matrix._d
                        except Exception:
                            return False
                    dlist.append(d)
                funiq, sorder = np.unique(fids, return_index=True)
                if match_flushed_rows is None:
                    return False
                cnt_m = match_flushed_rows(np.ascontiguousarray(row_tids[:n], dtype=np.uint64), np.ascontiguousarray(funiq), self._partial_rows[:n], self._partial_which[:n])
            except Exception:
                return False
            if not cnt_m:
                try:
                    rv = scene._render_version if scene is not None else None; tv = scene._transform_version if scene is not None else None
                    self._flat_sig = (id(scene), rv, tv, n); self._flat_src_list = renderable_shadow
                except Exception:
                    pass
                return True
            try:
                idx_arr = np.ascontiguousarray(self._partial_rows[:cnt_m], dtype=np.intp); which = np.ascontiguousarray(self._partial_which[:cnt_m], dtype=np.intp)
                Dall = np.stack([np.ascontiguousarray(d, dtype=np.float64) for d in dlist]); Ds = Dall[np.ascontiguousarray(sorder, dtype=np.intp)]; M = Ds[which]
            except Exception:
                return False
            try:
                self._flat_centers[idx_arr] = M[:, 3, :3]; col = M[:, :3, :]
                ms = np.sqrt(np.einsum('nca,nca->na', col, col)).max(axis=1); base = self._flat_row_base
                self._flat_radii[idx_arr] = ms * base[idx_arr]
                self._flat_mats[idx_arr] = np.ascontiguousarray(M.reshape(M.shape[0], 16).astype(np.float32))
                try:
                    self._flat_max_radius = float(np.max(self._flat_radii[:self._flat_n]))
                except Exception:
                    pass
                try:
                    rv = scene._render_version if scene is not None else None; tv = scene._transform_version if scene is not None else None
                    self._flat_sig = (id(scene), rv, tv, n); self._flat_src_list = renderable_shadow
                except Exception:
                    pass
                return True
            except Exception:
                return False
        except Exception:
            return False
    def _cull_flat_count(self, vp: np.ndarray) -> int:
        n = self._flat_n
        if n == 0:
            return 0
        try:
            _o = self._shadow_origin
        except Exception:
            _o = None
        cen = self._flat_centers[:n]; vpm = vp
        if _o is not None:
            try:
                cen = cen - np.asarray(_o, dtype=np.float64).reshape(3); vpm = np.frombuffer(shift_vp_bytes(vp, _o), dtype=np.float32).copy().reshape(4, 4)
            except Exception:
                cen = self._flat_centers[:n]; vpm = vp
        if cull_flat is not None:
            try:
                return int(cull_flat(np.ascontiguousarray(cen, dtype=np.float64), np.ascontiguousarray(self._flat_radii[:n], dtype=np.float64), np.ascontiguousarray(vpm, dtype=np.float32), self._flat_out[:n]))
            except Exception:
                pass
        from core.renderer.culling import cpu_frustum_cull
        try:
            vis = cpu_frustum_cull(cen, self._flat_radii[:n], np.ascontiguousarray(np.asarray(vpm, dtype=np.float64).T)); m = len(vis); self._flat_out[:m] = vis
            return m
        except Exception:
            return n
    def _cull_flat_min_count(self, vp: np.ndarray, min_radius: float) -> int:
        n = self._flat_n
        if n == 0:
            return 0
        if min_radius <= 0.0:
            return self._cull_flat_count(vp)
        try:
            _o = self._shadow_origin
        except Exception:
            _o = None
        cen = self._flat_centers[:n]; vpm = vp
        if _o is not None:
            try:
                cen = cen - np.asarray(_o, dtype=np.float64).reshape(3); vpm = np.frombuffer(shift_vp_bytes(vp, _o), dtype=np.float32).copy().reshape(4, 4)
            except Exception:
                cen = self._flat_centers[:n]; vpm = vp
        if cull_flat_min is not None:
            try:
                return int(cull_flat_min(np.ascontiguousarray(cen, dtype=np.float64), np.ascontiguousarray(self._flat_radii[:n], dtype=np.float64), np.ascontiguousarray(vpm, dtype=np.float32), float(min_radius), self._flat_out[:n]))
            except Exception:
                pass
        return self._cull_flat_count(vp)
    def _cull_flat_range_count(self, vp: np.ndarray, lx: float, ly: float, lz: float, range_sq: float, min_radius: float = 0.0) -> int:
        n = self._flat_n
        if n == 0:
            return 0
        try:
            import math as _m; base_range = _m.sqrt(max(float(range_sq), 0.0))
        except Exception:
            base_range = 0.0
        try:
            _o = self._shadow_origin
        except Exception:
            _o = None
        cen = self._flat_centers[:n]; vpm = vp; _lx = float(lx); _ly = float(ly); _lz = float(lz)
        if _o is not None:
            try:
                _ox = float(_o[0]); _oy = float(_o[1]); _oz = float(_o[2])
                cen = cen - np.asarray(_o, dtype=np.float64).reshape(3); vpm = np.frombuffer(shift_vp_bytes(vp, _o), dtype=np.float32).copy().reshape(4, 4); _lx -= _ox; _ly -= _oy; _lz -= _oz
            except Exception:
                cen = self._flat_centers[:n]; vpm = vp; _lx = float(lx); _ly = float(ly); _lz = float(lz)
        try:
            cen_c = np.ascontiguousarray(cen, dtype=np.float64); rad_c = np.ascontiguousarray(self._flat_radii[:n], dtype=np.float64); vpm_c = np.ascontiguousarray(vpm, dtype=np.float32)
        except Exception:
            return 0
        if cull_flat_range_min is not None:
            try:
                eff = base_range + float(self._flat_max_radius)
                return int(cull_flat_range_min(cen_c, rad_c, vpm_c, _lx, _ly, _lz, eff * eff, float(min_radius), self._flat_out[:n]))
            except Exception:
                pass
        return self._cull_flat_count(vp)
