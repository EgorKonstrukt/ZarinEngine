from __future__ import annotations

from core.config.editor_scale import scale, scale_xy
from PyQt6.QtWidgets import (QToolBar, QPushButton, QLabel, QDoubleSpinBox, QComboBox,
                             QWidget, QSizePolicy, QHBoxLayout, QVBoxLayout,
                             QFrame, QToolButton, QTabBar)
from PyQt6.QtCore import Qt, QSize
import qtawesome as qta
from PyQt6.QtGui import QAction, QIcon

from editor.scene_toolbar import SceneToolbar, RenderToolbar
from editor.main_window.handlers import toggle_play_stop, reset_camera, on_gizmo_vis_toggled, launch_external_player


def _set_play_btn_style(btn, text):
    if text == "Play":
        btn.setStyleSheet("QPushButton { background: #2e7d32; color: #fff; }")
        btn.setIcon(qta.icon("fa5s.play", color="#fff"))
    elif text == "Stop":
        btn.setStyleSheet("QPushButton { background: #c0392b; color: #fff; }")
        btn.setIcon(qta.icon("fa5s.stop", color="#fff"))
    btn.setText(text)


def _action_to_toolbutton(action, parent=None) -> QToolButton:
    btn = QToolButton(parent)
    btn.setDefaultAction(action)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    btn.setAutoRaise(True)
    return btn


def setup_toolbar(mw):
    mw._main_toolbar = QToolBar("Main", mw)
    mw._main_toolbar.setObjectName("MainToolbar")
    mw._main_toolbar.setMovable(False)
    mw._main_toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    s = scale_xy(18, 18)
    mw._main_toolbar.setIconSize(QSize(*s))
    mw.addToolBar(Qt.ToolBarArea.TopToolBarArea, mw._main_toolbar)

    # Main container with vertical layout: row1 = toolbar, row2 = tabs
    container = QWidget()
    container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    main_lay = QVBoxLayout(container)
    main_lay.setContentsMargins(0, 0, 0, 0)
    main_lay.setSpacing(0)

    # Row 1: toolbar content
    top_widget = QWidget()
    top_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay = QHBoxLayout(top_widget)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)

    # ── Left section ──
    mw._gizmo_vis_act = QAction(qta.icon("fa5s.mouse-pointer", color="#d4d4d4"), "Gizmo", mw)
    mw._gizmo_vis_act.setCheckable(True)
    mw._gizmo_vis_act.setChecked(True)
    mw._gizmo_vis_act.setToolTip("Toggle Gizmo Visibility")
    mw._gizmo_vis_act.triggered.connect(lambda c: on_gizmo_vis_toggled(mw, c))
    lay.addWidget(_action_to_toolbutton(mw._gizmo_vis_act, mw))

    reset_cam_btn = QToolButton(mw)
    reset_cam_btn.setIcon(qta.icon("fa5s.crosshairs", color="#d4d4d4"))
    reset_cam_btn.setToolTip("Reset Camera Position")
    reset_cam_btn.setAutoRaise(True)
    reset_cam_btn.clicked.connect(lambda: reset_camera(mw))
    lay.addWidget(reset_cam_btn)

    nav_label = QLabel("Nav:")
    lay.addWidget(nav_label)
    mw._nav_mode_cb = QComboBox(mw)
    mw._nav_mode_cb.addItems(["Fly", "Orbit"])
    mw._nav_mode_cb.setToolTip("Fly: WASD + RMB look, MMB pan, wheel dolly. Orbit: RMB orbit around 3D cursor, MMB pan like fly, Shift+RMB click places cursor, Ctrl+MMB / wheel dolly")
    mw._nav_mode_cb.setFixedWidth(scale(90))
    lay.addWidget(mw._nav_mode_cb)

    def _on_nav_mode_selected(text: str):
        mode = "orbit" if text == "Orbit" else "fly"
        try:
            vp = getattr(mw, "_viewport", None)
            cam = getattr(vp, "camera", None) if vp is not None else None
            if cam is None and vp is not None:
                cam = getattr(vp, "_cam", None)
            if cam is not None:
                cam.set_nav_mode(mode)
        except Exception:
            pass
        try:
            from core.config.config import get_global_config
            cfg = get_global_config()
            cfg.set("camera.nav_mode", mode)
            cfg.save()
        except Exception:
            pass
        try:
            if vp is not None:
                vp.update()
        except Exception:
            pass

    mw._nav_mode_cb.currentTextChanged.connect(_on_nav_mode_selected)

    def _sync_nav_mode_ui(mode: str):
        try:
            want = "Orbit" if mode == "orbit" else "Fly"
            cb = getattr(mw, "_nav_mode_cb", None)
            if cb is not None and cb.currentText() != want:
                cb.blockSignals(True)
                cb.setCurrentText(want)
                cb.blockSignals(False)
        except Exception:
            pass

    mw._sync_nav_mode_ui = _sync_nav_mode_ui
    try:
        vp0 = getattr(mw, "_viewport", None)
        cam0 = getattr(vp0, "_cam", None) if vp0 is not None else None
        if cam0 is not None:
            cur0 = getattr(cam0, "_nav_mode", "fly")
            mw._nav_mode_cb.blockSignals(True)
            mw._nav_mode_cb.setCurrentText("Orbit" if cur0 == "orbit" else "Fly")
            mw._nav_mode_cb.blockSignals(False)
            cam0._on_nav_mode_changed = _sync_nav_mode_ui
    except Exception:
        pass

    mw._scene_toolbar = SceneToolbar(mw)
    mw._scene_toolbar.setObjectName("SceneToolbar")
    lay.addWidget(mw._scene_toolbar)

    sep_left = QFrame()
    sep_left.setFrameShape(QFrame.Shape.VLine)
    sep_left.setFrameShadow(QFrame.Shadow.Sunken)
    lay.addWidget(sep_left)

    # ── Stretch: push center toward middle ──
    lay.addStretch(1)

    # ── Center section: Play/Stop, Pause, Time Scale ──
    mw._play_btn = QPushButton("Play")
    _set_play_btn_style(mw._play_btn, "Play")
    mw._play_btn.setFixedWidth(scale(90))
    mw._play_btn.clicked.connect(lambda: toggle_play_stop(mw))
    lay.addWidget(mw._play_btn)

    mw._pause_btn = QPushButton(qta.icon("fa5s.pause", color="#fff"), " Pause")
    mw._pause_btn.setStyleSheet(
        "QPushButton { background: #b7950b; color: #fff; }"
        "QPushButton:disabled { background: #5a5a5a; color: #888; }"
    )
    mw._pause_btn.setFixedWidth(scale(90))
    mw._pause_btn.setEnabled(False)
    lay.addWidget(mw._pause_btn)

    mw._player_btn = QPushButton(qta.icon("fa5s.gamepad", color="white"), " Player")
    mw._player_btn.setStyleSheet("QPushButton { background: rgb(106,27,154); color: rgb(255,255,255); }")
    mw._player_btn.setFixedWidth(scale(90))
    mw._player_btn.setToolTip("Launch in standalone Player")
    mw._player_btn.clicked.connect(lambda: launch_external_player(mw))
    lay.addWidget(mw._player_btn)

    ts_label = QLabel(" TS:")
    lay.addWidget(ts_label)
    mw._ts_sb = QDoubleSpinBox()
    mw._ts_sb.setRange(0.0, 10.0)
    mw._ts_sb.setSingleStep(0.1)
    mw._ts_sb.setDecimals(2)
    mw._ts_sb.setValue(1.0)
    mw._ts_sb.setFixedWidth(scale(70))
    mw._ts_sb.valueChanged.connect(lambda v: setattr(mw._engine, "time_scale", v))
    lay.addWidget(mw._ts_sb)

    # ── Stretch: push center toward middle ──
    lay.addStretch(1)

    sep_right = QFrame()
    sep_right.setFrameShape(QFrame.Shape.VLine)
    sep_right.setFrameShadow(QFrame.Shadow.Sunken)
    lay.addWidget(sep_right)

    # ── Right section: render/camera/snap + plugins ──
    mw._render_toolbar = RenderToolbar(mw)
    mw._render_toolbar.setObjectName("RenderToolbar")
    lay.addWidget(mw._render_toolbar)

    add_plugin_toolbar_actions(mw, lay)
    subscribe_plugin_toolbar_updates(mw)

    main_lay.addWidget(top_widget)

    # Row 2: Scene tab bar
    mw._scene_tab_bar = QTabBar()
    mw._scene_tab_bar.setObjectName("SceneTabBar")
    mw._scene_tab_bar.setDrawBase(False)
    mw._scene_tab_bar.setExpanding(False)
    mw._scene_tab_bar.setTabsClosable(True)
    mw._scene_tab_bar.setMovable(True)

    main_lay.addWidget(mw._scene_tab_bar)

    mw._main_toolbar.addWidget(container)


def _plugin_toolbar_icon(icon):
    if not icon:
        return None
    try:
        return qta.icon(icon, color="#d4d4d4")
    except Exception:
        try:
            return QIcon(str(icon))
        except Exception:
            return None


def _append_plugin_toolbar_action(mw, layout, info: dict):
    try:
        text = info["text"]
        callback = info["callback"]
        tooltip = info.get("tooltip", text)
        icon = _plugin_toolbar_icon(info.get("icon"))
        act = QAction(icon, text, mw) if icon is not None else QAction(text, mw)
        act.setToolTip(tooltip)
        act.setProperty("plugin", info.get("plugin", "Plugins"))
        act.triggered.connect(callback)
        layout.addWidget(_action_to_toolbutton(act, mw))
    except Exception as e:
        from core.foundation.logger import Logger
        Logger.error(f"Failed to add plugin toolbar action '{info.get('text', '?')}': {e}")


def _remove_plugin_toolbar_actions(mw, plugin_name: str):
    layout = getattr(mw, "_plugin_toolbar_layout", None)
    if layout is None:
        return
    for i in range(layout.count()):
        try:
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            act = w.defaultAction() if w is not None and hasattr(w, "defaultAction") else None
            if act is not None and act.property("plugin") == plugin_name:
                layout.removeWidget(w)
                w.deleteLater()
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.warning(f"[Plugin] toolbar cleanup failed: {e}")


def subscribe_plugin_toolbar_updates(mw):
    reg = mw._engine.plugin_ui_registry
    listeners = reg.setdefault("runtime_listeners", [])
    for cb in listeners:
        if getattr(cb, "_zpl_scope", None) == "toolbar" and getattr(cb, "_zpl_mw", None) is mw:
            return
    def _on_runtime(payload):
        try:
            name = payload.get("unregistered")
            if name:
                _remove_plugin_toolbar_actions(mw, name)
                return
            layout = getattr(mw, "_plugin_toolbar_layout", None)
            if layout is None:
                return
            for info in payload.get("toolbar_actions", []) or []:
                _append_plugin_toolbar_action(mw, layout, info)
        except Exception as e:
            from core.foundation.logger import Logger
            Logger.error(f"[Plugin] toolbar update failed: {e}", e)
    _on_runtime._zpl_scope = "toolbar"
    _on_runtime._zpl_mw = mw
    listeners.append(_on_runtime)


def add_plugin_toolbar_actions(mw, layout):
    registry = mw._engine.plugin_ui_registry
    mw._plugin_toolbar_layout = layout
    for info in registry.get("toolbar_actions", []):
        _append_plugin_toolbar_action(mw, layout, info)
