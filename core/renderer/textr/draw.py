# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import numpy as np
import moderngl
from typing import Any
class TextDrawMixin:
    _OUTLINE_DIRS = [
        (1.0, 0.0), (0.9239, 0.3827), (0.7071, 0.7071), (0.3827, 0.9239),
        (0.0, 1.0), (-0.3827, 0.9239), (-0.7071, 0.7071), (-0.9239, 0.3827),
        (-1.0, 0.0), (-0.9239, -0.3827), (-0.7071, -0.7071), (-0.3827, -0.9239),
        (0.0, -1.0), (0.3827, -0.9239), (0.7071, -0.7071), (0.9239, -0.3827),
    ]
    _GLOW_RINGS = [
        (1.0, 0.5),
        (1.5, 0.3),
        (2.5, 0.15),
    ]
    def _render_quads(self, vi: int, color, tex: Any, write_depth: bool, solid: bool, start_v: int = 0, clip_alpha: float = 0.01):
        prog = self._prog
        if vi == 0:
            return
        if tex is None:
            return
        names = getattr(self, "_prog_names", None)
        if names is None or getattr(self, "_prog_id", None) is not id(prog):
            names = frozenset(prog)
            self._prog_names = names
            self._prog_id = id(prog)
        try:
            if len(color) > 3:
                ckey = (float(color[0]), float(color[1]), float(color[2]), float(color[3]))
            else:
                ckey = (float(color[0]), float(color[1]), float(color[2]), 1.0)
        except Exception:
            ckey = None
        if "u_color" in names:
            if ckey is not None and ckey == self._rq_color:
                pass
            else:
                try:
                    prog["u_color"].write(np.array(ckey if ckey is not None else color, dtype=np.float32).tobytes())
                except Exception:
                    try:
                        prog["u_color"].write(np.array(color, dtype=np.float32).tobytes())
                    except Exception:
                        pass
                self._rq_color = ckey
        try:
            skey = 1.0 if solid else 0.0
        except Exception:
            skey = 0.0
        if "u_solid" in names and skey != self._rq_solid:
            try:
                prog["u_solid"].value = skey
            except Exception:
                pass
            self._rq_solid = skey
        try:
            akey = float(clip_alpha)
        except Exception:
            akey = 0.01
        if "u_clip_alpha" in names and akey != self._rq_clip:
            try:
                prog["u_clip_alpha"].value = akey
            except Exception:
                pass
            self._rq_clip = akey
        try:
            tid = id(tex)
        except Exception:
            tid = None
        if tid != self._rq_tex:
            try:
                tex.use(0)
            except Exception:
                return
            if "u_texture" in names:
                try:
                    prog["u_texture"].value = 0
                except Exception:
                    pass
            self._rq_tex = tid
        try:
            self._vao.render(moderngl.TRIANGLES, vertices=vi * 6, first=start_v * 6)
        except Exception:
            pass
    def _write_offset(self, prog, names, x: float, y: float, z: float):
        try:
            key = (float(x), float(y), float(z))
        except Exception:
            return
        if key == self._rq_offset:
            return
        if "u_offset" in names:
            try:
                prog["u_offset"].write(np.array(key, dtype=np.float32).tobytes())
            except Exception:
                pass
        self._rq_offset = key
    def _draw_shadow(self, prog, names, tr, tex, vi, evi, ev, has_shadow):
        if not has_shadow:
            return
        try:
            self._ctx.disable(moderngl.DEPTH_TEST)
        except Exception:
            pass
        try:
            sx, sy = tr.shadow_offset[0], tr.shadow_offset[1]
        except Exception:
            sx, sy = 0.0, 0.0
        self._write_offset(prog, names, -float(sx), -float(sy), 0.0)
        if vi > 0:
            self._render_quads(vi, tr.shadow_color, tex, False, False, 0)
        if evi > 0:
            self._render_quads(evi, tr.shadow_color, tex, False, True, ev)
        self._write_offset(prog, names, 0.0, 0.0, 0.0)
        if tr.font_world_space:
            try:
                self._ctx.enable(moderngl.DEPTH_TEST)
            except Exception:
                pass
    def _draw_glow(self, prog, names, tr, tex, vi, evi, ev, has_glow, write_depth):
        if not has_glow:
            return
        gc = list(tr.glow_color)
        try:
            base_intensity = float(gc[3]) * float(tr.glow_intensity)
        except Exception:
            base_intensity = 0.0
        try:
            glow_size = float(tr.glow_size)
        except Exception:
            glow_size = 0.0
        for radius, alpha_scale in self._GLOW_RINGS:
            r = glow_size * radius
            a = base_intensity * alpha_scale
            if a < 0.005:
                continue
            gc[3] = a
            for dx, dy in self._OUTLINE_DIRS:
                self._write_offset(prog, names, float(dx * r), float(dy * r), 0.0)
                if vi > 0:
                    self._render_quads(vi, gc, tex, write_depth, False, 0)
                if evi > 0:
                    self._render_quads(evi, gc, tex, write_depth, False, ev)
            self._write_offset(prog, names, 0.0, 0.0, 0.0)
    def _draw_outline(self, prog, names, tr, tex, vi, evi, ev, has_outline, write_depth):
        if not has_outline:
            return
        oc = tr.outline_color
        try:
            ow = float(tr.outline_width)
        except Exception:
            ow = 0.0
        for dx, dy in self._OUTLINE_DIRS:
            self._write_offset(prog, names, float(dx * ow), float(dy * ow), 0.0)
            if vi > 0:
                self._render_quads(vi, oc, tex, write_depth, False, 0)
            if evi > 0:
                self._render_quads(evi, oc, tex, write_depth, False, ev)
        self._write_offset(prog, names, 0.0, 0.0, 0.0)
    def _draw_extruded(self, prog, names, tr, tex, vi, evi, ev, write_depth, clip_main):
        try:
            layer_step = float(tr.extrusion_depth) / max(int(tr.extrusion_layers), 1)
        except Exception:
            layer_step = 0.0
        for layer in range(int(tr.extrusion_layers), 0, -1):
            z_off = layer * layer_step
            try:
                t_factor = 0.3 + 0.7 * (1.0 - layer / max(int(tr.extrusion_layers), 1))
            except Exception:
                t_factor = 1.0
            try:
                ecolor = [
                    tr.extrusion_color[0] * t_factor,
                    tr.extrusion_color[1] * t_factor,
                    tr.extrusion_color[2] * t_factor,
                    tr.color[3],
                ]
            except Exception:
                continue
            self._write_offset(prog, names, 0.0, 0.0, -float(z_off))
            if vi > 0:
                self._render_quads(vi, ecolor, tex, write_depth, False, 0)
            if evi > 0:
                self._render_quads(evi, ecolor, tex, write_depth, True, ev)
        self._write_offset(prog, names, 0.0, 0.0, 0.0)
        if vi > 0:
            self._render_quads(vi, tr.color, tex, write_depth, False, 0, clip_main)
        if evi > 0:
            self._render_quads(evi, tr.color, tex, write_depth, True, ev)
    def _draw_main(self, tr, tex, vi, evi, ev, write_depth, clip_main):
        if self._rich_seg_info:
            for seg in self._rich_seg_info:
                try:
                    seg_color = seg["color"]
                    seg_vc = int(seg["vi_count"])
                except Exception:
                    continue
                if seg_vc > 0:
                    try:
                        seg_vs = int(seg["vi_start"])
                    except Exception:
                        seg_vs = 0
                    self._render_quads(seg_vc, seg_color, tex, write_depth, False, seg_vs, clip_main)
                try:
                    seg_fx = bool(seg["underline"] or seg["strikethrough"])
                except Exception:
                    seg_fx = False
                if seg_fx:
                    try:
                        seg_ec = int(seg["evi_count"])
                        seg_es = int(seg["evi_start"])
                    except Exception:
                        seg_ec = 0
                        seg_es = 0
                    self._render_quads(seg_ec, seg_color, tex, write_depth, True, ev + seg_es)
        else:
            if vi > 0:
                self._render_quads(vi, tr.color, tex, write_depth, False, 0, clip_main)
            if evi > 0:
                self._render_quads(evi, tr.color, tex, write_depth, True, ev)
