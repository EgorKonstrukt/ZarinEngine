# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import ctypes
import moderngl
try:
    import xr
except ImportError:
    xr = None
from plugins.vr_plugin.core.state import _vr_state, _XR_AVAILABLE, _VRParams, _world_quat_to_local, is_active
from plugins.vr_plugin.core.state2 import _sync_controller_input, get_eye_transforms, update_vr_locomotion, _sync_ar_session, get_controller_world_pos, get_controller_world_quat, get_hmd_world_pos, get_hmd_world_quat
from plugins.vr_plugin.core.swapchain import VRRenderer, handle_trigger_selection, session_running, get_ipd, get_ar_blend_mode
from plugins.vr_plugin.core.session import _create_swapchains, initialize, shutdown

def update_vr_entities(vp, dt: float):
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng is None or eng.scene is None:
            return
        sc = eng.scene
        active = is_active() and session_running()
        if active:
            try:
                sync_hmd_pose()
            except Exception:
                pass
            try:
                update_vr_locomotion(vp._cam, dt)
            except Exception:
                pass
            try:
                from plugins.vr_plugin.components.xr_locomotion import apply_locomotion_providers
                apply_locomotion_providers(sc, dt)
            except Exception:
                pass
        rig_pos = (0.0, 0.0, 0.0)
        rig_yaw = 0.0
        from plugins.vr_plugin.components.xr_rig import XRRig
        for e in sc.get_all_entities():
            rc = e.get_component(XRRig)
            if rc is not None:
                t = e.transform
                if t is not None:
                    wp = t.position
                    rig_pos = (wp.x, wp.y, wp.z)
                    rig_yaw = rc.rig_yaw
                break
        try:
            params = _VRParams(rig_pos, rig_yaw, 0.0)
            get_eye_transforms(params)
        except Exception:
            pass
        Vec3 = __import__('core.maths.math3d', fromlist=['Vec3']).Vec3
        Quat = __import__('core.maths.math3d', fromlist=['Quat']).Quat
        from plugins.vr_plugin.components.xr_rig import XRTrackedPoseDriver, XRController, XRHand
        for e in sc.get_all_entities():
            if not e.active:
                continue
            tpd = e.get_component(XRTrackedPoseDriver)
            if tpd is not None:
                _drive_xr_tracked_pose(e, tpd, active, Vec3, Quat)
            xrc = e.get_component(XRController)
            if xrc is not None:
                _drive_xr_controller(e, xrc, active, Vec3, Quat)
            xrh = e.get_component(XRHand)
            if xrh is not None:
                _drive_xr_hand(e, xrh, active, Vec3, Quat)
        if active:
            try:
                from plugins.vr_plugin.components.xrinter import XRInteractionManager
                mgr = None
                for e in sc.get_all_entities():
                    m = e.get_component(XRInteractionManager)
                    if m is not None:
                        mgr = m
                        break
                if mgr is not None and mgr.enabled:
                    from plugins.vr_plugin.components.xrinter import update_interaction
                    update_interaction(sc, dt, mgr)
            except Exception:
                pass
        try:
            _sync_ar_session(sc)
        except Exception:
            pass
        if active:
            try:
                handle_trigger_selection(vp)
            except Exception:
                pass
    except Exception:
        pass

def _drive_xr_tracked_pose(e, tpd, active, Vec3, Quat):
    tr = e.transform
    if tr is None:
        return
    pt = tpd.pose_type
    p = None
    q = None
    if pt in ("Head", "Center"):
        p = get_hmd_world_pos() if active else (0.0, 1.6, 0.0)
        q = get_hmd_world_quat() if active else (0.0, 0.0, 0.0, 1.0)
    elif pt == "LeftHand":
        p = get_controller_world_pos(0) if active else (-0.25, 1.2, -0.2)
        q = get_controller_world_quat(0) if active else (0.0, 0.0, 0.0, 1.0)
    elif pt == "RightHand":
        p = get_controller_world_pos(1) if active else (0.25, 1.2, -0.2)
        q = get_controller_world_quat(1) if active else (0.0, 0.0, 0.0, 1.0)
    elif pt in ("LeftEye", "RightEye"):
        hp = get_hmd_world_pos() if active else (0.0, 1.6, 0.0)
        hq = get_hmd_world_quat() if active else (0.0, 0.0, 0.0, 1.0)
        if hp is not None:
            ipd = 0.064
            try:
                ipd = get_ipd()
            except Exception:
                pass
            hq = hq or (0.0, 0.0, 0.0, 1.0)
            hmd_q = Quat(hq[0], hq[1], hq[2], hq[3])
            right = hmd_q * Vec3(1.0, 0.0, 0.0)
            side = -1.0 if pt == "LeftEye" else 1.0
            p = (hp[0] + right.x * ipd * 0.5 * side, hp[1] + right.y * ipd * 0.5 * side, hp[2] + right.z * ipd * 0.5 * side)
            q = hq
    if p is not None:
        if active:
            tr.position = Vec3(p[0], p[1], p[2])
        else:
            if e.parent is not None:
                tr.local_position = Vec3(p[0], p[1], p[2])
            else:
                tr.position = Vec3(p[0], p[1], p[2])
    if q is not None:
        lq = Quat(q[0], q[1], q[2], q[3])
        if active:
            lq = _world_quat_to_local(e, lq)
        tr.local_rotation = lq

def _drive_xr_controller(e, xrc, active, Vec3, Quat):
    tr = e.transform
    if tr is None:
        return
    idx = 0 if xrc.controller_hand == "Left" else 1
    p = get_controller_world_pos(idx) if active else (xrc.controller_hand == "Left" and -0.25 or 0.25, 1.2, -0.2)
    q = get_controller_world_quat(idx) if active else (0.0, 0.0, 0.0, 1.0)
    if p is not None:
        if active:
            tr.position = Vec3(p[0], p[1], p[2])
        else:
            if e.parent is not None:
                tr.local_position = Vec3(p[0], p[1], p[2])
            else:
                tr.position = Vec3(p[0], p[1], p[2])
    if q is not None:
        lq = Quat(q[0], q[1], q[2], q[3])
        if active:
            lq = _world_quat_to_local(e, lq)
        tr.local_rotation = lq
    cs = _vr_state.controllers[idx]
    xrc.trigger = getattr(cs, 'trigger', 0.0)
    xrc.grip = getattr(cs, 'grip', 0.0)
    xrc.thumbstick = getattr(cs, 'thumbstick', (0.0, 0.0))
    xrc.primary_button = getattr(cs, 'primary_button', False)
    xrc.secondary_button = getattr(cs, 'secondary_button', False)
    if xrc._model_entity is None or getattr(xrc, '_current_model', None) != xrc.model:
        xrc.set_model(xrc.model)

def _drive_xr_hand(e, xrh, active, Vec3, Quat):
    tr = e.transform
    if tr is None:
        return
    idx = 0 if xrh.hand == "Left" else 1
    p = get_controller_world_pos(idx) if active else (xrh.hand == "Left" and -0.25 or 0.25, 1.2, -0.2)
    q = get_controller_world_quat(idx) if active else (0.0, 0.0, 0.0, 1.0)
    if p is not None:
        if active:
            tr.position = Vec3(p[0], p[1], p[2])
        else:
            if e.parent is not None:
                tr.local_position = Vec3(p[0], p[1], p[2])
            else:
                tr.position = Vec3(p[0], p[1], p[2])
    if q is not None:
        lq = Quat(q[0], q[1], q[2], q[3])
        if active:
            lq = _world_quat_to_local(e, lq)
        tr.local_rotation = lq
    cs = _vr_state.controllers[idx]
    xrh.index_curl = getattr(cs, 'trigger', 0.0)
    xrh.grip_curl = getattr(cs, 'grip', 0.0)
    xrh.thumbs_up = 1.0 - getattr(cs, 'grip', 0.0)

class VRToggleState:
    def __init__(self):
        self.enabled = False
        self.renderer: VRRenderer | None = None
        self._ctx: moderngl.Context | None = None
    def toggle(self, ctx: moderngl.Context) -> bool:
        if self.enabled:
            self._disable()
        else:
            self._enable(ctx)
        return self.enabled
    def _enable(self, ctx: moderngl.Context):
        self._ctx = ctx
        if initialize(ctx):
            self.enabled = True
            print('[VR] VR mode enabled.')
        else:
            self.enabled = False
            print('[VR] VR initialization failed.')
    def _disable(self):
        if self.renderer is not None:
            self.renderer.release()
            self.renderer = None
        if _XR_AVAILABLE:
            shutdown()
        self.enabled = False
        print('[VR] VR mode disabled.')

_vr_toggle = VRToggleState()

def toggle_vr(ctx: moderngl.Context) -> bool:
    return _vr_toggle.toggle(ctx)

def vr_enabled() -> bool:
    return _vr_toggle.enabled or _vr_state.active

def get_renderer() -> VRRenderer | None:
    return _vr_toggle.renderer

def poll_xr_events():
    if not (_XR_AVAILABLE and _vr_state.active and _vr_state.instance):
        return
    try:
        while True:
            try:
                event = xr.poll_event(_vr_state.instance)
            except xr.EventUnavailable:
                break
            if event.type == xr.StructureType.EVENT_DATA_SESSION_STATE_CHANGED:
                try:
                    if isinstance(event, xr.EventDataSessionStateChanged):
                        ev = event
                    else:
                        ev = ctypes.cast(
                            ctypes.addressof(event),
                            ctypes.POINTER(xr.EventDataSessionStateChanged)
                        ).contents
                except Exception:
                    ev = ctypes.cast(
                        ctypes.addressof(event),
                        ctypes.POINTER(xr.EventDataSessionStateChanged)
                    ).contents
                if ev.state == xr.SessionState.READY and not _vr_state._session_running:
                    try:
                        xr.begin_session(
                            _vr_state.session,
                            xr.SessionBeginInfo(primary_view_configuration_type=xr.ViewConfigurationType.PRIMARY_STEREO)
                        )
                        _vr_state._session_running = True
                        _vr_state._ever_running = True
                        _create_swapchains()
                        ctx_for_renderer = _vr_toggle._ctx
                        if ctx_for_renderer is None:
                            try:
                                import moderngl
                                ctx_for_renderer = moderngl.create_context(standalone=False)
                            except Exception:
                                ctx_for_renderer = None
                        if ctx_for_renderer is not None:
                            if _vr_toggle.renderer is not None:
                                try:
                                    _vr_toggle.renderer.release()
                                except Exception:
                                    pass
                                _vr_toggle.renderer = None
                            try:
                                _vr_toggle.renderer = VRRenderer(ctx_for_renderer)
                                _vr_toggle._ctx = ctx_for_renderer
                            except Exception as e:
                                print(f'[VR] VRRenderer creation failed: {e}')
                        print('[VR] Session started, swapchains ready.')
                    except Exception as e:
                        print(f'[VR] begin_session failed: {e}')
                elif ev.state in (xr.SessionState.STOPPING, xr.SessionState.EXITING) and _vr_state._session_running:
                    try:
                        end_xr_frame()
                    except Exception:
                        pass
                    try:
                        xr.end_session(_vr_state.session)
                    except Exception:
                        pass
                    _vr_state._session_running = False
                    _vr_state._frame_begun = False
                    _vr_state._frame_discard = False
                    _vr_state._frame_state = None
                    for p_i in range(2):
                        _vr_state._eye_poses[p_i] = None
    except Exception as e:
        print(f'[VR] poll_xr_events error: {e}')

def sync_hmd_pose():
    if not (_XR_AVAILABLE and _vr_state.active and _vr_state._session_running):
        return False
    try:
        frame_state = xr.wait_frame(_vr_state.session, xr.FrameWaitInfo())
    except Exception as e:
        print(f'[VR] wait_frame error: {e}')
        _vr_state._frame_state = None
        _vr_state._frame_begun = False
        _vr_state._frame_discard = False
        return False
    _vr_state._frame_state = frame_state
    _vr_state._display_time = frame_state.predicted_display_time
    try:
        xr.begin_frame(_vr_state.session, xr.FrameBeginInfo())
        _vr_state._frame_discard = False
    except Exception as e:
        _vr_state._frame_discard = True
        print(f'[VR] begin_frame discarded: {e}')
    _vr_state._frame_begun = True
    try:
        _, views = xr.locate_views(_vr_state.session, xr.ViewLocateInfo(
            view_configuration_type=xr.ViewConfigurationType.PRIMARY_STEREO,
            display_time=frame_state.predicted_display_time,
            space=_vr_state.space
        ))
        for i, view in enumerate(views[:2]):
            p, o, f = view.pose.position, view.pose.orientation, view.fov
            _vr_state._eye_positions[i] = (p.x, p.y, p.z)
            _vr_state._eye_quats[i] = (o.x, o.y, o.z, o.w)
            _vr_state._hmd_pos = _vr_state._eye_positions[0]
            _vr_state._hmd_quat = _vr_state._eye_quats[0]
            _vr_state._eye_fovs[i] = (f.angle_left, f.angle_right, f.angle_up, f.angle_down)
            _vr_state._eye_poses[i] = view.pose
        p0 = _vr_state._eye_positions[0]
        p1 = _vr_state._eye_positions[1]
        mid_pos = ((p0[0]+p1[0])*0.5, (p0[1]+p1[1])*0.5, (p0[2]+p1[2])*0.5)
        if _vr_state._hmd_pos_origin is None:
            _vr_state._hmd_pos_origin = (mid_pos[0], mid_pos[1] - 1.6, mid_pos[2])
        ox, oy, oz = _vr_state._hmd_pos_origin
        _vr_state._hmd_pos_offset = (mid_pos[0]-ox, mid_pos[1]-oy, mid_pos[2]-oz)
        _sync_controller_input()
        return True
    except Exception as e:
        print(f'[VR] locate_views error: {e}')
        return False

def end_xr_frame():
    if not (_XR_AVAILABLE and _vr_state.active and _vr_state._frame_begun):
        return
    fs = _vr_state._frame_state
    try:
        layers = []
        if not _vr_state._frame_discard and fs is not None and len(_vr_state._swapchains) == 2 and all(p is not None for p in _vr_state._eye_poses):
            layer = getattr(_vr_state, '_xr_layer', None)
            if layer is None:
                sub_imgs = []
                fovs = []
                for i in range(2):
                    sc = _vr_state._swapchains[i]
                    sub_imgs.append(xr.SwapchainSubImage(
                        swapchain=sc.swapchain,
                        image_rect=xr.Rect2Di(
                            offset=xr.Offset2Di(x=0, y=0),
                            extent=xr.Extent2Di(width=sc.w, height=sc.h)
                        ),
                        image_array_index=0
                    ))
                    fovs.append(xr.Fovf(angle_left=0.0, angle_right=0.0, angle_up=0.0, angle_down=0.0))
                proj_views = (xr.CompositionLayerProjectionView * 2)(
                    xr.CompositionLayerProjectionView(sub_image=sub_imgs[0], fov=fovs[0]),
                    xr.CompositionLayerProjectionView(sub_image=sub_imgs[1], fov=fovs[1]))
                proj_layer = xr.CompositionLayerProjection()
                proj_layer.layer_flags = 0
                proj_layer.space = _vr_state.space
                proj_layer.view_count = 2
                proj_layer._views = ctypes.cast(proj_views, ctypes.POINTER(xr.CompositionLayerProjectionView))
                layers_arr = (ctypes.POINTER(xr.CompositionLayerBaseHeader) * 1)(
                    ctypes.cast(ctypes.byref(proj_layer), ctypes.POINTER(xr.CompositionLayerBaseHeader))
                )
                _vr_state._xr_layer = (proj_views, fovs, proj_layer, layers_arr)
            proj_views, fovs, proj_layer, layers_arr = _vr_state._xr_layer
            for i in range(2):
                fovs[i] = xr.Fovf(
                    angle_left=_vr_state._eye_fovs[i][0],
                    angle_right=_vr_state._eye_fovs[i][1],
                    angle_up=_vr_state._eye_fovs[i][2],
                    angle_down=_vr_state._eye_fovs[i][3]
                )
                proj_views[i].pose = _vr_state._eye_poses[i]
                proj_views[i].fov = fovs[i]
            layers = layers_arr
        xr.end_frame(_vr_state.session, xr.FrameEndInfo(
            display_time=_vr_state._display_time,
            environment_blend_mode=get_ar_blend_mode(),
            layer_count=len(layers),
            layers=layers if layers else None,
        ))
        _vr_state._frames_rendered += 1
    except Exception as e:
        print(f'[VR] end_xr_frame error: {e}')
    finally:
        _vr_state._frame_begun = False
        _vr_state._frame_discard = False
        _vr_state._frame_state = None
