# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.shader_graph.nodesp.base import _InputNode, _OutputNode, _TextureNode


class _VertexPositionNode(_InputNode):
    NODE_NAME = "Vertex Position"
    NODE_ICON = "mdl-cube.png"

    def __init__(self):
        super().__init__()
        self.add_output("position", "vec3")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "vp0")
        return f"vec3 {uid} = in_position;"


class _UVNode(_InputNode):
    NODE_NAME = "UV"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_output("uv", "vec2")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "uv0")
        return f"vec2 {uid} = in_uv;"


class _NormalNode(_InputNode):
    NODE_NAME = "Normal"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_output("normal", "vec3")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "n0")
        return f"vec3 {uid} = normalize(v_normal);"


class _TimeNode(_InputNode):
    NODE_NAME = "Time"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_output("time", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "t0")
        return f"float {uid} = u_time;"


class _ColorNode(_InputNode):
    NODE_NAME = "Color"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("in", "vec4")
        self.add_output("out", "vec4")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "c0")
        return f"vec4 {uid} = vec4(1.0);"


class _FloatNode(_InputNode):
    NODE_NAME = "Float"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_output("out", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "f0")
        return f"float {uid} = 0.0;"


class _Texture2DNode(_TextureNode):
    NODE_NAME = "Texture 2D"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("uv", "vec2")
        self.add_output("color", "vec4")
        self.add_output("r", "float")
        self.add_output("g", "float")
        self.add_output("b", "float")
        self.add_output("a", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "tex0")
        uv_uid = self._find_input_uid(uid_map, "uv", f"{uid}_uv")
        return (
            f"vec4 {uid} = texture(u_tex0, {uv_uid});\n"
            f"float {uid}_r = {uid}.r;\n"
            f"float {uid}_g = {uid}.g;\n"
            f"float {uid}_b = {uid}.b;\n"
            f"float {uid}_a = {uid}.a;"
        )

    def _find_input_uid(self, uid_map, port_name, default):
        for node_id, node_uid in uid_map.items():
            if node_id != id(self):
                continue
        return default


class _VertexOutputNode(_OutputNode):
    NODE_NAME = "Vertex Output"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("position", "vec3")
        self.add_input("normal", "vec3")
        self.add_input("uv", "vec2")

    def generate_code(self, uid_map):
        pos = self._get_connected_value(uid_map, "position", "in_position")
        nrm = self._get_connected_value(uid_map, "normal", "in_normal")
        uv = self._get_connected_value(uid_map, "uv", "in_uv")
        return (
            f"v_normal = normalize(_normal_matrix * {nrm});\n"
            f"v_uv = {uv};\n"
            f"vec4 world_pos = _model * vec4({pos}, 1.0);\n"
            f"v_world_pos = world_pos.xyz;\n"
            f"vec4 view_pos = u_view * world_pos;\n"
            f"v_view_pos = view_pos.xyz;\n"
            f"gl_Position = u_proj * u_view * world_pos;"
        )

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _FragmentOutputNode(_OutputNode):
    NODE_NAME = "Fragment Output"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("color", "vec3")
        self.add_input("alpha", "float")
        self.add_input("emission", "vec3")

    def generate_code(self, uid_map):
        color = self._get_connected_value(uid_map, "color", "vec3(1.0, 0.0, 1.0)")
        alpha = self._get_connected_value(uid_map, "alpha", "1.0")
        emission = self._get_connected_value(uid_map, "emission", "vec3(0.0)")
        return (
            f"vec3 result = {color};\n"
            f"vec3 emission = {emission};\n"
            f"result = result / (result + vec3(1.0));\n"
            f"result = pow(result, vec3(1.0 / 2.2));\n"
            f"frag_color = vec4(result + emission, {alpha});"
        )

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default
