# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import json
import os
from typing import Optional, Any
from core.foundation.logger import Logger
from .shader import _parse_shader_file, _project_root, ShaderProperty


class Material:
    def __init__(self, name: str = "Material"):
        self.name: str = name
        self.shader_path: str = ""
        self.properties: dict[str, Any] = {}
        self._shader_properties: list[ShaderProperty] = []
        self._gl_program: Optional[Any] = None

    def set_property(self, name: str, value: Any): self.properties[name] = value
    def get_property(self, name: str, default: Any = None) -> Any: return self.properties.get(name, default)

    @staticmethod
    def _resolve_shader_path(shader_path: str, project_root: str) -> str:
        if os.path.isabs(shader_path) and os.path.exists(shader_path):
            return shader_path
        candidates = []
        if not os.path.isabs(shader_path) and project_root:
            candidates.append(os.path.normpath(os.path.join(project_root, shader_path)))
        engine_root = _project_root()
        if not os.path.isabs(shader_path):
            candidates.append(os.path.normpath(os.path.join(engine_root, shader_path)))
            candidates.append(os.path.normpath(os.path.join(engine_root, "core", "shaders", shader_path)))
        shader_name = os.path.basename(shader_path)
        for sub in ("materials", "internal", "compute", "include", "legacy"):
            candidates.append(os.path.normpath(os.path.join(engine_root, "core", "shaders", sub, shader_name)))
        for c in candidates:
            if os.path.exists(c):
                if os.path.isabs(shader_path):
                    Logger.warning(f"Shader path '{shader_path}' not found, remapped to '{c}'")
                return c
        if os.path.isabs(shader_path):
            return shader_path
        return candidates[0] if candidates else shader_path

    def load_shader_properties(self, shader_path: str, project_root: str = "") -> bool:
        if not shader_path or shader_path in ("default", ""):
            self._shader_properties = []
            return False
        abs_shader = self._resolve_shader_path(shader_path, project_root)
        ext = os.path.splitext(abs_shader)[1].lower()
        if ext != ".shader":
            self._shader_properties = []
            return False
        result = _parse_shader_file(abs_shader)
        if not result:
            self._shader_properties = []
            return False
        shader_props, vert_src, frag_src = result
        self._shader_properties = shader_props
        for p in shader_props:
            if p.name not in self.properties:
                self.properties[p.name] = p.default_value
        return True

    def save(self, path: str, project_root: str = ""):
        root = project_root or os.getcwd()
        abs_path = path if os.path.isabs(path) else os.path.normpath(os.path.join(root, path))
        abs_path = os.path.normpath(abs_path)
        rel_shader = self._rel_path(self.shader_path, root)
        rel_props = dict(self.properties)
        for k, v in list(rel_props.items()):
            if isinstance(v, str) and v:
                rel_props[k] = self._rel_path(v, root)
        data = {"name": self.name, "shader_path": rel_shader, "properties": rel_props}
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        MaterialLibrary._materials[abs_path] = self
        if os.path.normpath(path) != abs_path:
            MaterialLibrary._materials[os.path.normpath(path)] = self

    @classmethod
    def load(cls, path: str, project_root: str = "") -> Optional[Material]:
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".mat", ".zpem"):
                return cls._load_mat_file(path, project_root)
            elif ext == ".json":
                return cls._load_json_file(path, project_root)
            else:
                return None
        except Exception as e:
            Logger.error(f"Failed to load material '{path}': {e}", e)
            return None

    @classmethod
    def _load_mat_file(cls, path: str, project_root: str = "") -> Optional[Material]:
        try:
            mat_dir = os.path.dirname(os.path.abspath(path))
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            name = os.path.splitext(os.path.basename(path))[0]
            m = cls(name)
            if raw.startswith("{"):
                try:
                    data = json.loads(raw)
                    m.shader_path = data.get("shader_path", "")
                    saved_props = data.get("properties", {})
                    m.properties.update(saved_props)
                    if "name" in data:
                        m.name = data["name"]
                except json.JSONDecodeError:
                    pass
            if not m.shader_path:
                m.shader_path = "default"
            false_val = m.properties.pop("false", None)
            if false_val is not None and isinstance(false_val, list) and len(false_val) >= 3:
                m.properties.setdefault("albedo_color", false_val)
            for old_key, new_key in _PROP_MIGRATION.items():
                if old_key in m.properties and new_key not in m.properties:
                    m.properties[new_key] = m.properties[old_key]
            for old_key in _PROP_MIGRATION:
                m.properties.pop(old_key, None)
            m.load_shader_properties(m.shader_path, project_root)
            for k, v in list(m.properties.items()):
                if isinstance(v, str) and v and not os.path.isabs(v):
                    resolved = cls._resolve_texture(v, mat_dir)
                    if not resolved:
                        resolved = cls._resolve_tex_path(v, mat_dir, project_root or os.getcwd())
                    if resolved:
                        m.properties[k] = resolved
            MaterialLibrary._materials[os.path.normpath(path)] = m
            if not os.path.isabs(path) and project_root:
                abs_key = os.path.normpath(os.path.join(project_root, path))
                MaterialLibrary._materials[abs_key] = m
            return m
        except Exception as e:
            Logger.error(f"Failed to load .mat file '{path}': {e}", e)
            return None

    @classmethod
    def _load_json_file(cls, path: str, project_root: str = "") -> Optional[Material]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            m = cls(data.get("name", "Material"))
            m.shader_path = data.get("shader_path", "")
            if not m.shader_path:
                m.shader_path = "default"
            m.properties.update(data.get("properties", {}))
            false_val = m.properties.pop("false", None)
            if false_val is not None and isinstance(false_val, list) and len(false_val) >= 3:
                m.properties.setdefault("albedo_color", false_val)
            for old_key, new_key in _PROP_MIGRATION.items():
                if old_key in m.properties and new_key not in m.properties:
                    m.properties[new_key] = m.properties[old_key]
            for old_key in _PROP_MIGRATION:
                m.properties.pop(old_key, None)
            root = project_root or os.getcwd()
            mat_dir = os.path.dirname(path)
            for k, v in list(m.properties.items()):
                if isinstance(v, str) and v:
                    resolved = cls._resolve_tex_path(v, mat_dir, root)
                    if resolved:
                        m.properties[k] = resolved
            m.load_shader_properties(m.shader_path, project_root)
            MaterialLibrary._materials[os.path.normpath(path)] = m
            if not os.path.isabs(path) and project_root:
                abs_key = os.path.normpath(os.path.join(project_root, path))
                MaterialLibrary._materials[abs_key] = m
            return m
        except Exception as e:
            Logger.error(f"Failed to load material '{path}': {e}", e)
            return None

    @classmethod
    def _resolve_texture(cls, tex_name: str, mat_dir: str) -> str:
        if not tex_name:
            return ""
        for ext in ["", ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".dds"]:
            candidate = os.path.join(mat_dir, tex_name + ext)
            if os.path.exists(candidate):
                return candidate
        candidates = [
            os.path.join(mat_dir, tex_name),
            os.path.join(mat_dir, tex_name + ".png"),
            os.path.join(mat_dir, tex_name + ".jpg"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return ""

    @staticmethod
    def _resolve_tex_path(val: str, mat_dir: str, root: str) -> str:
        if os.path.exists(val):
            return val
        candidate = os.path.normpath(os.path.join(mat_dir, val))
        if os.path.exists(candidate):
            return candidate.replace("\\", "/")
        candidate = os.path.normpath(os.path.join(root, val))
        if os.path.exists(candidate):
            return candidate.replace("\\", "/")
        if len(val) > 1 and val[1] == ":":
            parts = val.replace("\\", "/").split("/")
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if sub:
                    c = os.path.normpath(os.path.join(root, sub))
                    if os.path.exists(c):
                        return c.replace("\\", "/")
        return val

    @staticmethod
    def _rel_path(val: str, root: str) -> str:
        if not val:
            return ""
        if not os.path.isabs(val):
            return val.replace("\\", "/")
        try:
            rel = os.path.relpath(val, root)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:
            pass
        return val


_PROP_MIGRATION = {
    "albedo_color": "_BaseColor",
    "metallic": "_Metallic",
    "smoothness": "_Smoothness",
    "emission_color": "_EmissionColor",
    "emission_intensity": "_EmissionIntensity",
    "_MainTex": "albedo_texture",
    "diffuseMap": "albedo_texture",
    "_BaseTex": "albedo_texture",
}


class MaterialLibrary:
    _materials: dict[str, Material] = {}

    @classmethod
    def register(cls, name: str, mat: Material): cls._materials[name] = mat

    @classmethod
    def get(cls, name: str) -> Optional[Material]: return cls._materials.get(name)

    @classmethod
    def load(cls, path: str, project_root: str = "") -> Optional[Material]:
        if path in cls._materials: return cls._materials[path]
        m = Material.load(path, project_root) if project_root else Material.load(path)
        if m: cls._materials[path] = m
        return m

    @classmethod
    def create_default(cls) -> Material:
        m = Material("Default")
        m.shader_path = "default"
        m.properties = {
            "_BaseColor": [1.0, 1.0, 1.0, 1.0],
            "_Metallic": 0.0,
            "_Smoothness": 0.5,
            "_EmissionColor": [0.0, 0.0, 0.0, 0.0],
            "_EmissionIntensity": 0.0,
            "_OcclusionStrength": 1.0,
            "_Transmission": 0.0,
            "_IOR": 1.5,
        }
        cls._materials["Default"] = m
        return m
