# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations


class TransparencySortMixin:
    def _remember_parts(self, renderable, opaque, transparent, all_opaque):
        try:
            self._part_lists = (id(renderable), opaque, transparent, bool(all_opaque))
        except Exception:
            pass
        return opaque, transparent

    def _partition_transparent(self, renderable):
        opaque = []
        transparent = []
        mm = self._materials
        if mm is None:
            try:
                self._last_has_sprite = False
            except Exception:
                pass
            return self._remember_parts(renderable, list(renderable), transparent, True)
        try:
            ism = mm.mesh_transparency
            lm = mm.load_material
        except Exception:
            try:
                self._last_has_sprite = False
            except Exception:
                pass
            return self._remember_parts(renderable, list(renderable), transparent, True)
        try:
            _pc = self._part_cache
        except Exception:
            _pc = None
        try:
            _pn = len(renderable)
        except Exception:
            _pn = -1
        if _pc is not None and _pn > 0 and _pc[0] == _pn:
            try:
                _cmp = self._partition_cached(renderable, _pn, _pc, ism, lm)
                if _cmp is not None:
                    return _cmp
            except Exception:
                pass
        uniq = set()
        has_sprite = False
        uniq_add = uniq.add
        _rec_mp = []
        _rec_mp_append = _rec_mp.append
        for e in renderable:
            mr = e[3]
            if mr is None:
                uniq_add("")
                _rec_mp_append("")
                continue
            sp = mr.sprite_texture
            if sp:
                has_sprite = True
                break
            mats = mr.materials
            if not mats:
                uniq_add("")
                _rec_mp_append("")
            else:
                sub = e[5]
                if sub < len(mats):
                    _mp0 = mats[sub].get("path", "")
                else:
                    _mp0 = mats[-1].get("path", "")
                uniq_add(_mp0)
                _rec_mp_append(_mp0)
        if has_sprite:
            try:
                self._last_has_sprite = True
                self._last_uniq = None
                self._last_trans = None
            except Exception:
                pass
            for e in renderable:
                try:
                    mr = e[3]
                    sub = e[5] if len(e) > 5 else 0
                    mat = lm(mr.get_material_path(sub) if mr else "")
                    if ism(mr, mat):
                        transparent.append(e)
                    else:
                        opaque.append(e)
                except Exception:
                    opaque.append(e)
            return self._remember_parts(renderable, opaque, transparent, False)
        trans_set = set()
        for p in uniq:
            try:
                mat = lm(p)
                if ism(None, mat):
                    trans_set.add(p)
            except Exception:
                pass
        try:
            self._last_has_sprite = False
            self._last_uniq = frozenset(uniq)
            self._last_trans = frozenset(trans_set)
        except Exception:
            pass
        if not trans_set:
            try:
                if len(_rec_mp) == len(renderable):
                    self._part_cache = (len(renderable), _rec_mp, bytearray(len(renderable)), frozenset(uniq), frozenset(trans_set))
            except Exception:
                pass
            return self._remember_parts(renderable, list(renderable), transparent, True)
        for e in renderable:
            mr = e[3]
            if mr is None:
                opaque.append(e)
                continue
            mats = mr.materials
            if not mats:
                opaque.append(e)
            else:
                sub = e[5]
                if sub < len(mats):
                    p = mats[sub].get("path", "")
                else:
                    p = mats[-1].get("path", "")
                if p in trans_set:
                    transparent.append(e)
                else:
                    opaque.append(e)
        try:
            if len(_rec_mp) == len(renderable):
                self._part_cache = (len(renderable), _rec_mp, bytearray(len(renderable)), frozenset(uniq), frozenset(trans_set))
        except Exception:
            pass
        return self._remember_parts(renderable, opaque, transparent, not transparent)

    def _partition_cached(self, renderable, n, pc, ism, lm):
        cached_mpaths = pc[1]
        for i in range(n):
            try:
                e = renderable[i]
                mr = e[3]
                if mr is None:
                    if cached_mpaths[i] != "":
                        return None
                    continue
                try:
                    _spt = mr.sprite_texture
                    if _spt:
                        return None
                except Exception:
                    pass
                mats = mr.materials
                if mats:
                    sub = e[5]
                    if sub < len(mats):
                        mp = mats[sub].get("path", "")
                    else:
                        mp = mats[-1].get("path", "")
                else:
                    mp = ""
            except Exception:
                mp = ""
            if mp != cached_mpaths[i]:
                return None
        uniq = pc[3]
        trans_set = set()
        try:
            for p in uniq:
                try:
                    mat = lm(p)
                    if ism(None, mat):
                        trans_set.add(p)
                except Exception:
                    pass
        except Exception:
            return None
        try:
            self._last_has_sprite = False
            self._last_uniq = frozenset(uniq)
            self._last_trans = frozenset(trans_set)
        except Exception:
            pass
        if not trans_set:
            try:
                _pl = self._part_lists
                if _pl is not None and _pl[0] == id(renderable) and _pl[3]:
                    return _pl[1], _pl[2]
            except Exception:
                pass
            return self._remember_parts(renderable, list(renderable), [], True)
        opaque = []
        transparent = []
        for i in range(n):
            try:
                e = renderable[i]
            except Exception:
                continue
            if cached_mpaths[i] in trans_set:
                transparent.append(e)
            else:
                opaque.append(e)
        return self._remember_parts(renderable, opaque, transparent, not transparent)

    def _sort_transparent_far_first(self, entries, cam_pos):
        try:
            n = len(entries)
        except Exception:
            return
        if n < 2:
            return
        try:
            cx = float(cam_pos.x)
            cy = float(cam_pos.y)
            cz = float(cam_pos.z)
        except Exception:
            return
        try:
            import numpy as _np
            try:
                from core._render_utils import build_frustum_cull_inputs as _bfci
                centers, _ = _bfci(entries)
            except Exception:
                centers = _np.empty((n, 3), dtype=_np.float64)
                for _i, _e in enumerate(entries):
                    _d = _e[4]._d
                    centers[_i, 0] = _d[3, 0]
                    centers[_i, 1] = _d[3, 1]
                    centers[_i, 2] = _d[3, 2]
            _dx = centers[:, 0] - cx
            _dy = centers[:, 1] - cy
            _dz = centers[:, 2] - cz
            _idx = _np.argsort(-(_dx * _dx + _dy * _dy + _dz * _dz), kind="stable")
            entries[:] = [entries[int(_i)] for _i in _idx]
        except Exception:
            pass

    def _sort_opaque_front_first(self, entries, cam_pos):
        try:
            n = len(entries)
        except Exception:
            return
        if n < 64:
            return
        try:
            cx = float(cam_pos.x)
            cy = float(cam_pos.y)
            cz = float(cam_pos.z)
        except Exception:
            return
        try:
            _ck = getattr(self, "_opaque_sort_cache", None)
            if _ck is not None and _ck[0] == id(entries) and _ck[1] == n and _ck[2] == cx and _ck[3] == cy and _ck[4] == cz:
                try:
                    _e0 = entries[0][4]._d
                    _e1 = entries[-1][4]._d
                    if _e0[3, 0] == _ck[5] and _e0[3, 1] == _ck[6] and _e0[3, 2] == _ck[7] and _e1[3, 0] == _ck[8] and _e1[3, 1] == _ck[9] and _e1[3, 2] == _ck[10]:
                        return
                except Exception:
                    pass
        except Exception:
            pass
        try:
            import numpy as _np
            try:
                from core._render_utils import build_frustum_cull_inputs as _bfci
                centers, _ = _bfci(entries)
            except ImportError:
                centers = _np.empty((n, 3), dtype=_np.float64)
                for _i, _e in enumerate(entries):
                    _d = _e[4]._d
                    centers[_i, 0] = _d[3, 0]
                    centers[_i, 1] = _d[3, 1]
                    centers[_i, 2] = _d[3, 2]
            _dx = centers[:, 0] - cx
            _dy = centers[:, 1] - cy
            _dz = centers[:, 2] - cz
            _idx = _np.argsort(_dx * _dx + _dy * _dy + _dz * _dz, kind="stable")
            _ordered = [entries[int(_i)] for _i in _idx]
            entries[:] = _ordered
            try:
                _n0 = entries[0][4]._d
                _n1 = entries[-1][4]._d
                self._opaque_sort_cache = (id(entries), n, cx, cy, cz, float(_n0[3, 0]), float(_n0[3, 1]), float(_n0[3, 2]), float(_n1[3, 0]), float(_n1[3, 1]), float(_n1[3, 2]))
            except Exception:
                pass
        except Exception:
            pass
