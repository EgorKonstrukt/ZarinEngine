# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.terrain_graph.nodesp.base import _TerrainNode


class DomainWarpNode(_TerrainNode):
    NODE_NAME = "Domain Warp"
    NODE_TYPE = "uv_modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "strength": {"default": 0.6, "label": "Strength", "min": 0.0, "max": 2.0, "step": 0.01, "decimals": 3},
        "warpFrequency": {"default": 0.018, "label": "Frequency", "min": 0.0, "max": 0.2, "step": 0.001, "decimals": 4},
        "warpIterations": {"default": 3.0, "label": "Iterations", "min": 1.0, "max": 4.0, "step": 1.0, "decimals": 0},
        "seed": {"default": 1337.0, "label": "Seed", "min": 0.0, "max": 100000.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_output("out", "uv")

    def get_glsl(self, var_name, var_map):
        v = var_name
        return """for (int _wi = 0; _wi < 4; _wi++) {{
            if (_wi >= int(u_{v}_warpIterations)) break;
            vec2 _wq{v} = vec2(
                fbm(p * u_{v}_warpFrequency * 0.5 + float(_wi) * 2.7, u_{v}_seed + 17.0 + float(_wi) * 5.0, 3, 2.0, 0.5, 0.0, 4.0, 1.0, 0.0, 2.0, 0.0),
                fbm((p + vec2(5.2, 1.3)) * u_{v}_warpFrequency * 0.5 + float(_wi) * 2.7, u_{v}_seed + 83.0 + float(_wi) * 5.0, 3, 2.0, 0.5, 0.0, 4.0, 1.0, 0.0, 2.0, 0.0)
            );
            p = p + _wq{v} * u_{v}_strength;
        }}""".format(v=v)


class ErosionNode(_TerrainNode):
    NODE_NAME = "Erosion"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "thermal": {"default": 0.35, "label": "Thermal", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "hydraulic": {"default": 0.5, "label": "Hydraulic", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "iterations": {"default": 16.0, "label": "Iterations", "min": 1.0, "max": 24.0, "step": 1.0, "decimals": 0},
        "talus": {"default": 0.04, "label": "Talus Angle", "min": 0.001, "max": 0.2, "step": 0.001, "decimals": 4},
        "sedimentCapacity": {"default": 4.0, "label": "Sediment Capacity", "min": 0.0, "max": 12.0, "step": 0.1, "decimals": 2},
        "erosionStrength": {"default": 0.3, "label": "Erosion Strength", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        inp = self._input_var(var_map, 0)
        v = var_name
        return """heights[y * res + x] = {inp};
        barrier();
        for (int _ek = 0; _ek < 24; _ek++) {{
            bool _doE = float(_ek) < u_{v}_iterations;
            if (u_{v}_hydraulic > 0.0 && _doE && x > 0 && y > 0 && x < res - 1 && y < res - 1) {{
                float _t = sample_h(ivec2(x, y));
                float _hl = sample_h(ivec2(x - 1, y));
                float _hr = sample_h(ivec2(x + 1, y));
                float _hd = sample_h(ivec2(x, y - 1));
                float _hu = sample_h(ivec2(x, y + 1));
                float _dx = (_hr - _hl) * 0.5;
                float _dy = (_hu - _hd) * 0.5;
                float _sl = max(1e-5, sqrt(_dx * _dx + _dy * _dy));
                float _cap = u_{v}_sedimentCapacity * (_sl / sqrt(1.0 + _sl * _sl)) * u_{v}_erosionStrength;
                float _dep = 0.0;
                if (_dep < _cap) {{
                    float _erode = min((_cap - _dep) * 0.2, max(0.0, _sl * 0.5));
                    heights[y * res + x] = _t - _erode;
                    _dep += _erode;
                }} else {{
                    float _dp = (_dep - _cap) * 0.2;
                    heights[y * res + x] = _t + _dp;
                    _dep -= _dp;
                }}
            }}
            if (u_{v}_thermal > 0.0 && _doE && x > 0 && y > 0 && x < res - 1 && y < res - 1) {{
                float _t = sample_h(ivec2(x, y));
                float _ne = sample_h(ivec2(x + 1, y)) - _t;
                float _nw = sample_h(ivec2(x - 1, y)) - _t;
                float _nn = sample_h(ivec2(x, y + 1)) - _t;
                float _ns = sample_h(ivec2(x, y - 1)) - _t;
                float _maxd = max(max(_ne, _nw), max(_nn, _ns));
                if (_maxd > u_{v}_talus) {{
                    float _loss = min((_maxd - u_{v}_talus) * u_{v}_thermal * 0.25, _maxd * 0.5);
                    heights[y * res + x] = _t - _loss;
                }}
            }}
            barrier();
        }}
        float {v} = heights[y * res + x];""".format(inp=inp, v=v)


class TerraceNode(_TerrainNode):
    NODE_NAME = "Terrace"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "steps": {"default": 8.0, "label": "Steps", "min": 2.0, "max": 32.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = terrace_func({inp}, u_{v}_steps);".format(v=var_name, inp=self._input_var(var_map, 0))


class PlateauNode(_TerrainNode):
    NODE_NAME = "Plateau"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "level": {"default": 0.5, "label": "Level", "min": -1.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "sharpness": {"default": 4.0, "label": "Sharpness", "min": 0.0, "max": 16.0, "step": 0.1, "decimals": 2},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = plateau_func({inp}, u_{v}_level, u_{v}_sharpness);".format(v=var_name, inp=self._input_var(var_map, 0))


class SlopeMaskNode(_TerrainNode):
    NODE_NAME = "Slope Mask"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "minSlope": {"default": 0.35, "label": "Min Slope", "min": 0.0, "max": 1.5, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        inp = self._input_var(var_map, 0)
        v = var_name
        return """    float _sx_{v} = 0.0;
            float _sz_{v} = 0.0;
            if (x > 0 && x < res - 1) {{
                _sx_{v} = (heights[y * res + x + 1] - heights[y * res + x - 1]) * 0.5;
            }}
            if (y > 0 && y < res - 1) {{
                _sz_{v} = (heights[(y + 1) * res + x] - heights[(y - 1) * res + x]) * 0.5;
            }}
            float _slope_{v} = sqrt(_sx_{v} * _sx_{v} + _sz_{v} * _sz_{v});
            float {v} = 1.0 - smoothstep(u_{v}_minSlope, u_{v}_minSlope + 0.25, _slope_{v});""".format(v=v)


class StrataNode(_TerrainNode):
    NODE_NAME = "Strata"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "scale": {"default": 12.0, "label": "Scale", "min": 1.0, "max": 40.0, "step": 0.5, "decimals": 2},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = {inp} + strata_func({inp}, u_{v}_scale) * 0.04;".format(v=var_name, inp=self._input_var(var_map, 0))


class SharpenNode(_TerrainNode):
    NODE_NAME = "Sharpen"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "strength": {"default": 0.5, "label": "Strength", "min": 0.0, "max": 2.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        inp = self._input_var(var_map, 0)
        return "float {v} = {inp} + sign({inp}) * pow(abs({inp}) * 0.5 + 1e-10, u_{v}_strength) * u_{v}_strength;".format(v=var_name, inp=inp)


class SmoothNode(_TerrainNode):
    NODE_NAME = "Smooth"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "strength": {"default": 0.15, "label": "Strength", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        inp = self._input_var(var_map, 0)
        v = var_name
        return """    float _avg_{v} = 0.0;
            if (x > 0 && x < res - 1 && y > 0 && y < res - 1) {{
                _avg_{v} = (sample_h(ivec2(x-1,y)) + sample_h(ivec2(x+1,y)) +
                            sample_h(ivec2(x,y-1)) + sample_h(ivec2(x,y+1))) * 0.25;
            }} else {{
                _avg_{v} = {inp};
            }}
            float {v} = ({inp} > _avg_{v}) ? mix({inp}, _avg_{v}, u_{v}_strength) : {inp};""".format(v=v, inp=inp)


class NormalizeNode(_TerrainNode):
    NODE_NAME = "Normalize"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        inp = self._input_var(var_map, 0)
        return "float {v} = {inp} * 0.5 + 0.5;".format(v=var_name, inp=inp)


class InvertNode(_TerrainNode):
    NODE_NAME = "Invert"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = -{inp};".format(v=var_name, inp=self._input_var(var_map, 0))


class HeightBiasNode(_TerrainNode):
    NODE_NAME = "Height Bias"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "bias": {"default": 0.0, "label": "Bias", "min": -1.0, "max": 1.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = {inp} + u_{v}_bias;".format(v=var_name, inp=self._input_var(var_map, 0))


class RiverNode(_TerrainNode):
    NODE_NAME = "River"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "strength": {"default": 0.0, "label": "Strength", "min": 0.0, "max": 1.0, "step": 0.01, "decimals": 3},
        "seed": {"default": 1337.0, "label": "Seed", "min": 0.0, "max": 100000.0, "step": 1.0, "decimals": 0},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        inp = self._input_var(var_map, 0)
        return "float {v} = {inp} - river_carve(uv, u_{v}_seed) * u_{v}_strength;".format(v=var_name, inp=inp)


class ClampNode(_TerrainNode):
    NODE_NAME = "Clamp"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "min_val": {"default": -1.0, "label": "Min", "min": -10.0, "max": 10.0, "step": 0.01, "decimals": 3},
        "max_val": {"default": 1.0, "label": "Max", "min": -10.0, "max": 10.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        return "float {v} = clamp({inp}, u_{v}_min_val, u_{v}_max_val);".format(v=var_name, inp=self._input_var(var_map, 0))


class RemapNode(_TerrainNode):
    NODE_NAME = "Remap"
    NODE_TYPE = "modifier"
    NODE_ICON = "qobject.png"
    _PARAMS = {
        "in_min": {"default": -1.0, "label": "In Min", "min": -10.0, "max": 10.0, "step": 0.01, "decimals": 3},
        "in_max": {"default": 1.0, "label": "In Max", "min": -10.0, "max": 10.0, "step": 0.01, "decimals": 3},
        "out_min": {"default": 0.0, "label": "Out Min", "min": -10.0, "max": 10.0, "step": 0.01, "decimals": 3},
        "out_max": {"default": 1.0, "label": "Out Max", "min": -10.0, "max": 10.0, "step": 0.01, "decimals": 3},
    }

    def __init__(self):
        super().__init__()
        self.add_input("in", "hf")
        self.add_output("out", "hf")

    def get_glsl(self, var_name, var_map):
        inp = self._input_var(var_map, 0)
        v = var_name
        return "float {v} = ({inp} - u_{v}_in_min) / max(u_{v}_in_max - u_{v}_in_min, 1e-10) * (u_{v}_out_max - u_{v}_out_min) + u_{v}_out_min;".format(v=v, inp=inp)
