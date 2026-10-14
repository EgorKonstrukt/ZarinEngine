# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import ctypes
import os
import numpy as np
import moderngl
from pathlib import Path
try:
    import xr
except ImportError:
    xr = None
from plugins.vr_plugin.core.state import _vr_state, _XR_AVAILABLE, _SHADER_DIR, _quat_to_mat3, _normalize3, _controller_world_quat, _xr_controller_to_world, _xr_hmd_to_world, _make_model_matrix, _mat4_mul, _make_proj_matrix, _make_view_matrix, has_vr_rig, ControllerState

def _build_controller_mesh():
    verts = []
    indices = []
    def _add_box(cx, cy, cz, sx, sy, sz, nx_faces=True):
        hx, hy, hz = sx*0.5, sy*0.5, sz*0.5
        corners = [
            (-hx+cx, -hy+cy, -hz+cz),
            ( hx+cx, -hy+cy, -hz+cz),
            ( hx+cx,  hy+cy, -hz+cz),
            (-hx+cx,  hy+cy, -hz+cz),
            (-hx+cx, -hy+cy,  hz+cz),
            ( hx+cx, -hy+cy,  hz+cz),
            ( hx+cx,  hy+cy,  hz+cz),
            (-hx+cx,  hy+cy,  hz+cz),
        ]
        faces = [
            (0,1,2,3, ( 0, 0,-1)),
            (5,4,7,6, ( 0, 0, 1)),
            (1,5,6,2, ( 1, 0, 0)),
            (4,0,3,7, (-1, 0, 0)),
            (3,2,6,7, ( 0, 1, 0)),
            (0,4,5,1, ( 0,-1, 0)),
        ]
        for fi, (a,b,c,d, n) in enumerate(faces):
            base = len(verts) // 6
            for vi in (a,b,c,d):
                verts.extend(corners[vi])
                verts.extend(n)
            indices.extend([base, base+1, base+2, base, base+2, base+3])
    def _add_capsule(cx, cy, cz, radius, length, segments=8):
        half = length * 0.5
        for seg in range(segments):
            a0 = seg * 2*math.pi / segments
            a1 = (seg+1) * 2*math.pi / segments
            x0, z0 = math.cos(a0)*radius, math.sin(a0)*radius
            x1, z1 = math.cos(a1)*radius, math.sin(a1)*radius
            base = len(verts) // 6
            n0 = _normalize3((x0, 0, z0))
            n1 = _normalize3((x1, 0, z1))
            for (px, py, pz, nx, ny, nz) in [
                (cx+x0, cy-half, cz+z0, n0[0], n0[1], n0[2]),
                (cx+x1, cy-half, cz+z1, n1[0], n1[1], n1[2]),
                (cx+x1, cy+half, cz+z1, n1[0], n1[1], n1[2]),
                (cx+x0, cy+half, cz+z0, n0[0], n0[1], n0[2]),
            ]:
                verts.extend([px, py, pz, nx, ny, nz])
            indices.extend([base, base+1, base+2, base, base+2, base+3])
        for cap_y, cap_sign in [(-half, -1.0), (half, 1.0)]:
            rings = 4
            for ring in range(rings):
                phi0 = ring * (math.pi*0.5) / rings
                phi1 = (ring+1) * (math.pi*0.5) / rings
                for seg in range(segments):
                    a0 = seg * 2*math.pi / segments
                    a1 = (seg+1) * 2*math.pi / segments
                    for (phi, aa, ab) in [(phi0, a0, a1), (phi1, a0, a1)]:
                        pass
                    r0, r1 = math.cos(phi0)*radius, math.cos(phi1)*radius
                    h0, h1 = math.sin(phi0)*radius*cap_sign, math.sin(phi1)*radius*cap_sign
                    x00, z00 = math.cos(a0)*r0, math.sin(a0)*r0
                    x01, z01 = math.cos(a1)*r0, math.sin(a1)*r0
                    x10, z10 = math.cos(a0)*r1, math.sin(a0)*r1
                    x11, z11 = math.cos(a1)*r1, math.sin(a1)*r1
                    pts = [
                        (cx+x00, cy+cap_y+h0, cz+z00),
                        (cx+x01, cy+cap_y+h0, cz+z01),
                        (cx+x11, cy+cap_y+h1, cz+z11),
                        (cx+x10, cy+cap_y+h1, cz+z10),
                    ]
                    base = len(verts) // 6
                    for px, py, pz in pts:
                        nx, ny, nz = _normalize3((px-cx, (py-cy-cap_y)*cap_sign, pz-cz))
                        verts.extend([px, py, pz, nx, ny, nz])
                    indices.extend([base, base+1, base+2, base, base+2, base+3])
    _add_capsule(0.0, 0.0, 0.0, 0.018, 0.12)
    _add_box(0.0, -0.04, 0.022, 0.030, 0.020, 0.012)
    _add_box(0.0,  0.035, 0.010, 0.022, 0.015, 0.010)
    _add_box(-0.014, -0.015, 0.016, 0.008, 0.010, 0.008)
    _add_box( 0.014, -0.015, 0.016, 0.008, 0.010, 0.008)
    return np.array(verts, dtype='f4'), np.array(indices, dtype='i4')

def _resolve_vr_model_path(*parts):
    base = Path(__file__).resolve().parents[3]
    p = base.joinpath(*parts)
    if p.exists():
        return str(p)
    alt = Path.cwd().joinpath(*parts)
    if alt.exists():
        return str(alt)
    return str(p)

def _load_mesh_to_vao(path, ctx, prog):
    if not os.path.exists(path):
        return None
    try:
        from core.assets.importer import load_mesh, load_obj
        ext = os.path.splitext(path)[1].lower()
        if ext == ".obj":
            data = load_obj(path)
        else:
            data = load_mesh(path)
        if data is None or len(data.vertices) == 0:
            return None
        verts = np.array(data.vertices, dtype=np.float32).reshape(-1, 3)
        norms = np.array(data.normals, dtype=np.float32).reshape(-1, 3) if len(data.normals) >= len(data.vertices) else np.zeros_like(verts)
        if norms.shape[0] != verts.shape[0]:
            norms = np.zeros_like(verts)
        try:
            mn = verts.min(axis=0)
            mx = verts.max(axis=0)
            extent = mx - mn
            max_ext = float(max(extent))
            if max_ext > 0.5:
                sc = 0.12 / max_ext
                verts = verts * sc
        except Exception:
            pass
        n = verts.shape[0]
        vdata = np.empty((n, 6), dtype=np.float32)
        vdata[:, 0:3] = verts
        vdata[:, 3:6] = norms
        vbo = ctx.buffer(vdata.tobytes())
        idx = np.array(data.indices, dtype=np.int32) if len(data.indices) else np.array([], dtype=np.int32)
        if idx.size == 0:
            idx = np.arange(n, dtype=np.int32)
        ibo = ctx.buffer(idx.tobytes())
        vao = ctx.vertex_array(prog, [(vbo, '3f 3f', 'in_pos', 'in_normal')], ibo)
        return (vbo, ibo, vao, idx.size)
    except Exception:
        return None

_CTRL_VERT = open(_SHADER_DIR / "shaders/vr/vr_controller_vert.glsl", "r", encoding="utf-8").read()
_CTRL_FRAG = open(_SHADER_DIR / "shaders/vr/vr_controller_frag.glsl", "r", encoding="utf-8").read()

class ControllerRenderer:
    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._prog = ctx.program(vertex_shader=_CTRL_VERT, fragment_shader=_CTRL_FRAG)
        self._uloc = {n: self._prog[n] for n in self._prog}
        self._gl_clear = ctypes.windll.opengl32.glClear
        self._custom = [None, None]
        self._hmd_mesh = None
        self._load_custom(ctx)
        verts, indices = _build_controller_mesh()
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._vao = ctx.vertex_array(
            self._prog,
            [(self._vbo, '3f 3f', 'in_pos', 'in_normal')],
            self._ibo,
        )
    def _load_custom(self, ctx):
        try:
            left_path = _resolve_vr_model_path("core", "3d_models", "OculusQ2", "OculusQ2ControllerL.fbx")
            right_path = _resolve_vr_model_path("core", "3d_models", "OculusQ2", "OculusQ2ControllerR.fbx")
            hmd_path = _resolve_vr_model_path("core", "3d_models", "generic_hmd", "generic_hmd.obj")
            lm = _load_mesh_to_vao(left_path, ctx, self._prog)
            rm = _load_mesh_to_vao(right_path, ctx, self._prog)
            hm = _load_mesh_to_vao(hmd_path, ctx, self._prog)
            if lm is not None:
                self._custom[0] = lm
            if rm is not None:
                self._custom[1] = rm
            if hm is not None:
                self._hmd_mesh = hm
        except Exception:
            pass
    def _set(self, name, val):
        if name in self._uloc:
            self._uloc[name].value = val
    def render_controller(self, ctrl: ControllerState, proj, view, color, idx=0):
        if not ctrl.valid:
            return
        custom = self._custom[idx] if 0 <= idx < 2 else None
        if custom is not None and isinstance(custom, tuple) and len(custom) == 4:
            vbo, ibo, vao, cnt = custom
            wq = _controller_world_quat(ctrl.quat)
            model = _make_model_matrix(_xr_controller_to_world(ctrl.pos), wq, scale=1.0)
            mv = _mat4_mul(view, model)
            mvp = _mat4_mul(proj, mv)
            rot = _quat_to_mat3(*wq)
            nm = (rot[0], rot[3], rot[6], rot[1], rot[4], rot[7], rot[2], rot[5], rot[8])
            self._set('u_mvp', tuple(mvp))
            self._set('u_normal_mat', nm)
            self._set('u_color', color)
            self._set('u_grip', ctrl.grip)
            try:
                vao.render(moderngl.TRIANGLES)
            except Exception:
                pass
            return
        model = _make_model_matrix(_xr_controller_to_world(ctrl.pos), _controller_world_quat(ctrl.quat), scale=1.0)
        mv = _mat4_mul(view, model)
        mvp = _mat4_mul(proj, mv)
        rot = _quat_to_mat3(*_controller_world_quat(ctrl.quat))
        nm = (rot[0], rot[3], rot[6], rot[1], rot[4], rot[7], rot[2], rot[5], rot[8])
        self._set('u_mvp', tuple(mvp))
        self._set('u_normal_mat', nm)
        self._set('u_color', color)
        self._set('u_grip', ctrl.grip)
        self._vao.render(moderngl.TRIANGLES)
    def render_hmd(self, proj, view):
        if self._hmd_mesh is None:
            return
        pos = _xr_hmd_to_world()
        quat = _controller_world_quat(_vr_state._hmd_quat)
        model = _make_model_matrix(pos, quat, scale=1.0)
        mv = _mat4_mul(view, model)
        mvp = _mat4_mul(proj, mv)
        rot = _quat_to_mat3(*quat)
        nm = (rot[0], rot[3], rot[6], rot[1], rot[4], rot[7], rot[2], rot[5], rot[8])
        self._set('u_mvp', tuple(mvp))
        self._set('u_normal_mat', nm)
        self._set('u_color', (0.2, 0.2, 0.22))
        self._set('u_grip', 0.0)
        try:
            vbo, ibo, vao, cnt = self._hmd_mesh
            vao.render(moderngl.TRIANGLES)
        except Exception:
            pass
    def render_for_eye(self, eye: dict):
        try:
            if has_vr_rig():
                return
        except Exception:
            pass
        self._gl_clear(0x00000100)
        self._ctx.enable(moderngl.DEPTH_TEST)
        proj = _make_proj_matrix(_vr_state._eye_fovs[eye['eye_idx']], near=0.001, far=50.0)
        view = _make_view_matrix(eye['pos'], eye['fwd'], eye['right'], eye['up'])
        colors = [(0.3, 0.6, 1.0), (1.0, 0.4, 0.3)]
        for i, ctrl in enumerate(_vr_state.controllers):
            self.render_controller(ctrl, proj, view, colors[i], idx=i)
        try:
            self.render_hmd(proj, view)
        except Exception:
            pass
        self._ctx.disable(moderngl.DEPTH_TEST)
    def render_for_desktop(self, view, proj):
        try:
            if has_vr_rig():
                return
        except Exception:
            pass
        self._ctx.enable(moderngl.DEPTH_TEST)
        colors = [(0.3, 0.6, 1.0), (1.0, 0.4, 0.3)]
        for i, ctrl in enumerate(_vr_state.controllers):
            self.render_controller(ctrl, proj, view, colors[i], idx=i)
        try:
            self.render_hmd(proj, view)
        except Exception:
            pass
        self._ctx.disable(moderngl.DEPTH_TEST)
    def release(self):
        try:
            self._vbo.release()
            self._ibo.release()
            self._vao.release()
        except Exception:
            pass
        for m in self._custom:
            if m is not None and isinstance(m, tuple):
                try:
                    m[0].release()
                    m[1].release()
                    m[2].release()
                except Exception:
                    pass
        if self._hmd_mesh is not None and isinstance(self._hmd_mesh, tuple):
            try:
                self._hmd_mesh[0].release()
                self._hmd_mesh[1].release()
                self._hmd_mesh[2].release()
            except Exception:
                pass
        self._prog.release()

def trigger_haptic(side: int, frequency: float = 1.0, amplitude: float = 1.0, duration_s: float = 0.1):
    if not (_XR_AVAILABLE and _vr_state.active and _vr_state._session_running):
        return False
    action = _vr_state._haptic_actions[side] if 0 <= side < 2 else None
    if action is None:
        return False
    try:
        from xr import HapticVibration, HapticActionInfo
        hand_paths = getattr(_vr_state, '_hand_paths', None)
        sub = hand_paths[side] if hand_paths is not None else xr.NULL_PATH
        info = HapticActionInfo(action=action, subaction_path=sub)
        vib = HapticVibration(
            duration=xr.Duration(int(duration_s * 1e9)),
            frequency=frequency,
            amplitude=max(0.0, min(1.0, amplitude)),
        )
        xr.apply_haptic_feedback(_vr_state.session, info, vib)
        return True
    except Exception as e:
        try:
            print(f'[VR] apply_haptic_feedback failed: {e}')
        except Exception:
            pass
        return False

def stop_haptic(side: int):
    if not (_XR_AVAILABLE and _vr_state.active and _vr_state._session_running):
        return
    action = _vr_state._haptic_actions[side] if 0 <= side < 2 else None
    if action is None:
        return
    try:
        from xr import HapticActionInfo
        hand_paths = getattr(_vr_state, '_hand_paths', None)
        sub = hand_paths[side] if hand_paths is not None else xr.NULL_PATH
        info = HapticActionInfo(action=action, subaction_path=sub)
        xr.stop_haptic_feedback(_vr_state.session, info)
    except Exception:
        pass

def set_uniforms_for_eye(set_fn, eye: dict, rw: int, rh: int):
    al, ar, au, ad = eye['fov_angles']
    tl = math.tan(al)
    tr = math.tan(ar)
    tu = math.tan(au)
    td = math.tan(ad)
    cx = (tl + tr) * 0.5
    cy = (tu + td) * 0.5
    hw = (tr - tl) * 0.5
    hh = (tu - td) * 0.5
    r, u, f = eye['right'], eye['up'], eye['fwd']
    fn = f
    flen = math.sqrt(fn[0]*fn[0] + fn[1]*fn[1] + fn[2]*fn[2])
    if flen > 1e-9:
        fn = (fn[0]/flen, fn[1]/flen, fn[2]/flen)
    fa = (fn[0] + cx*r[0] + cy*u[0],
          fn[1] + cx*r[1] + cy*u[1],
          fn[2] + cx*r[2] + cy*u[2])
    aspect = rw / rh if rh else 1.0
    ra = (r[0]*hw/aspect, r[1]*hw/aspect, r[2]*hw/aspect)
    ua = (u[0]*hh, u[1]*hh, u[2]*hh)
    set_fn('u_cam_pos',   eye['pos'])
    set_fn('u_cam_fwd',   fa)
    set_fn('u_cam_right', ra)
    set_fn('u_cam_up',    ua)
    set_fn('u_resolution', (float(rw), float(rh)))
    set_fn('u_fov', 1.0)
