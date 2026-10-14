# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.terrain_graph.nodesp.base import _TerrainNode


class PerlinNoiseNode(_TerrainNode):
    NODE_NAME = "Perlin Noise"
    NODE_TYPE = "generator"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "frequency": {"default": 0.010, "label": "Frequency", "min": 0.001, "max": 1.0, "step": 0.001, "decimals": 4},
        "octaves": {"default": 9, "label": "Octaves", "min": 1, "max": 16, "step": 1, "decimals": 0, "glsl_type": "int"},
        "lacunarity": {"default": 2.03, "label": "Lacunarity", "min": 0.5, "max": 4.0, "step": 0.01, "decimals": 3},
        "persistence": {"default": 0.5, "label": "Persistence", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "fractalTwist": {"default": 0.0, "label": "Fractal Twist", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "seed": {"default": 1337.0, "label": "Seed", "min": 0.0, "max": 100000.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = fbm(p * u_{v}_frequency * float(res) * 0.5, u_{v}_seed, u_{v}_octaves, u_{v}_lacunarity, u_{v}_persistence, 0.0, 4.0, 1.0, 0.0, 2.0, u_{v}_fractalTwist);".format(v=var_name)


class RidgedNoiseNode(_TerrainNode):
    NODE_NAME = "Ridged Noise"
    NODE_TYPE = "generator"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "frequency": {"default": 0.010, "label": "Frequency", "min": 0.001, "max": 1.0, "step": 0.001, "decimals": 4},
        "octaves": {"default": 9, "label": "Octaves", "min": 1, "max": 16, "step": 1, "decimals": 0, "glsl_type": "int"},
        "lacunarity": {"default": 2.03, "label": "Lacunarity", "min": 0.5, "max": 4.0, "step": 0.01, "decimals": 3},
        "persistence": {"default": 0.5, "label": "Persistence", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "ridgePower": {"default": 4.0, "label": "Ridge Power", "min": 0.5, "max": 8.0, "step": 0.1, "decimals": 2},
        "ridgeSharpness": {"default": 1.0, "label": "Ridge Sharpness", "min": 0.5, "max": 1.0, "step": 0.01, "decimals": 3},
        "seed": {"default": 1337.0, "label": "Seed", "min": 0.0, "max": 100000.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = fbm(p * u_{v}_frequency * float(res) * 0.5, u_{v}_seed, u_{v}_octaves, u_{v}_lacunarity, u_{v}_persistence, 1.0, u_{v}_ridgePower, u_{v}_ridgeSharpness, 0.0, 2.0, 0.0);".format(v=var_name)


class BillowNoiseNode(_TerrainNode):
    NODE_NAME = "Billow Noise"
    NODE_TYPE = "generator"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "frequency": {"default": 0.010, "label": "Frequency", "min": 0.001, "max": 1.0, "step": 0.001, "decimals": 4},
        "octaves": {"default": 9, "label": "Octaves", "min": 1, "max": 16, "step": 1, "decimals": 0, "glsl_type": "int"},
        "lacunarity": {"default": 2.03, "label": "Lacunarity", "min": 0.5, "max": 4.0, "step": 0.01, "decimals": 3},
        "persistence": {"default": 0.5, "label": "Persistence", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "billowPower": {"default": 2.0, "label": "Billow Power", "min": 0.5, "max": 6.0, "step": 0.1, "decimals": 2},
        "seed": {"default": 1337.0, "label": "Seed", "min": 0.0, "max": 100000.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = fbm(p * u_{v}_frequency * float(res) * 0.5, u_{v}_seed, u_{v}_octaves, u_{v}_lacunarity, u_{v}_persistence, 0.0, 4.0, 1.0, 1.0, u_{v}_billowPower, 0.0);".format(v=var_name)


class VoronoiNode(_TerrainNode):
    NODE_NAME = "Voronoi"
    NODE_TYPE = "generator"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "frequency": {"default": 0.020, "label": "Frequency", "min": 0.001, "max": 1.0, "step": 0.001, "decimals": 4},
        "seed": {"default": 1337.0, "label": "Seed", "min": 0.0, "max": 100000.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = voronoi(p, u_{v}_frequency * float(res) * 0.5, u_{v}_seed);".format(v=var_name)


class ConstantNode(_TerrainNode):
    NODE_NAME = "Constant"
    NODE_TYPE = "generator"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "value": {"default": 0.0, "label": "Value", "min": -10.0, "max": 10.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = u_{v}_value;".format(v=var_name)


class ContinentMaskNode(_TerrainNode):
    NODE_NAME = "Continent Mask"
    NODE_TYPE = "generator"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "scale": {"default": 0.0025, "label": "Scale", "min": 0.0005, "max": 0.05, "step": 0.0005, "decimals": 5},
        "falloff": {"default": 1.4, "label": "Falloff", "min": 0.2, "max": 4.0, "step": 0.01, "decimals": 3},
        "seed": {"default": 1337.0, "label": "Seed", "min": 0.0, "max": 100000.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = continent_func(p, u_{v}_seed, u_{v}_scale * float(res) * 0.5, u_{v}_falloff);".format(v=var_name)


class DuneNode(_TerrainNode):
    NODE_NAME = "Dune"
    NODE_TYPE = "generator"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "frequency": {"default": 8.0, "label": "Frequency", "min": 1.0, "max": 32.0, "step": 0.5, "decimals": 1},
        "direction": {"default": 0.0, "label": "Direction", "min": 0.0, "max": 6.283, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = dune_func(p, u_{v}_frequency, u_{v}_direction);".format(v=var_name)
