# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.config.editor_scale import scale, scale_xy
from PySide6.QtWidgets import (QToolBar, QLabel, QPushButton, QCheckBox,
                             QDoubleSpinBox, QComboBox, QFrame, QWidget,
                             QHBoxLayout, QSizePolicy)
import editor.icons as qta
from PySide6.QtCore import Signal, Qt, QSize
from core.gizmo.core import GizmoMode, GizmoSpace
from core.renderer.types import RenderMode


def _make_sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


def _registry_for(widget):
    try:
        from editor.toolbar_registry import get_toolbar_registry
        host = None
        try:
            host = widget.window()
        except Exception:
            host = None
        if host is None:
            try:
                host = widget.parent()
            except Exception:
                host = None
        if host is None:
            return None
        return get_toolbar_registry(host)
    except Exception:
        return None


def _apply_gizmo_mode(mw, value) -> None:
    try:
        name = str(value).lower()
        mapping = {"none": GizmoMode.NONE, "translate": GizmoMode.TRANSLATE, "rotate": GizmoMode.ROTATE, "scale": GizmoMode.SCALE}
        if name not in mapping:
            return
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is None:
            return
        gizmo.mode = mapping[name]
    except Exception:
        pass


def _apply_gizmo_space(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is None:
            return
        gizmo.space = GizmoSpace.WORLD if str(value).lower() == "world" else GizmoSpace.LOCAL
    except Exception:
        pass


def _apply_multigizmo_enabled(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is None:
            return
        gizmo.multigizmo_enabled = bool(value)
        if bool(value):
            gizmo.mode = GizmoMode.MULTI
        try:
            gizmo.load_config(__import__("core.config.config", fromlist=["get_global_config"]).get_global_config())
            if bool(value):
                gizmo.mode = GizmoMode.MULTI
        except Exception:
            pass
        try:
            vp.update()
        except Exception:
            pass
    except Exception:
        pass


def _apply_multigizmo_alignment(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is None:
            return
        gizmo.alignment = str(value).lower()
        try:
            vp.update()
        except Exception:
            pass
    except Exception:
        pass


def _apply_orientation_lock(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is None:
            return
        gizmo.orientation_lock = bool(value)
        if not bool(value):
            try:
                gizmo._orientation_lock_cache = None
            except Exception:
                pass
        try:
            vp.update()
        except Exception:
            pass
    except Exception:
        pass


def _apply_multigizmo_visible(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is not None:
            gizmo.multigizmo_visible = bool(value)
        if vp is not None:
            vp._gizmo_visible = bool(value)
            try:
                vp.update()
            except Exception:
                pass
    except Exception:
        pass


def _apply_render_mode(mw, value) -> None:
    try:
        name = str(value).lower()
        if name in ("shaded-wireframe", "shadedwireframe"):
            name = "shaded_wireframe"
        vp = getattr(mw, "_viewport", None)
        renderer = getattr(vp, "renderer", None) if vp is not None else None
        if renderer is None and vp is not None:
            renderer = getattr(vp, "_renderer", None)
        if renderer is None:
            return
        for mode in RenderMode:
            if mode.value == name:
                renderer.render_mode = mode
                break
        try:
            vp.update()
        except Exception:
            pass
    except Exception:
        pass


def _apply_camera_projection(mw, value) -> None:
    try:
        want_ortho = str(value).lower() == "orthographic"
        vp = getattr(mw, "_viewport", None)
        cam = getattr(vp, "camera", None) if vp is not None else None
        if cam is None and vp is not None:
            cam = getattr(vp, "_cam", None)
        if cam is None:
            return
        if cam.is_orthographic != want_ortho:
            cam.toggle_projection()
        try:
            tb = getattr(mw, "_render_toolbar", None)
            if tb is not None and hasattr(tb, "set_camera_projection"):
                tb.set_camera_projection(cam.is_orthographic)
        except Exception:
            pass
    except Exception:
        pass


def _apply_camera_2d(mw, value) -> None:
    try:
        want_2d = bool(value)
        vp = getattr(mw, "_viewport", None)
        cam = getattr(vp, "camera", None) if vp is not None else None
        if cam is None and vp is not None:
            cam = getattr(vp, "_cam", None)
        if cam is None:
            return
        if cam.is_2d_mode != want_2d:
            cam.toggle_2d_mode()
        try:
            tb = getattr(mw, "_render_toolbar", None)
            if tb is not None and hasattr(tb, "set_camera_2d"):
                tb.set_camera_2d(cam.is_2d_mode)
        except Exception:
            pass
    except Exception:
        pass


def _apply_skybox(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        renderer = getattr(vp, "renderer", None) if vp is not None else None
        if renderer is None and vp is not None:
            renderer = getattr(vp, "_renderer", None)
        if renderer is not None:
            renderer.skybox_enabled = bool(value)
        try:
            play = getattr(mw, "_play_dock", None)
            pr = getattr(getattr(play, "_viewport", None), "_renderer", None) if play is not None else None
            if pr is not None:
                pr.skybox_enabled = bool(value)
        except Exception:
            pass
    except Exception:
        pass


def _apply_effects(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        renderer = getattr(vp, "renderer", None) if vp is not None else None
        if renderer is None and vp is not None:
            renderer = getattr(vp, "_renderer", None)
        if renderer is not None:
            renderer.set_effects_enabled(bool(value))
        try:
            play = getattr(mw, "_play_dock", None)
            pr = getattr(getattr(play, "_viewport", None), "_renderer", None) if play is not None else None
            if pr is not None:
                pr.set_effects_enabled(bool(value))
        except Exception:
            pass
    except Exception:
        pass


def _apply_grid(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        renderer = getattr(vp, "renderer", None) if vp is not None else None
        if renderer is None and vp is not None:
            renderer = getattr(vp, "_renderer", None)
        if renderer is not None:
            renderer.show_grid = bool(value)
    except Exception:
        pass


def _apply_snap(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is not None:
            gizmo.snap_enabled = bool(value)
    except Exception:
        pass


def _apply_snap_translate(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is not None:
            gizmo.snap_translate = float(value)
        if vp is not None and hasattr(vp, "set_grid_step"):
            try:
                vp.set_grid_step(float(value))
            except Exception:
                pass
    except Exception:
        pass


def _apply_snap_rotate(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is not None:
            gizmo.snap_rotate = float(value)
    except Exception:
        pass


def _apply_snap_scale(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        gizmo = getattr(vp, "gizmo", None) if vp is not None else None
        if gizmo is None and vp is not None:
            gizmo = getattr(vp, "_gizmo", None)
        if gizmo is not None:
            gizmo.snap_scale = float(value)
    except Exception:
        pass


class SceneToolbar(QToolBar):
    gizmo_mode_changed = Signal(object)
    gizmo_space_changed = Signal(object)
    multigizmo_toggled = Signal(bool)
    multigizmo_align_changed = Signal(str)
    multigizmo_lock_toggled = Signal(bool)
    multigizmo_visible_toggled = Signal(bool)

    OWNED_IDS = ["gizmo_mode", "gizmo_space", "multigizmo_enabled", "multigizmo_alignment", "multigizmo_orientation_lock", "multigizmo_visible"]

    def __init__(self, parent=None):
        super().__init__("Scene Tools", parent)
        self.setMovable(False)
        self.setIconSize(QSize(16, 16))
        self._loading = False
        self._current_mode = "translate"
        self._setup()
        self._bind_registry()

    def _setup(self):
        gizmo_label = QLabel("Gizmo: ")
        self.addWidget(gizmo_label)
        self._btn_none = QPushButton(qta.icon("fa5s.ban", color="#d4d4d4"), "")
        self._btn_none.setToolTip("No Gizmo (Q)")
        self._btn_none.setCheckable(True)
        self._btn_none.clicked.connect(lambda: self._on_mode_clicked(GizmoMode.NONE, "none"))
        self.addWidget(self._btn_none)
        self._btn_translate = QPushButton(qta.icon("fa5s.arrows-alt", color="#d4d4d4"), "")
        self._btn_translate.setToolTip("Translate (W)")
        self._btn_translate.setCheckable(True)
        self._btn_translate.clicked.connect(lambda: self._on_mode_clicked(GizmoMode.TRANSLATE, "translate"))
        self.addWidget(self._btn_translate)
        self._btn_rotate = QPushButton(qta.icon("fa5s.sync-alt", color="#d4d4d4"), "")
        self._btn_rotate.setToolTip("Rotate (E)")
        self._btn_rotate.setCheckable(True)
        self._btn_rotate.clicked.connect(lambda: self._on_mode_clicked(GizmoMode.ROTATE, "rotate"))
        self.addWidget(self._btn_rotate)
        self._btn_scale = QPushButton(qta.icon("fa5s.expand-arrows-alt", color="#d4d4d4"), "")
        self._btn_scale.setToolTip("Scale (R)")
        self._btn_scale.setCheckable(True)
        self._btn_scale.clicked.connect(lambda: self._on_mode_clicked(GizmoMode.SCALE, "scale"))
        self.addWidget(self._btn_scale)
        self.addWidget(_make_sep())
        space_label = QLabel("Space: ")
        self.addWidget(space_label)
        self._space_cb = QComboBox()
        self._space_cb.addItems(["World", "Local"])
        self._space_cb.currentTextChanged.connect(self._on_space_changed)
        self.addWidget(self._space_cb)
        self.addWidget(_make_sep())
        self._multi_cb = QCheckBox("Multi")
        self._multi_cb.setToolTip("Vertex Tools Multi Gizmo (Translate+Rotate+Scale)")
        self._multi_cb.toggled.connect(self._on_multi_toggled)
        self.addWidget(self._multi_cb)
        self._align_cb = QComboBox()
        self._align_cb.addItems(["Local", "World", "View", "Custom"])
        self._align_cb.setToolTip("Gizmo Alignment - View/World/Local/Custom (Vertex Tools)")
        self._align_cb.currentTextChanged.connect(self._on_align_changed)
        self.addWidget(self._align_cb)
        self._lock_cb = QCheckBox("Lock")
        self._lock_cb.setToolTip("Orientation Lock - retain orientation when rotating")
        self._lock_cb.toggled.connect(self._on_lock_toggled)
        self.addWidget(self._lock_cb)
        self._gizmo_vis_cb = QCheckBox("Gizmo")
        self._gizmo_vis_cb.setChecked(True)
        self._gizmo_vis_cb.setToolTip("Toggle Gizmo Visibility")
        self._gizmo_vis_cb.toggled.connect(self._on_vis_toggled)
        self.addWidget(self._gizmo_vis_cb)
        self._refresh_mode_buttons()

    def _bind_registry(self):
        try:
            reg = _registry_for(self)
            if reg is None:
                return
            reg.bind("gizmo_mode", lambda: self._current_mode, self._set_mode_value, _apply_gizmo_mode)
            reg.bind("gizmo_space", lambda: "world" if self._space_cb.currentText() == "World" else "local", self._set_space_value, _apply_gizmo_space)
            reg.bind("multigizmo_enabled", lambda: bool(self._multi_cb.isChecked()), self._set_multi_value, _apply_multigizmo_enabled)
            reg.bind("multigizmo_alignment", lambda: str(self._align_cb.currentText()).lower(), self._set_align_value, _apply_multigizmo_alignment)
            reg.bind("multigizmo_orientation_lock", lambda: bool(self._lock_cb.isChecked()), self._set_lock_value, _apply_orientation_lock)
            reg.bind("multigizmo_visible", lambda: bool(self._gizmo_vis_cb.isChecked()), self._set_vis_value, _apply_multigizmo_visible)
        except Exception:
            pass

    def _set_mode_value(self, value) -> None:
        try:
            name = str(value).lower()
            if name == "multi":
                return
            if name not in ("none", "translate", "rotate", "scale"):
                return
            self._current_mode = name
            self._refresh_mode_buttons()
        except Exception:
            pass

    def _set_space_value(self, value) -> None:
        try:
            want = "World" if str(value).lower() == "world" else "Local"
            if self._space_cb.currentText() != want:
                self._space_cb.blockSignals(True)
                self._space_cb.setCurrentText(want)
                self._space_cb.blockSignals(False)
        except Exception:
            pass

    def _set_multi_value(self, value) -> None:
        try:
            self._multi_cb.blockSignals(True)
            self._multi_cb.setChecked(bool(value))
            self._multi_cb.blockSignals(False)
            for btn in [self._btn_none, self._btn_translate, self._btn_rotate, self._btn_scale]:
                btn.setEnabled(not bool(value))
        except Exception:
            pass

    def _set_align_value(self, value) -> None:
        try:
            want = str(value).capitalize()
            if want not in ("Local", "World", "View", "Custom"):
                want = "Local"
            self._align_cb.blockSignals(True)
            self._align_cb.setCurrentText(want)
            self._align_cb.blockSignals(False)
        except Exception:
            pass

    def _set_lock_value(self, value) -> None:
        try:
            self._lock_cb.blockSignals(True)
            self._lock_cb.setChecked(bool(value))
            self._lock_cb.blockSignals(False)
        except Exception:
            pass

    def _set_vis_value(self, value) -> None:
        try:
            self._gizmo_vis_cb.blockSignals(True)
            self._gizmo_vis_cb.setChecked(bool(value))
            self._gizmo_vis_cb.blockSignals(False)
        except Exception:
            pass

    def _refresh_mode_buttons(self):
        mapping = {
            "none": self._btn_none,
            "translate": self._btn_translate,
            "rotate": self._btn_rotate,
            "scale": self._btn_scale,
        }
        for name, btn in mapping.items():
            try:
                btn.blockSignals(True)
                btn.setChecked(name == self._current_mode)
                btn.blockSignals(False)
            except Exception:
                pass

    def _on_mode_clicked(self, mode, name: str):
        if self._loading:
            return
        if self._multi_cb.isChecked() and mode != GizmoMode.NONE:
            return
        self._current_mode = name
        self._refresh_mode_buttons()
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("gizmo_mode", name)
        except Exception:
            pass
        self.gizmo_mode_changed.emit(mode)

    def _on_space_changed(self, text: str):
        if self._loading:
            return
        space = GizmoSpace.WORLD if text == "World" else GizmoSpace.LOCAL
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("gizmo_space", "world" if text == "World" else "local")
        except Exception:
            pass
        self.gizmo_space_changed.emit(space)

    def _on_multi_toggled(self, checked: bool):
        for btn in [self._btn_none, self._btn_translate, self._btn_rotate, self._btn_scale]:
            btn.setEnabled(not checked)
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("multigizmo_enabled", bool(checked))
        except Exception:
            pass
        self.multigizmo_toggled.emit(checked)

    def _on_align_changed(self, text: str):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("multigizmo_alignment", text.lower())
        except Exception:
            pass
        self.multigizmo_align_changed.emit(text.lower())

    def _on_lock_toggled(self, checked: bool):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("multigizmo_orientation_lock", bool(checked))
        except Exception:
            pass
        self.multigizmo_lock_toggled.emit(checked)

    def _on_vis_toggled(self, checked: bool):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("multigizmo_visible", bool(checked))
        except Exception:
            pass
        self.multigizmo_visible_toggled.emit(checked)

    def set_gizmo_mode(self, mode) -> None:
        self._set_mode_value(mode.value if hasattr(mode, "value") else str(mode))

    def set_gizmo_space(self, space) -> None:
        self._set_space_value(space.value if hasattr(space, "value") else str(space))

    def save_state(self):
        try:
            reg = _registry_for(self)
            if reg is not None:
                reg.save_ids(list(self.OWNED_IDS))
                return
        except Exception:
            pass

    def load_state(self):
        try:
            reg = _registry_for(self)
            if reg is None:
                return
            self._loading = True
            try:
                reg.load_ids(list(self.OWNED_IDS))
            finally:
                self._loading = False
        except Exception:
            try:
                self._loading = False
            except Exception:
                pass


class RenderToolbar(QToolBar):
    render_mode_changed = Signal(object)
    grid_toggled = Signal(bool)
    snap_toggled = Signal(bool)
    snap_translate_changed = Signal(float)
    snap_rotate_changed = Signal(float)
    snap_scale_changed = Signal(float)
    skybox_toggled = Signal(bool)
    effects_toggled = Signal(bool)
    camera_projection_changed = Signal()
    mode_2d_toggled = Signal()

    OWNED_IDS = ["render_mode", "camera_projection", "camera_2d", "skybox", "effects", "grid", "snap", "snap_translate", "snap_rotate", "snap_scale"]

    def __init__(self, parent=None):
        super().__init__("Render Tools", parent)
        self.setMovable(False)
        self.setIconSize(QSize(16, 16))
        self._loading = False
        self._current_render_mode = "shaded"
        self._setup()
        self._bind_registry()

    def _setup(self):
        self.addWidget(QLabel("Render: "))
        self._shaded_btn = QPushButton(qta.icon("fa5s.fill-drip", color="#d4d4d4"), "")
        self._shaded_btn.setToolTip("Shaded")
        self._shaded_btn.setCheckable(True)
        self._shaded_btn.clicked.connect(lambda: self._on_render_mode_clicked(RenderMode.SHADED, "shaded"))
        self.addWidget(self._shaded_btn)
        self._sh_wire_btn = QPushButton(qta.icon("fa5s.border-all", color="#d4d4d4"), "")
        self._sh_wire_btn.setToolTip("Shaded + Wireframe")
        self._sh_wire_btn.setCheckable(True)
        self._sh_wire_btn.clicked.connect(lambda: self._on_render_mode_clicked(RenderMode.SHADED_WIREFRAME, "shaded_wireframe"))
        self.addWidget(self._sh_wire_btn)
        self._flat_btn = QPushButton(qta.icon("fa5s.adjust", color="#d4d4d4"), "")
        self._flat_btn.setToolTip("Flat (no lighting)")
        self._flat_btn.setCheckable(True)
        self._flat_btn.clicked.connect(lambda: self._on_render_mode_clicked(RenderMode.FLAT, "flat"))
        self.addWidget(self._flat_btn)
        self.addWidget(_make_sep())
        self._cam_persp_btn = QPushButton(qta.icon("fa5s.camera", color="#d4d4d4"), " Perspective")
        self._cam_persp_btn.setToolTip("Toggle Perspective/Orthographic Camera")
        self._cam_persp_btn.setCheckable(True)
        self._cam_persp_btn.setChecked(True)
        self._cam_persp_btn.clicked.connect(self._on_camera_projection_clicked)
        self.addWidget(self._cam_persp_btn)
        self._cam_2d_btn = QPushButton(qta.icon("fa5s.crop-alt", color="#d4d4d4"), "")
        self._cam_2d_btn.setToolTip("Toggle 2D Mode")
        self._cam_2d_btn.setCheckable(True)
        self._cam_2d_btn.clicked.connect(self._on_2d_clicked)
        self.addWidget(self._cam_2d_btn)
        self.addWidget(_make_sep())
        self._skybox_cb = QCheckBox("Skybox")
        self._skybox_cb.setChecked(True)
        self._skybox_cb.toggled.connect(self._on_skybox_toggled)
        self.addWidget(self._skybox_cb)
        self._effects_cb = QCheckBox("FX")
        self._effects_cb.setChecked(True)
        self._effects_cb.setToolTip("Toggle post-processing effects")
        self._effects_cb.toggled.connect(self._on_effects_toggled)
        self.addWidget(self._effects_cb)
        self.addWidget(_make_sep())
        self._grid_cb = QCheckBox("Grid")
        self._grid_cb.setChecked(True)
        self._grid_cb.toggled.connect(self._on_grid_toggled)
        self.addWidget(self._grid_cb)
        self.addWidget(_make_sep())
        self._snap_cb = QCheckBox("Snap")
        self._snap_cb.setChecked(True)
        self._snap_cb.toggled.connect(self._on_snap_toggled)
        self.addWidget(self._snap_cb)
        snap_t_label = QLabel(" T:")
        self.addWidget(snap_t_label)
        self._snap_t_sb = QDoubleSpinBox()
        self._snap_t_sb.setRange(0.0, 100.0)
        self._snap_t_sb.setSingleStep(0.1)
        self._snap_t_sb.setDecimals(3)
        self._snap_t_sb.setValue(0.25)
        self._snap_t_sb.setFixedWidth(scale(65))
        self._snap_t_sb.setToolTip("Translate snap")
        self._snap_t_sb.valueChanged.connect(self._on_snap_t_changed)
        self.addWidget(self._snap_t_sb)
        snap_r_label = QLabel(" R:")
        self.addWidget(snap_r_label)
        self._snap_r_sb = QDoubleSpinBox()
        self._snap_r_sb.setRange(0.0, 360.0)
        self._snap_r_sb.setSingleStep(5.0)
        self._snap_r_sb.setDecimals(1)
        self._snap_r_sb.setValue(15.0)
        self._snap_r_sb.setFixedWidth(scale(60))
        self._snap_r_sb.setToolTip("Rotate snap (degrees)")
        self._snap_r_sb.valueChanged.connect(self._on_snap_r_changed)
        self.addWidget(self._snap_r_sb)
        snap_s_label = QLabel(" S:")
        self.addWidget(snap_s_label)
        self._snap_s_sb = QDoubleSpinBox()
        self._snap_s_sb.setRange(0.0, 100.0)
        self._snap_s_sb.setSingleStep(0.1)
        self._snap_s_sb.setDecimals(3)
        self._snap_s_sb.setValue(0.25)
        self._snap_s_sb.setFixedWidth(scale(60))
        self._snap_s_sb.setToolTip("Scale snap")
        self._snap_s_sb.valueChanged.connect(self._on_snap_s_changed)
        self.addWidget(self._snap_s_sb)
        self._refresh_render_buttons()

    def _bind_registry(self):
        try:
            reg = _registry_for(self)
            if reg is None:
                return
            reg.bind("render_mode", lambda: self._current_render_mode, self._set_render_value, _apply_render_mode)
            reg.bind("camera_projection", lambda: "orthographic" if not self._cam_persp_btn.isChecked() else "perspective", self._set_projection_value, _apply_camera_projection)
            reg.bind("camera_2d", lambda: bool(self._cam_2d_btn.isChecked()), self._set_2d_value, _apply_camera_2d)
            reg.bind("skybox", lambda: bool(self._skybox_cb.isChecked()), self._set_skybox_value, _apply_skybox)
            reg.bind("effects", lambda: bool(self._effects_cb.isChecked()), self._set_effects_value, _apply_effects)
            reg.bind("grid", lambda: bool(self._grid_cb.isChecked()), self._set_grid_value, _apply_grid)
            reg.bind("snap", lambda: bool(self._snap_cb.isChecked()), self._set_snap_value, _apply_snap)
            reg.bind("snap_translate", lambda: float(self._snap_t_sb.value()), self._set_snap_t_value, _apply_snap_translate)
            reg.bind("snap_rotate", lambda: float(self._snap_r_sb.value()), self._set_snap_r_value, _apply_snap_rotate)
            reg.bind("snap_scale", lambda: float(self._snap_s_sb.value()), self._set_snap_s_value, _apply_snap_scale)
        except Exception:
            pass

    def _set_render_value(self, value) -> None:
        try:
            name = str(value).lower()
            if name in ("shaded-wireframe", "shadedwireframe"):
                name = "shaded_wireframe"
            if name not in ("shaded", "shaded_wireframe", "flat"):
                return
            self._current_render_mode = name
            self._refresh_render_buttons()
        except Exception:
            pass

    def _set_projection_value(self, value) -> None:
        try:
            self.set_camera_projection(str(value).lower() == "orthographic")
        except Exception:
            pass

    def _set_2d_value(self, value) -> None:
        try:
            self.set_camera_2d(bool(value))
        except Exception:
            pass

    def _set_skybox_value(self, value) -> None:
        try:
            self._skybox_cb.blockSignals(True)
            self._skybox_cb.setChecked(bool(value))
            self._skybox_cb.blockSignals(False)
        except Exception:
            pass

    def _set_effects_value(self, value) -> None:
        try:
            self._effects_cb.blockSignals(True)
            self._effects_cb.setChecked(bool(value))
            self._effects_cb.blockSignals(False)
        except Exception:
            pass

    def _set_grid_value(self, value) -> None:
        try:
            self._grid_cb.blockSignals(True)
            self._grid_cb.setChecked(bool(value))
            self._grid_cb.blockSignals(False)
        except Exception:
            pass

    def _set_snap_value(self, value) -> None:
        try:
            self._snap_cb.blockSignals(True)
            self._snap_cb.setChecked(bool(value))
            self._snap_cb.blockSignals(False)
        except Exception:
            pass

    def _set_snap_t_value(self, value) -> None:
        try:
            self._snap_t_sb.blockSignals(True)
            self._snap_t_sb.setValue(float(value))
            self._snap_t_sb.blockSignals(False)
        except Exception:
            pass

    def _set_snap_r_value(self, value) -> None:
        try:
            self._snap_r_sb.blockSignals(True)
            self._snap_r_sb.setValue(float(value))
            self._snap_r_sb.blockSignals(False)
        except Exception:
            pass

    def _set_snap_s_value(self, value) -> None:
        try:
            self._snap_s_sb.blockSignals(True)
            self._snap_s_sb.setValue(float(value))
            self._snap_s_sb.blockSignals(False)
        except Exception:
            pass

    def _refresh_render_buttons(self):
        mapping = {
            "shaded": self._shaded_btn,
            "shaded_wireframe": self._sh_wire_btn,
            "flat": self._flat_btn,
        }
        for name, btn in mapping.items():
            try:
                btn.blockSignals(True)
                btn.setChecked(name == self._current_render_mode)
                btn.blockSignals(False)
            except Exception:
                pass

    def _on_render_mode_clicked(self, mode, name: str):
        if self._loading:
            return
        self._current_render_mode = name
        self._refresh_render_buttons()
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("render_mode", name)
        except Exception:
            pass
        self.render_mode_changed.emit(mode)

    def _on_camera_projection_clicked(self):
        if self._loading:
            return
        self.camera_projection_changed.emit()

    def _on_2d_clicked(self):
        if self._loading:
            return
        self.mode_2d_toggled.emit()

    def _on_skybox_toggled(self, checked: bool):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("skybox", bool(checked))
        except Exception:
            pass
        self.skybox_toggled.emit(checked)

    def _on_effects_toggled(self, checked: bool):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("effects", bool(checked))
        except Exception:
            pass
        self.effects_toggled.emit(checked)

    def _on_grid_toggled(self, checked: bool):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("grid", bool(checked))
        except Exception:
            pass
        self.grid_toggled.emit(checked)

    def _on_snap_toggled(self, checked: bool):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("snap", bool(checked))
        except Exception:
            pass
        self.snap_toggled.emit(checked)

    def _on_snap_t_changed(self, value: float):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("snap_translate", float(value))
        except Exception:
            pass
        self.snap_translate_changed.emit(value)

    def _on_snap_r_changed(self, value: float):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("snap_rotate", float(value))
        except Exception:
            pass
        self.snap_rotate_changed.emit(value)

    def _on_snap_s_changed(self, value: float):
        if self._loading:
            return
        try:
            reg = _registry_for(self)
            if reg is not None and not reg.loading:
                reg.store("snap_scale", float(value))
        except Exception:
            pass
        self.snap_scale_changed.emit(value)

    def set_render_mode(self, mode) -> None:
        try:
            name = mode.value if hasattr(mode, "value") else str(mode)
            self._set_render_value(name)
        except Exception:
            pass

    def set_camera_projection(self, is_orthographic: bool) -> None:
        try:
            import editor.icons as _qta
            self._cam_persp_btn.blockSignals(True)
            self._cam_persp_btn.setChecked(not bool(is_orthographic))
            self._cam_persp_btn.blockSignals(False)
            if bool(is_orthographic):
                self._cam_persp_btn.setIcon(_qta.icon("fa5s.camera-retro", color=chr(35) + "d4d4d4"))
                self._cam_persp_btn.setText(" Ortho")
            else:
                self._cam_persp_btn.setIcon(_qta.icon("fa5s.camera", color=chr(35) + "d4d4d4"))
                self._cam_persp_btn.setText(" Perspective")
        except Exception:
            pass

    def set_camera_2d(self, is_2d: bool) -> None:
        try:
            self._cam_2d_btn.blockSignals(True)
            self._cam_2d_btn.setChecked(bool(is_2d))
            self._cam_2d_btn.blockSignals(False)
        except Exception:
            pass

    def save_state(self):
        try:
            reg = _registry_for(self)
            if reg is not None:
                reg.save_ids(list(self.OWNED_IDS))
        except Exception:
            pass

    def load_state(self):
        try:
            reg = _registry_for(self)
            if reg is None:
                return
            self._loading = True
            try:
                reg.load_ids(list(self.OWNED_IDS))
            finally:
                self._loading = False
        except Exception:
            try:
                self._loading = False
            except Exception:
                pass
