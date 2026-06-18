from __future__ import annotations

from PyQt6.QtWidgets import QToolBar, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon

from editor.scene_toolbar import SceneToolbar
from editor.main_window.handlers import toggle_play_stop, reset_camera, on_gizmo_vis_toggled


def setup_toolbar(mw):
    mw._main_toolbar = QToolBar("Main", mw)
    mw._main_toolbar.setObjectName("MainToolbar")
    mw._main_toolbar.setMovable(False)
    mw.addToolBar(Qt.ToolBarArea.TopToolBarArea, mw._main_toolbar)
    mw._play_btn = QPushButton("Play")
    mw._play_btn.setFixedWidth(60)
    mw._play_btn.clicked.connect(lambda: toggle_play_stop(mw))
    mw._main_toolbar.addWidget(mw._play_btn)
    mw._pause_btn = QPushButton("Pause")
    mw._pause_btn.setFixedWidth(60)
    mw._pause_btn.setEnabled(False)
    mw._main_toolbar.addWidget(mw._pause_btn)
    mw._gizmo_vis_act = QAction(QIcon.fromTheme("transform-both", QIcon("")), "Gizmo", mw)
    mw._gizmo_vis_act.setCheckable(True)
    mw._gizmo_vis_act.setChecked(True)
    mw._gizmo_vis_act.setToolTip("Toggle Gizmo Visibility")
    mw._gizmo_vis_act.triggered.connect(lambda c: on_gizmo_vis_toggled(mw, c))
    mw._main_toolbar.addAction(mw._gizmo_vis_act)
    reset_cam_act = QAction("Reset Camera", mw)
    reset_cam_act.setToolTip("Reset Camera Position")
    reset_cam_act.triggered.connect(lambda: reset_camera(mw))
    mw._main_toolbar.addAction(reset_cam_act)
    mw._main_toolbar.addSeparator()
    mw._scene_toolbar = SceneToolbar(mw)
    mw._scene_toolbar.setObjectName("SceneToolbar")
    mw._main_toolbar.addWidget(mw._scene_toolbar)
    add_plugin_toolbar_actions(mw)


def add_plugin_toolbar_actions(mw):
    registry = mw._engine.plugin_ui_registry
    for info in registry["toolbar_actions"]:
        try:
            text = info["text"]
            callback = info["callback"]
            tooltip = info.get("tooltip", text)
            icon_path = info.get("icon")
            if icon_path:
                act = QAction(QIcon(icon_path), text, mw)
            else:
                act = QAction(text, mw)
            act.setToolTip(tooltip)
            act.triggered.connect(callback)
            mw._main_toolbar.addAction(act)
        except Exception as e:
            from core.logger import Logger
            Logger.error(f"Failed to add plugin toolbar action '{info.get('text', '?')}': {e}")
