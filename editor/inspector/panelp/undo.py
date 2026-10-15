# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from PyQt6.QtWidgets import QDialog, QLabel, QDoubleSpinBox, QCheckBox, QComboBox, QPushButton, QLineEdit, QHBoxLayout
import editor.icons as qta
from core.components.animation.animator_controller import AnimatorConditionMode, AnimatorCondition
from editor.inspector.component_picker import ComponentPickerDialog
from core.config.editor_scale import scale, scale_xy
from core.foundation.logger import Logger
from core.foundation.cmd import SetComponentCommand, CompoundCommand, get_history
from editor.inspector.constants import _accent

class InspectorUndoMixin:
    def _build_animator_state_inspector(self, state: AnimatorState):
        self._build_section_title(f"State: {state.name}")
        name_edit = QLineEdit(state.name)
        name_edit.setStyleSheet(self._animator_input_style())
        name_edit.textChanged.connect(lambda t: self._on_animator_state_name_changed(state, t))
        self._content_layout.addWidget(QLabel("Name"))
        self._content_layout.addWidget(name_edit)
        speed_sb = QDoubleSpinBox()
        speed_sb.setRange(-100.0, 100.0)
        speed_sb.setValue(state.speed)
        speed_sb.valueChanged.connect(lambda v: setattr(state, 'speed', v))
        speed_sb.setStyleSheet(self._animator_input_style())
        self._content_layout.addWidget(QLabel("Speed"))
        self._content_layout.addWidget(speed_sb)
        tag_edit = QLineEdit(state.tag)
        tag_edit.setStyleSheet(self._animator_input_style())
        tag_edit.textChanged.connect(lambda t: setattr(state, 'tag', t))
        self._content_layout.addWidget(QLabel("Tag"))
        self._content_layout.addWidget(tag_edit)

    def _build_animator_transition_inspector(self, trans: AnimatorTransition):
        self._build_section_title("Transition")
        dur_sb = QDoubleSpinBox()
        dur_sb.setRange(0.0, 10.0)
        dur_sb.setSingleStep(0.05)
        dur_sb.setValue(trans.transition_duration)
        dur_sb.valueChanged.connect(lambda v: setattr(trans, 'transition_duration', v))
        dur_sb.setStyleSheet(self._animator_input_style())
        self._content_layout.addWidget(QLabel("Duration"))
        self._content_layout.addWidget(dur_sb)
        exit_sb = QDoubleSpinBox()
        exit_sb.setRange(0.0, 1.0)
        exit_sb.setSingleStep(0.05)
        exit_sb.setValue(trans.exit_time)
        exit_sb.valueChanged.connect(lambda v: setattr(trans, 'exit_time', v))
        exit_sb.setStyleSheet(self._animator_input_style())
        self._content_layout.addWidget(QLabel("Exit Time"))
        self._content_layout.addWidget(exit_sb)
        has_exit_cb = QCheckBox("Has Exit Time")
        has_exit_cb.setChecked(trans.has_exit_time)
        has_exit_cb.toggled.connect(lambda v: setattr(trans, 'has_exit_time', v))
        has_exit_cb.setStyleSheet("font-size: 10px;")
        self._content_layout.addWidget(has_exit_cb)
        fixed_dur_cb = QCheckBox("Fixed Duration")
        fixed_dur_cb.setChecked(trans.has_fixed_duration)
        fixed_dur_cb.toggled.connect(lambda v: setattr(trans, 'has_fixed_duration', v))
        fixed_dur_cb.setStyleSheet("font-size: 10px;")
        self._content_layout.addWidget(fixed_dur_cb)
        self._build_section_title("Conditions")
        for cond in trans.conditions:
            self._build_animator_condition_row(trans, cond)
        add_cond_btn = QPushButton(qta.icon("fa5s.plus", color=chr(35) + "9ccc65"), " Add Condition")
        add_cond_btn.clicked.connect(lambda: self._add_animator_condition(trans))
        add_cond_btn.setStyleSheet(self._animator_btn_style())
        self._content_layout.addWidget(add_cond_btn)

    def _build_animator_condition_row(self, trans, cond):
        row = QHBoxLayout()
        param_combo = QComboBox()
        ctrl = self._animator_controller
        if ctrl:
            for p in ctrl.parameters:
                param_combo.addItem(p.name)
        param_combo.setCurrentText(cond.parameter)
        param_combo.textActivated.connect(lambda text, c=cond: setattr(c, 'parameter', text))
        param_combo.setStyleSheet(self._animator_input_style())
        row.addWidget(param_combo)
        mode_combo = QComboBox()
        modes = ["if", "if_not", "greater", "less", "equals", "not_equal"]
        mode_combo.addItems(modes)
        mode_combo.setCurrentText(cond.mode.value)
        mode_combo.textActivated.connect(lambda text, c=cond: setattr(c, 'mode', AnimatorConditionMode(text)))
        mode_combo.setStyleSheet(self._animator_input_style())
        row.addWidget(mode_combo)
        thresh_sb = QDoubleSpinBox()
        thresh_sb.setRange(-99999.0, 99999.0)
        thresh_sb.setValue(cond.threshold)
        thresh_sb.valueChanged.connect(lambda v, c=cond: setattr(c, 'threshold', v))
        thresh_sb.setStyleSheet(self._animator_input_style())
        row.addWidget(thresh_sb)
        del_btn = QPushButton(qta.icon("fa5s.times", color=chr(35) + "c66"), "")
        del_btn.setFixedSize(*scale_xy(20, 20))
        del_btn.clicked.connect(lambda: self._remove_animator_condition(trans, cond))
        del_btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { }")
        row.addWidget(del_btn)
        self._content_layout.addLayout(row)

    def _add_animator_condition(self, trans):
        trans.conditions.append(AnimatorCondition())
        self._rebuild()

    def _remove_animator_condition(self, trans, cond):
        if cond in trans.conditions:
            trans.conditions.remove(cond)
        self._rebuild()

    def _on_animator_state_name_changed(self, state, new_name):
        old_name = state.name
        state.name = new_name
        self._rebuild()

    def _on_active_changed(self, checked: bool):
        if self._updating or not self._entity: return
        entities = self._selected_entities if len(self._selected_entities) > 1 else [self._entity]
        cmds = []
        for ent in entities:
            old = ent.active
            if old == checked:
                continue
            ent.active = checked
            cmds.append(SetComponentCommand(ent, type(ent), "active", old, checked))
        if len(cmds) == 1:
            get_history().execute(cmds[0])
        elif cmds:
            get_history().execute(CompoundCommand(cmds, f"Set active -> {checked} x{len(cmds)}"))

    def _on_name_changed(self, text: str):
        if self._updating or not self._entity: return
        if len(self._selected_entities) > 1:
            return
        old = self._entity.name
        self._entity.name = text
        get_history().execute(SetComponentCommand(self._entity, type(self._entity), "name", old, text))
        if self._engine.scene: self._engine.scene.mark_dirty()

    def _on_tag_changed(self, text: str):
        if self._updating or not self._entity: return
        entities = self._selected_entities if len(self._selected_entities) > 1 else [self._entity]
        new_tags = set(t.strip() for t in text.split(",") if t.strip())
        cmds = []
        for ent in entities:
            old = set(ent.tags)
            if old == new_tags:
                continue
            ent._tags = set(new_tags)
            cmds.append(SetComponentCommand(ent, type(ent), "tags", old, set(new_tags)))
        if len(cmds) == 1:
            get_history().execute(cmds[0])
        elif cmds:
            get_history().execute(CompoundCommand(cmds, f"Set tags x{len(cmds)}"))

    def _on_layer_changed(self, val: int):
        if self._updating or not self._entity: return
        entities = self._selected_entities if len(self._selected_entities) > 1 else [self._entity]
        cmds = []
        for ent in entities:
            old = ent.layer
            if old == val:
                continue
            ent.layer = val
            cmds.append(SetComponentCommand(ent, type(ent), "layer", old, val))
        if len(cmds) == 1:
            get_history().execute(cmds[0])
        elif cmds:
            get_history().execute(CompoundCommand(cmds, f"Set layer -> {val} x{len(cmds)}"))

    def _remove_component(self, comp_name: str, comp_key: str = ""):
        if not self._entity: return
        from core.ecs import ComponentRegistry
        from core.foundation.cmd import RemoveComponentCommand, CompoundCommand
        cls = ComponentRegistry.get(comp_name)
        if not cls:
            return
        if len(self._selected_entities) > 1:
            cmds = []
            for ent in list(self._selected_entities):
                target_key = comp_key
                if not target_key:
                    for k, c in ent._components.items():
                        if k == comp_name or k.startswith(comp_name + "."):
                            target_key = k
                            break
                    else:
                        continue
                if target_key not in ent._components and comp_name not in ent._components:
                    continue
                cmds.append(RemoveComponentCommand(ent, cls, component_key=target_key))
            if len(cmds) == 1:
                get_history().execute(cmds[0])
            elif cmds:
                get_history().execute(CompoundCommand(cmds, f"Remove {comp_name} x{len(cmds)}"))
            for ent in self._selected_entities:
                key_to_send = comp_key or comp_name
                if key_to_send in ent._components or any(k.startswith(comp_name+".") for k in ent._components):
                    continue
                collab = self._engine.collab_manager if hasattr(self._engine, 'collab_manager') else None
                if collab and collab.connected:
                    collab.send_component_remove(ent.id, key_to_send)
        else:
            cmd = RemoveComponentCommand(self._entity, cls, component_key=comp_key)
            get_history().execute(cmd)
            self._send_collab_component_remove(comp_key or comp_name)
        self._rebuild()

    def _on_reorder_component(self, source_eid: str, dragged_key: str, target_key: str):
        if not self._entity or self._entity.id != source_eid:
            return
        keys = list(self._entity._components.keys())
        if dragged_key not in keys or target_key not in keys:
            return
        dragged_idx = keys.index(dragged_key)
        target_idx = keys.index(target_key)
        if dragged_idx == target_idx:
            return
        keys.remove(dragged_key)
        new_pos = keys.index(target_key)
        keys.insert(new_pos + 1 if dragged_idx < target_idx else new_pos, dragged_key)
        self._entity._components = {k: self._entity._components[k] for k in keys}
        self._rebuild()

    def _move_component_up(self, comp_key: str):
        if not self._entity: return
        self._entity.move_component(comp_key, -1)
        self._rebuild()

    def _move_component_down(self, comp_key: str):
        if not self._entity: return
        self._entity.move_component(comp_key, 1)
        self._rebuild()

    def _show_add_component_menu(self):
        if not self._entity: return
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QCursor
        dlg = ComponentPickerDialog(self._entity, None)
        dlg.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        dw, dh = dlg.width(), dlg.height()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() - dw // 2
        y = cursor_pos.y() + 4
        if y + dh > screen.bottom():
            y = cursor_pos.y() - dh - 4
        if y < screen.top():
            y = screen.top()
        if x + dw > screen.right():
            x = screen.right() - dw
        if x < screen.left():
            x = screen.left()
        dlg.move(x, y)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.selected_result()
            if result and result["type"] == "component":
                self._add_component(result["name"])
            elif result and result["type"] == "script":
                self._add_script_component(result["path"])

    def _send_collab_component_add(self, comp_name: str, added_key: str):
        if not self._entity or not hasattr(self, '_engine') or not self._engine:
            return
        collab = self._engine.collab_manager if hasattr(self._engine, 'collab_manager') else None
        if not collab or not collab.connected:
            return
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(comp_name)
        if not cls:
            return
        comp_key = added_key or next((k for k in self._entity._components if k == comp_name or k.startswith(comp_name + ".")), None)
        comp = self._entity._components.get(comp_key) if comp_key else None
        if not comp:
            return
        comp_data = comp.serialize() if hasattr(comp, 'serialize') else {}
        if not comp_data:
            comp_data = {}
            for attr in dir(comp):
                if attr.startswith('_'): continue
                v = getattr(comp, attr)
                if callable(v): continue
                comp_data[attr] = v
        collab.send_component_add(self._entity.id, comp_name, comp_data)

    def _send_collab_component_remove(self, comp_key: str):
        if not self._entity or not hasattr(self, '_engine') or not self._engine:
            return
        collab = self._engine.collab_manager if hasattr(self._engine, 'collab_manager') else None
        if not collab or not collab.connected:
            return
        collab.send_component_remove(self._entity.id, comp_key)

    def _add_component(self, comp_name: str):
        if not self._entity: return
        from core.ecs import ComponentRegistry
        from core.foundation.cmd import AddComponentCommand, CompoundCommand
        cls = ComponentRegistry.get(comp_name)
        if not cls:
            return
        can_multiple = getattr(cls, '_allow_multiple', False)
        if len(self._selected_entities) > 1:
            cmds = []
            added_keys = []
            for ent in list(self._selected_entities):
                if not can_multiple and ent.has_component(cls):
                    continue
                cmd = AddComponentCommand(ent, cls)
                cmds.append(cmd)
                added_keys.append((ent, cmd))
            if not cmds:
                return
            if len(cmds) == 1:
                get_history().execute(cmds[0])
            else:
                get_history().execute(CompoundCommand(cmds, f"Add {comp_name} x{len(cmds)}"))
            for ent, cmd in added_keys:
                self._send_collab_component_add_for_entity(ent, comp_name, cmd._added_key)
        else:
            if not can_multiple and self._entity.has_component(cls):
                return
            cmd = AddComponentCommand(self._entity, cls)
            get_history().execute(cmd)
            self._send_collab_component_add(comp_name, cmd._added_key)
        self._rebuild()

    def _send_collab_component_add_for_entity(self, entity, comp_name: str, added_key: str):
        if not hasattr(self, '_engine') or not self._engine:
            return
        collab = self._engine.collab_manager if hasattr(self._engine, 'collab_manager') else None
        if not collab or not collab.connected:
            return
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(comp_name)
        if not cls:
            return
        comp_key = added_key or next((k for k in entity._components if k == comp_name or k.startswith(comp_name + ".")), None)
        comp = entity._components.get(comp_key) if comp_key else None
        if not comp:
            return
        comp_data = comp.serialize() if hasattr(comp, 'serialize') else {}
        collab.send_component_add(entity.id, comp_name, comp_data)

    def _add_script_component(self, script_path: str):
        if not self._entity: return
        from core.components.scripting.scriptc import ScriptComponent
        from core.foundation.cmd import AddComponentCommand, CompoundCommand
        if len(self._selected_entities) > 1:
            cmds = []
            targets = []
            for ent in list(self._selected_entities):
                cmd = AddComponentCommand(ent, ScriptComponent)
                cmds.append(cmd)
                targets.append((ent, cmd))
            if cmds:
                if len(cmds) == 1:
                    get_history().execute(cmds[0])
                else:
                    get_history().execute(CompoundCommand(cmds, f"Add ScriptComponent x{len(cmds)}"))
                root = self._engine.project_root
                for ent, cmd in targets:
                    found = ent.get_components(ScriptComponent)
                    if found:
                        try:
                            found[-1].script_path = os.path.relpath(script_path, root).replace("\\", "/")
                        except ValueError:
                            found[-1].script_path = os.path.abspath(script_path)
                    self._send_collab_component_add_for_entity(ent, "ScriptComponent", cmd._added_key)
        else:
            cmd = AddComponentCommand(self._entity, ScriptComponent)
            get_history().execute(cmd)
            found = self._entity.get_components(ScriptComponent)
            if found:
                root = self._engine.project_root
                try:
                    found[-1].script_path = os.path.relpath(script_path, root).replace("\\", "/")
                except ValueError:
                    found[-1].script_path = os.path.abspath(script_path)
            self._send_collab_component_add("ScriptComponent", cmd._added_key)
        self._rebuild()

    def _on_apply_prefab(self):
        if not self._entity or not self._entity.is_prefab_instance:
            return
        from core.ecs.prefabp import Prefab, PrefabLibrary
        from core.foundation.logger import Logger
        prefab_path = PrefabLibrary.path_for_guid(self._entity._prefab_guid)
        if not prefab_path:
            Logger.warning("Cannot find prefab asset for this instance.")
            return
        roots = Prefab.get_prefab_roots([self._entity])
        all_entities = []
        def collect(e):
            all_entities.append(e)
            for c in e.children:
                collect(c)
        for r in roots:
            collect(r)
        current_data = {}
        for e in all_entities:
            current_data[e.id] = e.serialize()
        pref = Prefab(self._entity.name, self._entity._prefab_guid)
        pref.roots_data = [current_data[r.id] for r in roots]
        pref.save(prefab_path)
        PrefabLibrary.invalidate(prefab_path)
        self._rebuild()

    def _on_revert_prefab(self):
        if not self._entity or not self._entity.is_prefab_instance:
            return
        from core.foundation.cmd import RevertPrefabInstanceCommand, get_history
        from core.ecs.prefabp import Prefab
        scene = self._engine.scene if hasattr(self._engine, 'scene') else None
        if not scene:
            return
        roots = Prefab.get_prefab_roots([self._entity])
        cmd = RevertPrefabInstanceCommand(scene, roots)
        get_history().execute(cmd)
        self._rebuild()

