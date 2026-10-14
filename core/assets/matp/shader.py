# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import re
import os
from typing import Any
from core.foundation.logger import Logger


def _project_root():
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.basename(cur) == "core":
            return os.path.dirname(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_SHADER_PROP_RE = re.compile(
    r'(?:\[(\w+)\]\s*)?'
    r'_(\w+)'
    r'\s*\(\s*"([^"]+)"'
    r'\s*,\s*(\w+(?:\s*\([^)]*\))?)'
    r'\s*\)\s*=\s*(.+)'
)


class ShaderProperty:
    def __init__(self, name: str, display_name: str, prop_type: str,
                 default_value: Any, attributes: list[str] | None = None,
                 range_min: float = 0.0, range_max: float = 1.0):
        self.name = name
        self.display_name = display_name
        self.prop_type = prop_type
        self.default_value = default_value
        self.attributes = attributes or []
        self.range_min = range_min
        self.range_max = range_max

    def __repr__(self):
        return f"ShaderProperty({self.name}, {self.display_name}, {self.prop_type})"


def _parse_shader_properties_block(text: str) -> list[ShaderProperty]:
    props = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line == "{" or line == "}":
            continue
        m = _SHADER_PROP_RE.match(line)
        if not m:
            continue
        attr = m.group(1)
        name = "_" + m.group(2)
        display_name = m.group(3)
        raw_type = m.group(4).strip()
        raw_default = m.group(5).strip()
        attributes = [attr] if attr else []
        prop_type = raw_type
        range_min, range_max = 0.0, 1.0
        range_match = re.match(r'Range\s*\(([^,]+),([^)]+)\)', raw_type, re.IGNORECASE)
        if range_match:
            prop_type = "Range"
            range_min = float(range_match.group(1))
            range_max = float(range_match.group(2))
        default_value = _parse_shader_default(raw_type, raw_default)
        props.append(ShaderProperty(
            name=name,
            display_name=display_name,
            prop_type=prop_type,
            default_value=default_value,
            attributes=attributes,
            range_min=range_min,
            range_max=range_max,
        ))
    return props


def _parse_shader_default(raw_type: str, raw_default: str) -> Any:
    t = raw_type.lower().strip()
    if t == "color" or t.startswith("vector"):
        vals = re.findall(r'[\d.]+(?:e[+-]?\d+)?', raw_default)
        return [float(v) for v in vals]
    if t == "float" or t.startswith("range"):
        return float(raw_default.strip())
    if t == "int":
        return int(raw_default.strip())
    if t == "2d" or t == "cube":
        m = re.match(r'"([^"]*)"', raw_default)
        return m.group(1) if m else ""
    return raw_default.strip()


def _extract_all_subshaders(text: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for m in re.finditer(r'GLSLPROGRAM(.*?)ENDGLSL', text, re.DOTALL):
        glsl_body = m.group(1).strip()
        frag_marker = "// @FRAGMENT"
        frag_pos = glsl_body.find(frag_marker)
        if frag_pos < 0:
            continue
        vert_src = glsl_body[:frag_pos].strip()
        frag_src = glsl_body[frag_pos + len(frag_marker):].strip()
        results.append((vert_src, frag_src))
    return results


def _extract_glsl_from_shader(text: str) -> tuple[str, str] | None:
    all_shaders = _extract_all_subshaders(text)
    if not all_shaders:
        return None
    return all_shaders[0]


def _parse_shader_file(path: str) -> tuple[list[ShaderProperty], str, str] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        Logger.error(f"Failed to read shader '{path}': {e}", e)
        return None
    props_start = text.find("Properties")
    if props_start < 0:
        Logger.error(f"No Properties block in shader '{path}'")
        return None
    brace = text.find("{", props_start)
    if brace < 0:
        return None
    depth = 0
    props_end = -1
    for i in range(brace, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                props_end = i
                break
    if props_end < 0:
        return None
    props_text = text[brace + 1:props_end]
    properties = _parse_shader_properties_block(props_text)
    glsl = _extract_glsl_from_shader(text)
    if not glsl:
        return None
    vert_src, frag_src = glsl
    return (properties, vert_src, frag_src)


class ShaderSource:
    def __init__(self, vert: str, frag: str, geom: str = ""):
        self.vert = vert
        self.frag = frag
        self.geom = geom
