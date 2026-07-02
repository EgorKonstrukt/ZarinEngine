# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.editor_scale import scale, scale_xy
from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSpinBox, QVBoxLayout, QWidget, QWidgetAction

from core.math3d import Vec3


def setup_toolbar(vp):
    vp._toolbar = QFrame(vp)
    vp._toolbar.setStyleSheet("""
        QFrame {
            background-color: rgba(30, 30, 30, 200);
            border-bottom: 1px solid #444;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
    """)
    toolbar_layout = QVBoxLayout(vp._toolbar)
    toolbar_layout.setContentsMargins(8, 4, 8, 4)
    toolbar_layout.setSpacing(4)

    cam_row = QHBoxLayout()
    vp._cam_menu_btn = QPushButton("Camera")
    vp._cam_menu_btn.setMenu(create_camera_menu(vp))
    vp._cam_menu_btn.setMinimumWidth(80)
    vp._cam_menu_btn.setStyleSheet("""
        QPushButton {
            background-color: #2a2a2a;
            color: #ddd;
            border: 1px solid #444;
            border-radius: 3px;
            padding: 3px 8px;
            font-size: 10px;
        }
    """)
    cam_row.addWidget(vp._cam_menu_btn)

    vp._stats_btn = QPushButton("Stats")
    vp._stats_btn.setCheckable(True)
    vp._stats_btn.setMinimumWidth(60)
    vp._stats_btn.setStyleSheet("""
        QPushButton {
            background-color: #2a2a2a;
            color: #ddd;
            border: 1px solid #444;
            border-radius: 3px;
            padding: 3px 8px;
            font-size: 10px;
        }
        QPushButton:checked {
            background-color: #2d5a8e;
            color: #fff;
            border: 1px solid #4a7ab5;
        }
    """)
    vp._stats_btn.clicked.connect(vp._toggle_stats)
    cam_row.addWidget(vp._stats_btn)

    vp._bvh_btn = QPushButton("BVH")
    vp._bvh_btn.setCheckable(True)
    vp._bvh_btn.setMinimumWidth(40)
    vp._bvh_btn.setStyleSheet("""
        QPushButton {
            background-color: #2a2a2a;
            color: #ddd;
            border: 1px solid #444;
            border-radius: 3px;
            padding: 3px 8px;
            font-size: 10px;
        }
        QPushButton:checked {
            background-color: #8e5d2d;
            color: #fff;
            border: 1px solid #b57a4a;
        }
    """)
    vp._bvh_btn.clicked.connect(vp._toggle_bvh_debug)
    cam_row.addWidget(vp._bvh_btn)

    vp._depth_spin = QSpinBox()
    vp._depth_spin.setRange(0, 32)
    vp._depth_spin.setValue(24)
    vp._depth_spin.setMinimumWidth(50)
    cam_row.addWidget(vp._depth_spin)

    depth_label = QLabel("Depth")
    cam_row.addWidget(depth_label)
    cam_row.addStretch()

    vp._cam_pos_label = QLabel("Cam: 0.0, 0.0, 0.0")
    vp._cam_pos_label.setStyleSheet("color: #aaa; font-size: 10px;")
    cam_row.addWidget(vp._cam_pos_label)

    vp._cursor_x_label = QLabel("X: -")
    vp._cursor_x_label.setStyleSheet("color: #ff4444; font-size: 10px;")
    cam_row.addWidget(vp._cursor_x_label)

    vp._cursor_y_label = QLabel("Y: -")
    vp._cursor_y_label.setStyleSheet("color: #44cc44; font-size: 10px;")
    cam_row.addWidget(vp._cursor_y_label)

    vp._cursor_z_label = QLabel("Z: -")
    vp._cursor_z_label.setStyleSheet("color: #4488ff; font-size: 10px;")
    cam_row.addWidget(vp._cursor_z_label)

    toolbar_layout.addLayout(cam_row)

    vp._depth_spin.valueChanged.connect(vp._on_depth_changed)
    vp._depth_spin.installEventFilter(vp)
    vp._toolbar.setFixedHeight(scale(35))


def create_camera_menu(vp):
    menu = QMenu(vp._toolbar)

    fov_label_w = QWidget()
    fov_label_layout = QHBoxLayout(fov_label_w)
    fov_label_layout.setContentsMargins(4, 2, 4, 2)
    fov_label_layout.addWidget(QLabel("FOV"))
    fov_label_layout.addStretch()
    fov_label_action = QWidgetAction(menu)
    fov_label_action.setDefaultWidget(fov_label_w)
    menu.addAction(fov_label_action)

    vp._fov_spin = QDoubleSpinBox()
    vp._fov_spin.setRange(1.0, 179.0)
    vp._fov_spin.setValue(vp._cam._fov if hasattr(vp._cam, '_fov') else vp._cam.DEFAULT_FOV)
    vp._fov_spin.setSingleStep(5.0)
    vp._fov_spin.setDecimals(1)
    vp._fov_spin.setMinimumWidth(80)
    fov_widget = QWidget()
    fov_layout = QHBoxLayout(fov_widget)
    fov_layout.setContentsMargins(4, 2, 4, 2)
    fov_layout.addWidget(vp._fov_spin)
    vp._fov_spin.valueChanged.connect(vp._on_fov_changed)
    fov_spin_action = QWidgetAction(menu)
    fov_spin_action.setDefaultWidget(fov_widget)
    menu.addAction(fov_spin_action)

    near_label_w = QWidget()
    near_label_layout = QHBoxLayout(near_label_w)
    near_label_layout.setContentsMargins(4, 2, 4, 2)
    near_label_layout.addWidget(QLabel("Near"))
    near_label_layout.addStretch()
    near_label_action = QWidgetAction(menu)
    near_label_action.setDefaultWidget(near_label_w)
    menu.addAction(near_label_action)

    vp._near_spin = QDoubleSpinBox()
    vp._near_spin.setRange(0.001, 10.0)
    vp._near_spin.setValue(vp._cam._near if hasattr(vp._cam, '_near') else vp._cam.DEFAULT_NEAR)
    vp._near_spin.setSingleStep(0.01)
    vp._near_spin.setDecimals(3)
    vp._near_spin.setMinimumWidth(80)
    near_widget = QWidget()
    near_layout = QHBoxLayout(near_widget)
    near_layout.setContentsMargins(4, 2, 4, 2)
    near_layout.addWidget(vp._near_spin)
    vp._near_spin.valueChanged.connect(vp._on_near_changed)
    near_spin_action = QWidgetAction(menu)
    near_spin_action.setDefaultWidget(near_widget)
    menu.addAction(near_spin_action)

    far_label_w = QWidget()
    far_label_layout = QHBoxLayout(far_label_w)
    far_label_layout.setContentsMargins(4, 2, 4, 2)
    far_label_layout.addWidget(QLabel("Far"))
    far_label_layout.addStretch()
    far_label_action = QWidgetAction(menu)
    far_label_action.setDefaultWidget(far_label_w)
    menu.addAction(far_label_action)

    vp._far_spin = QDoubleSpinBox()
    vp._far_spin.setRange(10.0, 10000.0)
    vp._far_spin.setValue(vp._cam._far if hasattr(vp._cam, '_far') else vp._cam.DEFAULT_FAR)
    vp._far_spin.setSingleStep(100.0)
    vp._far_spin.setDecimals(0)
    vp._far_spin.setMinimumWidth(80)
    far_widget = QWidget()
    far_layout = QHBoxLayout(far_widget)
    far_layout.setContentsMargins(4, 2, 4, 2)
    far_layout.addWidget(vp._far_spin)
    vp._far_spin.valueChanged.connect(vp._on_far_changed)
    far_spin_action = QWidgetAction(menu)
    far_spin_action.setDefaultWidget(far_widget)
    menu.addAction(far_spin_action)

    move_label_w = QWidget()
    move_label_layout = QHBoxLayout(move_label_w)
    move_label_layout.setContentsMargins(4, 2, 4, 2)
    move_label_layout.addWidget(QLabel("Move Speed"))
    move_label_layout.addStretch()
    move_label_action = QWidgetAction(menu)
    move_label_action.setDefaultWidget(move_label_w)
    menu.addAction(move_label_action)

    vp._move_speed_spin = QDoubleSpinBox()
    vp._move_speed_spin.setRange(1.0, 50.0)
    vp._move_speed_spin.setValue(vp._cam._move_speed if hasattr(vp._cam, '_move_speed') else vp._cam.MOVE_SPEED)
    vp._move_speed_spin.setSingleStep(1.0)
    vp._move_speed_spin.setDecimals(1)
    vp._move_speed_spin.setMinimumWidth(80)
    move_widget = QWidget()
    move_layout = QHBoxLayout(move_widget)
    move_layout.setContentsMargins(4, 2, 4, 2)
    move_layout.addWidget(vp._move_speed_spin)
    vp._move_speed_spin.valueChanged.connect(vp._on_move_speed_changed)
    move_spin_action = QWidgetAction(menu)
    move_spin_action.setDefaultWidget(move_widget)
    menu.addAction(move_spin_action)

    rot_label_w = QWidget()
    rot_label_layout = QHBoxLayout(rot_label_w)
    rot_label_layout.setContentsMargins(4, 2, 4, 2)
    rot_label_layout.addWidget(QLabel("Rotate Speed"))
    rot_label_layout.addStretch()
    rot_label_action = QWidgetAction(menu)
    rot_label_action.setDefaultWidget(rot_label_w)
    menu.addAction(rot_label_action)

    vp._rotate_speed_spin = QDoubleSpinBox()
    vp._rotate_speed_spin.setRange(0.05, 2.0)
    vp._rotate_speed_spin.setValue(vp._cam._rotate_speed if hasattr(vp._cam, '_rotate_speed') else vp._cam.ROTATE_SPEED)
    vp._rotate_speed_spin.setSingleStep(0.05)
    vp._rotate_speed_spin.setDecimals(2)
    vp._rotate_speed_spin.setMinimumWidth(80)
    rot_widget = QWidget()
    rot_layout = QHBoxLayout(rot_widget)
    rot_layout.setContentsMargins(4, 2, 4, 2)
    rot_layout.addWidget(vp._rotate_speed_spin)
    vp._rotate_speed_spin.valueChanged.connect(vp._on_rotate_speed_changed)
    rot_spin_action = QWidgetAction(menu)
    rot_spin_action.setDefaultWidget(rot_widget)
    menu.addAction(rot_spin_action)

    return menu
