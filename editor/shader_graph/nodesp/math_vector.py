# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.shader_graph.nodesp.base import _MathNode, _VectorNode


class _AddNode(_MathNode):
    NODE_NAME = "Add"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "float")
        self.add_input("B", "float")
        self.add_output("result", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "add0")
        a = self._get_connected_value(uid_map, "A", "0.0")
        b = self._get_connected_value(uid_map, "B", "0.0")
        return f"float {uid} = {a} + {b};"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _MultiplyNode(_MathNode):
    NODE_NAME = "Multiply"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "float")
        self.add_input("B", "float")
        self.add_output("result", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "mul0")
        a = self._get_connected_value(uid_map, "A", "0.0")
        b = self._get_connected_value(uid_map, "B", "0.0")
        return f"float {uid} = {a} * {b};"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _SubtractNode(_MathNode):
    NODE_NAME = "Subtract"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "float")
        self.add_input("B", "float")
        self.add_output("result", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "sub0")
        a = self._get_connected_value(uid_map, "A", "0.0")
        b = self._get_connected_value(uid_map, "B", "0.0")
        return f"float {uid} = {a} - {b};"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _LerpNode(_MathNode):
    NODE_NAME = "Lerp"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "vec3")
        self.add_input("B", "vec3")
        self.add_input("T", "float")
        self.add_output("result", "vec3")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "lerp0")
        a = self._get_connected_value(uid_map, "A", "vec3(0.0)")
        b = self._get_connected_value(uid_map, "B", "vec3(1.0)")
        t = self._get_connected_value(uid_map, "T", "0.5")
        return f"vec3 {uid} = mix({a}, {b}, {t});"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _NormalizeNode(_VectorNode):
    NODE_NAME = "Normalize"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("in", "vec3")
        self.add_output("out", "vec3")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "norm0")
        inp = self._get_connected_value(uid_map, "in", "vec3(0.0, 1.0, 0.0)")
        return f"vec3 {uid} = normalize({inp});"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _DotProductNode(_MathNode):
    NODE_NAME = "Dot Product"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "vec3")
        self.add_input("B", "vec3")
        self.add_output("result", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "dot0")
        a = self._get_connected_value(uid_map, "A", "vec3(0.0)")
        b = self._get_connected_value(uid_map, "B", "vec3(0.0)")
        return f"float {uid} = dot({a}, {b});"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _FresnelNode(_MathNode):
    NODE_NAME = "Fresnel"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("normal", "vec3")
        self.add_input("view_dir", "vec3")
        self.add_output("result", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "fres0")
        n = self._get_connected_value(uid_map, "normal", "v_normal")
        v = self._get_connected_value(uid_map, "view_dir", "normalize(u_camera_pos - v_world_pos)")
        return f"float {uid} = 1.0 - max(dot({n}, {v}), 0.0);"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _StepNode(_MathNode):
    NODE_NAME = "Step"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("edge", "float")
        self.add_input("x", "float")
        self.add_output("result", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "step0")
        e = self._get_connected_value(uid_map, "edge", "0.5")
        x = self._get_connected_value(uid_map, "x", "0.0")
        return f"float {uid} = step({e}, {x});"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default


class _ClampNode(_MathNode):
    NODE_NAME = "Clamp"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("in", "float")
        self.add_input("min", "float")
        self.add_input("max", "float")
        self.add_output("result", "float")

    def generate_code(self, uid_map):
        uid = uid_map.get(id(self), "clamp0")
        i = self._get_connected_value(uid_map, "in", "0.0")
        mn = self._get_connected_value(uid_map, "min", "0.0")
        mx = self._get_connected_value(uid_map, "max", "1.0")
        return f"float {uid} = clamp({i}, {mn}, {mx});"

    def _get_connected_value(self, uid_map, port_name, default):
        for n in self.inputs()[port_name].connected_ports():
            node = n.node()
            if node in uid_map.values():
                for k, v in uid_map.items():
                    if v == node:
                        return k
        return default
