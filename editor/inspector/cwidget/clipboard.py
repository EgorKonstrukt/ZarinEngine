# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from PySide6.QtWidgets import QApplication, QMenu, QLineEdit, QPlainTextEdit
from PySide6.QtGui import QAction
from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history
from core.foundation.logger import Logger
from core.config.editor_scale import scale
from editor.inspector.constants import _FUSION_INPUT_RADIUS, _accent
class ClipboardMixin:
    def _show_context_menu(self, pos):
        menu = QMenu(self)
        from editor.inspector.panelp import InspectorPanel
        copy_comp = QAction("Copy Component", self)
        copy_comp.triggered.connect(self._copy_component)
        menu.addAction(copy_comp)
        copy_vals = QAction("Copy Values", self)
        copy_vals.triggered.connect(self._copy_values)
        menu.addAction(copy_vals)
        paste_vals = QAction("Paste Component Values", self)
        paste_vals.setEnabled(InspectorPanel._clipboard is not None)
        paste_vals.triggered.connect(self._paste_values)
        menu.addAction(paste_vals)
        menu.addSeparator()
        rem = QAction("Remove Component", self)
        rem.triggered.connect(lambda: self.remove_requested.emit(type(self._component).__name__, self._component_key))
        menu.addAction(rem)
        menu.exec(self.mapToGlobal(pos))
    def _copy_component(self):
        from editor.inspector.panelp import InspectorPanel
        InspectorPanel._clipboard = {
            "mode": "component",
            "type": type(self._component).__name__,
            "data": self._component.serialize(),
        }
    def _copy_values(self):
        from editor.inspector.panelp import InspectorPanel
        data = self._component.serialize()
        InspectorPanel._clipboard = {
            "mode": "values",
            "type": type(self._component).__name__,
            "data": data,
        }
    def _paste_values(self):
        from editor.inspector.panelp import InspectorPanel
        if InspectorPanel._clipboard is None:
            return
        from core.ecs import ComponentRegistry
        cb = InspectorPanel._clipboard
        target_type_name = cb["type"]
        target_cls = ComponentRegistry.get(target_type_name)
        if not target_cls:
            return
        source_data = cb["data"]
        current_type_name = type(self._component).__name__
        if target_type_name != current_type_name:
            return
        cmds = []
        entities = [e for e in self._selected_entities if e.has_component(target_cls)]
        if not entities:
            entities = [self._entity] if self._entity else []
            if not entities:
                return
        for ent in entities:
            comp = ent.get_component(target_cls)
            if comp:
                for key, val in source_data.items():
                    if key in ("type", "_key", "enabled"):
                        continue
                    old_val = getattr(comp, key, None)
                    if old_val is not None:
                        setattr(comp, key, val)
                        cmds.append(SetComponentCommand(ent, target_cls, key, old_val, val))
        if cmds:
            get_history().execute(CompoundCommand(cmds, f"Paste {target_type_name}"))
    def _copy_value(self, prop_name: str):
        try:
            val = getattr(self._component, prop_name)
            from core.foundation.cmd import collapse_value as _cv
            QApplication.clipboard().setText(str(_cv(val)))
        except Exception:
            pass
    def _paste_value(self, prop_name: str):
        text = QApplication.clipboard().text()
        if not text:
            return
        c = self._component
        old = getattr(c, prop_name, None)
        f = self._current_field
        try:
            if f is not None and f.field_type.value == "int":
                v = int(float(text))
            elif f is not None and f.field_type.value in ("float", "slider", "int_slider"):
                v = float(text)
            elif f is not None and f.field_type.value == "bool":
                v = text.strip().lower() in ("1", "true", "yes")
            else:
                v = text
            setattr(c, prop_name, v)
            get_history().execute(SetComponentCommand(self._entity, type(c), prop_name, old, v))
            self._rebuild_fields()
        except Exception:
            pass
    def _show_field_context_menu(self, pos, prop_name: str):
        menu = QMenu(self)
        copy_act = QAction("Copy Value", self)
        copy_act.triggered.connect(lambda: self._copy_value(prop_name))
        menu.addAction(copy_act)
        paste_act = QAction("Paste Value", self)
        paste_act.triggered.connect(lambda: self._paste_value(prop_name))
        menu.addAction(paste_act)
        reset_act = QAction("Reset to Default", self)
        reset_act.triggered.connect(lambda: self._reset_to_default(prop_name))
        menu.addAction(reset_act)
        f = self._current_field
        if f is not None and f.field_type.value in ("float", "vec2", "vec3", "vec4"):
            menu.addSeparator()
            key_act = QAction("Add Keyframe", self)
            key_act.triggered.connect(lambda: Logger.info(f"Keyframe requested for {prop_name}"))
            menu.addAction(key_act)
        menu.exec(self.sender().mapToGlobal(pos))
    def _show_source(self, file_path: str, line_number: int, comp_type: str, prop_name: str):
        from editor.inspector.source_viewer import SourceViewerDialog
        dlg = SourceViewerDialog(file_path, line_number, f"{comp_type}.{prop_name}", self)
        dlg.exec()
    def _build_text_field(self, field, prop_name, c, value):
        comp_cls = type(c)
        if field.multiline:
            te = QPlainTextEdit()
            te.setPlainText(str(value) if value else "")
            te.setFixedHeight(scale(60))
            def _commit_multi_text():
                new_val = te.toPlainText()
                entities = [e for e in self._selected_entities if e.has_component(comp_cls)] or ([self._entity] if self._entity else [])
                cmds = []
                for ent in entities:
                    comp = ent.get_component(comp_cls)
                    if comp and hasattr(comp, prop_name):
                        old = getattr(comp, prop_name)
                        try:
                            setattr(comp, prop_name, new_val)
                        except Exception:
                            continue
                        cmds.append(SetComponentCommand(ent, comp_cls, prop_name, old, new_val))
                if len(cmds) == 1:
                    get_history().execute(cmds[0])
                elif cmds:
                    get_history().execute(CompoundCommand(cmds, f"Set {prop_name} x{len(cmds)}"))
            te.focusOutEvent = lambda ev, _f=_commit_multi_text: (_f(), QPlainTextEdit.focusOutEvent(te, ev))
        else:
            te = QLineEdit()
            te.setText(str(value) if value else "")
            def _commit_single_text():
                new_val = te.text()
                entities = [e for e in self._selected_entities if e.has_component(comp_cls)] or ([self._entity] if self._entity else [])
                cmds = []
                for ent in entities:
                    comp = ent.get_component(comp_cls)
                    if comp and hasattr(comp, prop_name):
                        old = getattr(comp, prop_name)
                        try:
                            setattr(comp, prop_name, new_val)
                        except Exception:
                            continue
                        cmds.append(SetComponentCommand(ent, comp_cls, prop_name, old, new_val))
                if len(cmds) == 1:
                    get_history().execute(cmds[0])
                elif cmds:
                    get_history().execute(CompoundCommand(cmds, f"Set {prop_name} x{len(cmds)}"))
            te.editingFinished.connect(_commit_single_text)
        self._add_field(field.label, te, prop_name, field.toggle_field)
    def _build_string_field(self, field, prop_name, c, value):
        te = QLineEdit()
        te.setText(str(value) if value else "")
        te.setStyleSheet(f"""
                QLineEdit {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QLineEdit:focus {{ border-color: {_accent()}; }}
            """)
        te.textChanged.connect(lambda: setattr(c, prop_name, te.text()))
        comp_cls = type(c)
        te.editingFinished.connect(lambda: get_history().execute(SetComponentCommand(self._entity, comp_cls, prop_name, value, te.text())))
        self._add_field(field.label, te, prop_name, field.toggle_field)
    def _build_textarea_field(self, field, prop_name, c, value):
        te = QPlainTextEdit()
        te.setPlainText(str(value) if value else "")
        te.setFixedHeight(scale(60))
        te.setStyleSheet(f"""
                QPlainTextEdit {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QPlainTextEdit:focus {{ border-color: {_accent()}; }}
            """)
        te.textChanged.connect(lambda: setattr(c, prop_name, te.toPlainText()))
        comp_cls = type(c)
        te.focusOutEvent = lambda ev: (get_history().execute(SetComponentCommand(self._entity, comp_cls, prop_name, value, te.toPlainText())), QPlainTextEdit.focusOutEvent(te, ev))
        self._add_field(field.label, te, prop_name, field.toggle_field)
    def _build_keybinding_field(self, field, prop_name, c, value):
        te = QLineEdit()
        te.setText(str(value) if value else "")
        te.setStyleSheet(f"""
                QLineEdit {{
                    border-radius: {_FUSION_INPUT_RADIUS};
                    padding: 2px 4px;
                    font-size: 11px;
                    selection-background-color: {_accent()};
                }}
                QLineEdit:focus {{ border-color: {_accent()}; }}
            """)
        comp_cls = type(c)
        def _on_keybinding_commit():
            new_val = te.text()
            self._undo_setter_all(comp_cls, prop_name)(new_val)
        te.editingFinished.connect(_on_keybinding_commit)
        self._add_field(field.label, te, prop_name, field.toggle_field)
