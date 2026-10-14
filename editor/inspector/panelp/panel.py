# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
import qtawesome as qta
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QLineEdit, QPushButton, QCheckBox, QSpinBox, QFrame, QDialog
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from core.config.editor_scale import scale, scale_xy
from core.foundation.logger import Logger
from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history
from editor.inspector.constants import _FUSION_ACCENT_ORANGE, _accent
from editor.inspector.cwidget import ComponentWidget
from editor.inspector.component_picker import ComponentPickerDialog
from editor.inspector.panelp.util import _smart_label_width
from editor.inspector.panelp.sections import InspectorSectionsMixin
from editor.inspector.panelp.clipboard import InspectorClipboardMixin
from editor.inspector.panelp.filter import InspectorFilterMixin
from editor.inspector.panelp.undo import InspectorUndoMixin
if TYPE_CHECKING:
    from core.ecs import Entity, Scene
    from core.engine.eng import Engine


class InspectorPanel(InspectorSectionsMixin, InspectorClipboardMixin, InspectorFilterMixin, InspectorUndoMixin, QDockWidget):
    open_prefab_editor = pyqtSignal(str)
    def __init__(self, engine: Engine, parent=None):
        super().__init__("Inspector", parent)
        self._engine = engine
        self._entity: Optional[Entity] = None
        self._selected_entities: list = []
        self._comp_widgets: list[ComponentWidget] = []
        self._asset_widgets: list[QWidget] = []
        self._updating: bool = False
        self._locked: bool = False
        self._asset_path: Optional[str] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_transform)
        self._refresh_timer.start(300)
        self._animator_mode = False
        self._animator_state: Optional[AnimatorState] = None
        self._animator_transition: Optional[AnimatorTransition] = None
        self._animator_controller: Optional[AnimatorController] = None
        self._saved_entity: Optional[Entity] = None
        self._saved_entities: list[Entity] = []
        self._setup_ui()

    def load_config(self, config) -> None:
        refresh_interval = config.get("inspector.refresh_interval", 300)
        self._refresh_timer.setInterval(refresh_interval)

    def _setup_ui(self):
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self._header_widget = QWidget()
        header_layout = QHBoxLayout(self._header_widget)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.setSpacing(4)
        self._lock_btn = QPushButton("\U0001F512")
        self._lock_btn.setFixedSize(*scale_xy(22, 22))
        self._lock_btn.setCheckable(True)
        self._lock_btn.setChecked(False)
        self._lock_btn.setToolTip("Lock Inspector")
        self._lock_btn.toggled.connect(self._on_lock_toggled)
        header_layout.addWidget(self._lock_btn)
        self._active_cb = QCheckBox()
        self._active_cb.toggled.connect(self._on_active_changed)
        self._active_cb.setStyleSheet(f"background: transparent;")
        header_layout.addWidget(self._active_cb)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Entity name")
        self._name_edit.setStyleSheet(f"QLineEdit {{ selection-background-color: {_accent()}; }} QLineEdit:focus {{ border-color: {_accent()}; }}")
        self._name_edit.textChanged.connect(self._on_name_changed)
        header_layout.addWidget(self._name_edit, 1)
        self._tag_edit = QLineEdit()
        self._tag_edit.setPlaceholderText("Tag")
        self._tag_edit.setFixedWidth(scale(80))
        self._tag_edit.setStyleSheet(f"QLineEdit:focus {{ border-color: {_accent()}; }}")
        self._tag_edit.textChanged.connect(self._on_tag_changed)
        header_layout.addWidget(self._tag_edit)
        layer_lbl = QLabel("Layer")
        header_layout.addWidget(layer_lbl)
        self._layer_sb = QSpinBox()
        self._layer_sb.setRange(0, 31)
        self._layer_sb.setFixedWidth(scale(46))
        self._layer_sb.valueChanged.connect(self._on_layer_changed)
        header_layout.addWidget(self._layer_sb)
        outer_layout.addWidget(self._header_widget)
        self._prefab_bar_widget = QWidget()
        prefab_bar_layout = QHBoxLayout(self._prefab_bar_widget)
        prefab_bar_layout.setContentsMargins(6, 2, 6, 2)
        self._prefab_label = QLabel()
        self._prefab_label.setStyleSheet(f"color: {_accent()}; font-weight: 600; font-size: 11px; background: transparent;")
        prefab_bar_layout.addWidget(self._prefab_label)
        self._override_label = QLabel()
        self._override_label.setStyleSheet(f"color: {_FUSION_ACCENT_ORANGE}; font-size: 10px; background: transparent;")
        prefab_bar_layout.addWidget(self._override_label)
        prefab_bar_layout.addStretch()
        _prefab_btn_style = f"QPushButton {{ padding: 2px 8px; font-size: 10px; }}"
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setFixedHeight(scale(22))
        self._apply_btn.setStyleSheet(_prefab_btn_style)
        self._apply_btn.clicked.connect(self._on_apply_prefab)
        prefab_bar_layout.addWidget(self._apply_btn)
        self._revert_btn = QPushButton("Revert")
        self._revert_btn.setFixedHeight(scale(22))
        self._revert_btn.setStyleSheet(_prefab_btn_style)
        self._revert_btn.clicked.connect(self._on_revert_prefab)
        prefab_bar_layout.addWidget(self._revert_btn)
        self._select_prefab_btn = QPushButton("Select")
        self._select_prefab_btn.setFixedHeight(scale(22))
        self._select_prefab_btn.setStyleSheet(_prefab_btn_style)
        self._select_prefab_btn.clicked.connect(self._on_select_prefab_asset)
        prefab_bar_layout.addWidget(self._select_prefab_btn)
        self._open_prefab_btn = QPushButton("Open Prefab")
        self._open_prefab_btn.setFixedHeight(scale(22))
        self._open_prefab_btn.setStyleSheet(f"QPushButton {{ padding: 2px 10px; font-size: 10px; font-weight: 700; color: {_accent()}; border: 1px solid {_accent()}; border-radius: 3px; }} QPushButton:hover {{ background: {_accent()}; color: {chr(35)}fff; }}")
        self._open_prefab_btn.clicked.connect(self._on_open_prefab_editor)
        prefab_bar_layout.addWidget(self._open_prefab_btn)
        outer_layout.addWidget(self._prefab_bar_widget)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        outer_layout.addWidget(sep)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search properties...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setStyleSheet(f"QLineEdit {{ border: 1px solid {chr(35)}444; border-radius: 3px; padding: 3px 6px; font-size: 11px; background: {chr(35)}1e1e1e; }} QLineEdit:focus {{ border-color: {_accent()}; }}")
        self._search_edit.textChanged.connect(self._on_search_changed)
        outer_layout.addWidget(self._search_edit)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content_widget)
        outer_layout.addWidget(self._scroll, 1)
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(6, 4, 6, 6)
        self._add_comp_btn = QPushButton(qta.icon("fa5s.plus", color=chr(35) + "fff"), " Add Component")
        self._add_comp_btn.setFixedHeight(scale(24))
        self._add_comp_btn.setStyleSheet("QPushButton { background: " + chr(35) + "2e7d32; }")
        self._add_comp_btn.clicked.connect(self._show_add_component_menu)
        bottom_layout.addWidget(self._add_comp_btn)
        outer_layout.addWidget(bottom)
        self._prefab_bar_widget.setVisible(False)
        self._header_widget.setVisible(False)
        self._add_comp_btn.setVisible(False)
        self.setWidget(outer)

    def _on_lock_toggled(self, checked: bool):
        self._locked = checked
        self._lock_btn.setToolTip("Unlock Inspector" if checked else "Lock Inspector")

    def set_entity(self, entity: Optional[Entity]):
        if self._locked:
            return
        if entity is self._entity and not self._animator_mode and not self._asset_path:
            self._selected_entities = [entity] if entity else []
            if entity:
                self._updating = True
                try:
                    self._active_cb.setChecked(entity.active)
                    self._name_edit.setText(entity.name)
                    self._tag_edit.setText(", ".join(entity.tags))
                    self._layer_sb.setValue(entity.layer)
                finally:
                    self._updating = False
            self._refresh_transform()
            return
        self._animator_mode = False
        self._animator_state = None
        self._animator_transition = None
        self._animator_controller = None
        self._entity = entity
        self._selected_entities = [entity] if entity else []
        self._asset_path = None
        self._rebuild()

    def set_selected_entities(self, entities: list):
        if self._locked:
            return
        cur = self._selected_entities
        if (not self._animator_mode and not self._asset_path
                and len(entities) == len(cur)
                and all(a is b for a, b in zip(entities, cur))):
            self._entity = entities[0] if entities else None
            self._refresh_transform()
            return
        self._animator_mode = False
        self._animator_state = None
        self._animator_transition = None
        self._animator_controller = None
        self._selected_entities = list(entities)
        self._entity = entities[0] if entities else None
        self._asset_path = None
        self._rebuild()

    def show_import_settings(self, path: str):
        self._entity = None
        self._asset_path = path
        self._rebuild()

    def show_animator_state(self, state: AnimatorState, controller: AnimatorController):
        self._saved_entity = self._entity
        self._saved_entities = list(self._selected_entities)
        self._entity = None
        self._asset_path = None
        self._animator_mode = True
        self._animator_state = state
        self._animator_transition = None
        self._animator_controller = controller
        self._rebuild()

    def show_animator_transition(self, trans: AnimatorTransition, controller: AnimatorController):
        self._saved_entity = self._entity
        self._saved_entities = list(self._selected_entities)
        self._entity = None
        self._asset_path = None
        self._animator_mode = True
        self._animator_transition = trans
        self._animator_state = None
        self._animator_controller = controller
        self._rebuild()

    def clear_animator_mode(self):
        if self._animator_mode:
            self._animator_mode = False
            self._animator_state = None
            self._animator_transition = None
            self._entity = self._saved_entity
            self._selected_entities = self._saved_entities
            self._animator_controller = None
            self._rebuild()

    def _add_asset_widget(self, w: QWidget):
        self._asset_widgets.append(w)
        self._content_layout.addWidget(w)

    def _rebuild(self):
        self._content_widget.setVisible(False)
        try:
            self._updating = True
            for w in self._comp_widgets:
                try:
                    w.blockSignals(True)
                except Exception:
                    pass
                w.hide()
                w.deleteLater()
            self._comp_widgets.clear()
            while self._content_layout.count():
                item = self._content_layout.takeAt(0)
                if item and item.widget():
                    try:
                        item.widget().blockSignals(True)
                    except Exception:
                        pass
                    item.widget().hide()
                    item.widget().deleteLater()
            self._asset_widgets.clear()
            try:
                self._mesh_preview = None
            except Exception:
                pass
            if self._animator_mode:
                self._header_widget.setVisible(False)
                self._add_comp_btn.setVisible(False)
                if self._animator_state:
                    self._build_animator_state_inspector(self._animator_state)
                elif self._animator_transition:
                    self._build_animator_transition_inspector(self._animator_transition)
                self._content_layout.addStretch()
                self._search_edit.setVisible(False)
                return
            if self._asset_path:
                self._header_widget.setVisible(False)
                self._add_comp_btn.setVisible(False)
                self._build_import_settings()
                self._content_layout.addStretch()
                self._search_edit.setVisible(False)
                return
            if not self._entity:
                self._header_widget.setVisible(False)
                self._add_comp_btn.setVisible(False)
                self._content_layout.addStretch()
                self._search_edit.setVisible(False)
                return
            self._header_widget.setVisible(True)
            self._add_comp_btn.setVisible(True)
            if self._entity.is_prefab_instance:
                from core.ecs.prefabp import Prefab, PrefabLibrary
                prefab_path = PrefabLibrary.path_for_guid(self._entity._prefab_guid)
                overrides = Prefab.compute_all_overrides([self._entity])
                prefab_name = prefab_path.replace("\\", "/").split("/")[-1] if prefab_path else "Prefab"
                self._prefab_label.setText(f"Prefab: {prefab_name}")
                if overrides:
                    self._override_label.setText(f"({len(overrides)} override{'s' if len(overrides) != 1 else ''})")
                    self._override_label.setVisible(True)
                else:
                    self._override_label.setVisible(False)
                self._prefab_bar_widget.setVisible(True)
            else:
                self._prefab_bar_widget.setVisible(False)
            for i in range(self._header_widget.layout().count() - 1, -1, -1):
                item = self._header_widget.layout().itemAt(i)
                if item and item.widget() and item.widget().property("is_multi_label"):
                    item.widget().deleteLater()
            if len(self._selected_entities) > 1:
                multi_label = QLabel(f"({len(self._selected_entities)} selected)")
                multi_label.setProperty("is_multi_label", True)
                multi_label.setStyleSheet(f"color: {_accent()}; font-size: 11px; padding: 2px 0; background: transparent;")
                self._header_widget.layout().insertWidget(0, multi_label)
            self._active_cb.setChecked(self._entity.active)
            self._name_edit.setText(self._entity.name)
            tags = ", ".join(self._entity.tags)
            self._tag_edit.setText(tags)
            self._layer_sb.setValue(self._entity.layer)
            overridden = set()
            if self._entity.is_prefab_instance:
                from core.ecs.prefabp import Prefab
                for ov in Prefab.compute_all_overrides([self._entity]):
                    prop = ov.get("property", "")
                    if "." in prop:
                        overridden.add(prop.split(".", 1)[1])
            self._search_edit.setVisible(True)
            if len(self._selected_entities) > 1:
                type_sets = []
                for ent in self._selected_entities:
                    tset = set()
                    for k in ent._components.keys():
                        base = k.split(".")[0]
                        tset.add(base)
                    type_sets.append(tset)
                common = set.intersection(*type_sets) if type_sets else set()
                comps_to_show = []
                seen = set()
                rev_map_first = {id(c): k for k, c in self._entity._components.items()}
                for k, comp in self._entity._components.items():
                    base = k.split(".")[0]
                    if base in common and base not in seen:
                        if getattr(type(comp), "_editor_hidden", False):
                            continue
                        actual_key = base if not getattr(type(comp), "_allow_multiple", False) else k
                        seen.add(base)
                        comps_to_show.append((comp, actual_key))
                for idx, (comp, key) in enumerate(comps_to_show):
                    try:
                        cw = ComponentWidget(comp, self._entity, self._selected_entities, self._content_widget,
                                             component_key=key, overridden_props=overridden)
                        cw.remove_requested.connect(self._remove_component)
                        cw.move_up_requested.connect(self._move_component_up)
                        cw.move_down_requested.connect(self._move_component_down)
                        cw.reorder_requested.connect(self._on_reorder_component)
                        cw._move_up_btn.setEnabled(False)
                        cw._move_down_btn.setEnabled(False)
                        self._content_layout.addWidget(cw)
                        self._comp_widgets.append(cw)
                    except Exception as e:
                        Logger.error(f"Inspector build error for {type(comp).__name__}: {e}", e)
            else:
                rev_map = {id(c): k for k, c in self._entity._components.items()}
                comps = self._entity.get_all_components()
                for idx, comp in enumerate(comps):
                    if getattr(type(comp), "_editor_hidden", False):
                        continue
                    try:
                        key = rev_map.get(id(comp), "")
                        cw = ComponentWidget(comp, self._entity, self._selected_entities, self._content_widget,
                                             component_key=key, overridden_props=overridden)
                        cw.remove_requested.connect(self._remove_component)
                        cw.move_up_requested.connect(self._move_component_up)
                        cw.move_down_requested.connect(self._move_component_down)
                        cw.reorder_requested.connect(self._on_reorder_component)
                        cw._move_up_btn.setEnabled(idx > 0)
                        cw._move_down_btn.setEnabled(idx < len(comps) - 1)
                        self._content_layout.addWidget(cw)
                        self._comp_widgets.append(cw)
                    except Exception as e:
                        Logger.error(f"Inspector build error for {type(comp).__name__}: {e}", e)
            self._content_layout.addStretch()
        finally:
            self._updating = False
            self._content_widget.setVisible(True)

