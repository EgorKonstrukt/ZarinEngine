from __future__ import annotations

from core.config.editor_scale import scale, scale_xy
from PySide6.QtWidgets import (QToolBar, QPushButton, QLabel, QDoubleSpinBox, QComboBox,
                             QWidget, QSizePolicy, QHBoxLayout, QVBoxLayout,
                             QFrame, QToolButton, QTabBar, QCheckBox)
from PySide6.QtCore import Qt, QSize
import editor.icons as qta
from PySide6.QtGui import QAction, QIcon

from editor.scene_toolbar import SceneToolbar, RenderToolbar
from editor.main_window.handlersp import toggle_play_stop, reset_camera, on_gizmo_vis_toggled, launch_external_player
from editor.main_window.palettep import show_command_palette


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


def _apply_gizmo_visible(mw, value) -> None:
    try:
        vp = getattr(mw, "_viewport", None)
        if vp is not None:
            vp._gizmo_visible = bool(value)
            vp._gizmo_icons_visible = bool(value)
            try:
                vp.update()
            except Exception:
                pass
        try:
            act = getattr(mw, "_gizmo_vis_act", None)
            if act is not None and act.isChecked() != bool(value):
                act.blockSignals(True)
                act.setChecked(bool(value))
                act.blockSignals(False)
        except Exception:
            pass
    except Exception:
        pass


def _apply_nav_mode(mw, value) -> None:
    try:
        mode = str(value).lower()
        if mode not in ("fly", "orbit"):
            mode = "fly"
        vp = getattr(mw, "_viewport", None)
        cam = getattr(vp, "camera", None) if vp is not None else None
        if cam is None and vp is not None:
            cam = getattr(vp, "_cam", None)
        if cam is not None:
            try:
                cam.set_nav_mode(mode)
            except Exception:
                pass
        try:
            sync_fn = getattr(mw, "_sync_nav_mode_ui", None)
            if callable(sync_fn):
                sync_fn(mode)
        except Exception:
            pass
    except Exception:
        pass


def _apply_time_scale(mw, value) -> None:
    try:
        mw._engine.time_scale = float(value)
    except Exception:
        pass


def _registry(mw):
    try:
        from editor.toolbar_registry import get_toolbar_registry
        return get_toolbar_registry(mw)
    except Exception:
        return None


def register_toolbar_check(mw, layout, item_id: str, text: str, tooltip: str = "", config_key: str = "", default: bool = False, apply=None):
    try:
        from editor.toolbar_registry import define_toolbar_item
        key = config_key or f"toolbar.{item_id}"
        define_toolbar_item(item_id, key, bool(default), kind="check")
        reg = _registry(mw)
        cb = QCheckBox(text, mw)
        cb.setChecked(bool(default))
        if tooltip:
            cb.setToolTip(tooltip)
        layout.addWidget(cb)
        if reg is not None:
            reg.bind(item_id, lambda c=cb: bool(c.isChecked()), lambda v, c=cb: (c.blockSignals(True), c.setChecked(bool(v)), c.blockSignals(False)), apply)
            cb.toggled.connect(lambda checked, _id=item_id, _r=reg: _r.store(_id, bool(checked)))
            if callable(apply):
                cb.toggled.connect(lambda checked, _id=item_id, _r=reg: _r.apply_one(_id, mw, bool(checked)))
        return cb
    except Exception:
        return None


def register_toolbar_combo(mw, layout, item_id: str, options: list, tooltip: str = "", config_key: str = "", default: str = "", apply=None, width: int = 90):
    try:
        from editor.toolbar_registry import define_toolbar_item
        opts = list(options or [])
        key = config_key or f"toolbar.{item_id}"
        define_toolbar_item(item_id, key, default if default else (opts[0] if opts else ""), kind="combo", options=opts)
        reg = _registry(mw)
        cb = QComboBox(mw)
        cb.addItems(opts)
        if tooltip:
            cb.setToolTip(tooltip)
        cb.setFixedWidth(scale(width))
        layout.addWidget(cb)
        if reg is not None:
            reg.bind(item_id, lambda c=cb: str(c.currentText()), lambda v, c=cb: (c.blockSignals(True), c.setCurrentText(str(v)), c.blockSignals(False)), apply)
            cb.currentTextChanged.connect(lambda text, _id=item_id, _r=reg: _r.store(_id, str(text)))
            if callable(apply):
                cb.currentTextChanged.connect(lambda text, _id=item_id, _r=reg: _r.apply_one(_id, mw, str(text)))
        return cb
    except Exception:
        return None


def register_toolbar_spin(mw, layout, item_id: str, tooltip: str = "", config_key: str = "", default: float = 0.0, minimum: float = 0.0, maximum: float = 100.0, apply=None, width: int = 70):
    try:
        from editor.toolbar_registry import define_toolbar_item
        key = config_key or f"toolbar.{item_id}"
        define_toolbar_item(item_id, key, float(default), kind="spin")
        reg = _registry(mw)
        sb = QDoubleSpinBox(mw)
        sb.setRange(float(minimum), float(maximum))
        sb.setValue(float(default))
        if tooltip:
            sb.setToolTip(tooltip)
        sb.setFixedWidth(scale(width))
        layout.addWidget(sb)
        if reg is not None:
            reg.bind(item_id, lambda s=sb: float(s.value()), lambda v, s=sb: (s.blockSignals(True), s.setValue(float(v)), s.blockSignals(False)), apply)
            sb.valueChanged.connect(lambda v, _id=item_id, _r=reg: _r.store(_id, float(v)))
            if callable(apply):
                sb.valueChanged.connect(lambda v, _id=item_id, _r=reg: _r.apply_one(_id, mw, float(v)))
        return sb
    except Exception:
        return None


def setup_toolbar(mw):
    mw._main_toolbar = QToolBar("Main", mw)
    mw._main_toolbar.setObjectName("MainToolbar")
    mw._main_toolbar.setMovable(False)
    mw._main_toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    s = scale_xy(18, 18)
    mw._main_toolbar.setIconSize(QSize(*s))
    mw.addToolBar(Qt.ToolBarArea.TopToolBarArea, mw._main_toolbar)
    container = QWidget()
    container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    main_lay = QVBoxLayout(container)
    main_lay.setContentsMargins(0, 0, 0, 0)
    main_lay.setSpacing(0)
    top_widget = QWidget()
    top_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay = QHBoxLayout(top_widget)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    mw._toolbar_loading = False
    reg = _registry(mw)
    mw._gizmo_vis_act = QAction(qta.icon("fa5s.mouse-pointer", color="#d4d4d4"), "Gizmo", mw)
    mw._gizmo_vis_act.setCheckable(True)
    mw._gizmo_vis_act.setChecked(True)
    mw._gizmo_vis_act.setToolTip("Toggle Gizmo Visibility")
    mw._gizmo_vis_act.triggered.connect(lambda c: on_gizmo_vis_toggled(mw, c))
    lay.addWidget(_action_to_toolbutton(mw._gizmo_vis_act, mw))
    if reg is not None:
        try:
            reg.bind("gizmo_visible", lambda: bool(mw._gizmo_vis_act.isChecked()), lambda v: (mw._gizmo_vis_act.blockSignals(True), mw._gizmo_vis_act.setChecked(bool(v)), mw._gizmo_vis_act.blockSignals(False)), _apply_gizmo_visible)
        except Exception:
            pass
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
        if getattr(mw, "_toolbar_loading", False):
            return
        mode = "orbit" if text == "Orbit" else "fly"
        try:
            if reg is not None and not reg.loading:
                reg.store("nav_mode", mode)
        except Exception:
            pass
        try:
            if reg is not None:
                reg.apply_one("nav_mode", mw, mode)
        except Exception:
            pass
        try:
            vp = getattr(mw, "_viewport", None)
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
    if reg is not None:
        try:
            reg.bind("nav_mode", lambda: "orbit" if mw._nav_mode_cb.currentText() == "Orbit" else "fly", lambda v: (mw._nav_mode_cb.blockSignals(True), mw._nav_mode_cb.setCurrentText("Orbit" if str(v).lower() == "orbit" else "Fly"), mw._nav_mode_cb.blockSignals(False)), _apply_nav_mode)
        except Exception:
            pass
    try:
        vp0 = getattr(mw, "_viewport", None)
        cam0 = getattr(vp0, "_cam", None) if vp0 is not None else None
        if cam0 is not None:
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
    mw._search_btn = QPushButton(qta.icon("fa5s.search", color="#fff"), " Search")
    mw._search_btn.setToolTip("Search Everywhere (Ctrl+F)")
    mw._search_btn.setFixedWidth(scale(90))
    mw._search_btn.clicked.connect(lambda: show_command_palette(mw))
    lay.addWidget(mw._search_btn)
    lay.addStretch(1)
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

    def _on_ts_changed(v: float):
        if getattr(mw, "_toolbar_loading", False):
            return
        try:
            if reg is not None and not reg.loading:
                reg.store("time_scale", float(v))
        except Exception:
            pass
        try:
            if reg is not None:
                reg.apply_one("time_scale", mw, float(v))
        except Exception:
            pass

    mw._ts_sb.valueChanged.connect(_on_ts_changed)
    lay.addWidget(mw._ts_sb)
    if reg is not None:
        try:
            reg.bind("time_scale", lambda: float(mw._ts_sb.value()), lambda v: (mw._ts_sb.blockSignals(True), mw._ts_sb.setValue(float(v)), mw._ts_sb.blockSignals(False)), _apply_time_scale)
        except Exception:
            pass
    lay.addStretch(1)
    sep_right = QFrame()
    sep_right.setFrameShape(QFrame.Shape.VLine)
    sep_right.setFrameShadow(QFrame.Shadow.Sunken)
    lay.addWidget(sep_right)
    mw._render_toolbar = RenderToolbar(mw)
    mw._render_toolbar.setObjectName("RenderToolbar")
    lay.addWidget(mw._render_toolbar)
    add_plugin_toolbar_actions(mw, lay)
    add_plugin_toolbar_items(mw, lay)
    subscribe_plugin_toolbar_updates(mw)
    main_lay.addWidget(top_widget)
    mw._scene_tab_bar = QTabBar()
    mw._scene_tab_bar.setObjectName("SceneTabBar")
    mw._scene_tab_bar.setDrawBase(False)
    mw._scene_tab_bar.setExpanding(False)
    mw._scene_tab_bar.setTabsClosable(True)
    mw._scene_tab_bar.setMovable(True)
    mw._scene_tab_bar.setDocumentMode(False)
    mw._scene_tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
    mw._scene_tab_bar.setStyleSheet(
        "QTabBar#SceneTabBar::tab { border-top: 2px solid transparent; }"
        "QTabBar#SceneTabBar::tab:selected { border-top: 2px solid #007acc; }"
        "QTabBar#SceneTabBar::close-button:hover { background: #e81123; }"
    )
    main_lay.addWidget(mw._scene_tab_bar)
    mw._main_toolbar.addWidget(container)
    try:
        load_main_toolbar_state(mw)
    except Exception:
        pass
    try:
        apply_toolbar_runtime_state(mw)
    except Exception:
        pass


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


def _append_plugin_toolbar_item(mw, layout, info: dict):
    try:
        from editor.toolbar_registry import define_toolbar_item, get_toolbar_registry
        item_id = str(info.get("item_id", ""))
        if not item_id:
            return
        kind = str(info.get("kind", "check")).lower()
        config_key = str(info.get("config_key", "") or f"toolbar_plugins.{info.get('plugin', 'Plugins')}.{item_id}")
        default = info.get("default", False if kind == "check" else "")
        options = info.get("options") or []
        define_toolbar_item(item_id, config_key, default, kind=kind, options=list(options) if options else None)
        reg = get_toolbar_registry(mw)
        callback = info.get("callback")
        plugin = str(info.get("plugin", "Plugins"))

        def _plugin_apply(target, value, _cb=callback):
            try:
                if callable(_cb):
                    try:
                        _cb(value)
                    except Exception:
                        try:
                            _cb(target, value)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                vp = getattr(target, "_viewport", None)
                if vp is not None:
                    vp.update()
            except Exception:
                pass

        if kind == "check":
            text = str(info.get("text", item_id))
            cb = QCheckBox(text, mw)
            cb.setChecked(bool(default))
            tooltip = str(info.get("tooltip", text))
            if tooltip:
                cb.setToolTip(tooltip)
            cb.setProperty("plugin", plugin)
            cb.setProperty("toolbar_item_id", item_id)
            layout.addWidget(cb)
            reg.bind(item_id, lambda c=cb: bool(c.isChecked()), lambda v, c=cb: (c.blockSignals(True), c.setChecked(bool(v)), c.blockSignals(False)), _plugin_apply)
            cb.toggled.connect(lambda checked, _id=item_id, _r=reg: _r.store(_id, bool(checked)))
            cb.toggled.connect(lambda checked, _id=item_id, _r=reg: _r.apply_one(_id, mw, bool(checked)))
        elif kind == "combo":
            combo = QComboBox(mw)
            combo.addItems([str(o) for o in options])
            try:
                combo.setCurrentText(str(default))
            except Exception:
                pass
            tooltip = str(info.get("tooltip", ""))
            if tooltip:
                combo.setToolTip(tooltip)
            combo.setProperty("plugin", plugin)
            combo.setProperty("toolbar_item_id", item_id)
            combo.setFixedWidth(scale(110))
            layout.addWidget(combo)
            reg.bind(item_id, lambda c=combo: str(c.currentText()), lambda v, c=combo: (c.blockSignals(True), c.setCurrentText(str(v)), c.blockSignals(False)), _plugin_apply)
            combo.currentTextChanged.connect(lambda text, _id=item_id, _r=reg: _r.store(_id, str(text)))
            combo.currentTextChanged.connect(lambda text, _id=item_id, _r=reg: _r.apply_one(_id, mw, str(text)))
        elif kind == "spin":
            sb = QDoubleSpinBox(mw)
            try:
                sb.setRange(float(info.get("minimum", 0.0)), float(info.get("maximum", 100.0)))
            except Exception:
                pass
            try:
                sb.setValue(float(default))
            except Exception:
                pass
            tooltip = str(info.get("tooltip", ""))
            if tooltip:
                sb.setToolTip(tooltip)
            sb.setProperty("plugin", plugin)
            sb.setProperty("toolbar_item_id", item_id)
            sb.setFixedWidth(scale(80))
            layout.addWidget(sb)
            reg.bind(item_id, lambda s=sb: float(s.value()), lambda v, s=sb: (s.blockSignals(True), s.setValue(float(v)), s.blockSignals(False)), _plugin_apply)
            sb.valueChanged.connect(lambda v, _id=item_id, _r=reg: _r.store(_id, float(v)))
            sb.valueChanged.connect(lambda v, _id=item_id, _r=reg: _r.apply_one(_id, mw, float(v)))
        try:
            reg.load_ids([item_id])
            reg.apply_ids([item_id], mw)
        except Exception:
            pass
    except Exception as e:
        try:
            from core.foundation.logger import Logger
            Logger.error(f"Failed to add plugin toolbar item '{info.get('item_id', '?')}': {e}")
        except Exception:
            pass


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


def _remove_plugin_toolbar_items(mw, plugin_name: str):
    try:
        from editor.toolbar_registry import get_toolbar_registry
        reg = get_toolbar_registry(mw)
        layout = getattr(mw, "_plugin_toolbar_layout", None)
        if layout is None:
            return
        for i in range(layout.count() - 1, -1, -1):
            try:
                item = layout.itemAt(i)
                w = item.widget() if item is not None else None
                if w is None:
                    continue
                try:
                    prop = w.property("plugin")
                except Exception:
                    prop = None
                try:
                    item_id = w.property("toolbar_item_id")
                except Exception:
                    item_id = None
                if prop == plugin_name and item_id:
                    layout.removeWidget(w)
                    try:
                        reg.unbind(str(item_id))
                    except Exception:
                        pass
                    w.deleteLater()
            except Exception:
                pass
    except Exception:
        pass


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
                _remove_plugin_toolbar_items(mw, name)
                return
            layout = getattr(mw, "_plugin_toolbar_layout", None)
            if layout is None:
                return
            for info in payload.get("toolbar_actions", []) or []:
                _append_plugin_toolbar_action(mw, layout, info)
            for info in payload.get("toolbar_items", []) or []:
                _append_plugin_toolbar_item(mw, layout, info)
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


def add_plugin_toolbar_items(mw, layout):
    try:
        registry = mw._engine.plugin_ui_registry
        for info in registry.get("toolbar_items", []) or []:
            _append_plugin_toolbar_item(mw, layout, info)
    except Exception:
        pass


def save_main_toolbar_state(mw) -> None:
    try:
        from editor.toolbar_registry import get_toolbar_registry
        get_toolbar_registry(mw).save()
    except Exception:
        pass


def load_main_toolbar_state(mw) -> None:
    try:
        mw._toolbar_loading = True
        try:
            from editor.toolbar_registry import get_toolbar_registry
            get_toolbar_registry(mw).load()
        finally:
            mw._toolbar_loading = False
    except Exception:
        try:
            mw._toolbar_loading = False
        except Exception:
            pass


def apply_toolbar_runtime_state(mw) -> None:
    try:
        from editor.toolbar_registry import get_toolbar_registry
        get_toolbar_registry(mw).apply(mw)
        try:
            vp = getattr(mw, "_viewport", None)
            if vp is not None:
                vp.update()
        except Exception:
            pass
    except Exception:
        pass
