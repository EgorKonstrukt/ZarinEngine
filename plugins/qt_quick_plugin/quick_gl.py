# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import numpy as np

try:
    from core.foundation.logger import Logger

    _HAS_LOGGER = True
except Exception:
    Logger = None
    _HAS_LOGGER = False

try:
    import moderngl

    _HAS_GL = True
except Exception:
    moderngl = None
    _HAS_GL = False


QUICK_VERT = """#version 460 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec2 in_uv;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = u_proj * u_view * u_model * vec4(in_position, 1.0);
}
"""

QUICK_FRAG = """#version 460 core
in vec2 v_uv;
uniform sampler2D u_texture;
uniform float u_opacity;
uniform vec4 u_tint;
out vec4 frag_color;
void main() {
    vec4 tex = texture(u_texture, v_uv);
    vec3 col = tex.rgb * u_tint.rgb;
    float alpha = tex.a * u_opacity * u_tint.a;
    if (alpha < 0.01) {
        discard;
    }
    frag_color = vec4(col, alpha);
}
"""


def qimage_to_bytes(img):
    try:
        conv = img.convertToFormat(img.Format.Format_RGBA8888)
    except Exception:
        try:
            from PyQt6.QtGui import QImage as _QI

            conv = img.convertToFormat(_QI.Format.Format_RGBA8888)
        except Exception:
            return (None, 0, 0)
    try:
        w = int(conv.width())
        h = int(conv.height())
    except Exception:
        return (None, 0, 0)
    if w <= 0 or h <= 0:
        return (None, 0, 0)
    try:
        bits = conv.constBits()
        try:
            bits.setsize(conv.sizeInBytes())
        except Exception:
            pass
        try:
            raw = bytes(bits.asarray())
        except Exception:
            raw = bytes(bits)
        expect = w * h * 4
        if len(raw) < expect:
            return (None, 0, 0)
        return (raw[:expect], w, h)
    except Exception:
        pass
    try:
        ptr = conv.bits()
        try:
            ptr.setsize(conv.sizeInBytes())
        except Exception:
            pass
        raw = bytes(ptr.asarray())
        expect = w * h * 4
        if len(raw) < expect:
            return (None, 0, 0)
        return (raw[:expect], w, h)
    except Exception:
        return (None, 0, 0)


class QuickGLRenderer:
    def __init__(self):
        self._states: dict = {}
        self._cur = None
        self._prog_error_logged = False

    def _state_for(self, ctx) -> dict:
        try:
            key = id(ctx)
        except Exception:
            key = 0
        st = self._states.get(key)
        if st is None:
            st = {"ctx": ctx, "prog": None, "vbo": None, "ibo": None, "vao": None, "textures": {}, "sizes": {}}
            self._states[key] = st
        else:
            st["ctx"] = ctx
        self._cur = st
        return st

    def ensure(self, ctx) -> bool:
        if not _HAS_GL or ctx is None:
            return False
        st = self._state_for(ctx)
        if st["prog"] is not None and st["vao"] is not None:
            return True
        try:
            st["prog"] = ctx.program(vertex_shader=QUICK_VERT, fragment_shader=QUICK_FRAG)
            self._prog_error_logged = False
        except Exception as e:
            st["prog"] = None
            if _HAS_LOGGER and not self._prog_error_logged:
                self._prog_error_logged = True
                Logger.error("[QtQuickWorld] shader compile failed: " + str(e))
            return False
        try:
            quad = np.array(
                [
                    -0.5, -0.5, 0.0, 0.0, 1.0,
                    0.5, -0.5, 0.0, 1.0, 1.0,
                    0.5, 0.5, 0.0, 1.0, 0.0,
                    -0.5, 0.5, 0.0, 0.0, 0.0,
                ],
                dtype=np.float32,
            )
            idx = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
            st["vbo"] = ctx.buffer(quad.tobytes())
            st["ibo"] = ctx.buffer(idx.tobytes())
            st["vao"] = ctx.vertex_array(st["prog"], [(st["vbo"], "3f 2f", "in_position", "in_uv")], st["ibo"])
            return True
        except Exception:
            return False

    def release(self):
        for st in list(self._states.values()):
            try:
                for tex in list(st["textures"].values()):
                    try:
                        tex.release()
                    except Exception:
                        pass
                st["textures"].clear()
                st["sizes"].clear()
                for obj in (st["vao"], st["vbo"], st["ibo"]):
                    if obj is not None:
                        try:
                            obj.release()
                        except Exception:
                            pass
                st["vao"] = None
                st["vbo"] = None
                st["ibo"] = None
                if st["prog"] is not None:
                    try:
                        st["prog"].release()
                    except Exception:
                        pass
                st["prog"] = None
            except Exception:
                pass
        self._states.clear()
        self._cur = None

    def drop_view(self, key: str):
        for st in list(self._states.values()):
            try:
                tex = st["textures"].pop(key, None)
                st["sizes"].pop(key, None)
                if tex is not None:
                    try:
                        tex.release()
                    except Exception:
                        pass
            except Exception:
                pass

    def prune(self, keep: set):
        st = self._cur
        if st is None:
            return
        for key in list(st["textures"].keys()):
            if key not in keep:
                try:
                    tex = st["textures"].pop(key, None)
                    st["sizes"].pop(key, None)
                    if tex is not None:
                        try:
                            tex.release()
                        except Exception:
                            pass
                except Exception:
                    pass

    def upload(self, key: str, img) -> bool:
        st = self._cur
        if not _HAS_GL or st is None or img is None:
            return False
        ctx = st.get("ctx")
        if ctx is None:
            return False
        try:
            raw, w, h = qimage_to_bytes(img)
        except Exception:
            return False
        if raw is None:
            return False
        try:
            old = st["textures"].get(key)
            old_size = st["sizes"].get(key)
            if old is not None and old_size == (w, h):
                try:
                    old.write(raw)
                    return True
                except Exception:
                    pass
            if old is not None:
                try:
                    old.release()
                except Exception:
                    pass
            tex = ctx.texture((w, h), 4, raw)
            try:
                tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            except Exception:
                pass
            try:
                tex.repeat_x = False
                tex.repeat_y = False
            except Exception:
                pass
            st["textures"][key] = tex
            st["sizes"][key] = (w, h)
            return True
        except Exception:
            return False

    def model_for(self, comp, cam_pos):
        try:
            from core.maths.math3d import Mat4, Vec3

            tr = comp.transform
            if tr is None:
                return None
            mode = str(getattr(comp, "billboard", "Off"))
            sx = float(getattr(comp, "size_x", 1.0))
            sy = float(getattr(comp, "size_y", 1.0))
            if mode == "Off":
                try:
                    wm = tr.world_matrix
                except Exception:
                    return None
                try:
                    return Mat4.scale(Vec3(sx, sy, 1.0)) * wm
                except Exception:
                    return wm
            try:
                pos = tr.position
            except Exception:
                return None
            try:
                sc = tr.local_scale
                lx = abs(float(sc.x))
                ly = abs(float(sc.y))
            except Exception:
                lx, ly = 1.0, 1.0
            fx = sx * lx
            fy = sy * ly
            px, py, pz = float(pos.x), float(pos.y), float(pos.z)
            cx, cy, cz = float(cam_pos.x), float(cam_pos.y), float(cam_pos.z)
            if mode == "Y":
                import math

                dx = cx - px
                dz = cz - pz
                yaw = math.atan2(dx, dz)
                cyaw = math.cos(yaw)
                syaw = math.sin(yaw)
                arr = np.array(
                    [
                        [cyaw * fx, 0.0, syaw * fx, 0.0],
                        [0.0, fy, 0.0, 0.0],
                        [-syaw * fx, 0.0, cyaw * fx, 0.0],
                        [px, py, pz, 1.0],
                    ],
                    dtype=np.float64,
                )
                return Mat4(arr)
            import math

            dx = cx - px
            dy = cy - py
            dz = cz - pz
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            if dist < 1e-6:
                try:
                    wm = tr.world_matrix
                    return Mat4.scale(Vec3(sx, sy, 1.0)) * wm
                except Exception:
                    return None
            fz = np.array([dx / dist, dy / dist, dz / dist], dtype=np.float64)
            up = np.array([0.0, 1.0, 0.0], dtype=np.float64)
            if abs(float(fz[1])) > 0.999:
                up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            rx = np.cross(up, fz)
            rl = float(np.linalg.norm(rx))
            if rl < 1e-8:
                rx = np.array([1.0, 0.0, 0.0], dtype=np.float64)
            else:
                rx = rx / rl
            ux = np.cross(fz, rx)
            arr = np.array(
                [
                    [rx[0] * fx, rx[1] * fx, rx[2] * fx, 0.0],
                    [ux[0] * fy, ux[1] * fy, ux[2] * fy, 0.0],
                    [fz[0], fz[1], fz[2], 0.0],
                    [px, py, pz, 1.0],
                ],
                dtype=np.float64,
            )
            return Mat4(arr)
        except Exception:
            return None

    def render_into_scene(self, renderer, scene, views: list, images: dict, view_mat, proj_mat, cam_pos) -> int:
        st = self._cur
        if not _HAS_GL or st is None or st["prog"] is None or st["vao"] is None:
            return 0
        if not views:
            return 0
        try:
            ctx = st["ctx"]
            if ctx is None:
                return 0
        except Exception:
            return 0
        drawn = 0
        try:
            view_f32 = view_mat.to_f32()
            proj_f32 = proj_mat.to_f32()
        except Exception:
            return 0
        try:
            ctx.disable(moderngl.CULL_FACE)
        except Exception:
            pass
        try:
            ctx.enable(moderngl.BLEND)
        except Exception:
            pass
        try:
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        except Exception:
            pass
        try:
            ctx.enable(moderngl.DEPTH_TEST)
        except Exception:
            pass
        prog = st["prog"]
        vao = st["vao"]
        textures = st["textures"]
        for comp in views:
            try:
                ent = getattr(comp, "_entity", None)
                if ent is not None and not getattr(ent, "active", True):
                    continue
                if not getattr(comp, "enabled", True):
                    continue
                key = None
                try:
                    eid = ent.id if ent is not None else ""
                    key = str(eid) + "|" + str(getattr(comp, "_key", ""))
                except Exception:
                    key = str(id(comp))
                tex = textures.get(key)
                if tex is None:
                    continue
                model = self.model_for(comp, cam_pos)
                if model is None:
                    continue
                try:
                    model_f32 = model.to_f32()
                except Exception:
                    continue
                try:
                    prog["u_model"].write(model_f32.tobytes())
                    prog["u_view"].write(view_f32.tobytes())
                    prog["u_proj"].write(proj_f32.tobytes())
                except Exception:
                    continue
                try:
                    prog["u_opacity"].value = max(0.0, min(1.0, float(getattr(comp, "opacity", 1.0))))
                except Exception:
                    pass
                try:
                    tint = getattr(comp, "tint", [1.0, 1.0, 1.0, 1.0])
                    prog["u_tint"].write(np.array([float(tint[0]), float(tint[1]), float(tint[2]), float(tint[3])], dtype=np.float32).tobytes())
                except Exception:
                    pass
                try:
                    transparent = bool(getattr(comp, "transparent", True))
                except Exception:
                    transparent = True
                try:
                    ctx.depth_mask = not transparent
                except Exception:
                    pass
                try:
                    tex.use(0)
                    prog["u_texture"].value = 0
                except Exception:
                    continue
                try:
                    vao.render(moderngl.TRIANGLES)
                    drawn += 1
                except Exception:
                    continue
            except Exception:
                continue
        try:
            ctx.depth_mask = True
        except Exception:
            pass
        try:
            ctx.enable(moderngl.CULL_FACE)
        except Exception:
            pass
        return drawn
