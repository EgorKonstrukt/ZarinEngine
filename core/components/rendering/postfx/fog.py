# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np
import moderngl
from typing import Optional
from core.ecs.ecs import ComponentRegistry
from core.components.rendering.postfx.graphics_effect import GraphicsEffect
from core.components.inspector_meta import FieldType, InspectorField
from core.components.lighting.light import Light, LightType


FOG_VERT = """
#version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FOG_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
uniform sampler2D u_depth_tex;
uniform mat4 u_inv_proj;
uniform mat4 u_inv_view;
uniform vec3 u_camera_pos;
uniform vec3 u_fog_color;
uniform float u_density;
uniform float u_height_density;
uniform float u_height;
uniform float u_start;
uniform vec3 u_sun_dir;
uniform vec3 u_sun_color;
uniform float u_sun_intensity;
uniform float u_far;
uniform float u_sky_fade;
uniform float u_sky_horizon;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    vec3 scene = texture(u_input_tex, v_uv).rgb;
    float depth = texture(u_depth_tex, v_uv).r;
    if (depth >= 1.0) {
        vec4 rd = u_inv_proj * vec4(v_uv * 2.0 - 1.0, 1.0, 1.0);
        vec3 vd = rd.xyz / max(abs(rd.w), 1e-6);
        vec4 wd = u_inv_view * vec4(vd, 0.0);
        vec3 wdir = normalize(wd.xyz);
        float h = pow(1.0 - clamp(abs(wdir.y), 0.0, 1.0), 4.0) * u_sky_horizon;
        vec3 fog_col = u_fog_color + u_sun_color * (pow(max(dot(wdir, u_sun_dir), 0.0), 8.0) * u_sun_intensity);
        frag_color = vec4(mix(scene, fog_col, clamp(h, 0.0, 1.0)), 1.0);
        return;
    }
    vec4 ndc = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 v = u_inv_proj * ndc;
    vec3 view = v.xyz / max(v.w, 1e-6);
    float dist_full = length(view);
    float dist = max(dist_full - u_start, 0.0);
    vec4 w = u_inv_view * vec4(view, 1.0);
    vec3 world = w.xyz / max(w.w, 1e-6);
    float dens = u_density;
    if (u_height_density > 0.0001) {
        dens *= exp(-max(world.y - u_height, 0.0) * u_height_density);
    }
    float f = 1.0 - exp(-dist * dens);
    if (u_sky_fade > 0.5) {
        f *= 1.0 - smoothstep(u_far * 0.6, u_far * 0.99, dist_full);
    }
    vec3 vdir = (world - u_camera_pos) / max(dist_full, 1e-4);
    float sun = pow(max(dot(vdir, u_sun_dir), 0.0), 8.0) * u_sun_intensity;
    vec3 fog_col = u_fog_color + u_sun_color * sun;
    frag_color = vec4(mix(scene, fog_col, clamp(f, 0.0, 1.0)), 1.0);
}
"""


@ComponentRegistry.register
class Fog(GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "F"
    render_type = "screen"
    _intensity_prop = "density"

    def __init__(self):
        super().__init__()
        self._fog_color: tuple[float, float, float] = (0.65, 0.72, 0.82)
        self._density: float = 0.004
        self._start_distance: float = 0.0
        self._height_density: float = 0.0
        self._height: float = 0.0
        self._sun_color: tuple[float, float, float] = (1.0, 0.9, 0.75)
        self._sun_intensity: float = 0.25
        self._sun_light_entity_id: str = ""
        self._sky_fade: bool = True
        self._sky_horizon: float = 0.5
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Distance Fog", FieldType.HEADER),
            InspectorField("_fog_color", "Color", FieldType.COLOR),
            InspectorField("_density", "Density", FieldType.SLIDER, min_val=0.0, max_val=0.2, step=0.001, decimals=4),
            InspectorField("_start_distance", "Start Distance", FieldType.FLOAT, min_val=0.0, max_val=500.0, step=0.5, decimals=1),
            InspectorField("", "Height Fog", FieldType.HEADER),
            InspectorField("_height_density", "Height Density", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.01, decimals=3),
            InspectorField("_height", "Base Height", FieldType.FLOAT, min_val=-100.0, max_val=500.0, step=0.5, decimals=1),
            InspectorField("", "Sun Scattering", FieldType.HEADER),
            InspectorField("_sun_color", "Sun Tint", FieldType.COLOR),
            InspectorField("_sun_intensity", "Sun Intensity", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_sun_light_entity_id", "Sun Light", FieldType.GAMEOBJECT),
            InspectorField("", "Far Fade", FieldType.HEADER),
            InspectorField("_sky_fade", "Fade To Sky", FieldType.BOOL),
            InspectorField("", "Sky Horizon", FieldType.HEADER),
            InspectorField("_sky_horizon", "Horizon Haze", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_fog_color": list(self._fog_color),
            "_density": self._density,
            "_start_distance": self._start_distance,
            "_height_density": self._height_density,
            "_height": self._height,
            "_sun_color": list(self._sun_color),
            "_sun_intensity": self._sun_intensity,
            "_sun_light_entity_id": self._sun_light_entity_id,
            "_sky_fade": self._sky_fade,
            "_sky_horizon": self._sky_horizon,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> Fog:
        inst = super().deserialize(data)
        inst._fog_color = tuple(data.get("_fog_color", [0.65, 0.72, 0.82]))
        inst._density = float(data.get("_density", 0.004))
        inst._start_distance = float(data.get("_start_distance", 0.0))
        inst._height_density = float(data.get("_height_density", 0.0))
        inst._height = float(data.get("_height", 0.0))
        inst._sun_color = tuple(data.get("_sun_color", [1.0, 0.9, 0.75]))
        inst._sun_intensity = float(data.get("_sun_intensity", 0.25))
        inst._sun_light_entity_id = data.get("_sun_light_entity_id", "")
        inst._sky_fade = bool(data.get("_sky_fade", True))
        inst._sky_horizon = float(data.get("_sky_horizon", 0.5))
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
            self._prog = cached['_prog']
            self._vao = cached['_vao']
            self._vbo = cached['_vbo']
            self._ibo = cached['_ibo']
            return
        self._ctx = ctx
        self._prog = ctx.program(
            vertex_shader=FOG_VERT,
            fragment_shader=FOG_FRAG
        )
        verts = np.array([-1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.int32)
        self._vbo = ctx.buffer(verts.tobytes())
        self._ibo = ctx.buffer(indices.tobytes())
        self._vao = ctx.vertex_array(
            self._prog,
            [(self._vbo, '2f', 'in_position')],
            self._ibo
        )
        self._res_cache[ctx_id] = {
            '_prog': self._prog,
            '_vao': self._vao,
            '_vbo': self._vbo,
            '_ibo': self._ibo,
        }
        if len(self._res_cache) > 4:
            oldest = next(iter(self._res_cache))
            for obj in self._res_cache[oldest].values():
                if obj is not None and hasattr(obj, 'release'):
                    try:
                        obj.release()
                    except Exception:
                        pass
            del self._res_cache[oldest]

    def _sun_direction(self):
        sun_dir = (0.0, -0.3, -1.0)
        if float(self._sun_intensity) <= 0.0:
            return sun_dir
        try:
            ent = self._entity
            scene = ent._scene if ent is not None else None
            if scene is None:
                return sun_dir
            tgt = None
            if self._sun_light_entity_id:
                tgt = scene.get_entity(self._sun_light_entity_id)
            if tgt is not None:
                l = tgt.get_component(Light)
                t = tgt.transform
                if l is not None and t is not None and l.enabled and l.light_type == LightType.DIRECTIONAL:
                    f = t.forward
                    return (-f.x, -f.y, -f.z)
            for e in scene.get_entities_with_component(Light):
                l = e.get_component(Light)
                t = e.transform
                if l is not None and t is not None and l.enabled and l.light_type == LightType.DIRECTIONAL:
                    f = t.forward
                    return (-f.x, -f.y, -f.z)
        except Exception:
            pass
        return sun_dir

    def render(self, ctx, scene_color_tex, scene_depth_tex,
               view_mat, proj_mat, cam_pos, viewport_w, viewport_h,
               input_tex=None, output_fbo=None, **kwargs):
        if not self.enabled or not self.entity or not self.entity.active:
            return
        self._ensure_resources(ctx)
        tex = input_tex if input_tex is not None else scene_color_tex
        prog = self._prog
        names = getattr(self, "_prog_names", None)
        if names is None or getattr(self, "_prog_id", None) is not id(prog):
            names = frozenset(prog)
            self._prog_names = names
            self._prog_id = id(prog)
        prog["u_input_tex"] = 0
        tex.use(0)
        prog["u_depth_tex"] = 1
        scene_depth_tex.use(1)
        try:
            prog["u_inv_proj"].write(proj_mat.inverted().to_f32().tobytes())
        except Exception:
            pass
        try:
            prog["u_inv_view"].write(view_mat.inverted().to_f32().tobytes())
        except Exception:
            pass
        try:
            prog["u_camera_pos"].write(np.array([cam_pos.x, cam_pos.y, cam_pos.z], dtype=np.float32).tobytes())
        except Exception:
            pass
        if "u_fog_color" in names:
            prog["u_fog_color"].value = tuple(self._fog_color)
        if "u_density" in names:
            prog["u_density"].value = float(self._density)
        if "u_height_density" in names:
            prog["u_height_density"].value = float(self._height_density)
        if "u_height" in names:
            prog["u_height"].value = float(self._height)
        if "u_start" in names:
            prog["u_start"].value = float(self._start_distance)
        if "u_sun_color" in names:
            prog["u_sun_color"].value = tuple(self._sun_color)
        if "u_sun_intensity" in names:
            prog["u_sun_intensity"].value = float(self._sun_intensity)
        if "u_sun_dir" in names:
            prog["u_sun_dir"].value = self._sun_direction()
        try:
            _d = proj_mat._d
            if abs(float(_d[2, 3]) + 1.0) < 1e-6:
                _far = float(_d[3, 2]) / (1.0 + float(_d[2, 2]))
            else:
                _far = 1e9
            if not (_far > 0.0):
                _far = 1e9
        except Exception:
            _far = 1e9
        if "u_far" in names:
            prog["u_far"].value = float(_far)
        if "u_sky_fade" in names:
            prog["u_sky_fade"].value = 1.0 if self._sky_fade else 0.0
        if "u_sky_horizon" in names:
            prog["u_sky_horizon"].value = float(self._sky_horizon)
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
