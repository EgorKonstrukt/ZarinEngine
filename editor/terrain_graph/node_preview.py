# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
from typing import Optional, Set
from editor.terrain_graph.glsl_chunks import ALL_GLSL_FUNCTIONS
from core.foundation.logger import Logger

_PREVIEW_RES = 48
_CACHE: dict = {}
_CACHE_ORDER: list = []
_CACHE_MAX = 64


def _collect_ancestors(target, node_map: dict, id_set: set) -> Set[int]:
    visited = set()
    stack = [target]
    while stack:
        node = stack.pop()
        nid = id(node)
        if nid in visited:
            continue
        visited.add(nid)
        try:
            ports = node.input_ports()
        except Exception:
            continue
        for port in ports:
            try:
                connected = port.connected_ports()
            except Exception:
                continue
            for c in connected:
                try:
                    cn = c.node()
                except Exception:
                    continue
                if id(cn) in id_set and id(cn) not in visited:
                    stack.append(cn)
    return visited


def _topo_sort_nodes(nodes):
    visited = set()
    result = []
    node_map = {id(n): n for n in nodes}

    def visit(nid):
        if nid in visited:
            return
        visited.add(nid)
        node = node_map[nid]
        try:
            ports = node.input_ports()
        except Exception:
            result.append(node)
            return
        for port in ports:
            try:
                connected = port.connected_ports()
            except Exception:
                continue
            for c in connected:
                try:
                    cn = c.node()
                except Exception:
                    continue
                if id(cn) in node_map:
                    visit(id(cn))
        result.append(node)

    for nid in node_map:
        visit(nid)
    return result


def _snap_res(resolution: int) -> int:
    r = int(resolution)
    if r < 16:
        r = 16
    if r > _PREVIEW_RES:
        r = _PREVIEW_RES
    r = (r // 16) * 16
    if r < 16:
        r = 16
    return r


def _uniforms_key(all_uniforms: dict):
    try:
        items = []
        for k in sorted(all_uniforms.keys()):
            v = all_uniforms[k]
            if isinstance(v, str):
                v = float(v)
            items.append((k, float(v)))
        return hash(tuple(items))
    except Exception:
        try:
            return hash(repr(sorted(all_uniforms.items())))
        except Exception:
            return id(all_uniforms)


def _build_source(relevant, var_map, all_uniforms: dict, target_var: str, res: int) -> str:
    uniform_lines = []
    for n in relevant:
        vn = var_map[id(n)]
        try:
            lines = n.get_uniforms(vn)
        except Exception:
            continue
        for line in lines:
            uniform_lines.append("    " + line)
    code_blocks = []
    for n in relevant:
        vn = var_map[id(n)]
        try:
            block = n.get_glsl(vn, var_map)
        except Exception:
            continue
        code_blocks.append(block)
    code_str = "\n".join("    " + c.replace("\n", "\n    ") for c in code_blocks)
    return (
        "#version 430\n"
        "layout(local_size_x=16, local_size_y=16, local_size_z=1) in;\n"
        "layout(std430, binding=0) buffer HeightBuffer {\n"
        "    float heights[];\n"
        "};\n"
        "uniform int u_resolution;\n"
        + "\n".join(uniform_lines) + "\n"
        + ALL_GLSL_FUNCTIONS + "\n"
        "void main() {\n"
        "    int x = int(gl_GlobalInvocationID.x);\n"
        "    int y = int(gl_GlobalInvocationID.y);\n"
        "    int res = u_resolution;\n"
        "    if (x >= res || y >= res) return;\n"
        "    vec2 uv = (vec2(x, y) + 0.5) / float(res);\n"
        "    vec2 p = uv;\n"
        + code_str + "\n"
        "    heights[y * res + x] = " + target_var + ";\n"
        "}\n"
    )


def _collect_uniforms(relevant, var_map: dict) -> dict:
    all_uniforms: dict = {}
    for n in relevant:
        vn = var_map[id(n)]
        try:
            all_uniforms.update(n.get_uniform_values(vn))
        except Exception:
            pass
    return all_uniforms


def _preview_for_target(target_node, node_map: dict, id_set: set, global_order: list, res: int) -> Optional[np.ndarray]:
    if id(target_node) not in node_map:
        return None
    ancestor_ids = _collect_ancestors(target_node, node_map, id_set)
    relevant = [n for n in global_order if id(n) in ancestor_ids]
    if not relevant:
        return None
    var_map: dict = {}
    counter = 0
    for n in relevant:
        var_map[id(n)] = "n{}".format(counter)
        counter += 1
    all_uniforms = _collect_uniforms(relevant, var_map)
    target_var = var_map.get(id(target_node))
    if target_var is None:
        return None
    all_uniforms["u_resolution"] = res
    source = _build_source(relevant, var_map, all_uniforms, target_var, res)
    key = (hash(source), _uniforms_key(all_uniforms), res)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from editor.terrain_graph.gpu_runner import run_preview_shader
        hf = run_preview_shader(source, res, all_uniforms)
    except Exception as e:
        Logger.warning(f"TerrainNodePreview: failed to compute preview: {e}")
        return None
    if hf is not None:
        _CACHE[key] = hf
        _CACHE_ORDER.append(key)
        while len(_CACHE_ORDER) > _CACHE_MAX:
            old = _CACHE_ORDER.pop(0)
            _CACHE.pop(old, None)
    return hf


def compute_node_preview(target_node, graph, resolution: int = 64) -> Optional[np.ndarray]:
    graph_nodes = list(graph.all_nodes())
    if not graph_nodes:
        return None
    node_map = {id(n): n for n in graph_nodes}
    id_set = set(node_map.keys())
    res = _snap_res(resolution)
    global_order = _topo_sort_nodes(graph_nodes)
    return _preview_for_target(target_node, node_map, id_set, global_order, res)


def update_all_previews(graph, resolution: int = 64):
    graph_nodes = list(graph.all_nodes())
    if not graph_nodes:
        return
    res = _snap_res(resolution)
    node_map = {id(n): n for n in graph_nodes}
    id_set = set(node_map.keys())
    global_order = _topo_sort_nodes(graph_nodes)
    for node in list(global_order):
        pw = getattr(node, "_preview_widget", None)
        if pw is None:
            continue
        try:
            visible = pw.isVisible()
        except Exception:
            visible = True
        if not visible:
            continue
        hf = _preview_for_target(node, node_map, id_set, global_order, res)
        try:
            pw.set_preview(hf)
        except Exception:
            pass


def clear_preview_cache():
    _CACHE.clear()
    _CACHE_ORDER.clear()
