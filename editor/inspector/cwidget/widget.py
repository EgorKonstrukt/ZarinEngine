# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QApplication, QFormLayout
from PySide6.QtCore import Qt, Signal
import editor.icons as qta
from core.config.editor_scale import scale_xy
from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history
from editor.inspector.constants import _COMPONENT_MIME
from editor.inspector.helpersp import get_component_icon_pixmap
from .clipboard import ClipboardMixin
from .fields import FieldsMixin
from .lists import ListsMixin
from .vectors import VectorsMixin
from .scripts import ScriptsMixin
from .transform_section import TransformMixin
class ComponentWidget(ClipboardMixin, FieldsMixin, ListsMixin, VectorsMixin, ScriptsMixin, TransformMixin, QWidget):
    """Component inspector widget."""
    remove_requested = Signal(str, str)
    move_up_requested = Signal(str)
    move_down_requested = Signal(str)
    reorder_requested = Signal(str, str, str)
    def __init__(self, component, entity=None, selected_entities=None, parent=None, component_key: str = "", overridden_props: set = None):
        super().__init__(parent)
        self._component = component
        self._entity = entity
        self._selected_entities = list(selected_entities if selected_entities else [])
        self._component_key = component_key
        self._overridden_props = set(overridden_props) if overridden_props else set()
        self._updating = False
        self._collapsed = False
        self._field_rows: list[dict] = []
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self._header_widget = QWidget()
        self._header_widget.setObjectName("compHeader")
        header_layout = QHBoxLayout(self._header_widget)
        header_layout.setContentsMargins(6, 3, 6, 3)
        header_layout.setSpacing(4)
        self._collapse_btn = QPushButton(qta.icon("fa5s.caret-down", color="#d4d4d4"), "")
        self._collapse_btn.setFixedSize(*scale_xy(14, 14))
        self._collapse_btn.setFlat(True)
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self._collapse_btn)
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(*scale_xy(16, 16))
        comp_cls = type(component)
        pix = get_component_icon_pixmap(comp_cls, 16)
        self._icon_label.setPixmap(pix)
        self._icon_label.setToolTip(comp_cls.__name__)
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self._icon_label)
        self._name_label = QLabel(type(component).__name__)
        self._name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self._name_label, 1)
        self._drag_start_pos = None
        self._enabled_cb = QCheckBox()
        self._enabled_cb.setChecked(component.enabled)
        self._enabled_cb.toggled.connect(self._on_enabled_toggled)
        header_layout.addWidget(self._enabled_cb)
        self._move_up_btn = QPushButton(qta.icon("fa5s.chevron-up", color="#d4d4d4"), "")
        self._move_up_btn.setFixedSize(*scale_xy(16, 16))
        self._move_up_btn.setFlat(True)
        self._move_up_btn.clicked.connect(lambda: self.move_up_requested.emit(self._component_key))
        header_layout.addWidget(self._move_up_btn)
        self._move_down_btn = QPushButton(qta.icon("fa5s.chevron-down", color="#d4d4d4"), "")
        self._move_down_btn.setFixedSize(*scale_xy(16, 16))
        self._move_down_btn.setFlat(True)
        self._move_down_btn.clicked.connect(lambda: self.move_down_requested.emit(self._component_key))
        header_layout.addWidget(self._move_down_btn)
        self._header_widget.installEventFilter(self)
        main_layout.addWidget(self._header_widget)
        self._content_widget = QWidget()
        self._content_widget.setObjectName("compBody")
        self._layout = QFormLayout(self._content_widget)
        self._layout.setContentsMargins(8, 6, 8, 6)
        self._layout.setSpacing(3)
        self._layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._layout.setHorizontalSpacing(8)
        self._group_form: QFormLayout | None = None
        main_layout.addWidget(self._content_widget)
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._build_fields()
        self._update_appearance()
    def eventFilter(self, obj, event):
        if obj is self._header_widget:
            if event.type() == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_start_pos = event.position().toPoint()
                self._drag_started = False
            elif event.type() == event.Type.MouseMove and (event.buttons() & Qt.MouseButton.LeftButton):
                if self._drag_start_pos is not None and not self._drag_started:
                    delta = event.position().toPoint() - self._drag_start_pos
                    if delta.manhattanLength() >= QApplication.startDragDistance():
                        self._start_drag()
                return True
            elif event.type() == event.Type.MouseButtonRelease:
                self._drag_start_pos = None
                self._drag_started = False
        return super().eventFilter(obj, event)
    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        self._collapse_btn.setIcon(qta.icon("fa5s.caret-right" if self._collapsed else "fa5s.caret-down", color="#d4d4d4"))
        self._content_widget.setVisible(not self._collapsed)
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    def dropEvent(self, event):
        if event.mimeData().hasFormat(_COMPONENT_MIME):
            raw = bytes(event.mimeData().data(_COMPONENT_MIME)).decode("utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                event.ignore()
                return
            dragged_key = data.get("component_key", "")
            target_key = self._component_key
            source_eid = data.get("entity_id", "")
            if dragged_key and target_key and source_eid == (self._entity.id if self._entity else ""):
                self.reorder_requested.emit(source_eid, dragged_key, target_key)
                event.acceptProposedAction()
                return
            event.ignore()
        else:
            super().dropEvent(event)
    def _update_appearance(self):
        self._content_widget.setEnabled(self._component.enabled)
    def _on_enabled_toggled(self, checked: bool):
        comp_type = type(self._component)
        entities = [e for e in self._selected_entities if e.has_component(comp_type)]
        if len(entities) <= 1:
            old = not checked
            self._component.enabled = checked
            if checked: self._component.on_enable()
            else: self._component.on_disable()
            if self._entity:
                get_history().execute(SetComponentCommand(self._entity, comp_type, "enabled", old, checked))
            self._update_appearance()
            return
        cmds = []
        for ent in entities:
            comp = ent.get_component(comp_type)
            if comp:
                old = comp.enabled
                if old == checked:
                    continue
                comp.enabled = checked
                if checked:
                    try: comp.on_enable()
                    except Exception: pass
                else:
                    try: comp.on_disable()
                    except Exception: pass
                cmds.append(SetComponentCommand(ent, comp_type, "enabled", old, checked))
        if cmds:
            get_history().execute(CompoundCommand(cmds, f"Set enabled x{len(cmds)}"))
        self._update_appearance()
    def set_filter(self, text: str):
        text = text.strip().lower()
        for row in self._field_rows:
            if not text:
                row["label_widget"].setVisible(True)
                row["field_widget"].setVisible(True)
                continue
            match = text in row["label"].lower() or (row["prop_name"] and text in row["prop_name"].lower())
            row["label_widget"].setVisible(match)
            row["field_widget"].setVisible(match)
    def _rebuild_fields(self):
        self._group_form = None
        self._field_rows.clear()
        self._toggle_rows.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._build_fields()
    def _target_layout(self) -> QFormLayout:
        return self._group_form if self._group_form is not None else self._layout
    def _redraw_viewport(self):
        try:
            from core.engine.eng import Engine
            vp = Engine.instance().viewport
            if vp is not None:
                vp.update_scene()
        except Exception:
            pass
