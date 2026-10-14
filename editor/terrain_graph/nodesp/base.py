# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.NodeGraphQt import BaseNode
from editor.terrain_graph.preview_widget import NodePreviewWidget


class _TerrainNode(BaseNode):
    __identifier__ = 'zarin.terrain'
    NODE_TYPE = "value"
    _PARAMS = {}

    def __init__(self):
        super().__init__()
        for name, info in self._PARAMS.items():
            is_double = info.get("glsl_type", "float") == "float"
            self.add_spinbox(
                name,
                label=info.get("label", name),
                value=0,
                min_value=info.get("min", 0.0),
                max_value=info.get("max", 100.0),
                double=is_double,
            )
            self.set_property(name, info["default"], push_undo=False)
        self._preview_widget = NodePreviewWidget(parent=self.view)
        self.add_custom_widget(self._preview_widget, widget_type="HIDDEN")

    def _get_param(self, name):
        info = self._PARAMS[name]
        raw = self.get_property(name)
        if raw is None:
            return info["default"]
        if info.get("glsl_type", "float") == "int":
            return int(float(raw))
        return float(raw)

    def get_glsl(self, var_name, var_map):
        raise NotImplementedError

    def get_uniforms(self, var_name):
        lines = []
        for name, info in self._PARAMS.items():
            glsl_type = info.get("glsl_type", "float")
            lines.append("uniform {} u_{}_{};".format(glsl_type, var_name, name))
        return lines

    def get_uniform_values(self, var_name):
        vals = {}
        for name in self._PARAMS:
            vals["u_{}_{}".format(var_name, name)] = self._get_param(name)
        return vals

    def _input_var(self, var_map, index=0):
        ports = self.input_ports()
        if index >= len(ports):
            return "0.0"
        connected = ports[index].connected_ports()
        if connected:
            return var_map.get(id(connected[0].node()), "0.0")
        return "0.0"

    def _all_input_vars(self, var_map):
        result = []
        for port in self.input_ports():
            connected = port.connected_ports()
            if connected:
                result.append(var_map.get(id(connected[0].node()), "0.0"))
            else:
                result.append("0.0")
        return result
