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
from PyQt6.QtWidgets import QMessageBox, QFileDialog
from PyQt6.QtCore import Qt, QTimer

from core.maths.math3d import Vec3
from core.foundation.logger import Logger
from editor.splash import SplashScreen


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
    if hasattr(mw, '_scene_toolbar') and mw._scene_toolbar:
        if mode != mw._viewport.gizmo.__class__.__dict__.get('MULTI', None) and getattr(mw._viewport.gizmo, '_multigizmo_enabled', False):
            pass


def on_gizmo_space_changed(mw, space):
    mw._viewport.gizmo.space = space


def on_multigizmo_toggled(mw, enabled: bool):
    from core.gizmo.core import GizmoMode
    mw._viewport.gizmo.multigizmo_enabled = enabled
    if enabled:
        mw._viewport.gizmo.mode = GizmoMode.MULTI
        mw._viewport.gizmo.multigizmo_visible = True
    else:
        mw._viewport.gizmo.mode = GizmoMode.TRANSLATE
    from core.config.config import get_global_config
    get_global_config().set("gizmo.multigizmo_enabled", enabled)
    get_global_config().save()
    mw._viewport.update()


def on_multigizmo_align_changed(mw, align: str):
    mw._viewport.gizmo.alignment = align
    from core.config.config import get_global_config
    get_global_config().set("gizmo.multigizmo_alignment", align)
    get_global_config().save()
    mw._viewport.update()


def on_multigizmo_lock_toggled(mw, locked: bool):
    mw._viewport.gizmo.orientation_lock = locked
    from core.config.config import get_global_config
    get_global_config().set("gizmo.multigizmo_orientation_lock", locked)
    get_global_config().save()
    if not locked:
        mw._viewport.gizmo._orientation_lock_cache = None
    mw._viewport.update()


def on_multigizmo_visible_toggled(mw, visible: bool):
    mw._viewport.gizmo.multigizmo_visible = visible
    mw._viewport._gizmo_visible = visible
    from core.config.config import get_global_config
    get_global_config().set("gizmo.multigizmo_visible", visible)
    get_global_config().save()
    mw._viewport.update()


def on_grid_toggled(mw, enabled: bool):
    if mw._viewport.renderer:
        mw._viewport.renderer.show_grid = enabled
    mw._render_toolbar.save_state()


def on_snap_toggled(mw, enabled: bool):
    mw._viewport.gizmo.snap_enabled = enabled
    mw._render_toolbar.save_state()


def on_gizmo_vis_toggled(mw, checked: bool):
    mw._viewport._gizmo_visible = checked
    mw._viewport._gizmo_icons_visible = checked
    mw._viewport.update()


def on_snap_t_changed(mw, val: float):
    mw._viewport.gizmo.snap_translate = val
    mw._viewport.set_grid_step(val)
    mw._render_toolbar.save_state()


def on_snap_r_changed(mw, val: float):
    mw._viewport.gizmo.snap_rotate = val
    mw._render_toolbar.save_state()


def on_snap_s_changed(mw, val: float):
    mw._viewport.gizmo.snap_scale = val
    mw._render_toolbar.save_state()


def on_render_mode_changed(mw, mode):
    if mw._viewport.renderer:
        mw._viewport.renderer.render_mode = mode


def on_skybox_toggled(mw, enabled: bool):
    if mw._viewport.renderer:
        mw._viewport.renderer.skybox_enabled = enabled
    play = getattr(mw, '_play_dock', None)
    if play and hasattr(play, '_viewport') and play._viewport._renderer:
        play._viewport._renderer.skybox_enabled = enabled
    mw._render_toolbar.save_state()


def on_effects_toggled(mw, enabled: bool):
    if mw._viewport.renderer:
        mw._viewport.renderer.set_effects_enabled(enabled)
    play = getattr(mw, '_play_dock', None)
    if play and hasattr(play, '_viewport') and play._viewport._renderer:
        play._viewport._renderer.set_effects_enabled(enabled)
    mw._render_toolbar.save_state()


def on_camera_projection_changed(mw):
    mw._viewport.camera.toggle_projection()
    is_ortho = mw._viewport.camera.is_orthographic
    mw._render_toolbar._cam_persp_btn.setChecked(not is_ortho)


def on_camera_type_changed(mw):
    is_ortho = mw._viewport.camera.is_orthographic
    btn = mw._render_toolbar._cam_persp_btn
    if is_ortho:
        btn.setIcon(qta.icon("fa5s.camera-retro", color=chr(35) + "d4d4d4"))
        btn.setText(" Ortho")
    else:
        btn.setIcon(qta.icon("fa5s.camera", color=chr(35) + "d4d4d4"))
        btn.setText(" Perspective")


def on_camera_2d_toggled(mw):
    mw._viewport.camera.toggle_2d_mode()
    on_camera_2d_changed(mw)


def on_camera_2d_changed(mw):
    is_2d = mw._viewport.camera.is_2d_mode
    mw._render_toolbar._cam_2d_btn.setChecked(is_2d)
    on_camera_type_changed(mw)


