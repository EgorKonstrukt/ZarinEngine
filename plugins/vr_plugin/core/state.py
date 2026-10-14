# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import ctypes
from pathlib import Path
try:
    import xr
    _XR_AVAILABLE = True
except ImportError:
    _XR_AVAILABLE = False

_SHADER_DIR = Path(__file__).parent.parent
EYE_LEFT = 0
EYE_RIGHT = 1
IPD_DEFAULT = 0.063
FOV_VERT_DEFAULT = math.radians(90.0)
FOV_HORIZ_DEFAULT = math.radians(100.0)
EYE_TEX_W = 1440
EYE_TEX_H = 1600
GL_RGBA8 = 0x8058
GL_SRGB8_ALPHA8 = 0x8C43
GRIP_THRESHOLD = 0.5
IPD_SCALE = 0.5
VR_MOVE_SPEED = 3.0
VR_TURN_SPEED = math.radians(90.0)
VR_VERT_SPEED = 2.5
VR_DEADZONE = 0.20
TRIGGER_THRESHOLD = 0.6
RAY_MAX_DIST = 50.0
_gl = None
GL_DRAW_FRAMEBUFFER = 0x8CA9
GL_READ_FRAMEBUFFER = 0x8CA8
GL_FRAMEBUFFER = 0x8D40
GL_COLOR_ATTACHMENT0 = 0x8CE0
GL_TEXTURE_2D = 0x0DE1
GL_COLOR_BUFFER_BIT = 0x4000
GL_NEAREST = 0x2600
GL_FRAMEBUFFER_COMPLETE = 0x8CD5
_BLIT_FBO_IDS = None

def _quat_to_mat3(qx, qy, qz, qw):
    x2, y2, z2 = qx * 2, qy * 2, qz * 2
    xx, yy, zz = qx * x2, qy * y2, qz * z2
    xy, xz, yz = qx * y2, qx * z2, qy * z2
    wx, wy, wz = qw * x2, qw * y2, qw * z2
    return (1-(yy+zz), xy-wz, xz+wy, xy+wz, 1-(xx+zz), yz-wx, xz-wy, yz+wx, 1-(xx+yy))

def _quat_to_fwd(qx, qy, qz, qw):
    m = _quat_to_mat3(qx, qy, qz, qw)
    return _normalize3((-m[2], -m[5], -m[8]))

def _fov_to_tangents(al, ar, au, ad):
    return (math.tan(al), math.tan(ar), math.tan(au), math.tan(ad))

def _mat3_mul(a, b):
    result = []
    for r in range(3):
        for c in range(3):
            val = sum(a[r*3+k] * b[k*3+c] for k in range(3))
            result.append(val)
    return tuple(result)

def _rot_y_mat3(a):
    c, s = math.cos(a), math.sin(a)
    return (c, 0, s, 0, 1, 0, -s, 0, c)

def _rot_x_mat3(a):
    c, s = math.cos(a), math.sin(a)
    return (1, 0, 0, 0, c, -s, 0, s, c)

def _normalize3(v):
    l = math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])
    if l < 1e-9:
        return (0.0, 0.0, 1.0)
    return (v[0]/l, v[1]/l, v[2]/l)

def _quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by, aw*by - ax*bz + ay*bw + az*bx, aw*bz + ax*by - ay*bx + az*bw, aw*bw - ax*bx - ay*by - az*bz)

def _quat_from_yaw(yaw):
    h = yaw * 0.5
    return (0.0, math.sin(h), 0.0, math.cos(h))

def _rotate_y(v, yaw):
    c = math.cos(yaw)
    s = math.sin(yaw)
    x, y, z = v
    return (x*c + z*s, y, -x*s + z*c)

def _deadzone(v, dz=VR_DEADZONE):
    if abs(v) < dz:
        return 0.0
    s = (abs(v)-dz)/(1.0-dz)
    return math.copysign(s, v)

class VRState:
    IPD = IPD_DEFAULT
    EYE_TEX_W = EYE_TEX_W
    EYE_TEX_H = EYE_TEX_H
    def __init__(self):
        self.active = False
        self.session = None
        self.instance = None
        self.system_id = None
        self.space = None
        self._hmd_quat = (0.0, 0.0, 0.0, 1.0)
        self._hmd_pos = (0.0, 0.0, 0.0)
        self._eye_fovs = [
            (-FOV_HORIZ_DEFAULT*0.5, FOV_HORIZ_DEFAULT*0.5, FOV_VERT_DEFAULT*0.5, -FOV_VERT_DEFAULT*0.5),
            (-FOV_HORIZ_DEFAULT*0.5, FOV_HORIZ_DEFAULT*0.5, FOV_VERT_DEFAULT*0.5, -FOV_VERT_DEFAULT*0.5),
        ]
        self._eye_offsets = [(-self.IPD*0.5, 0.0, 0.0), (self.IPD*0.5, 0.0, 0.0)]
        self._eye_poses = [None, None]
        self._eye_positions = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
        self._eye_quats = [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0)]
        self._session_running = False
        self._frame_state = None
        self._frame_begun = False
        self._frame_discard = False
        self._swapchains: list = []
        self._display_time = 0
        self._binding = None
        self._hmd_pos_offset = (0.0, 0.0, 0.0)
        self._hmd_pos_origin = None
        self.controllers = [ControllerState(), ControllerState()]
        self._action_set = None
        self._grip_actions = [None, None]
        self._pose_actions = [None, None]
        self._pose_spaces = [None, None]
        self._thumbstick_actions = [None, None]
        self._trigger_actions = [None, None]
        self._ipd_pinch_active = False
        self._ipd_pinch_dist0 = 0.0
        self._ipd_pinch_ipd0 = IPD_DEFAULT
        self.ipd_override = IPD_DEFAULT
        self._xr_origin = (0.0, 0.0, 0.0)
        self._xr_mid = (0.0, 0.0, 0.0)
        self._xr_scale = 1.0
        self._frames_rendered = 0
        self._ever_running = False
        self.eye_view_enabled = True
        self._prev_trigger = [False, False]
        self.rig_yaw = 0.0
        self.rig_vel = (0.0, 0.0, 0.0)
        self._haptic_actions = [None, None]
        self._ar_enabled = False
        self._ar_planes = []
        self._ar_anchors = []
        self._ar_point_cloud = None
        self._ar_supports_passthrough = False
        self._ar_floor_y = 0.0

class ControllerState:
    def __init__(self):
        self.pos = (0.0, 0.0, 0.0)
        self.quat = (0.0, 0.0, 0.0, 1.0)
        self.grip = 0.0
        self.trigger = 0.0
        self.thumbstick = (0.0, 0.0)
        self.valid = False
        self._prev_trigger = False


class _VRParams:
    def __init__(self, cam_pos, cam_yaw, cam_pitch):
        self.cam_pos = cam_pos
        self.cam_yaw = cam_yaw
        self.cam_pitch = cam_pitch

def _make_perspective_flat(fov_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov_deg)*0.5)
    return [f/aspect, 0.0, 0.0, 0.0, 0.0, f, 0.0, 0.0, 0.0, 0.0, -(far+near)/(far-near), -1.0, 0.0, 0.0, -(2.0*far*near)/(far-near), 0.0]

_vr_state = VRState()

def _load_gl_funcs():
    global _gl
    if _gl is not None:
        return _gl
    lib = ctypes.windll.opengl32
    def _get(name, restype, *argtypes):
        ptr = lib.wglGetProcAddress(name.encode())
        if not ptr:
            raise RuntimeError(f'wglGetProcAddress({name}) returned NULL')
        return ctypes.WINFUNCTYPE(restype, *argtypes)(ptr)
    _gl = type('GL', (), {
        'GenFramebuffers':      _get('glGenFramebuffers',      None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
        'DeleteFramebuffers':   _get('glDeleteFramebuffers',   None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
        'BindFramebuffer':      _get('glBindFramebuffer',      None, ctypes.c_uint, ctypes.c_uint),
        'FramebufferTexture2D': _get('glFramebufferTexture2D', None, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int),
        'BlitFramebuffer':      _get('glBlitFramebuffer',      None, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint),
        'CheckFramebufferStatus': _get('glCheckFramebufferStatus', ctypes.c_uint, ctypes.c_uint),
        'DrawBuffer':           ctypes.WINFUNCTYPE(None, ctypes.c_uint)(ctypes.cast(lib.glDrawBuffer, ctypes.c_void_p).value),
        'ReadBuffer':           ctypes.WINFUNCTYPE(None, ctypes.c_uint)(ctypes.cast(lib.glReadBuffer, ctypes.c_void_p).value),
    })()
    return _gl

def _get_blit_fbo_id(gl, idx):
    global _BLIT_FBO_IDS
    if _BLIT_FBO_IDS is None:
        arr = (ctypes.c_uint * 2)(0, 0)
        gl.GenFramebuffers(2, arr)
        _BLIT_FBO_IDS = arr
    return int(_BLIT_FBO_IDS[idx])

def _free_blit_fbos():
    global _BLIT_FBO_IDS
    if _BLIT_FBO_IDS is not None:
        try:
            gl = _load_gl_funcs()
            gl.DeleteFramebuffers(2, _BLIT_FBO_IDS)
        except Exception:
            pass
        _BLIT_FBO_IDS = None

def is_available() -> bool:
    return _XR_AVAILABLE

def is_active() -> bool:
    return _vr_state.active

def is_eye_view() -> bool:
    return _vr_state.eye_view_enabled

def set_eye_view(v: bool):
    _vr_state.eye_view_enabled = bool(v)

def toggle_eye_view() -> bool:
    _vr_state.eye_view_enabled = not _vr_state.eye_view_enabled
    return _vr_state.eye_view_enabled

def has_vr_rig():
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng and eng.scene:
            for e in eng.scene.get_all_entities():
                from plugins.vr_plugin.components.xr_rig import XRRig
                if e.get_component(XRRig):
                    return True
    except Exception:
        pass
    return False

def _xr_to_world(xr_pos: tuple) -> tuple:
    ox, oy, oz = _vr_state._xr_origin
    mx, my, mz = _vr_state._xr_mid
    s = _vr_state._xr_scale
    dx = (xr_pos[0] - mx) * s
    dy = (xr_pos[1] - my) * s
    dz = (xr_pos[2] - mz) * s
    rig_yaw = getattr(_vr_state, 'rig_yaw', 0.0)
    if rig_yaw != 0.0 and _vr_state.active:
        dx, dy, dz = _rotate_y((dx, dy, dz), rig_yaw)
        pass
    return (
        ox + dx,
        oy + dy,
        oz + dz,
    )

def _xr_controller_to_world(xr_pos: tuple) -> tuple:
    rig_yaw = getattr(_vr_state, 'rig_yaw', 0.0)
    if _vr_state._hmd_pos_origin is not None and _vr_state.active:
        ox0, oy0, oz0 = _vr_state._hmd_pos_origin
        dx = xr_pos[0] - ox0
        dy = xr_pos[1] - oy0
        dz = xr_pos[2] - oz0
        if rig_yaw != 0.0:
            dx, dy, dz = _rotate_y((dx, dy, dz), rig_yaw)
        cam_pos = _vr_state._xr_origin
        hx, hy, hz = _vr_state._hmd_pos_offset
        if _vr_state.active:
            hx, hy, hz = _rotate_y((hx, hy, hz), rig_yaw)
        base_x = cam_pos[0] - hx
        base_y = cam_pos[1] - hy
        base_z = cam_pos[2] - hz
        return (
            base_x + dx,
            base_y + dy,
            base_z + dz,
        )
    ox, oy, oz = _vr_state._xr_origin
    mx, my, mz = _vr_state._xr_mid
    dx = xr_pos[0] - mx
    dy = xr_pos[1] - my
    dz = xr_pos[2] - mz
    if rig_yaw != 0.0 and _vr_state.active:
        dx, dy, dz = _rotate_y((dx, dy, dz), rig_yaw)
    return (
        ox + dx,
        oy + dy,
        oz + dz,
    )

def _xr_hmd_to_world() -> tuple:
    return _vr_state._xr_origin

def _controller_world_quat(q):
    rig_yaw = getattr(_vr_state, 'rig_yaw', 0.0)
    if rig_yaw != 0.0 and _vr_state.active:
        rig_q = _quat_from_yaw(rig_yaw)
        return _quat_mul(rig_q, q)
    return q

def _world_quat_to_local(e, wq):
    parent_ent = getattr(e, 'parent', None)
    if parent_ent is None:
        return wq
    pt = parent_ent.transform
    if pt is None:
        return wq
    try:
        pq = pt.world_matrix.decompose()[1]
    except Exception:
        return wq
    return (pq.conjugate().normalized() * wq).normalized()

def _make_proj_matrix(fov_angles, near=0.01, far=100.0):
    al, ar, au, ad = fov_angles
    tl, tr, tu, td = math.tan(al), math.tan(ar), math.tan(au), math.tan(ad)
    r_m_l = tr - tl
    t_m_b = tu - td
    r_p_l = tr + tl
    t_p_b = tu + td
    m = [0.0]*16
    m[0]  =  2.0 / r_m_l
    m[5]  =  2.0 / t_m_b
    m[8]  =  r_p_l / r_m_l
    m[9]  =  t_p_b / t_m_b
    m[10] = -(far + near) / (far - near)
    m[11] = -1.0
    m[14] = -(2.0 * far * near) / (far - near)
    return m

def _make_view_matrix(eye_pos, fwd, right, up):
    rx, ry, rz = right
    ux, uy, uz = up
    fx, fy, fz = fwd
    ex, ey, ez = eye_pos
    tx = -(rx*ex + ry*ey + rz*ez)
    ty = -(ux*ex + uy*ey + uz*ez)
    tz =  (fx*ex + fy*ey + fz*ez)
    return [
        rx,  ry,  rz, 0.0,
        ux,  uy,  uz, 0.0,
       -fx, -fy, -fz, 0.0,
        tx,  ty,  tz, 1.0,
    ]

def _mat4_mul(a, b):
    result = [0.0]*16
    for row in range(4):
        for col in range(4):
            s = 0.0
            for k in range(4):
                s += a[row + k*4] * b[k + col*4]
            result[row + col*4] = s
    return result

def _make_model_matrix(pos, quat, scale=1.0):
    rot = _quat_to_mat3(*quat)
    s = scale
    return [
        rot[0]*s, rot[3]*s, rot[6]*s, 0.0,
        rot[1]*s, rot[4]*s, rot[7]*s, 0.0,
        rot[2]*s, rot[5]*s, rot[8]*s, 0.0,
        pos[0],   pos[1],   pos[2],   1.0,
    ]
