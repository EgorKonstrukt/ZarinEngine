# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import ctypes
import math
import moderngl
try:
    import xr
except ImportError:
    xr = None
from plugins.vr_plugin.core.state import _vr_state, _XR_AVAILABLE, _free_blit_fbos, VRState, EYE_TEX_W, EYE_TEX_H
from plugins.vr_plugin.core.swapchain import VREyeSwapchain

def _get_wgl_handles():
    try:
        opengl32 = ctypes.windll.opengl32
        opengl32.wglGetCurrentDC.restype = ctypes.c_void_p
        opengl32.wglGetCurrentContext.restype = ctypes.c_void_p
        hdc = opengl32.wglGetCurrentDC()
        hglrc = opengl32.wglGetCurrentContext()
        if not hdc or not hglrc:
            return None, None
        return hdc, hglrc
    except Exception as e:
        print(f'[VR] Failed to get WGL handles: {e}')
        return None, None

def _call_get_graphics_requirements(instance, system_id):
    pfn = ctypes.cast(
        xr.get_instance_proc_addr(instance, 'xrGetOpenGLGraphicsRequirementsKHR'),
        xr.PFN_xrGetOpenGLGraphicsRequirementsKHR
    )
    gl_reqs = xr.GraphicsRequirementsOpenGLKHR()
    result = pfn(instance, system_id, ctypes.byref(gl_reqs))
    xr.check_result(xr.Result(result))

def _make_binding(hdc, hglrc):
    binding = xr.GraphicsBindingOpenGLWin32KHR()
    fields = [f[0] for f in binding._fields_]
    dc_field = next((f for f in fields if f.lower().replace('_', '') == 'hdc'), None)
    gl_field = next((f for f in fields if f.lower().replace('_', '') == 'hglrc'), None)
    if dc_field is None or gl_field is None:
        raise RuntimeError(f'Unknown GraphicsBindingOpenGLWin32KHR fields: {fields}')
    setattr(binding, dc_field, hdc)
    setattr(binding, gl_field, hglrc)
    return binding

def _setup_input(instance, session):
    try:
        action_set_info = xr.ActionSetCreateInfo(
            action_set_name='zarkifs_actions',
            localized_action_set_name='ZarKIFS Actions',
            priority=0,
        )
        action_set = xr.create_action_set(instance, action_set_info)
        _vr_state._action_set = action_set
        hand_paths = [
            xr.string_to_path(instance, '/user/hand/left'),
            xr.string_to_path(instance, '/user/hand/right'),
        ]
        _vr_state._hand_paths = hand_paths
        for i, side in enumerate(['left', 'right']):
            grip_info = xr.ActionCreateInfo(
                action_type=xr.ActionType.FLOAT_INPUT,
                action_name=f'grip_{side}',
                localized_action_name=f'Grip {side.capitalize()}',
                count_subaction_paths=1,
                subaction_paths=ctypes.cast(
                    (xr.Path * 1)(hand_paths[i]), ctypes.POINTER(xr.Path)
                ),
            )
            _vr_state._grip_actions[i] = xr.create_action(action_set, grip_info)
            pose_info = xr.ActionCreateInfo(
                action_type=xr.ActionType.POSE_INPUT,
                action_name=f'hand_pose_{side}',
                localized_action_name=f'Hand Pose {side.capitalize()}',
                count_subaction_paths=1,
                subaction_paths=ctypes.cast(
                    (xr.Path * 1)(hand_paths[i]), ctypes.POINTER(xr.Path)
                ),
            )
            _vr_state._pose_actions[i] = xr.create_action(action_set, pose_info)
            thumb_info = xr.ActionCreateInfo(
                action_type=xr.ActionType.VECTOR2F_INPUT,
                action_name=f'thumb_{side}',
                localized_action_name=f'Thumbstick {side.capitalize()}',
                count_subaction_paths=1,
                subaction_paths=ctypes.cast(
                    (xr.Path * 1)(hand_paths[i]), ctypes.POINTER(xr.Path)
                ),
            )
            _vr_state._thumbstick_actions[i] = xr.create_action(action_set, thumb_info)
            trig_info = xr.ActionCreateInfo(
                action_type=xr.ActionType.FLOAT_INPUT,
                action_name=f'trig_{side}',
                localized_action_name=f'Trigger {side.capitalize()}',
                count_subaction_paths=1,
                subaction_paths=ctypes.cast(
                    (xr.Path * 1)(hand_paths[i]), ctypes.POINTER(xr.Path)
                ),
            )
            _vr_state._trigger_actions[i] = xr.create_action(action_set, trig_info)
            try:
                haptic_type = getattr(xr.ActionType, 'VIBRATION_OUTPUT', None) or getattr(xr.ActionType, 'HAPTIC_OUTPUT', None) or 1000079000
                haptic_info = xr.ActionCreateInfo(
                    action_type=haptic_type,
                    action_name=f'haptic_{side}',
                    localized_action_name=f'Haptic {side.capitalize()}',
                    count_subaction_paths=1,
                    subaction_paths=ctypes.cast(
                        (xr.Path * 1)(hand_paths[i]), ctypes.POINTER(xr.Path)
                    ),
                )
                _vr_state._haptic_actions[i] = xr.create_action(action_set, haptic_info)
            except Exception as e:
                print(f'[VR] haptic action setup failed for {side}: {e}')
        grip_path_l = xr.string_to_path(instance, '/user/hand/left/input/squeeze/value')
        grip_path_r = xr.string_to_path(instance, '/user/hand/right/input/squeeze/value')
        pose_path_l = xr.string_to_path(instance, '/user/hand/left/input/grip/pose')
        pose_path_r = xr.string_to_path(instance, '/user/hand/right/input/grip/pose')
        thumb_l = xr.string_to_path(instance, '/user/hand/left/input/thumbstick')
        thumb_r = xr.string_to_path(instance, '/user/hand/right/input/thumbstick')
        trig_l = xr.string_to_path(instance, '/user/hand/left/input/trigger/value')
        trig_r = xr.string_to_path(instance, '/user/hand/right/input/trigger/value')
        trig_l2 = xr.string_to_path(instance, '/user/hand/left/input/select/click')
        trig_r2 = xr.string_to_path(instance, '/user/hand/right/input/select/click')
        profile_path = xr.string_to_path(instance, '/interaction_profiles/khr/simple_controller')
        bindings_simple = [
            xr.ActionSuggestedBinding(action=_vr_state._pose_actions[0], binding=pose_path_l),
            xr.ActionSuggestedBinding(action=_vr_state._pose_actions[1], binding=pose_path_r),
        ]
        try:
            xr.suggest_interaction_profile_bindings(instance, xr.InteractionProfileSuggestedBinding(
                interaction_profile=profile_path,
                count_suggested_bindings=len(bindings_simple),
                suggested_bindings=bindings_simple,
            ))
        except Exception:
            pass
        for profile_str, bindings in [
            ('/interaction_profiles/oculus/touch_controller', [
                ('grip', grip_path_l, grip_path_r),
                ('pose', pose_path_l, pose_path_r),
                ('thumb', thumb_l, thumb_r),
                ('trig', trig_l, trig_r),
                ('haptic', xr.string_to_path(instance, '/user/hand/left/output/haptic'), xr.string_to_path(instance, '/user/hand/right/output/haptic')),
            ]),
            ('/interaction_profiles/valve/index_controller', [
                ('grip', grip_path_l, grip_path_r),
                ('pose', pose_path_l, pose_path_r),
                ('thumb', thumb_l, thumb_r),
                ('trig', trig_l, trig_r),
                ('haptic', xr.string_to_path(instance, '/user/hand/left/output/haptic'), xr.string_to_path(instance, '/user/hand/right/output/haptic')),
            ]),
            ('/interaction_profiles/htc/vive_controller', [
                ('grip', xr.string_to_path(instance, '/user/hand/left/input/squeeze/click'), xr.string_to_path(instance, '/user/hand/right/input/squeeze/click')),
                ('pose', pose_path_l, pose_path_r),
                ('thumb', xr.string_to_path(instance, '/user/hand/left/input/trackpad'), xr.string_to_path(instance, '/user/hand/right/input/trackpad')),
                ('trig', trig_l, trig_r),
                ('haptic', xr.string_to_path(instance, '/user/hand/left/output/haptic'), xr.string_to_path(instance, '/user/hand/right/output/haptic')),
            ]),
            ('/interaction_profiles/microsoft/motion_controller', [
                ('grip', xr.string_to_path(instance, '/user/hand/left/input/squeeze/click'), xr.string_to_path(instance, '/user/hand/right/input/squeeze/click')),
                ('pose', pose_path_l, pose_path_r),
                ('thumb', thumb_l, thumb_r),
                ('trig', trig_l, trig_r),
                ('haptic', xr.string_to_path(instance, '/user/hand/left/output/haptic'), xr.string_to_path(instance, '/user/hand/right/output/haptic')),
            ]),
            ('/interaction_profiles/khr/simple_controller', [
                ('trig', trig_l2, trig_r2),
                ('haptic', xr.string_to_path(instance, '/user/hand/left/output/haptic'), xr.string_to_path(instance, '/user/hand/right/output/haptic')),
            ]),
        ]:
            try:
                prof_path = xr.string_to_path(instance, profile_str)
                b = []
                for kind, pl, pr in bindings:
                    if kind == 'grip':
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._grip_actions[0], binding=pl))
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._grip_actions[1], binding=pr))
                    elif kind == 'pose':
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._pose_actions[0], binding=pl))
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._pose_actions[1], binding=pr))
                    elif kind == 'thumb':
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._thumbstick_actions[0], binding=pl))
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._thumbstick_actions[1], binding=pr))
                    elif kind == 'trig':
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._trigger_actions[0], binding=pl))
                        b.append(xr.ActionSuggestedBinding(action=_vr_state._trigger_actions[1], binding=pr))
                    elif kind == 'haptic':
                        if _vr_state._haptic_actions[0] is not None:
                            b.append(xr.ActionSuggestedBinding(action=_vr_state._haptic_actions[0], binding=pl))
                        if _vr_state._haptic_actions[1] is not None:
                            b.append(xr.ActionSuggestedBinding(action=_vr_state._haptic_actions[1], binding=pr))
                if b:
                    xr.suggest_interaction_profile_bindings(instance, xr.InteractionProfileSuggestedBinding(
                        interaction_profile=prof_path,
                        count_suggested_bindings=len(b),
                        suggested_bindings=b,
                    ))
            except Exception:
                pass
        attach_info = xr.SessionActionSetsAttachInfo(
            count_action_sets=1,
            action_sets=ctypes.cast((xr.ActionSet * 1)(action_set), ctypes.POINTER(xr.ActionSet)),
        )
        xr.attach_session_action_sets(session, attach_info)
        for i, side in enumerate(['left', 'right']):
            hand_path = xr.string_to_path(instance, f'/user/hand/{side}')
            space_info = xr.ActionSpaceCreateInfo(
                action=_vr_state._pose_actions[i],
                subaction_path=hand_path,
                pose_in_action_space=xr.Posef(),
            )
            _vr_state._pose_spaces[i] = xr.create_action_space(session, space_info)
        print('[VR] Input actions set up.')
    except Exception as e:
        print(f'[VR] Input setup failed: {e}')

def initialize(ctx: moderngl.Context) -> bool:
    global _vr_state
    if not _XR_AVAILABLE:
        print('[VR] pyopenxr not installed.')
        return False
    try:
        hdc, hglrc = _get_wgl_handles()
        if hdc is None or hglrc is None:
            print('[VR] Failed to retrieve WGL context handles.')
            return False
        exts = xr.enumerate_instance_extension_properties()
        avail = {
            e.extension_name.decode('utf-8') if isinstance(e.extension_name, bytes) else e.extension_name
            for e in exts
        }
        if "XR_KHR_opengl_enable" not in avail:
            print('[VR] OpenGL backend unsupported by runtime.')
            return False
        app_info = xr.ApplicationInfo(
            application_name='ZarKIFS_VR',
            application_version=1,
            engine_name='ZarKIFS',
            engine_version=1,
            api_version=xr.Version(1, 0, 0)
        )
        create_info = xr.InstanceCreateInfo(
            application_info=app_info,
            enabled_extension_names=["XR_KHR_opengl_enable"]
        )
        _vr_state.instance = xr.create_instance(create_info)
        sys_info = xr.SystemGetInfo(form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY)
        _vr_state.system_id = xr.get_system(_vr_state.instance, sys_info)
        _call_get_graphics_requirements(_vr_state.instance, _vr_state.system_id)
        binding = _make_binding(hdc, hglrc)
        session_info = xr.SessionCreateInfo(
            system_id=_vr_state.system_id,
            create_flags=xr.SessionCreateFlags(0),
        )
        session_info.next = ctypes.cast(ctypes.pointer(binding), ctypes.c_void_p)
        _vr_state._binding = binding
        _vr_state.session = xr.create_session(_vr_state.instance, session_info)
        space_info = xr.ReferenceSpaceCreateInfo(
            reference_space_type=xr.ReferenceSpaceType.LOCAL,
            pose_in_reference_space=xr.Posef()
        )
        _vr_state.space = xr.create_reference_space(_vr_state.session, space_info)
        _setup_input(_vr_state.instance, _vr_state.session)
        _vr_state.active = True
        print('[VR] OpenXR session and space created successfully.')
        return True
    except Exception as e:
        print(f'[VR] OpenXR init failed: {e}')
        _vr_state.active = False
        return False

def _create_swapchains():
    if _vr_state._swapchains:
        return
    try:
        views = xr.enumerate_view_configuration_views(
            _vr_state.instance,
            _vr_state.system_id,
            xr.ViewConfigurationType.PRIMARY_STEREO
        )
        for i in range(2):
            w = views[i].recommended_image_rect_width if i < len(views) else EYE_TEX_W
            h = views[i].recommended_image_rect_height if i < len(views) else EYE_TEX_H
            VRState.EYE_TEX_W = w
            VRState.EYE_TEX_H = h
            sc = VREyeSwapchain(_vr_state.session, w, h)
            _vr_state._swapchains.append(sc)
        print(f'[VR] Swapchains created {VRState.EYE_TEX_W}x{VRState.EYE_TEX_H}')
    except Exception as e:
        print(f'[VR] Swapchain creation failed: {e}')

def shutdown():
    global _vr_state
    try:
        for space in _vr_state._pose_spaces:
            if space is not None:
                try:
                    xr.destroy_space(space)
                except Exception:
                    pass
        _vr_state._pose_spaces = [None, None]
        if _vr_state._action_set is not None:
            try:
                xr.destroy_action_set(_vr_state._action_set)
            except Exception:
                pass
            _vr_state._action_set = None
            _vr_state._thumbstick_actions = [None, None]
            _vr_state._trigger_actions = [None, None]
        for sc in _vr_state._swapchains:
            try:
                sc.destroy()
            except Exception:
                pass
        _vr_state._swapchains.clear()
        if _vr_state._session_running and _vr_state.session:
            try:
                xr.end_session(_vr_state.session)
            except Exception:
                pass
            _vr_state._session_running = False
        if _vr_state.session:
            xr.destroy_session(_vr_state.session)
        if _vr_state.instance:
            xr.destroy_instance(_vr_state.instance)
    except Exception:
        pass
    _vr_state.active = False
    _vr_state.session = None
    _vr_state.instance = None
    _vr_state.space = None
    _vr_state.system_id = None
    _vr_state._session_running = False
    _vr_state.rig_yaw = 0.0
    _vr_state.rig_vel = (0.0, 0.0, 0.0)
    _free_blit_fbos()
    _vr_state._xr_layer = None
    _vr_state._frame_begun = False
    _vr_state._frame_discard = False
    _vr_state._frame_state = None
    for p_i in range(2):
        _vr_state._eye_poses[p_i] = None
    print('[VR] OpenXR resources destroyed.')
