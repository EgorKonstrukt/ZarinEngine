# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import numpy as np
import moderngl
try:
    import xr
except ImportError:
    xr = None
from plugins.vr_plugin.core.state import _vr_state, _XR_AVAILABLE, _SHADER_DIR, _load_gl_funcs, _get_blit_fbo_id, VRState, IPD_DEFAULT, GL_RGBA8, GL_SRGB8_ALPHA8, GL_DRAW_FRAMEBUFFER, GL_READ_FRAMEBUFFER, GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, GL_COLOR_BUFFER_BIT, GL_NEAREST, GL_FRAMEBUFFER_COMPLETE, EYE_LEFT, EYE_RIGHT, TRIGGER_THRESHOLD, RAY_MAX_DIST, _make_view_matrix, _make_perspective_flat
from plugins.vr_plugin.core.controllers import ControllerRenderer
from plugins.vr_plugin.core.state2 import get_eye_transforms, get_controller_ray

class VREyeSwapchain:
    def __init__(self, session, w: int, h: int):
        self.w, self.h = w, h
        formats = xr.enumerate_swapchain_formats(session)
        chosen = GL_RGBA8 if GL_RGBA8 in formats else (GL_SRGB8_ALPHA8 if GL_SRGB8_ALPHA8 in formats else formats[0])
        sc_info = xr.SwapchainCreateInfo(
            usage_flags=xr.SwapchainUsageFlags.COLOR_ATTACHMENT_BIT | xr.SwapchainUsageFlags.SAMPLED_BIT,
            format=chosen,
            sample_count=1,
            width=w,
            height=h,
            face_count=1,
            array_size=1,
            mip_count=1,
        )
        self.swapchain = xr.create_swapchain(session, sc_info)
        self.images = xr.enumerate_swapchain_images(self.swapchain, xr.SwapchainImageOpenGLKHR)
        self.format = chosen
    def acquire(self):
        idx = xr.acquire_swapchain_image(self.swapchain, xr.SwapchainImageAcquireInfo())
        xr.wait_swapchain_image(self.swapchain, xr.SwapchainImageWaitInfo(timeout=xr.INFINITE_DURATION))
        return int(self.images[idx].image)
    def release_image(self):
        xr.release_swapchain_image(self.swapchain, xr.SwapchainImageReleaseInfo())
    def destroy(self):
        xr.destroy_swapchain(self.swapchain)

class VREyeFramebuffer:
    def __init__(self, ctx: moderngl.Context, w: int, h: int):
        self.w, self.h = w, h
        self.tex = ctx.texture((w, h), 4)
        self.tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.depth = ctx.depth_renderbuffer((w, h))
        self.fbo = ctx.framebuffer(color_attachments=[self.tex], depth_attachment=self.depth)
    def release(self):
        self.fbo.release()
        self.tex.release()
        self.depth.release()

class VRRenderer:
    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._fbos = [
            VREyeFramebuffer(ctx, VRState.EYE_TEX_W, VRState.EYE_TEX_H),
            VREyeFramebuffer(ctx, VRState.EYE_TEX_W, VRState.EYE_TEX_H),
        ]
        self._compose_prog = ctx.program(vertex_shader=_COMPOSE_VERT, fragment_shader=_COMPOSE_FRAG)
        self._compose_uloc = {n: self._compose_prog[n] for n in self._compose_prog}
        verts = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype='f4')
        self._compose_vao = ctx.simple_vertex_array(self._compose_prog, ctx.buffer(verts), 'in_position')
        self._ctrl_renderer = ControllerRenderer(ctx)
    def eye_fbo(self, eye_idx: int) -> VREyeFramebuffer:
        return self._fbos[eye_idx]
    def render_controllers_for_eye(self, eye: dict):
        fb = self._fbos[eye['eye_idx']].fbo
        fb.use()
        self._ctx.viewport = (0, 0, self._fbos[eye['eye_idx']].w, self._fbos[eye['eye_idx']].h)
        self._ctrl_renderer.render_for_eye(eye)
    def render_controllers_desktop(self, view, proj):
        self._ctrl_renderer.render_for_desktop(view, proj)
    def compose_to_screen(self, screen_fbo, wnd_w: int, wnd_h: int):
        screen_fbo.use()
        self._ctx.viewport = (0, 0, wnd_w, wnd_h)
        try:
            self._ctx.scissor = None
        except Exception:
            pass
        self._ctx.disable(moderngl.DEPTH_TEST)
        self._ctx.disable(moderngl.CULL_FACE)
        self._ctx.disable(moderngl.BLEND)
        self._ctx.clear(0.0, 0.0, 0.0)
        self._fbos[EYE_LEFT].tex.use(location=0)
        self._fbos[EYE_RIGHT].tex.use(location=1)
        u = self._compose_uloc
        if 'u_eye_left' in u:
            u['u_eye_left'].value = 0
        if 'u_eye_right' in u:
            u['u_eye_right'].value = 1
        if 'u_resolution' in u:
            u['u_resolution'].value = (float(wnd_w), float(wnd_h))
        self._compose_vao.render(moderngl.TRIANGLE_STRIP)
    def release(self):
        for fb in self._fbos:
            fb.release()
        self._ctrl_renderer.release()
        self._compose_prog.release()

_COMPOSE_VERT = open(_SHADER_DIR / "shaders/vr/vr_compose_vert.glsl", "r", encoding="utf-8").read()
_COMPOSE_FRAG = open(_SHADER_DIR / "shaders/vr/vr_compose_frag.glsl", "r", encoding="utf-8").read()

def render_desktop_vr(vp, view_mat, proj_mat, fw, fh):
    from plugins.vr_plugin.core.session2 import _vr_toggle
    rnd = _vr_toggle.renderer
    if rnd is None:
        try:
            if _vr_toggle._ctx is not None:
                rnd = VRRenderer(_vr_toggle._ctx)
                _vr_toggle.renderer = rnd
            else:
                return
        except Exception:
            return
    try:
        cam = getattr(vp, '_cam', None)
        if cam is None:
            return
        pos = cam.position
        fwd = cam.forward
        up = __import__('core.maths.math3d', fromlist=['Vec3']).Vec3(0,1,0)
        right = fwd.cross(up).normalized()
        cam_up = right.cross(fwd).normalized()
        view_flat = _make_view_matrix((pos.x, pos.y, pos.z), (fwd.x, fwd.y, fwd.z), (right.x, right.y, right.z), (cam_up.x, cam_up.y, cam_up.z))
        aspect = fw / max(1, fh)
        proj_flat = _make_perspective_flat(cam.fov if hasattr(cam, 'fov') else 60.0, aspect, cam.near if hasattr(cam, 'near') else 0.1, cam.far if hasattr(cam, 'far') else 1000.0)
        try:
            rnd.render_controllers_desktop(view_flat, proj_flat)
        except Exception:
            pass
        try:
            vp_mat = view_mat * proj_mat
        except Exception:
            vp_mat = None
        hits = get_controller_hits()
        lines = []
        for idx, (ent, hit, dist, ray) in enumerate(hits):
            if ray is None:
                continue
            origin, fwdv = ray
            has_hit = ent is not None and hit is not None
            end = hit if has_hit else (origin[0]+fwdv[0]*10.0, origin[1]+fwdv[1]*10.0, origin[2]+fwdv[2]*10.0)
            from core.maths.math3d import Vec3
            c = [1.0, 0.9, 0.2, 1.0] if has_hit else ([0.2, 0.9, 1.0, 1.0] if idx==0 else [1.0, 0.3, 0.3, 1.0])
            if has_hit:
                trig = _vr_state.controllers[idx].trigger
                if trig > TRIGGER_THRESHOLD:
                    c = [1.0, 1.0, 0.2, 1.0]
            lines.append((Vec3(*origin), Vec3(*end), c))
        if lines and vp_mat is not None:
            try:
                vp._renderer.render_gizmo_lines(lines, vp_mat, pos, fw, fh, thickness_multiplier=2.0)
            except Exception:
                pass
    except Exception:
        pass

def render_vr_frame(fractal_window_render_eye, ctx: moderngl.Context, screen_fbo, params, wnd_w: int, wnd_h: int):
    from plugins.vr_plugin.core.session2 import end_xr_frame
    rnd = _vr_toggle.renderer
    if rnd is None:
        print('[VR] render_vr_frame: renderer is None, skipping')
        end_xr_frame()
        return
    eye_view = _vr_state.eye_view_enabled
    use_xr = _vr_state.active and _vr_state._session_running and len(_vr_state._swapchains) == 2
    eyes = get_eye_transforms(params)
    for eye in eyes:
        efbo = rnd.eye_fbo(eye['eye_idx'])
        efbo.fbo.use()
        ctx.viewport = (0, 0, efbo.w, efbo.h)
        ctx.disable(moderngl.BLEND)
        ctx.enable(moderngl.DEPTH_TEST)
        if _vr_state._ar_enabled:
            efbo.fbo.clear(0.0, 0.0, 0.0, 0.0)
        else:
            efbo.fbo.clear(0.0, 0.0, 0.0, 1.0)
        fractal_window_render_eye(efbo.fbo, efbo.w, efbo.h, eye)
    for eye in eyes:
        rnd.render_controllers_for_eye(eye)
    if use_xr:
        try:
            gl = _load_gl_funcs()
            status_checked = [False]
            for i, sc in enumerate(_vr_state._swapchains):
                dst_tex = sc.acquire()
                try:
                    src_fb = rnd.eye_fbo(i)
                    src_fbo_id = src_fb.fbo.glo
                    w, h = sc.w, sc.h
                    sw, sh = src_fb.w, src_fb.h
                    blit_id = _get_blit_fbo_id(gl, i)
                    gl.BindFramebuffer(GL_DRAW_FRAMEBUFFER, blit_id)
                    gl.FramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, dst_tex, 0)
                    gl.DrawBuffer(GL_COLOR_ATTACHMENT0)
                    if not status_checked[0]:
                        if gl.CheckFramebufferStatus(GL_DRAW_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                            print(f'[VR] swapchain fbo {i} incomplete')
                        status_checked[0] = True
                    gl.BindFramebuffer(GL_READ_FRAMEBUFFER, src_fbo_id)
                    gl.ReadBuffer(GL_COLOR_ATTACHMENT0)
                    gl.BlitFramebuffer(0, 0, sw, sh, 0, 0, w, h, GL_COLOR_BUFFER_BIT, GL_NEAREST)
                except Exception as e:
                    print(f'[VR] blit eye {i} error: {e}')
                finally:
                    gl.BindFramebuffer(GL_READ_FRAMEBUFFER, 0)
                    gl.BindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)
                    try:
                        sc.release_image()
                    except Exception as e:
                        print(f'[VR] release_image {i} error: {e}')
        except Exception as e:
            print(f'[VR] Swapchain blit error: {e}')
    if eye_view:
        rnd.compose_to_screen(screen_fbo, wnd_w, wnd_h)
    else:
        try:
            ctx.viewport = (0, 0, wnd_w, wnd_h)
        except Exception:
            pass
    if use_xr:
        try:
            end_xr_frame()
        except Exception:
            pass

def get_hmd_pos_offset() -> tuple[float, float, float]:
    return _vr_state._hmd_pos_offset

def reset_hmd_origin():
    _vr_state._hmd_pos_origin = None

def get_ipd() -> float:
    return _vr_state.ipd_override

def set_ipd(ipd: float):
    _vr_state.ipd_override = max(0.010, min(0.200, ipd))

def reset_ipd():
    _vr_state.ipd_override = IPD_DEFAULT

def had_frames() -> bool:
    return _vr_state._frames_rendered > 0

def session_running() -> bool:
    return _vr_state._session_running

def get_controllers():
    return _vr_state.controllers

def is_ar_mode() -> bool:
    return bool(_vr_state._ar_enabled)

def supports_passthrough_ar() -> bool:
    if not _XR_AVAILABLE:
        return False
    try:
        exts = xr.enumerate_instance_extension_properties()
        avail = {e.extension_name.decode('utf-8') if isinstance(e.extension_name, bytes) else e.extension_name for e in exts}
        for name in ('XR_FB_passthrough', 'XR_MSFT_scene_understanding', 'XR_FB_scene'):
            if name in avail:
                return True
    except Exception:
        pass
    return False

def enable_ar(floor_y: float = 0.0):
    _vr_state._ar_enabled = True
    _vr_state._ar_floor_y = float(floor_y)
    _vr_state._ar_supports_passthrough = supports_passthrough_ar()
    try:
        from core.foundation.logger import Logger
        Logger.info('[VR] AR mode enabled (alpha-blend passthrough).')
    except Exception:
        pass

def disable_ar():
    _vr_state._ar_enabled = False
    _vr_state._ar_planes = []
    _vr_state._ar_anchors = []
    _vr_state._ar_point_cloud = None

def get_ar_blend_mode():
    if _vr_state._ar_enabled:
        try:
            return xr.EnvironmentBlendMode.ALPHA_BLEND
        except Exception:
            return 3
    try:
        return xr.EnvironmentBlendMode.OPAQUE
    except Exception:
        return 1

def get_ar_planes():
    return list(_vr_state._ar_planes)

def _ensure_ar_floor_plane():
    if not _vr_state._ar_enabled:
        return
    if any(p.get('type') == 'floor' for p in _vr_state._ar_planes):
        return
    fy = _vr_state._ar_floor_y
    _vr_state._ar_planes.append({
        'id': 'floor',
        'type': 'floor',
        'pose': (0.0, fy, 0.0),
        'normal': (0.0, 1.0, 0.0),
        'extents': (10.0, 10.0),
    })

def add_ar_anchor(position, orientation=(0.0, 0.0, 0.0, 1.0), trackable_id=None):
    if not _vr_state._ar_enabled:
        return None
    aid = f'anchor_{len(_vr_state._ar_anchors)}'
    rec = {'id': aid, 'pose': tuple(position), 'quat': tuple(orientation), 'trackable_id': trackable_id}
    _vr_state._ar_anchors.append(rec)
    return aid

def remove_ar_anchor(anchor_id):
    _vr_state._ar_anchors = [a for a in _vr_state._ar_anchors if a['id'] != anchor_id]

def get_ar_anchors():
    return list(_vr_state._ar_anchors)

def set_ar_point_cloud(points):
    _vr_state._ar_point_cloud = list(points) if points else None

def get_ar_point_cloud():
    return list(_vr_state._ar_point_cloud) if _vr_state._ar_point_cloud else []

def ar_raycast(origin, direction, max_dist=50.0):
    _ensure_ar_floor_plane()
    best = None
    best_d = float('inf')
    for p in _vr_state._ar_planes:
        n = p.get('normal', (0.0, 1.0, 0.0))
        po = p.get('pose', (0.0, 0.0, 0.0))
        denom = direction[0]*n[0] + direction[1]*n[1] + direction[2]*n[2]
        if abs(denom) < 1e-6:
            continue
        t = ((po[0]-origin[0])*n[0] + (po[1]-origin[1])*n[1] + (po[2]-origin[2])*n[2]) / denom
        if t < 0 or t > max_dist:
            continue
        hit = (origin[0]+direction[0]*t, origin[1]+direction[1]*t, origin[2]+direction[2]*t)
        if t < best_d:
            best_d = t
            best = (hit, p.get('id'))
    return best, best_d

def raycast_scene(origin, direction, max_dist=RAY_MAX_DIST):
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if not eng or not eng.scene:
            return None, None, float('inf')
        scene = eng.scene
        import numpy as np
        ro = np.array([origin[0], origin[1], origin[2], 1.0], dtype=np.float64)
        rd = np.array([direction[0], direction[1], direction[2], 0.0], dtype=np.float64)
        from editor.viewport.pick import _test_entity_pick
        from core.maths.math3d import Vec3
        ray_origin = Vec3(*origin)
        ray_dir = Vec3(*direction)
        best = None
        best_d = float('inf')
        best_hit = None
        for ent in scene.get_all_entities():
            if not ent.active or not ent.transform:
                continue
            try:
                from plugins.vr_plugin.components.xr_rig import XRRig, XRTrackedPoseDriver, XRController, XRHand
                if ent.get_component(XRRig) or ent.get_component(XRTrackedPoseDriver) or ent.get_component(XRController) or ent.get_component(XRHand):
                    continue
                if ent.get_component(XRRig) or ent.get_component(XRTrackedPoseDriver) or ent.get_component(XRController) or ent.get_component(XRHand):
                    continue
            except Exception:
                pass
            d = _test_entity_pick(ent, ro, rd, ray_origin, ray_dir)
            if d > 0 and d < best_d and d < max_dist:
                best_d = d
                best = ent
                best_hit = (origin[0]+direction[0]*d, origin[1]+direction[1]*d, origin[2]+direction[2]*d)
        if best is not None:
            return best, best_hit, best_d
        return None, None, float('inf')
    except Exception:
        return None, None, float('inf')
    except Exception:
        return None, None, float('inf')

def get_controller_hits():
    hits = []
    for i in range(2):
        ray = get_controller_ray(i)
        if ray is None:
            hits.append((None, None, float('inf'), None))
            continue
        origin, fwd = ray
        ent, hit, dist = raycast_scene(origin, fwd)
        hits.append((ent, hit, dist, ray))
    return hits

def handle_trigger_selection(viewport):
    for i in range(2):
        c = _vr_state.controllers[i]
        pressed = c.trigger > TRIGGER_THRESHOLD
        prev = _vr_state._prev_trigger[i]
        _vr_state._prev_trigger[i] = pressed
        if pressed and not prev:
            ray = get_controller_ray(i)
            if ray is None:
                continue
            origin, fwd = ray
            ent, hit, dist = raycast_scene(origin, fwd)
            if viewport is not None:
                try:
                    if ent is not None:
                        viewport.set_selected_entity(ent)
                        if hasattr(viewport, 'entity_selected'):
                            viewport.entity_selected.emit(ent)
                    else:
                        viewport.set_selected_entity(None)
                        if hasattr(viewport, 'entity_selected'):
                            viewport.entity_selected.emit(None)
                        try:
                            viewport._selected_entities = []
                            viewport._selected_set_version = getattr(viewport, '_selected_set_version', 0) + 1
                        except Exception:
                            pass
                    viewport.update()
                except Exception:
                    pass
