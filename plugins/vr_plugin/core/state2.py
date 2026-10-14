# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import ctypes
try:
    import xr
except ImportError:
    xr = None
from plugins.vr_plugin.core.state import _vr_state, _XR_AVAILABLE, _quat_from_yaw, _quat_mul, _quat_to_mat3, _mat3_mul, _rot_y_mat3, _rot_x_mat3, _rotate_y, _normalize3, _deadzone, _quat_to_fwd, _controller_world_quat, _xr_controller_to_world, _xr_hmd_to_world, _xr_to_world, _world_quat_to_local, GRIP_THRESHOLD, IPD_SCALE, VR_MOVE_SPEED, VR_TURN_SPEED, VR_DEADZONE

def _sync_controller_input():
    if not (_vr_state.active and _vr_state._session_running and _vr_state._action_set is not None):
        return
    hand_paths = getattr(_vr_state, '_hand_paths', None)
    if hand_paths is None:
        hand_paths = [
            xr.string_to_path(_vr_state.instance, '/user/hand/left'),
            xr.string_to_path(_vr_state.instance, '/user/hand/right'),
        ]
    try:
        active_sets = (xr.ActiveActionSet * 1)(
            xr.ActiveActionSet(action_set=_vr_state._action_set, subaction_path=xr.NULL_PATH)
        )
        xr.sync_actions(
            _vr_state.session,
            xr.ActionsSyncInfo(
                count_active_action_sets=1,
                active_action_sets=ctypes.cast(active_sets, ctypes.POINTER(xr.ActiveActionSet)),
            )
        )
    except xr.exception.SessionNotFocused:
        pass
    except Exception as e:
        if not getattr(_vr_state, '_sync_actions_warn', False):
            _vr_state._sync_actions_warn = True
            print(f'[VR] sync_actions exception: {e}')
    for i in range(2):
        ctrl = _vr_state.controllers[i]
        ctrl.valid = False
        if _vr_state._grip_actions[i] is not None:
            try:
                state = xr.get_action_state_float(
                    _vr_state.session,
                    xr.ActionStateGetInfo(
                        action=_vr_state._grip_actions[i],
                        subaction_path=hand_paths[i],
                    ),
                )
                ctrl.grip = float(state.current_state) if state.is_active else 0.0
            except Exception:
                ctrl.grip = 0.0
        if _vr_state._thumbstick_actions[i] is not None:
            try:
                st = xr.get_action_state_vector2f(
                    _vr_state.session,
                    xr.ActionStateGetInfo(
                        action=_vr_state._thumbstick_actions[i],
                        subaction_path=hand_paths[i],
                    ),
                )
                if st.is_active:
                    ctrl.thumbstick = (float(st.current_state.x), float(st.current_state.y))
                else:
                    ctrl.thumbstick = (0.0, 0.0)
            except Exception:
                ctrl.thumbstick = (0.0, 0.0)
        if _vr_state._trigger_actions[i] is not None:
            try:
                ts = xr.get_action_state_float(
                    _vr_state.session,
                    xr.ActionStateGetInfo(
                        action=_vr_state._trigger_actions[i],
                        subaction_path=hand_paths[i],
                    ),
                )
                ctrl.trigger = float(ts.current_state) if ts.is_active else 0.0
            except Exception:
                ctrl.trigger = 0.0
        if _vr_state._pose_spaces[i] is not None:
            try:
                loc = xr.locate_space(
                    _vr_state._pose_spaces[i],
                    _vr_state.space,
                    _vr_state._display_time,
                )
                flags = loc.location_flags
                pos_valid = bool(flags & xr.SpaceLocationFlags.POSITION_VALID_BIT.value)
                ori_valid = bool(flags & xr.SpaceLocationFlags.ORIENTATION_VALID_BIT.value)
                if not (pos_valid and ori_valid) and not getattr(_vr_state, f'_locate_warn_{i}', False):
                    setattr(_vr_state, f'_locate_warn_{i}', True)
                    print(f'[VR] Controller {i} locate_space flags={flags} display_time={_vr_state._display_time} pos_valid={pos_valid} ori_valid={ori_valid}')
                if pos_valid and ori_valid:
                    setattr(_vr_state, f'_locate_warn_{i}', False)
                    p = loc.pose.position
                    o = loc.pose.orientation
                    ctrl.pos = (p.x, p.y, p.z)
                    ctrl.quat = (o.x, o.y, o.z, o.w)
                    ctrl.valid = True
            except Exception as e:
                if not getattr(_vr_state, f'_locate_exc_{i}', False):
                    setattr(_vr_state, f'_locate_exc_{i}', True)
                    print(f'[VR] Controller {i} locate_space exception: {e}')
    _update_ipd_pinch()

def _update_ipd_pinch():
    c0, c1 = _vr_state.controllers[0], _vr_state.controllers[1]
    both_gripped = c0.grip > GRIP_THRESHOLD and c1.grip > GRIP_THRESHOLD
    both_valid = c0.valid and c1.valid
    if both_gripped and both_valid:
        p0, p1 = c0.pos, c1.pos
        dist = math.sqrt(sum((p0[k]-p1[k])**2 for k in range(3)))
        if not _vr_state._ipd_pinch_active:
            _vr_state._ipd_pinch_active = True
            _vr_state._ipd_pinch_dist0 = dist
            _vr_state._ipd_pinch_ipd0 = _vr_state.ipd_override
        else:
            delta = dist - _vr_state._ipd_pinch_dist0
            new_ipd = _vr_state._ipd_pinch_ipd0 + delta * IPD_SCALE
            _vr_state.ipd_override = max(0.010, min(0.200, new_ipd))
    else:
        _vr_state._ipd_pinch_active = False

def get_eye_transforms(*args, **kwargs) -> list[dict]:
    if len(args) == 1 and hasattr(args[0], 'cam_pos'):
        params = args[0]
        cam_pos = params.cam_pos
        cam_yaw = getattr(params, 'cam_yaw', 0.0)
        cam_pitch = getattr(params, 'cam_pitch', 0.0)
    elif len(args) >= 3:
        cam_pos = args[0]
        cam_yaw = args[1]
        cam_pitch = args[2]
        if isinstance(cam_pos, (list, tuple)) and len(cam_pos) == 3:
            cam_pos = tuple(cam_pos)
        else:
            try:
                cam_pos = (cam_pos.x, cam_pos.y, cam_pos.z)
            except Exception:
                cam_pos = tuple(cam_pos)
    elif 'cam_pos' in kwargs:
        cam_pos = kwargs['cam_pos']
        cam_yaw = kwargs.get('cam_yaw', 0.0)
        cam_pitch = kwargs.get('cam_pitch', 0.0)
    else:
        cam_pos = (0.0, 0.0, 0.0)
        cam_yaw = 0.0
        cam_pitch = 0.0
    eyes = []
    p0 = _vr_state._eye_positions[0]
    p1 = _vr_state._eye_positions[1]
    xr_ipd = math.sqrt(sum((p1[k]-p0[k])**2 for k in range(3)))
    use_xr_positions = 0.01 < xr_ipd < 0.12
    if use_xr_positions:
        mid = tuple((p0[k] + p1[k]) * 0.5 for k in range(3))
    hx, hy, hz = _vr_state._hmd_pos_offset
    rig_yaw = getattr(_vr_state, 'rig_yaw', 0.0)
    if _vr_state.active:
        hx, hy, hz = _rotate_y((hx, hy, hz), rig_yaw)
    base_pos = (
        cam_pos[0] + hx,
        cam_pos[1] + hy,
        cam_pos[2] + hz,
    )
    _vr_state._xr_origin = base_pos
    if use_xr_positions:
        xr_ipd_safe = max(xr_ipd, 1e-4)
        _vr_state._xr_mid = mid
        _vr_state._xr_scale = _vr_state.ipd_override / xr_ipd_safe
    else:
        _vr_state._xr_mid = (0.0, 0.0, 0.0)
        _vr_state._xr_scale = 1.0
    for i in range(2):
        if _vr_state.active:
            qx, qy, qz, qw = _vr_state._eye_quats[i]
            rig_q = _quat_from_yaw(rig_yaw)
            qx, qy, qz, qw = _quat_mul(rig_q, (qx, qy, qz, qw))
            rot = _quat_to_mat3(qx, qy, qz, qw)
            r = ( rot[0],  rot[3],  rot[6])
            u = ( rot[1],  rot[4],  rot[7])
            f = (-rot[2], -rot[5], -rot[8])
            if use_xr_positions:
                exi, eyi, ezi = _vr_state._eye_positions[i]
                dx = exi - mid[0]
                dy = eyi - mid[1]
                dz = ezi - mid[2]
                if rig_yaw != 0.0:
                    dx, dy, dz = _rotate_y((dx, dy, dz), rig_yaw)
                ipd_scale = _vr_state.ipd_override / max(xr_ipd, 1e-4)
                ep = (
                    base_pos[0] + dx * ipd_scale,
                    base_pos[1] + dy * ipd_scale,
                    base_pos[2] + dz * ipd_scale,
                )
            else:
                sign = -0.5 if i == 0 else 0.5
                half_ipd = _vr_state.ipd_override * sign
                ep = (
                    base_pos[0] + r[0]*half_ipd,
                    base_pos[1] + r[1]*half_ipd,
                    base_pos[2] + r[2]*half_ipd,
                )
        else:
            yaw, pitch = cam_yaw, cam_pitch
            bf = (math.cos(pitch)*math.sin(yaw), math.sin(pitch), -math.cos(pitch)*math.cos(yaw))
            brx, brz = -bf[2], bf[0]
            rlen = math.sqrt(brx**2 + brz**2) or 1.0
            br = (brx/rlen, 0.0, brz/rlen)
            bu = (br[1]*bf[2]-br[2]*bf[1], br[2]*bf[0]-br[0]*bf[2], br[0]*bf[1]-br[1]*bf[0])
            ulen = math.sqrt(sum(v*v for v in bu)) or 1.0
            bu = tuple(v/ulen for v in bu)
            sign = -0.5 if i == 0 else 0.5
            half_ipd = _vr_state.ipd_override * sign
            ep = (
                base_pos[0] + br[0]*half_ipd,
                base_pos[1] + br[1]*half_ipd,
                base_pos[2] + br[2]*half_ipd,
            )
            rot = _mat3_mul(_rot_y_mat3(yaw), _rot_x_mat3(pitch))
            r = (rot[0], rot[3], rot[6])
            u = (rot[1], rot[4], rot[7])
            f = (rot[2], rot[5], rot[8])
        eyes.append({
            'pos': ep,
            'fwd':   f,
            'right': r,
            'up':    u,
            'fov_angles': _vr_state._eye_fovs[i],
            'eye_idx': i,
        })
    return eyes

def get_controller_world_pos(i: int):
    if 0 <= i < 2:
        c = _vr_state.controllers[i]
        if c.valid:
            return _xr_controller_to_world(c.pos)
    return None

def get_controller_world_quat(i: int):
    if 0 <= i < 2:
        c = _vr_state.controllers[i]
        if c.valid:
            return _controller_world_quat(c.quat)
    return (0.0, 0.0, 0.0, 1.0)

def get_controller_ray(i: int):
    c = _vr_state.controllers[i]
    if not c.valid:
        return None
    origin = _xr_controller_to_world(c.pos)
    q = _controller_world_quat(c.quat)
    fwd = _quat_to_fwd(*q)
    return (origin, fwd)

def get_hmd_world_pos():
    return _xr_hmd_to_world()

def get_hmd_world_quat():
    return _controller_world_quat(_vr_state._hmd_quat)

def update_vr_locomotion(cam, dt: float):
    if not (_vr_state.active and _vr_state._session_running):
        return
    left = _vr_state.controllers[0]
    right = _vr_state.controllers[1]
    lx, ly = left.thumbstick
    rx, ry = right.thumbstick
    lx = _deadzone(lx)
    ly = _deadzone(ly)
    rx = _deadzone(rx)
    ry = _deadzone(ry)
    hmd_q = _controller_world_quat(_vr_state._hmd_quat)
    hmd_fwd = _quat_to_fwd(*hmd_q)
    fwd_h = (hmd_fwd[0], 0.0, hmd_fwd[2])
    flen = math.sqrt(fwd_h[0]*fwd_h[0] + fwd_h[2]*fwd_h[2])
    if flen > 1e-6:
        fwd_h = (fwd_h[0]/flen, 0.0, fwd_h[2]/flen)
    else:
        yr = math.radians(getattr(cam, '_yaw', 0.0))
        fwd_h = (math.sin(yr), 0.0, -math.cos(yr))
        flen = math.sqrt(fwd_h[0]*fwd_h[0] + fwd_h[2]*fwd_h[2])
        if flen > 1e-6:
            fwd_h = (fwd_h[0]/flen, 0.0, fwd_h[2]/flen)
        else:
            fwd_h = (0.0, 0.0, -1.0)
    right_v = (-fwd_h[2], 0.0, fwd_h[0])
    rlen = math.sqrt(right_v[0]*right_v[0] + right_v[2]*right_v[2])
    if rlen > 1e-6:
        right_v = (right_v[0]/rlen, 0.0, right_v[2]/rlen)
    speed = float(getattr(cam, '_move_speed', VR_MOVE_SPEED))
    try:
        accel_factor = float(getattr(cam, '_acceleration', 12.0))
    except Exception:
        accel_factor = 12.0
    desired_x = 0.0
    desired_z = 0.0
    desired_y = 0.0
    if abs(lx) > 1e-6 or abs(ly) > 1e-6:
        desired_x = (right_v[0]*lx + fwd_h[0]*ly) * speed
        desired_z = (right_v[2]*lx + fwd_h[2]*ly) * speed
    if abs(ry) > 1e-6:
        desired_y = ry * speed
    rvx, rvy, rvz = _vr_state.rig_vel
    lerp = min(1.0, dt * accel_factor)
    rvx += (desired_x - rvx) * lerp
    rvz += (desired_z - rvz) * lerp
    rvy += (desired_y - rvy) * lerp
    if abs(desired_x) < 1e-6 and abs(desired_z) < 1e-6 and abs(desired_y) < 1e-6:
        damp = math.exp(-8.0 * dt)
        try:
            dval = float(getattr(cam, '_damping', 8.0))
            damp = math.exp(-dval * dt)
        except Exception:
            pass
        rvx *= damp
        rvy *= damp
        rvz *= damp
        if abs(rvx) < 0.001 and abs(rvy) < 0.001 and abs(rvz) < 0.001:
            rvx = 0.0
            rvy = 0.0
            rvz = 0.0
    _vr_state.rig_vel = (rvx, rvy, rvz)
    rig_moved = False
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng and eng.scene:
                for e in eng.scene.get_all_entities():
                    from plugins.vr_plugin.components.xr_rig import XRRig
                    vr_comp = e.get_component(XRRig)
                    if vr_comp is not None:
                        tr = e.transform
                        if tr:
                            tr.position = tr.position + __import__('core.maths.math3d', fromlist=['Vec3']).Vec3(rvx * dt, rvy * dt, rvz * dt)
                            vr_comp.rig_yaw = _vr_state.rig_yaw
                            vr_comp.velocity = __import__('core.maths.math3d', fromlist=['Vec3']).Vec3(rvx, rvy, rvz)
                        rig_moved = True
                    break
    except Exception:
        pass
    if not rig_moved:
        cam._position.x += rvx * dt
        cam._position.y += rvy * dt
        cam._position.z += rvz * dt
    try:
        cam._vel.x = rvx
        cam._vel.y = rvy
        cam._vel.z = rvz
    except Exception:
        pass
    if abs(rx) > 1e-6:
        delta = rx * math.degrees(VR_TURN_SPEED) * dt
        cam._yaw -= delta
        _vr_state.rig_yaw -= math.radians(delta)
        if cam._yaw > 180.0:
            cam._yaw -= 360.0
        if cam._yaw < -180.0:
            cam._yaw += 360.0
        if _vr_state.rig_yaw > math.pi:
            _vr_state.rig_yaw -= 2*math.pi
        if _vr_state.rig_yaw < -math.pi:
            _vr_state.rig_yaw += 2*math.pi
        try:
            from core.engine.eng import Engine
            eng2 = Engine.instance()
            if eng2 and eng2.scene:
                for e2 in eng2.scene.get_all_entities():
                    from plugins.vr_plugin.components.xr_rig import XRRig
                    vr2 = e2.get_component(XRRig)
                    if vr2 is not None:
                        tr2 = e2.transform
                        if tr2:
                            try:
                                tr2.local_euler_angles = __import__('core.maths.math3d', fromlist=['Vec3']).Vec3(0, math.degrees(_vr_state.rig_yaw), 0)
                            except Exception:
                                tr2.local_rotation = __import__('core.maths.math3d', fromlist=['Quat']).Quat.from_euler(0, _vr_state.rig_yaw, 0)
                            vr2.rig_yaw = _vr_state.rig_yaw
                        break
        except Exception:
            pass

def _sync_ar_session(sc):
    from plugins.vr_plugin.core.swapchain import is_ar_mode, enable_ar, disable_ar, _ensure_ar_floor_plane
    from plugins.vr_plugin.components.xr_ar import ARSession
    sess = None
    for e in sc.get_all_entities():
        s = e.get_component(ARSession)
        if s is not None:
            sess = s
            break
    if sess is not None and sess.enabled:
        if not is_ar_mode():
            enable_ar(floor_y=sess.floor_y)
        else:
            _vr_state._ar_floor_y = sess.floor_y
        _ensure_ar_floor_plane()
    else:
        if is_ar_mode():
            disable_ar()
