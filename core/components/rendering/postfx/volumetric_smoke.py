# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import time
import numpy as np
import moderngl
from typing import Optional
from core.ecs.ecs import ComponentRegistry
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.components.inspector_meta import FieldType, InspectorField
from core.components.lighting.light import Light, LightType
from core.maths.math3d import Vec3


VOLUMETRIC_SMOKE_VERT = """
#version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

VOLUMETRIC_SMOKE_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
uniform sampler2D u_depth_tex;
uniform mat4 u_inv_view;
uniform mat4 u_inv_proj;
uniform mat4 u_inv_model;
uniform vec3 u_camera_pos;
uniform float u_time;
uniform float u_seed;
uniform float u_density;
uniform float u_opacity;
uniform int u_steps;
uniform int u_light_steps;
uniform int u_base_oct;
uniform int u_ridge_oct;
uniform int u_detail_oct;
uniform float u_noise_scale;
uniform float u_evolution;
uniform vec3 u_wind;
uniform float u_wind_speed;
uniform float u_fullness;
uniform float u_filaments;
uniform float u_erosion;
uniform float u_cavity;
uniform float u_edge_softness;
uniform float u_fade_top;
uniform float u_fade_bottom;
uniform vec3 u_deep;
uniform vec3 u_mid;
uniform vec3 u_core;
uniform float u_core_size;
uniform float u_emission;
uniform float u_ambient;
uniform vec3 u_sun_dir;
uniform vec3 u_sun_color;
uniform float u_scatter;
uniform float u_aniso;
uniform float u_self_shadow;
uniform float u_shadow_strength;
uniform float u_absorption;
uniform float u_radius;
uniform float u_depth_fade;
uniform float u_bypass;
in vec2 v_uv;
out vec4 frag_color;
float vs_hash(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.11, 0.17, 0.23));
    p *= 19.19;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vs_noise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    vec3 u = f * f * (3.0 - 2.0 * f);
    float a = vs_hash(i);
    float b = vs_hash(i + vec3(1.0, 0.0, 0.0));
    float c = vs_hash(i + vec3(0.0, 1.0, 0.0));
    float d = vs_hash(i + vec3(1.0, 1.0, 0.0));
    float e = vs_hash(i + vec3(0.0, 0.0, 1.0));
    float g = vs_hash(i + vec3(1.0, 0.0, 1.0));
    float h = vs_hash(i + vec3(0.0, 1.0, 1.0));
    float k = vs_hash(i + vec3(1.0, 1.0, 1.0));
    return mix(mix(mix(a, b, u.x), mix(c, d, u.x), u.y), mix(mix(e, g, u.x), mix(h, k, u.x), u.y), u.z);
}
float vs_fbm(vec3 p, int oct) {
    float v = 0.0;
    float amp = 0.5;
    int n = max(oct, 1);
    for (int i = 0; i < 8; i++) {
        if (i >= n) break;
        v += amp * vs_noise(p);
        p = p * 2.04 + vec3(3.1, 7.7, 5.3);
        amp *= 0.5;
    }
    return v / max(1.0 - pow(0.5, float(n)), 1e-3);
}
float vs_ign(vec2 p) {
    vec3 m = vec3(0.06711056, 0.00583715, 52.9829189);
    return fract(m.z * fract(dot(p, m.xy)));
}
vec3 vs_domain(vec3 lp) {
    float ang = u_time * u_evolution * 0.12 + u_seed * 1.7;
    float ca = cos(ang);
    float sa = sin(ang);
    vec3 q = vec3(ca * lp.x - sa * lp.z, lp.y, sa * lp.x + ca * lp.z);
    q += vec3(u_seed * 13.7, u_seed * 7.1 - u_time * u_evolution * 0.05, u_seed * 5.3);
    q += u_wind * (u_time * u_wind_speed);
    return q * u_noise_scale;
}
float vs_density(vec3 lp) {
    float r = length(lp);
    float e0 = min(mix(1.0, u_fullness * 0.85, u_edge_softness), 0.999);
    float shape = 1.0 - smoothstep(e0, 1.0, r);
    if (shape <= 0.001) return 0.0;
    if (u_cavity > 0.001) shape *= smoothstep(u_cavity * 0.8, u_cavity * 0.8 + 0.2, r);
    shape *= 1.0 - u_fade_top * smoothstep(0.2, 1.0, lp.y);
    shape *= 1.0 - u_fade_bottom * smoothstep(0.2, 1.0, -lp.y);
    if (shape <= 0.001) return 0.0;
    vec3 q = vs_domain(lp);
    float base = vs_fbm(q * 2.0, u_base_oct);
    float rb = vs_fbm(q * 2.0 + vec3(11.3, 5.9, 7.7), u_ridge_oct);
    float ridge = 1.0 - abs(2.0 * rb - 1.0);
    ridge *= ridge;
    float m = mix(base, base * 0.35 + ridge * 0.85, u_filaments);
    float det = vs_fbm(q * 5.0 + vec3(4.7, 9.1, 2.3), u_detail_oct);
    float d = m * shape;
    d -= (1.0 - det) * u_erosion * shape * 0.9;
    return max(d, 0.0) * u_density;
}
void main() {
    vec3 bg = texture(u_input_tex, v_uv).rgb;
    if (u_bypass > 0.5) {
        frag_color = vec4(bg, 1.0);
        return;
    }
    float depth = texture(u_depth_tex, v_uv).r;
    vec4 pv = u_inv_proj * vec4(v_uv * 2.0 - 1.0, 1.0, 1.0);
    vec3 vd = pv.xyz / max(abs(pv.w), 1e-6);
    vec4 pw = u_inv_view * vec4(vd, 0.0);
    vec3 D = normalize(pw.xyz);
    vec3 O = u_camera_pos;
    vec4 lo = u_inv_model * vec4(O, 1.0);
    vec4 ld = u_inv_model * vec4(D, 0.0);
    vec3 ro = lo.xyz;
    vec3 rd = ld.xyz;
    float t0 = -1.0;
    float t1 = -1.0;
    float qa = dot(rd, rd);
    if (qa > 1e-12) {
        float qb = dot(ro, rd);
        float qc = dot(ro, ro) - 1.0;
        float hh = qb * qb - qa * qc;
        if (hh > 0.0) {
            hh = sqrt(hh);
            t0 = (-qb - hh) / qa;
            t1 = (-qb + hh) / qa;
        }
    }
    if (t1 <= 0.0 || t0 >= t1) {
        frag_color = vec4(bg, 1.0);
        return;
    }
    float t_scene = 1e9;
    if (depth < 1.0) {
        vec4 ndc = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
        vec4 vv = u_inv_proj * ndc;
        vec3 vp2 = vv.xyz / max(abs(vv.w), 1e-6);
        vec4 wv = u_inv_view * vec4(vp2, 1.0);
        vec3 wp2 = wv.xyz / max(abs(wv.w), 1e-6);
        t_scene = dot(wp2 - O, D);
    }
    float ts = max(t0, 0.0);
    float te = min(t1, t_scene);
    if (te <= ts) {
        frag_color = vec4(bg, 1.0);
        return;
    }
    vec3 sun = u_sun_dir;
    if (dot(sun, sun) < 1e-8) sun = vec3(0.4, 0.6, 0.3);
    sun = normalize(sun);
    float mu = dot(D, sun);
    float ph = 0.35 + u_aniso * pow(clamp(mu * 0.5 + 0.5, 0.0, 1.0), 6.0) * 2.4;
    float rad = max(u_radius, 1e-3);
    int nsteps = max(u_steps, 1);
    int nlight = max(u_light_steps, 1);
    float dt = (te - ts) / float(nsteps);
    float t = ts + dt * vs_ign(gl_FragCoord.xy);
    vec3 C = vec3(0.0);
    float T = 1.0;
    for (int i = 0; i < 64; i++) {
        if (i >= nsteps) break;
        if (t >= te) break;
        vec3 p = O + D * t;
        vec4 lp4 = u_inv_model * vec4(p, 1.0);
        float d = vs_density(lp4.xyz);
        d *= clamp((t_scene - t) / max(u_depth_fade, 1e-3), 0.0, 1.0);
        if (d > 0.001) {
            float r = length(lp4.xyz);
            float core = 1.0 - clamp(r / max(u_core_size, 1e-3), 0.0, 1.0);
            core *= core;
            vec3 ncol = mix(u_deep, u_mid, clamp(d * 1.5, 0.0, 1.0));
            ncol = mix(ncol, u_core, clamp(core * (0.3 + 0.7 * clamp(d * 2.0, 0.0, 1.0)), 0.0, 1.0));
            float sun_t = 1.0;
            if (u_self_shadow > 0.5) {
                float od = 0.0;
                float sdt = rad * 1.4 / 5.0;
                for (int j = 0; j < 10; j++) {
                    if (j >= nlight) break;
                    vec3 sp = p + sun * (sdt * (float(j) + 0.5));
                    vec4 slp = u_inv_model * vec4(sp, 1.0);
                    od += vs_density(slp.xyz);
                }
                sun_t = exp(-od * sdt * u_absorption * u_shadow_strength * 1.2);
            }
            float powder = 1.0 - exp(-d * 2.5);
            vec3 S = ncol * (u_ambient * vec3(0.45, 0.5, 0.7) + u_sun_color * (sun_t * u_scatter * (0.2 + ph) * (0.35 + 0.65 * powder)));
            S += u_core * (core * d) * u_emission;
            float od = d * dt;
            float tr = exp(-od * u_absorption);
            C += T * S * (1.0 - tr);
            T *= tr;
            if (T < 0.02) break;
        }
        t += dt;
    }
    float ao = (1.0 - T) * u_opacity;
    frag_color = vec4(bg * (1.0 - ao) + C * u_opacity, 1.0);
}
"""


@ComponentRegistry.register
class VolumetricSmoke(GraphicsEffect):
    _allow_multiple = True
    _gizmo_icon_label = "Sm"
    render_type = "screen"
    _intensity_prop = "_density"

    def __init__(self):
        super().__init__()
        self._density: float = 0.55
        self._opacity: float = 1.0
        self._steps: int = 28
        self._light_steps: int = 5
        self._base_octaves: int = 4
        self._ridge_octaves: int = 3
        self._detail_octaves: int = 2
        self._noise_scale: float = 0.35
        self._evolution: float = 0.25
        self._seed: float = 0.0
        self._wind_dir: Vec3 = Vec3(0.15, 1.0, 0.05)
        self._wind_speed: float = 0.3
        self._fullness: float = 0.75
        self._filaments: float = 0.55
        self._erosion: float = 0.45
        self._cavity: float = 0.0
        self._edge_softness: float = 0.5
        self._fade_top: float = 0.0
        self._fade_bottom: float = 0.0
        self._color_deep: tuple[float, float, float] = (0.10, 0.08, 0.30)
        self._color_mid: tuple[float, float, float] = (0.45, 0.15, 0.55)
        self._color_core: tuple[float, float, float] = (0.30, 0.75, 0.85)
        self._core_size: float = 1.0
        self._emission: float = 1.2
        self._ambient: float = 0.25
        self._scatter: float = 1.0
        self._anisotropy: float = 0.55
        self._self_shadow: bool = True
        self._shadow_strength: float = 1.0
        self._absorption: float = 1.0
        self._depth_fade: float = 2.0
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Volumetric Smoke", FieldType.HEADER),
            InspectorField("_density", "Density", FieldType.SLIDER, min_val=0.0, max_val=5.0, step=0.05, decimals=2),
            InspectorField("_opacity", "Opacity", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_steps", "March Steps", FieldType.INT, min_val=8, max_val=64, step=4),
            InspectorField("_light_steps", "Light Steps", FieldType.INT, min_val=2, max_val=10, step=1),
            InspectorField("", "Noise Octaves", FieldType.HEADER),
            InspectorField("_base_octaves", "Base Octaves", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("_ridge_octaves", "Ridge Octaves", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("_detail_octaves", "Detail Octaves", FieldType.INT, min_val=1, max_val=8, step=1),
            InspectorField("_noise_scale", "Noise Scale", FieldType.SLIDER, min_val=0.05, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_evolution", "Evolution Speed", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_seed", "Seed", FieldType.SLIDER, min_val=0.0, max_val=100.0, step=1.0, decimals=0),
            InspectorField("_wind_dir", "Wind Direction", FieldType.VEC3),
            InspectorField("_wind_speed", "Wind Speed", FieldType.SLIDER, min_val=0.0, max_val=5.0, step=0.1, decimals=1),
            InspectorField("", "Shape", FieldType.HEADER),
            InspectorField("_fullness", "Fullness", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_filaments", "Filaments", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_erosion", "Erosion", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_cavity", "Cavity", FieldType.SLIDER, min_val=0.0, max_val=0.9, step=0.05, decimals=2),
            InspectorField("_edge_softness", "Edge Softness", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_fade_top", "Fade Top", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_fade_bottom", "Fade Bottom", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("", "Color", FieldType.HEADER),
            InspectorField("_color_deep", "Deep Color", FieldType.COLOR),
            InspectorField("_color_mid", "Mid Color", FieldType.COLOR),
            InspectorField("_color_core", "Core Color", FieldType.COLOR),
            InspectorField("_core_size", "Core Size", FieldType.SLIDER, min_val=0.05, max_val=1.0, step=0.05, decimals=2),
            InspectorField("_emission", "Emission", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.1, decimals=2),
            InspectorField("_ambient", "Ambient", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("", "Light", FieldType.HEADER),
            InspectorField("_scatter", "Sun Scatter", FieldType.SLIDER, min_val=0.0, max_val=4.0, step=0.1, decimals=2),
            InspectorField("_anisotropy", "Forward Scatter", FieldType.SLIDER, min_val=0.0, max_val=0.95, step=0.05, decimals=2),
            InspectorField("_self_shadow", "Self Shadow", FieldType.BOOL),
            InspectorField("_shadow_strength", "Shadow Strength", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.1, decimals=1),
            InspectorField("_absorption", "Absorption", FieldType.SLIDER, min_val=0.0, max_val=3.0, step=0.1, decimals=2),
            InspectorField("_depth_fade", "Depth Fade", FieldType.SLIDER, min_val=0.0, max_val=10.0, step=0.5, decimals=1),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        w = self._wind_dir
        if isinstance(w, Vec3):
            wv = [float(w.x), float(w.y), float(w.z)]
        else:
            wv = [float(w[0]), float(w[1]), float(w[2])]
        d.update({
            "_density": self._density,
            "_opacity": self._opacity,
            "_steps": self._steps,
            "_light_steps": self._light_steps,
            "_base_octaves": self._base_octaves,
            "_ridge_octaves": self._ridge_octaves,
            "_detail_octaves": self._detail_octaves,
            "_noise_scale": self._noise_scale,
            "_evolution": self._evolution,
            "_seed": self._seed,
            "_wind_dir": wv,
            "_wind_speed": self._wind_speed,
            "_fullness": self._fullness,
            "_filaments": self._filaments,
            "_erosion": self._erosion,
            "_cavity": self._cavity,
            "_edge_softness": self._edge_softness,
            "_fade_top": self._fade_top,
            "_fade_bottom": self._fade_bottom,
            "_color_deep": list(self._color_deep),
            "_color_mid": list(self._color_mid),
            "_color_core": list(self._color_core),
            "_core_size": self._core_size,
            "_emission": self._emission,
            "_ambient": self._ambient,
            "_scatter": self._scatter,
            "_anisotropy": self._anisotropy,
            "_self_shadow": self._self_shadow,
            "_shadow_strength": self._shadow_strength,
            "_absorption": self._absorption,
            "_depth_fade": self._depth_fade,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> VolumetricSmoke:
        inst = super().deserialize(data)
        inst._density = float(data.get("_density", 0.55))
        inst._opacity = float(data.get("_opacity", 1.0))
        inst._steps = int(data.get("_steps", 28))
        inst._light_steps = int(data.get("_light_steps", 5))
        inst._base_octaves = int(data.get("_base_octaves", 4))
        inst._ridge_octaves = int(data.get("_ridge_octaves", 3))
        inst._detail_octaves = int(data.get("_detail_octaves", 2))
        inst._noise_scale = float(data.get("_noise_scale", 0.35))
        inst._evolution = float(data.get("_evolution", 0.25))
        inst._seed = float(data.get("_seed", 0.0))
        inst._wind_dir = Vec3(*data.get("_wind_dir", [0.15, 1.0, 0.05]))
        inst._wind_speed = float(data.get("_wind_speed", 0.3))
        inst._fullness = float(data.get("_fullness", 0.75))
        inst._filaments = float(data.get("_filaments", 0.55))
        inst._erosion = float(data.get("_erosion", 0.45))
        inst._cavity = float(data.get("_cavity", 0.0))
        inst._edge_softness = float(data.get("_edge_softness", 0.5))
        inst._fade_top = float(data.get("_fade_top", 0.0))
        inst._fade_bottom = float(data.get("_fade_bottom", 0.0))
        inst._color_deep = tuple(data.get("_color_deep", [0.10, 0.08, 0.30]))
        inst._color_mid = tuple(data.get("_color_mid", [0.45, 0.15, 0.55]))
        inst._color_core = tuple(data.get("_color_core", [0.30, 0.75, 0.85]))
        inst._core_size = float(data.get("_core_size", 1.0))
        inst._emission = float(data.get("_emission", 1.2))
        inst._ambient = float(data.get("_ambient", 0.25))
        inst._scatter = float(data.get("_scatter", 1.0))
        inst._anisotropy = float(data.get("_anisotropy", 0.55))
        inst._self_shadow = bool(data.get("_self_shadow", True))
        inst._shadow_strength = float(data.get("_shadow_strength", 1.0))
        inst._absorption = float(data.get("_absorption", 1.0))
        inst._depth_fade = float(data.get("_depth_fade", 2.0))
        inst._ctx = None
        inst._prog = None
        inst._vao = None
        inst._vbo = None
        inst._ibo = None
        return inst

    _res_cache: dict[int, dict] = {}

    def _ensure_resources(self, ctx: moderngl.Context):
        ctx_id = id(ctx)
        cached = self._res_cache.get(ctx_id)
        if cached is not None:
            self._ctx = ctx
            self._prog = cached["_prog"]
            self._vao = cached["_vao"]
            self._vbo = cached["_vbo"]
            self._ibo = cached["_ibo"]
            return
        self._ctx = ctx
        self._prog = ctx.program(
            vertex_shader=VOLUMETRIC_SMOKE_VERT,
            fragment_shader=VOLUMETRIC_SMOKE_FRAG
        )
        verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._vao = ctx.vertex_array(
            self._prog,
            [(self._vbo, "2f", "in_position")],
            self._ibo
        )
        self._res_cache[ctx_id] = {
            "_prog": self._prog,
            "_vao": self._vao,
            "_vbo": self._vbo,
            "_ibo": self._ibo,
        }
        if len(self._res_cache) > 4:
            oldest = next(iter(self._res_cache))
            for obj in self._res_cache[oldest].values():
                if obj is not None and hasattr(obj, "release"):
                    try:
                        obj.release()
                    except Exception:
                        pass
            del self._res_cache[oldest]

    def _sun_light(self):
        sun_dir = (0.4, 0.6, 0.3)
        sun_col = (1.0, 0.95, 0.9)
        try:
            ent = self._entity
            scene = ent._scene if ent is not None else None
            if scene is None:
                return sun_dir, sun_col
            for e in scene.get_entities_with_component(Light):
                li = e.get_component(Light)
                t = e.transform
                if li is not None and t is not None and li.enabled and li.light_type == LightType.DIRECTIONAL:
                    f = t.forward
                    sun_dir = (-float(f.x), -float(f.y), -float(f.z))
                    c = li.color or [1.0, 1.0, 1.0]
                    sun_col = (float(c[0]), float(c[1]), float(c[2]))
                    break
        except Exception:
            pass
        return sun_dir, sun_col

    def _wind_tuple(self) -> tuple[float, float, float]:
        w = self._wind_dir
        try:
            if isinstance(w, Vec3):
                return (float(w.x), float(w.y), float(w.z))
            return (float(w[0]), float(w[1]), float(w[2]))
        except Exception:
            return (0.0, 1.0, 0.0)

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        self._ensure_resources(ctx)
        tex = input_tex if input_tex is not None else scene_color_tex
        prog = self._prog
        tr = self.transform
        bypass = 0.0
        inv_model = None
        radius = 1.0
        if tr is None:
            bypass = 1.0
        else:
            try:
                wm = tr.world_matrix
                inv_model = wm.inverted()
                d = wm._d
                sx = float(np.linalg.norm(d[0, :3]))
                sy = float(np.linalg.norm(d[1, :3]))
                sz = float(np.linalg.norm(d[2, :3]))
                radius = max(sx, sy, sz)
                if not (radius > 1e-6):
                    bypass = 1.0
            except Exception:
                bypass = 1.0
                inv_model = None
        if bypass > 0.5:
            try:
                inv_model = view_mat.inverted()
            except Exception:
                pass
        prog["u_input_tex"] = 0
        tex.use(0)
        prog["u_depth_tex"] = 1
        scene_depth_tex.use(1)
        prog["u_inv_view"].write(view_mat.inverted().to_f32().tobytes())
        prog["u_inv_proj"].write(proj_mat.inverted().to_f32().tobytes())
        if inv_model is not None:
            prog["u_inv_model"].write(inv_model.to_f32().tobytes())
        if "u_camera_pos" in prog:
            prog["u_camera_pos"].value = (float(cam_pos.x), float(cam_pos.y), float(cam_pos.z))
        if "u_time" in prog:
            prog["u_time"].value = float(time.perf_counter() % 3600.0)
        if "u_seed" in prog:
            prog["u_seed"].value = float(self._seed)
        if "u_density" in prog:
            prog["u_density"].value = max(float(self._density), 0.0)
        if "u_opacity" in prog:
            prog["u_opacity"].value = min(1.0, max(0.0, float(self._opacity)))
        if "u_steps" in prog:
            prog["u_steps"].value = max(1, min(64, int(self._steps)))
        if "u_light_steps" in prog:
            prog["u_light_steps"].value = max(1, min(10, int(self._light_steps)))
        if "u_base_oct" in prog:
            prog["u_base_oct"].value = max(1, min(8, int(self._base_octaves)))
        if "u_ridge_oct" in prog:
            prog["u_ridge_oct"].value = max(1, min(8, int(self._ridge_octaves)))
        if "u_detail_oct" in prog:
            prog["u_detail_oct"].value = max(1, min(8, int(self._detail_octaves)))
        if "u_noise_scale" in prog:
            prog["u_noise_scale"].value = max(float(self._noise_scale), 0.01)
        if "u_evolution" in prog:
            prog["u_evolution"].value = max(float(self._evolution), 0.0)
        if "u_wind" in prog:
            prog["u_wind"].value = self._wind_tuple()
        if "u_wind_speed" in prog:
            prog["u_wind_speed"].value = max(float(self._wind_speed), 0.0)
        if "u_fullness" in prog:
            prog["u_fullness"].value = min(1.0, max(0.0, float(self._fullness)))
        if "u_filaments" in prog:
            prog["u_filaments"].value = min(1.0, max(0.0, float(self._filaments)))
        if "u_erosion" in prog:
            prog["u_erosion"].value = min(1.0, max(0.0, float(self._erosion)))
        if "u_cavity" in prog:
            prog["u_cavity"].value = min(0.9, max(0.0, float(self._cavity)))
        if "u_edge_softness" in prog:
            prog["u_edge_softness"].value = min(1.0, max(0.0, float(self._edge_softness)))
        if "u_fade_top" in prog:
            prog["u_fade_top"].value = min(1.0, max(0.0, float(self._fade_top)))
        if "u_fade_bottom" in prog:
            prog["u_fade_bottom"].value = min(1.0, max(0.0, float(self._fade_bottom)))
        if "u_deep" in prog:
            prog["u_deep"].value = tuple(float(v) for v in self._color_deep)
        if "u_mid" in prog:
            prog["u_mid"].value = tuple(float(v) for v in self._color_mid)
        if "u_core" in prog:
            prog["u_core"].value = tuple(float(v) for v in self._color_core)
        if "u_core_size" in prog:
            prog["u_core_size"].value = min(1.0, max(0.05, float(self._core_size)))
        if "u_emission" in prog:
            prog["u_emission"].value = max(float(self._emission), 0.0)
        if "u_ambient" in prog:
            prog["u_ambient"].value = max(float(self._ambient), 0.0)
        sun_dir, sun_col = self._sun_light()
        if "u_sun_dir" in prog:
            prog["u_sun_dir"].value = sun_dir
        if "u_sun_color" in prog:
            prog["u_sun_color"].value = sun_col
        if "u_scatter" in prog:
            prog["u_scatter"].value = max(float(self._scatter), 0.0)
        if "u_aniso" in prog:
            prog["u_aniso"].value = min(0.95, max(0.0, float(self._anisotropy)))
        if "u_self_shadow" in prog:
            prog["u_self_shadow"].value = 1.0 if self._self_shadow else 0.0
        if "u_shadow_strength" in prog:
            prog["u_shadow_strength"].value = min(2.0, max(0.0, float(self._shadow_strength)))
        if "u_absorption" in prog:
            prog["u_absorption"].value = max(float(self._absorption), 0.0)
        if "u_radius" in prog:
            prog["u_radius"].value = max(float(radius), 1e-3)
        if "u_depth_fade" in prog:
            prog["u_depth_fade"].value = max(float(self._depth_fade), 0.0)
        if "u_bypass" in prog:
            prog["u_bypass"].value = bypass
        ctx.disable(moderngl.BLEND)
        self._vao.render()

    def _release_gl(self):
        for obj in (self._prog, self._vao, self._vbo, self._ibo):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self._ctx = None
        self._prog = None
        self._vao = None
        self._vbo = None
        self._ibo = None

    @property
    def density(self) -> float:
        return getattr(self, "_density", 0.55)

    @density.setter
    def density(self, v: float):
        self._density = float(v)

    @property
    def opacity(self) -> float:
        return getattr(self, "_opacity", 1.0)

    @opacity.setter
    def opacity(self, v: float):
        self._opacity = float(v)

    @property
    def march_steps(self) -> int:
        return getattr(self, "_steps", 28)

    @march_steps.setter
    def march_steps(self, v: int):
        self._steps = int(v)

    @property
    def emission(self) -> float:
        return getattr(self, "_emission", 1.2)

    @emission.setter
    def emission(self, v: float):
        self._emission = float(v)
