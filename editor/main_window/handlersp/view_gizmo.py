# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import editor.icons as qta
from PySide6.QtWidgets import QMessageBox, QFileDialog
from PySide6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen


def _reg(mw):
    try:
        from editor.toolbar_registry import get_toolbar_registry
        return get_toolbar_registry(mw)
    except Exception:
        return None


def reset_camera(mw):
    cam = mw._viewport.camera
    cam._position = Vec3(0.0, 3.0, 10.0)
    cam._yaw = 0.0
    cam._pitch = -15.0
    cam._focus_active = False
    cam._focus_transition_blend = 1.0
    cam._orbit_target = Vec3.zero()
    try:
        cam._orbit_dist = (cam._position - cam._orbit_target).length()
    except Exception:
        cam._orbit_dist = 10.0
    cam._orbit_dist_target = cam._orbit_dist
    cam._fly_dolly_remaining = 0.0
    cam._vel = Vec3.zero()


def on_gizmo_mode_changed(mw, mode):
    mw._viewport.gizmo.mode = mode
    try:
        name = mode.value if hasattr(mode, "value") else str(mode).lower()
        reg = _reg(mw)
        if reg is not None:
            reg.store("gizmo_mode", str(name).lower())
    except Exception:
        pass
    try:
        tb = getattr(mw, "_scene_toolbar", None)
        if tb is not None and hasattr(tb, "set_gizmo_mode"):
            tb.set_gizmo_mode(mode)
    except Exception:
        pass
    try:
        mw._viewport.update()
    except Exception:
        pass


def on_gizmo_space_changed(mw, space):
    mw._viewport.gizmo.space = space
    try:
        name = space.value if hasattr(space, "value") else str(space).lower()
        reg = _reg(mw)
        if reg is not None:
            reg.store("gizmo_space", str(name).lower())
    except Exception:
        pass
    try:
        tb = getattr(mw, "_scene_toolbar", None)
        if tb is not None and hasattr(tb, "set_gizmo_space"):
            tb.set_gizmo_space(space)
    except Exception:
        pass


def on_multigizmo_toggled(mw, enabled: bool):
    from core.gizmo.core import GizmoMode
    mw._viewport.gizmo.multigizmo_enabled = enabled
    if enabled:
        mw._viewport.gizmo.mode = GizmoMode.MULTI
        mw._viewport.gizmo.multigizmo_visible = True
    else:
        mw._viewport.gizmo.mode = GizmoMode.TRANSLATE
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("multigizmo_enabled", bool(enabled))
    except Exception:
        pass
    mw._viewport.update()


def on_multigizmo_align_changed(mw, align: str):
    mw._viewport.gizmo.alignment = align
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("multigizmo_alignment", str(align))
    except Exception:
        pass
    mw._viewport.update()


def on_multigizmo_lock_toggled(mw, locked: bool):
    mw._viewport.gizmo.orientation_lock = locked
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("multigizmo_orientation_lock", bool(locked))
    except Exception:
        pass
    if not locked:
        mw._viewport.gizmo._orientation_lock_cache = None
    mw._viewport.update()


def on_multigizmo_visible_toggled(mw, visible: bool):
    mw._viewport.gizmo.multigizmo_visible = visible
    mw._viewport._gizmo_visible = visible
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("multigizmo_visible", bool(visible))
    except Exception:
        pass
    mw._viewport.update()


def on_grid_toggled(mw, enabled: bool):
    if mw._viewport.renderer:
        mw._viewport.renderer.show_grid = enabled
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("grid", bool(enabled))
    except Exception:
        pass


def on_snap_toggled(mw, enabled: bool):
    mw._viewport.gizmo.snap_enabled = enabled
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("snap", bool(enabled))
    except Exception:
        pass


def on_gizmo_vis_toggled(mw, checked: bool):
    mw._viewport._gizmo_visible = checked
    mw._viewport._gizmo_icons_visible = checked
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("gizmo_visible", bool(checked))
    except Exception:
        pass
    try:
        act = getattr(mw, "_gizmo_vis_act", None)
        if act is not None and act.isChecked() != bool(checked):
            act.blockSignals(True)
            act.setChecked(bool(checked))
            act.blockSignals(False)
    except Exception:
        pass
    mw._viewport.update()


def on_snap_t_changed(mw, val: float):
    mw._viewport.gizmo.snap_translate = val
    mw._viewport.set_grid_step(val)
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("snap_translate", float(val))
    except Exception:
        pass


def on_snap_r_changed(mw, val: float):
    mw._viewport.gizmo.snap_rotate = val
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("snap_rotate", float(val))
    except Exception:
        pass


def on_snap_s_changed(mw, val: float):
    mw._viewport.gizmo.snap_scale = val
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("snap_scale", float(val))
    except Exception:
        pass


def on_render_mode_changed(mw, mode):
    if mw._viewport.renderer:
        mw._viewport.renderer.render_mode = mode
    try:
        name = mode.value if hasattr(mode, "value") else str(mode).lower()
        reg = _reg(mw)
        if reg is not None:
            reg.store("render_mode", str(name).lower())
    except Exception:
        pass
    try:
        tb = getattr(mw, "_render_toolbar", None)
        if tb is not None and hasattr(tb, "set_render_mode"):
            tb.set_render_mode(mode)
    except Exception:
        pass
    try:
        mw._viewport.update()
    except Exception:
        pass


def on_skybox_toggled(mw, enabled: bool):
    if mw._viewport.renderer:
        mw._viewport.renderer.skybox_enabled = enabled
    play = getattr(mw, '_play_dock', None)
    if play and hasattr(play, '_viewport') and play._viewport._renderer:
        play._viewport._renderer.skybox_enabled = enabled
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("skybox", bool(enabled))
    except Exception:
        pass


def on_effects_toggled(mw, enabled: bool):
    if mw._viewport.renderer:
        mw._viewport.renderer.set_effects_enabled(enabled)
    play = getattr(mw, '_play_dock', None)
    if play and hasattr(play, '_viewport') and play._viewport._renderer:
        play._viewport._renderer.set_effects_enabled(enabled)
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("effects", bool(enabled))
    except Exception:
        pass


def on_camera_projection_changed(mw):
    mw._viewport.camera.toggle_projection()
    is_ortho = mw._viewport.camera.is_orthographic
    try:
        tb = getattr(mw, "_render_toolbar", None)
        if tb is not None and hasattr(tb, "set_camera_projection"):
            tb.set_camera_projection(is_ortho)
        else:
            mw._render_toolbar._cam_persp_btn.setChecked(not is_ortho)
    except Exception:
        pass
    try:
        on_camera_type_changed(mw)
    except Exception:
        pass
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("camera_projection", "orthographic" if is_ortho else "perspective")
    except Exception:
        pass
    try:
        mw._viewport.update()
    except Exception:
        pass


def on_camera_type_changed(mw):
    is_ortho = mw._viewport.camera.is_orthographic
    try:
        tb = getattr(mw, "_render_toolbar", None)
        if tb is not None and hasattr(tb, "set_camera_projection"):
            tb.set_camera_projection(is_ortho)
        else:
            btn = mw._render_toolbar._cam_persp_btn
            if is_ortho:
                btn.setIcon(qta.icon("fa5s.camera-retro", color=chr(35) + "d4d4d4"))
                btn.setText(" Ortho")
            else:
                btn.setIcon(qta.icon("fa5s.camera", color=chr(35) + "d4d4d4"))
                btn.setText(" Perspective")
    except Exception:
        pass
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("camera_projection", "orthographic" if is_ortho else "perspective")
    except Exception:
        pass


def on_camera_2d_toggled(mw):
    mw._viewport.camera.toggle_2d_mode()
    on_camera_2d_changed(mw)


def on_camera_2d_changed(mw):
    is_2d = mw._viewport.camera.is_2d_mode
    try:
        tb = getattr(mw, "_render_toolbar", None)
        if tb is not None and hasattr(tb, "set_camera_2d"):
            tb.set_camera_2d(is_2d)
        else:
            mw._render_toolbar._cam_2d_btn.setChecked(is_2d)
    except Exception:
        pass
    try:
        reg = _reg(mw)
        if reg is not None:
            reg.store("camera_2d", bool(is_2d))
    except Exception:
        pass
    on_camera_type_changed(mw)
