# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.terrain_graph.nodesp.base import _TerrainNode


class AddNode(_TerrainNode):
    NODE_NAME = "Add"
    NODE_TYPE = "math"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "hf")
        self.add_input("B", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        iv = self._all_input_vars(var_map)
        return "float {v} = {a} + {b};".format(v=var_name, a=iv[0], b=iv[1])


class SubtractNode(_TerrainNode):
    NODE_NAME = "Subtract"
    NODE_TYPE = "math"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "hf")
        self.add_input("B", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        iv = self._all_input_vars(var_map)
        return "float {v} = {a} - {b};".format(v=var_name, a=iv[0], b=iv[1])


class MultiplyNode(_TerrainNode):
    NODE_NAME = "Multiply"
    NODE_TYPE = "math"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "hf")
        self.add_input("B", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        iv = self._all_input_vars(var_map)
        return "float {v} = {a} * {b};".format(v=var_name, a=iv[0], b=iv[1])


class BlendNode(_TerrainNode):
    NODE_NAME = "Blend"
    NODE_TYPE = "math"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "factor": {"default": 0.5, "label": "Factor", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("A", "hf")
        self.add_input("B", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        iv = self._all_input_vars(var_map)
        return "float {v} = mix({a}, {b}, u_{v}_factor);".format(v=var_name, a=iv[0], b=iv[1])


class MaxNode(_TerrainNode):
    NODE_NAME = "Max"
    NODE_TYPE = "math"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "hf")
        self.add_input("B", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        iv = self._all_input_vars(var_map)
        return "float {v} = max({a}, {b});".format(v=var_name, a=iv[0], b=iv[1])


class MinNode(_TerrainNode):
    NODE_NAME = "Min"
    NODE_TYPE = "math"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("A", "hf")
        self.add_input("B", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        iv = self._all_input_vars(var_map)
        return "float {v} = min({a}, {b});".format(v=var_name, a=iv[0], b=iv[1])


class HeightOutputNode(_TerrainNode):
    NODE_NAME = "Height Output"
    NODE_TYPE = "output"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "heightScale": {"default": 120.0, "label": "Height Scale", "min": 0.0, "max": 500.0, "step": 0.5, "decimals": 2},
        "offset": {"default": 0.0, "label": "Offset", "min": -200.0, "max": 200.0, "step": 0.5, "decimals": 2},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = {inp} * u_{v}_heightScale + u_{v}_offset;".format(v=var_name, inp=self._input_var(var_map, 0))
