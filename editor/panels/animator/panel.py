# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Optional
import editor.icons as qta
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem, QSplitter, QGraphicsView, QCheckBox, QMenu, QInputDialog, QMessageBox, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QAction, QColor
from core.components.animation.animator_controller import AnimatorController, AnimatorState, AnimatorTransition
from core.config.editor_scale import scale
from editor.panels.animator.graph import AnimatorScene
from editor.panels.animator.params import AnimatorParamsMixin
class AnimatorPanel(AnimatorParamsMixin, QDockWidget):
    state_selected_signal = pyqtSignal(object, object)
    transition_selected_signal = pyqtSignal(object, object)
    selection_cleared = pyqtSignal()
    def __init__(self, engine, main_window):
        super().__init__("Animator", main_window)
        self._engine = engine
        self._main_window = main_window
        self._controller: Optional[AnimatorController] = None
        self._selected_state: Optional[AnimatorState] = None
        self._selected_transition: Optional[AnimatorTransition] = None
        self.setObjectName("AnimatorDock")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setMinimumSize(scale(680), scale(420))
        self._build_ui()
    def _build_ui(self):
        central = QWidget()
        self.setWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        toolbar = self._build_toolbar()
        main_layout.addWidget(toolbar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._params_panel = self._build_params_panel()
        self._params_panel.setMinimumWidth(scale(180))
        self._params_panel.setMaximumWidth(scale(220))
        self._params_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self._params_panel)
        self._scene = AnimatorScene()
        self._scene.node_selected.connect(self._on_node_selected)
        self._scene.transition_selected.connect(self._on_transition_selected)
        self._scene.states_changed.connect(self._refresh_state_list)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self._view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self._view.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self._view.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._view.setStyleSheet("background: transparent; border: none;")
        self._view.setMinimumWidth(scale(320))
        self._view.setMinimumHeight(scale(200))
        self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self._view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([scale(190), scale(600)])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        main_layout.addWidget(splitter, 1)
    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self._add_state_btn = QPushButton(qta.icon("fa5s.plus", color=QColor(156, 204, 101)), " State")
        self._add_state_btn.setFixedHeight(scale(22))
        self._add_state_btn.clicked.connect(self._add_state)
        layout.addWidget(self._add_state_btn)
        self._add_param_btn = QPushButton(qta.icon("fa5s.plus", color=QColor(156, 204, 101)), " Parameter")
        self._add_param_btn.setFixedHeight(scale(22))
        self._add_param_btn.clicked.connect(self._add_parameter)
        layout.addWidget(self._add_param_btn)
        self._ctrl_name_label = QLabel("No Controller")
        self._ctrl_name_label.setStyleSheet("font-size: 11px; padding: 0 8px;")
        layout.addWidget(self._ctrl_name_label)
        layout.addStretch()
        self._live_link_cb = QCheckBox("Live Link")
        self._live_link_cb.setStyleSheet("font-size: 10px;")
        self._live_link_cb.setChecked(True)
        layout.addWidget(self._live_link_cb)
        return tb
    def _btn_style(self) -> str:
        return ""
    def load_controller(self, ctrl: Optional[AnimatorController]):
        self._controller = ctrl
        self._ctrl_name_label.setText(ctrl.name if ctrl else "No Controller")
        self._scene.set_controller(ctrl)
        self._update_param_list()
        self._refresh_state_list()
        self._selected_state = None
        self._selected_transition = None
        self.selection_cleared.emit()
    def _add_state(self):
        if not self._controller:
            QMessageBox.warning(self, "No Controller", "Create an Animator Controller first.")
            return
        name, ok = QInputDialog.getText(self, "New State", "State name:", text="New State")
        if ok and name:
            state = self._scene.add_state(name)
            self._refresh_state_list()
            if state is not None:
                self._scene.select_state(state.name)
                self._sync_state_list_selection(state.name)
    def _refresh_state_list(self):
        if not hasattr(self, "_state_list"):
            return
        current = None
        try: current_item = self._state_list.currentItem()
        except Exception: current_item = None
        try:
            if current_item is not None:
                current = current_item.data(Qt.ItemDataRole.UserRole)
        except Exception: pass
        self._state_list.clear()
        if not self._controller or not self._controller.layers:
            self._filter_state_list(self._state_search.text() if hasattr(self, "_state_search") else "")
            return
        layer = self._controller.layers[0]
        for state in layer.states:
            item = QListWidgetItem(state.name)
            item.setData(Qt.ItemDataRole.UserRole, state.name)
            self._state_list.addItem(item)
            if state.name == current:
                self._state_list.setCurrentItem(item)
        self._filter_state_list(self._state_search.text() if hasattr(self, "_state_search") else "")
    def _filter_state_list(self, text: str):
        query = str(text).lower().strip()
        if hasattr(self, "_state_list"):
            for i in range(self._state_list.count()):
                item = self._state_list.item(i)
                name = str(item.data(Qt.ItemDataRole.UserRole) or item.text()).lower()
                item.setHidden(bool(query) and query not in name)
        if hasattr(self, "_param_list"):
            for i in range(self._param_list.count()):
                item = self._param_list.item(i)
                name = str(item.data(Qt.ItemDataRole.UserRole) or item.text()).lower()
                item.setHidden(bool(query) and query not in name)
    def _sync_state_list_selection(self, name: str | None):
        if not hasattr(self, "_state_list"):
            return
        try:
            self._state_list.blockSignals(True)
            if not name:
                self._state_list.clearSelection()
            else:
                for i in range(self._state_list.count()):
                    item = self._state_list.item(i)
                    if item.data(Qt.ItemDataRole.UserRole) == name:
                        self._state_list.setCurrentItem(item)
                        break
        finally:
            try: self._state_list.blockSignals(False)
            except Exception: pass
    def _on_state_list_clicked(self, item):
        name = item.data(Qt.ItemDataRole.UserRole)
        self._scene.select_state(str(name))
        self._sync_state_list_selection(str(name))
    def _state_list_menu(self, pos):
        item = self._state_list.itemAt(pos)
        menu = QMenu(self)
        add_action = QAction("Create State", self)
        add_action.triggered.connect(self._add_state)
        menu.addAction(add_action)
        if item is not None:
            name = str(item.data(Qt.ItemDataRole.UserRole))
            del_action = QAction("Delete State", self)
            del_action.triggered.connect(lambda _, n=name: self._delete_state_from_list(n))
            menu.addAction(del_action)
        menu.exec(self._state_list.mapToGlobal(pos))
    def _delete_state_from_list(self, name: str):
        self._scene.remove_state(name)
        self._refresh_state_list()
        self._selected_state = None
        self._selected_transition = None
        self.selection_cleared.emit()
    def _on_node_selected(self, state):
        self._selected_state = state
        self._selected_transition = None
        if state:
            self._sync_state_list_selection(state.name)
            self.state_selected_signal.emit(state, self._controller)
        else:
            self._sync_state_list_selection(None)
            self.selection_cleared.emit()
    def _on_transition_selected(self, transition):
        self._selected_transition = transition
        self._selected_state = None
        self._sync_state_list_selection(None)
        if transition:
            self.transition_selected_signal.emit(transition, self._controller)
        else:
            self.selection_cleared.emit()
    def load_config(self, config):
        pass
