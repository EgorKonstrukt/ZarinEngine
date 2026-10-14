# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations


class ScenevSkinnedMixin:
    def _scenev_render_skinned(self, snap, view_f32, proj_f32, cam_pos, lights, prof=None):
        try:
            has_skinned = bool(snap.skinned_renderables)
        except Exception:
            has_skinned = False
        if not has_skinned:
            return
        try:
            if prof:
                prof.start("render_skinned")
        except Exception:
            pass
        try:
            self._render_skinned_meshes(snap, view_f32, proj_f32, cam_pos, lights)
        except Exception:
            pass
        try:
            if prof:
                prof.stop("render_skinned")
        except Exception:
            pass
