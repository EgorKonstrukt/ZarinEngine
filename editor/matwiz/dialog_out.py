# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import re
from PySide6.QtWidgets import QFileDialog, QMessageBox, QComboBox
from PySide6.QtCore import Qt
from core.assets.matp import Material, _project_root
from .keywords import (
    _ALBEDO_KEYWORDS,
    _NORMAL_KEYWORDS,
    _METALLIC_KEYWORDS,
    _ROUGHNESS_KEYWORDS,
    _SMOOTHNESS_KEYWORDS,
    _AO_KEYWORDS,
    _EMISSION_KEYWORDS,
    _HEIGHT_KEYWORDS,
    _DETAIL_ALBEDO_KEYWORDS,
    _DETAIL_NORMAL_KEYWORDS,
    _CLEARCOAT_KEYWORDS,
    _SUBSURFACE_KEYWORDS,
    _THIN_FILM_KEYWORDS,
)
from .naming import _normalize_name, _guess_map_type
from .shaders import _extract_shader_name


class _DialogOutputMixin:
    def _on_browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self._project_root
        )
        if d:
            try:
                rel = os.path.relpath(d, self._project_root)
            except ValueError:
                rel = d
            self._dir_edit.setText(rel.replace("\\", "/"))

    def _build_assignment_map(self) -> dict[str, str]:
        assignments = {}
        for row in range(self._texture_table.rowCount()):
            name_item = self._texture_table.item(row, 0)
            combo = self._texture_table.cellWidget(row, 1)
            if not name_item or not isinstance(combo, QComboBox):
                continue
            filepath = name_item.data(Qt.ItemDataRole.UserRole) or name_item.text()
            prop = combo.currentData()
            if prop and prop != "custom" and prop != "":
                assignments[prop] = filepath
            elif prop == "" or prop == "Auto-detect":
                filename = os.path.basename(filepath)
                guessed = _guess_map_type(filename)
                if guessed:
                    assignments[guessed] = filepath
        return assignments

    def _refresh_preview(self):
        assignments = self._build_assignment_map()
        shader_path = self._get_current_shader_path()
        shader_name = _extract_shader_name(shader_path) if shader_path else "None"
        output_dir = self._dir_edit.text().strip() or "Materials/"
        name_pattern = self._name_edit.text().strip() or "{material_name}"
        lines = [f"Shader: {shader_name}"]
        lines.append(f"Output: {output_dir}/")
        lines.append(f"Name: {name_pattern}")
        if self._submesh_names:
            lines.append(f"Submeshes: {', '.join(self._submesh_names)}")
        lines.append("")
        if assignments:
            lines.append("Texture Assignments:")
            for prop, path in sorted(assignments.items()):
                fname = os.path.basename(path)
                lines.append(f"  {prop} <- {fname}")
        else:
            lines.append("No textures assigned.")
        self._preview_label.setText("\n".join(lines))

    def _on_create(self):
        shader_path = self._get_current_shader_path()
        if not shader_path:
            QMessageBox.warning(self, "Material Wizard", "Please select a shader.")
            return
        assignments = self._build_assignment_map()
        if not assignments:
            QMessageBox.warning(self, "Material Wizard", "Please add and map at least one texture.")
            return
        output_dir = self._dir_edit.text().strip() or "Materials"
        if not os.path.isabs(output_dir):
            output_dir = os.path.normpath(os.path.join(self._project_root, output_dir))
        os.makedirs(output_dir, exist_ok=True)
        name_pattern = self._name_edit.text().strip() or "{material_name}"
        shader_name = _extract_shader_name(shader_path).split("/")[-1].replace(" ", "_")
        created_paths = []
        if self._per_mesh_cb.isChecked():
            if self._submesh_names:
                groups = self._group_textures_by_pattern()
                group_map = {}
                for gname, gprops in groups:
                    group_map[gname.lower()] = (gname, gprops)
                matched_groups = {}
                unmatched_textures = {}
                used_groups = set()
                for sn in self._submesh_names:
                    sn_lower = sn.lower()
                    if sn_lower in group_map:
                        matched_groups[sn] = group_map[sn_lower]
                        used_groups.add(sn_lower)
                    else:
                        unmatched_textures[sn] = dict(assignments)
                for gname, gprops in groups:
                    if gname.lower() not in used_groups:
                        for sn in self._submesh_names:
                            if sn not in matched_groups and sn not in unmatched_textures:
                                matched_groups[sn] = (gname, gprops)
                                break
                for sn in self._submesh_names:
                    if sn in matched_groups:
                        _, group_props = matched_groups[sn]
                    elif sn in unmatched_textures:
                        group_props = unmatched_textures[sn]
                    else:
                        group_props = dict(assignments)
                    mat_name = name_pattern.replace("{material_name}", sn)
                    mat_name = mat_name.replace("{shader_name}", shader_name)
                    mat_name = re.sub(r'[<>:"/\\|?*]', '_', mat_name)
                    if not mat_name.endswith(".mat"):
                        mat_name += ".mat"
                    mat_path = os.path.join(output_dir, mat_name)
                    mat = self._create_material(sn, shader_path, group_props)
                    mat.save(mat_path, self._project_root)
                    created_paths.append(mat_path)
            else:
                groups = self._group_textures_by_pattern()
                if not groups:
                    groups = [("Material", assignments)]
                for group_name, group_props in groups:
                    mat_name = name_pattern.replace("{material_name}", group_name)
                    mat_name = mat_name.replace("{shader_name}", shader_name)
                    mat_name = re.sub(r'[<>:"/\\|?*]', '_', mat_name)
                    if not mat_name.endswith(".mat"):
                        mat_name += ".mat"
                    mat_path = os.path.join(output_dir, mat_name)
                    mat = self._create_material(
                        os.path.splitext(os.path.basename(mat_name))[0],
                        shader_path, group_props
                    )
                    mat.save(mat_path, self._project_root)
                    created_paths.append(mat_path)
        else:
            all_props = dict(assignments)
            mat_name = name_pattern.replace("{material_name}", "Material")
            mat_name = mat_name.replace("{shader_name}", shader_name)
            mat_name = re.sub(r'[<>:"/\\|?*]', '_', mat_name)
            if not mat_name.endswith(".mat"):
                mat_name += ".mat"
            mat_path = os.path.join(output_dir, mat_name)
            mat = self._create_material(
                os.path.splitext(os.path.basename(mat_name))[0],
                shader_path, all_props
            )
            mat.save(mat_path, self._project_root)
            created_paths.append(mat_path)
        self.materials_created.emit(created_paths)
        self.accept()

    def _group_textures_by_pattern(self) -> list[tuple[str, dict[str, str]]]:
        all_files = self._get_texture_files()
        if not all_files:
            return []
        groups: dict[str, dict[str, str]] = {}
        for filepath in all_files:
            filename = os.path.basename(filepath)
            base = _normalize_name(filename)
            group_name = self._extract_group_name(base)
            prop = _guess_map_type(filename)
            if not prop:
                shader_path = self._get_current_shader_path()
                props = self._get_texture_properties(shader_path)
                if props:
                    prop = props[0][0]
                else:
                    prop = "_BaseMap"
            if group_name not in groups:
                groups[group_name] = {}
            groups[group_name][prop] = filepath
        result = [(k, v) for k, v in groups.items()]
        result.sort(key=lambda x: x[0])
        return result

    def _extract_group_name(self, normalized_base: str) -> str:
        suffixes = []
        suffixes.extend(_ALBEDO_KEYWORDS)
        suffixes.extend(_NORMAL_KEYWORDS)
        suffixes.extend(_METALLIC_KEYWORDS)
        suffixes.extend(_ROUGHNESS_KEYWORDS)
        suffixes.extend(_SMOOTHNESS_KEYWORDS)
        suffixes.extend(_AO_KEYWORDS)
        suffixes.extend(_EMISSION_KEYWORDS)
        suffixes.extend(_HEIGHT_KEYWORDS)
        suffixes.extend(_DETAIL_ALBEDO_KEYWORDS)
        suffixes.extend(_DETAIL_NORMAL_KEYWORDS)
        suffixes.extend(_CLEARCOAT_KEYWORDS)
        suffixes.extend(_SUBSURFACE_KEYWORDS)
        suffixes.extend(_THIN_FILM_KEYWORDS)
        suffixes.sort(key=len, reverse=True)
        name = normalized_base
        for suffix in suffixes:
            for sep in ("_", "-", " "):
                token = sep + suffix
                idx = name.rfind(token)
                if idx >= 0:
                    candidate = name[:idx].rstrip("_- ")
                    if candidate:
                        return candidate.replace("_", " ").replace("-", " ").title()
                    break
        name = re.sub(r'_?(color|albedo|diffuse|normal|nrm|metallic|metal|roughness|rough|smoothness|smooth|ao|ambient|emission|emissive|height|displacement|map|tex|texture)\b.*$', '', name)
        name = name.rstrip("_- ")
        if name:
            return name.replace("_", " ").replace("-", " ").title()
        return "Material"

    def _store_shader_path(self, shader_path: str) -> str:
        if shader_path and os.path.isabs(shader_path):
            norm = os.path.normpath(shader_path)
            if self._project_root:
                proj = os.path.normpath(os.path.abspath(self._project_root))
                if norm == proj or norm.startswith(proj + os.sep):
                    return os.path.relpath(norm, proj).replace("\\", "/")
            eng = os.path.normpath(_project_root())
            if norm == eng or norm.startswith(eng + os.sep):
                return os.path.relpath(norm, eng).replace("\\", "/")
        return shader_path

    def _create_material(self, name: str, shader_path: str, texture_map: dict[str, str]) -> Material:
        mat = Material(name)
        mat.shader_path = self._store_shader_path(shader_path)
        mat.load_shader_properties(mat.shader_path, self._project_root)
        for prop in mat._shader_properties:
            if prop.name not in mat.properties:
                mat.properties[prop.name] = prop.default_value
        for prop_name, tex_path in texture_map.items():
            mat.properties[prop_name] = tex_path
        return mat

    def get_created_paths(self) -> list[str]:
        return []
