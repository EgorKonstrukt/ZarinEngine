# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

"""Post-processing helpers."""

from __future__ import annotations
import os
from core.components.rendering.postfx.graphics_effect import GraphicsEffect


class PostPassMixin:
    """Post-processing helpers."""


    def _has_tonemap_effect(self):
        if not GraphicsEffect._registry:
            return False
        from core.components.rendering.postfx.color_grading import ColorGrading
        for e in GraphicsEffect._registry:
            if isinstance(e, ColorGrading) and e.enabled and e.entity and e.entity.active:
                return True
        return False


    def _present_composite(self, tex, fbo, disp_w, disp_h):
        if fbo is not None:
            fbo.use()
            fbo.viewport = (0, 0, disp_w, disp_h)
        elif self._ctx.screen is not None:
            self._ctx.screen.use()
            self._ctx.viewport = (0, 0, disp_w, disp_h)
        if self._has_tonemap_effect() or self._pp_tonemap_prog is None:
            prog = self._pp_copy_prog
            vao = self._pp_copy_vao
        else:
            prog = self._pp_tonemap_prog
            vao = self._pp_tonemap_vao
            prog["u_exposure"].value = float(self._exposure)
        prog["u_input_tex"] = 0
        tex.use(0)
        vao.render()


    def _gaussian_ply_path(self, gs, eng) -> str:
        ply_path = gs.ply_path
        if ply_path and not os.path.isabs(ply_path):
            root = eng.project_root if eng and getattr(eng, "project_root", None) else os.getcwd()
            abs_ply = os.path.join(root, ply_path)
            if not os.path.exists(abs_ply):
                alt = os.path.join(root, "assets", os.path.basename(ply_path))
                if os.path.exists(alt):
                    abs_ply = alt
                else:
                    alt2 = os.path.join(root, "assets", ply_path)
                    if os.path.exists(alt2):
                        abs_ply = alt2
            ply_path = abs_ply
        return ply_path
