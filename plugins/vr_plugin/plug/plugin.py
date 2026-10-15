# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
import ctypes
import time
import types
import numpy as np
import moderngl

from core.foundation.plugins import PluginBase
from plugins.vr_plugin.components import (
    XRRig, XRTrackedPoseDriver, XRController, XRHand, XRCull,
    XRHaptics, XRInteractionManager, XRRayInteractor, XRDirectInteractor, XRPokeInteractor,
    XRGrabInteractable, XRSmoothMoveProvider, XRSnapTurnProvider, XRTeleportationProvider,
    ARSession, ARCameraBackground, ARPlaneManager, ARRaycastManager, ARAnchorManager, ARPointCloudManager,
)
from core.maths.math3d import Mat4, Vec3

try:
    from core._vr_batch import build_eye_view_proj, build_controller_mvp
    _HAS_VR_BATCH = True
except Exception:
    _HAS_VR_BATCH = False

def spawn_xr_rig(engine):
    try:
        if engine is None or engine.scene is None:
            return None
        sc = engine.scene
        for e in sc.get_all_entities():
            if e.get_component(XRRig) is not None:
                return e
        from core.components.rendering.renderers.mesh_filter import MeshFilter
        from core.components.rendering.renderers.mesh_renderer import MeshRenderer
        from core.assets.matp import Material
        import os
        mat_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "materials", "vr_unlit.mat")

        rig = sc.create_entity("XRRig")
        rig.add_component(XRRig())

        def _add_model(parent, path, scale):
            me = sc.create_entity("XRModel")
            mf = MeshFilter()
            mf.mesh_path = path
            mf.mesh_name = "mesh"
            me.add_component(mf)
            mr = MeshRenderer()
            mr.enabled = True
            try:
                mr.material = Material.load(mat_path)
            except Exception:
                pass
            me.transform.local_scale = Vec3(scale, scale, scale)
            me.set_parent(parent, preserve_world=False)
            return me

        hmd = sc.create_entity("XRHMD")
        hmd.add_component(XRTrackedPoseDriver())
        hmd.get_component(XRTrackedPoseDriver).pose_type = "Center"
        hmd.add_component(XRCull())
        hmd.transform.local_position = Vec3(0.0, 1.6, 0.0)
        hmd.set_parent(rig, preserve_world=False)
        _add_model(hmd, "core/3d_models/OculusQ2/OculusQ2.fbx", 0.00035)

        def _hand(name, hand, model, pos):
            he = sc.create_entity(name)
            tpd = XRTrackedPoseDriver()
            tpd.pose_type = "LeftHand" if hand == "Left" else "RightHand"
            he.add_component(tpd)
            he.add_component(XRController(controller_hand=hand))
            he.get_component(XRController).model = model
            he.transform.local_position = Vec3(*pos)
            he.set_parent(rig, preserve_world=False)
            _add_model(he, "core/3d_models/OculusTouch/OculusTouch.fbx", 1.0)
            he.add_component(XRHand(hand=hand))

        _hand("XRControllerLeft", "Left", "OculusTouch", (-0.25, 1.2, -0.2))
        _hand("XRControllerRight", "Right", "OculusTouch", (0.25, 1.2, -0.2))

        rig.add_component(XRInteractionManager())
        rig.add_component(XRSmoothMoveProvider())
        rig.add_component(XRSnapTurnProvider())
        rig.add_component(XRTeleportationProvider())
        return rig
    except Exception:
        return None

class _EyeCamera:
    DEFAULT_FOV = 60.0
    def __init__(self, view_mat, proj_mat, pos, fwd, fov_deg):
        self._view = view_mat
        self._proj = proj_mat
        self._pos = pos
        self._fwd = fwd
        self._fov = fov_deg
        self._is_2d_mode = False
        self._is_orthographic = False
        self._ortho_zoom_distance = 1.0
    def get_view_matrix(self):
        return self._view
    def get_projection_matrix(self, aspect=1.0):
        return self._proj
    @property
    def forward(self):
        return self._fwd
    @property
    def position(self):
        return self._pos
    @property
    def fov(self):
        return self._fov
    @property
    def is_2d_mode(self):
        return False
    @property
    def is_orthographic(self):
        return False

class VRPluginBase(PluginBase):
    NAME = "VRPlugin"
    VERSION = "1.0.0"
    DESCRIPTION = "VR display integration with OpenXR"
    SYSTEM = True
    def __init__(self):
        super().__init__()
        self._viewport = None
        self._original_paintGL = None
        self._vr_active = False
        self._dock_widget = None
        self._vr_view_btn = None
        self._eye_view = True
    def initialize(self, engine):
        super().initialize(engine)
        self.register_dock("VR Control", self._create_dock, area="bottom")
    def _create_dock(self):
        from plugins.vr_plugin.vr_dock import VRControlWidget
        self._dock_widget = VRControlWidget(self._engine, self)
        return self._dock_widget
    def ensure_vr_entities(self, scene=None):
        try:
            from core.engine.eng import Engine
            eng = Engine.instance() if hasattr(self, '_engine') else None
            sc = scene or (eng.scene if eng else None)
            if sc is None:
                return
            from plugins.vr_plugin import core as vr_core
            if not vr_core.is_active():
                return
            spawn_xr_rig(sc)
            sc._dirty = True
            sc._render_version += 1
        except Exception:
            pass

    def remove_vr_entities(self, scene=None):
        try:
            from core.engine.eng import Engine
            eng = Engine.instance() if hasattr(self, '_engine') else None
            sc = scene or (eng.scene if eng else None)
            if sc is None:
                return
            to_remove = []
            for e in sc.get_all_entities():
                if e.get_component(XRRig) is not None:
                    to_remove.append(e._id)
            for eid in to_remove:
                try:
                    sc.remove_entity(eid)
                except Exception:
                    pass
            sc._dirty = True
            sc._render_version += 1
        except Exception:
            pass

    def on_scene_loaded(self, scene):
        try:
            from plugins.vr_plugin import core as vr_core
            if vr_core.is_active():
                self.ensure_vr_entities(scene)
            else:
                self.remove_vr_entities(scene)
        except Exception:
            pass

    def on_viewport_ready(self, vp):
        try:
            if self._vr_active:
                self._install_toolbar_button(vp)
            try:
                from core.engine.eng import Engine
                eng = Engine.instance()
                if eng and eng.scene:
                    from plugins.vr_plugin import core as vr_core
                    if vr_core.is_active():
                        self.ensure_vr_entities(eng.scene)
                    else:
                        self.remove_vr_entities(eng.scene)
            except Exception:
                pass
        except Exception:
            pass

    def toggle_vr(self):
        if self._vr_active:
            self._disable_vr()
        else:
            self._enable_vr()

    def spawn_xr_rig(self, engine=None):
        from core.engine.eng import Engine
        eng = engine or Engine.instance()
        return spawn_xr_rig(eng)
    def _install_toolbar_button(self, vp):
        try:
            import editor.icons as qta
            from PyQt6.QtWidgets import QPushButton
            if self._vr_view_btn is not None:
                try:
                    self._vr_view_btn.setVisible(True)
                    return
                except Exception:
                    pass
            bar = getattr(vp, '_toolbar', None)
            if bar is None:
                return
            lay = bar.layout()
            if lay is None:
                return
            cam_row = lay.itemAt(0).layout() if lay.count() > 0 else None
            if cam_row is None:
                return
            btn = QPushButton(qta.icon("fa5s.eye", color=chr(35) + "d4d4d4"), " Eye")
            btn.setCheckable(False)
            btn.setToolTip("Toggle VR Eye / Desktop view")
            btn.setMinimumWidth(70)
            def _on_click():
                self._eye_view = not self._eye_view
                try:
                    from plugins.vr_plugin import core as vr_core
                    vr_core.set_eye_view(self._eye_view)
                except Exception:
                    pass
                if self._eye_view:
                    btn.setText(" Eye")
                    btn.setIcon(qta.icon("fa5s.eye", color=chr(35) + "4fc3f7"))
                else:
                    btn.setText(" Desktop")
                    btn.setIcon(qta.icon("fa5s.desktop", color=chr(35) + "aed581"))
                try:
                    vp.update()
                except Exception:
                    pass
            btn.clicked.connect(_on_click)
            if self._eye_view:
                btn.setIcon(qta.icon("fa5s.eye", color=chr(35) + "4fc3f7"))
            else:
                btn.setIcon(qta.icon("fa5s.desktop", color=chr(35) + "aed581"))
            cam_row.addWidget(btn)
            self._vr_view_btn = btn
            self._eye_view = True
            try:
                from plugins.vr_plugin import core as vr_core
                vr_core.set_eye_view(True)
            except Exception:
                pass
        except Exception:
            pass
    def _remove_toolbar_button(self):
        if self._vr_view_btn is not None:
            try:
                self._vr_view_btn.setVisible(False)
                self._vr_view_btn.deleteLater()
            except Exception:
                pass
            self._vr_view_btn = None

    def _disable_vr(self):
        from plugins.vr_plugin import core as vr_core
        if self._original_paintGL and self._viewport:
            try:
                self._viewport.paintGL = self._original_paintGL
            except Exception:
                pass
            try:
                self._viewport.update()
            except Exception:
                pass
        self._remove_toolbar_button()
        try:
            self.remove_vr_entities()
        except Exception:
            pass
        r = vr_core.get_renderer()
        if r is not None:
            try:
                r.release()
            except Exception:
                pass
            vr_core._vr_toggle.renderer = None
        vr_core._vr_toggle.enabled = False
        vr_core._vr_toggle._ctx = None
        try:
            vr_core.set_eye_view(True)
        except Exception:
            pass
        vr_core.shutdown()
        self._vr_active = False
        self._eye_view = True
        self._original_paintGL = None
        self._viewport = None
        from core.foundation.logger import Logger
        Logger.info("[VR] VR disabled, original viewport restored.")
    def shutdown(self):
        if self._vr_active:
            self._disable_vr()
        super().shutdown()
