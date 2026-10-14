# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import qtawesome as qta
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem, QLineEdit, QComboBox, QMenu, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor
from core.config.editor_scale import scale, scale_xy
from core.components.animation.animator_controller import AnimatorParameter, AnimatorParameterType
_GRID_COLOR = QColor(50, 50, 50)
_CONDITION_TRUE = QColor(60, 180, 60)
_CONDITION_FALSE = QColor(200, 80, 80)
class AnimatorParamsMixin:
    def _build_params_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(scale(180))
        w.setMaximumWidth(scale(220))
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        header = QLabel("Node Palette")
        header.setStyleSheet("color: rgb(187, 187, 187); font-weight: bold; font-size: 11px; padding: 2px 4px;")
        layout.addWidget(header)
        self._state_search = QLineEdit()
        self._state_search.setPlaceholderText("Search nodes...")
        self._state_search.setClearButtonEnabled(True)
        self._state_search.setStyleSheet("QLineEdit { background-color: rgb(30, 30, 30); color: rgb(204, 204, 204); border: 1px solid rgb(68, 68, 68); border-radius: 3px; padding: 3px 6px; font-size: 10px; }")
        self._state_search.textChanged.connect(self._filter_state_list)
        layout.addWidget(self._state_search)
        states_title = QLabel("States")
        states_title.setStyleSheet("color: rgb(119, 119, 119); font-size: 9px; padding: 4px 4px 1px 4px;")
        layout.addWidget(states_title)
        self._state_list = QListWidget()
        self._state_list.setStyleSheet("border: none; font-size: 10px;")
        self._state_list.itemClicked.connect(self._on_state_list_clicked)
        self._state_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._state_list.customContextMenuRequested.connect(self._state_list_menu)
        layout.addWidget(self._state_list, 1)
        add_state_btn = QPushButton("Add State")
        add_state_btn.setFixedHeight(scale(28))
        add_state_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_state_btn.setStyleSheet("QPushButton { background-color: rgb(45, 90, 58); color: white; border: 1px solid rgb(85, 85, 85); border-radius: 3px; padding: 3px 8px; font-size: 10px; text-align: left; } QPushButton:hover { background-color: rgb(80, 138, 90); border: 1px solid rgb(74, 122, 181); }")
        add_state_btn.clicked.connect(self._add_state)
        layout.addWidget(add_state_btn)
        params_title = QLabel("Parameters")
        params_title.setStyleSheet("color: rgb(119, 119, 119); font-size: 9px; padding: 4px 4px 1px 4px;")
        layout.addWidget(params_title)
        self._param_list = QListWidget()
        self._param_list.setStyleSheet("border: none; font-size: 10px;")
        self._param_list.itemClicked.connect(self._on_param_selected)
        self._param_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._param_list.customContextMenuRequested.connect(self._param_context_menu)
        layout.addWidget(self._param_list, 1)
        add_row = QWidget()
        ar_layout = QHBoxLayout(add_row)
        ar_layout.setContentsMargins(4, 2, 4, 2)
        self._param_name_edit = QLineEdit()
        self._param_name_edit.setPlaceholderText("param name")
        self._param_name_edit.setStyleSheet("border: 1px solid; border-radius: 3px; padding: 2px 4px; font-size: 10px;")
        ar_layout.addWidget(self._param_name_edit)
        self._param_type_combo = QComboBox()
        self._param_type_combo.addItems(["Float", "Int", "Bool", "Trigger"])
        self._param_type_combo.setStyleSheet("border: 1px solid; border-radius: 3px; font-size: 10px;")
        ar_layout.addWidget(self._param_type_combo)
        add_btn = QPushButton(qta.icon("fa5s.plus", color=QColor(156, 204, 101)), "")
        add_btn.setFixedSize(*scale_xy(22, 22))
        add_btn.clicked.connect(self._add_parameter)
        ar_layout.addWidget(add_btn)
        layout.addWidget(add_row)
        return w
    def _add_parameter(self):
        if not self._controller:
            QMessageBox.warning(self, "No Controller", "Create an Animator Controller first.")
            return
        name = self._param_name_edit.text().strip() or "NewParam"
        ptype_str = self._param_type_combo.currentText()
        ptype_map = {"Float": AnimatorParameterType.FLOAT, "Int": AnimatorParameterType.INT, "Bool": AnimatorParameterType.BOOL, "Trigger": AnimatorParameterType.TRIGGER}
        param = AnimatorParameter(name=name, param_type=ptype_map[ptype_str])
        self._controller.add_parameter(param)
        self._update_param_list()
        self._param_name_edit.clear()
    def _update_param_list(self):
        self._param_list.clear()
        if not self._controller:
            return
        for p in self._controller.parameters:
            item = QListWidgetItem(f"{p.name} ({p.param_type.value})")
            item.setData(Qt.ItemDataRole.UserRole, p.name)
            self._param_list.addItem(item)
    def _param_context_menu(self, pos):
        item = self._param_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        del_action = QAction("Delete Parameter", self)
        param_name = item.data(Qt.ItemDataRole.UserRole)
        del_action.triggered.connect(lambda: self._delete_param(param_name))
        menu.addAction(del_action)
        menu.exec(self._param_list.mapToGlobal(pos))
    def _delete_param(self, name: str):
        if self._controller:
            self._controller.remove_parameter(name)
            self._update_param_list()
    def _on_param_selected(self, item):
        pass
