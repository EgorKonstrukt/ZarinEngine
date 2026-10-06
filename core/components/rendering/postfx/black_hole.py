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


BLACK_HOLE_VERT = """
#version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

BLACK_HOLE_FRAG = """
#version 330 core
uniform sampler2D u_input_tex;
uniform sampler2D u_depth_tex;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat4 u_inv_view;
uniform mat4 u_inv_proj;
uniform vec3 u_camera_pos;
uniform vec3 u_hole_pos;
uniform vec3 u_disk_normal;
uniform float u_rs;
uniform float u_lensing;
uniform float u_disk_inner;
uniform float u_disk_outer;
uniform vec3 u_inner_color;
uniform vec3 u_outer_color;
uniform float u_disk_brightness;
uniform float u_spin_speed;
uniform float u_doppler;
uniform float u_time;
uniform float u_photon_intensity;
uniform float u_photon_width;
uniform float u_fringe;
uniform float u_noise_amount;
uniform float u_show_disk;
uniform float u_bypass;
in vec2 v_uv;
out vec4 frag_color;
float bh_hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float bh_noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = bh_hash(i);
    float b = bh_hash(i + vec2(1.0, 0.0));
    float c = bh_hash(i + vec2(0.0, 1.0));
    float d = bh_hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float bh_fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    v += a * bh_noise(p);
    v += a * 0.5 * bh_noise(p * 2.03 + vec2(17.3, 9.1));
    v += a * 0.25 * bh_noise(p * 4.11 + vec2(5.7, 3.2));
    return v / 0.875;
}
vec3 bh_ray_dir(vec2 uv) {
    vec4 r = u_inv_proj * vec4(uv * 2.0 - 1.0, 1.0, 1.0);
    vec3 vd = r.xyz / max(abs(r.w), 0.000001);
    vec4 wd = u_inv_view * vec4(vd, 0.0);
    return normalize(wd.xyz);
}
vec2 bh_project(vec3 dir) {
    vec3 wp = u_camera_pos + dir * 1000.0;
    vec4 vp = u_view * vec4(wp, 1.0);
    vec4 cp = u_proj * vp;
    if (cp.w <= 0.0001) return vec2(-10.0, -10.0);
    return cp.xy / cp.w * 0.5 + 0.5;
}
vec3 bh_bend(vec3 d, vec3 perp, float alpha) {
    float ca = cos(alpha);
    float sa = sin(alpha);
    return normalize(d * ca + perp * sa);
}
void main() {
    vec3 original = texture(u_input_tex, v_uv).rgb;
    if (u_bypass > 0.5) {
        frag_color = vec4(original, 1.0);
        return;
    }
    float rs = max(u_rs, 0.0001);
    float rs_eff = max(rs * max(u_lensing, 0.0), 0.000001);
    vec3 N = u_disk_normal;
    if (dot(N, N) < 0.000001) N = vec3(0.0, 1.0, 0.0);
    N = normalize(N);
    vec3 D = bh_ray_dir(v_uv);
    vec3 O = u_camera_pos;
    vec3 CO = u_hole_pos - O;
    float t_ca = dot(CO, D);
    float b = 1000000.0;
    vec3 perp = vec3(0.0);
    float has_bend = 0.0;
    if (t_ca > 0.0) {
        vec3 closest = O + D * t_ca - u_hole_pos;
        b = length(closest);
        vec3 to_hole = -closest / max(b, 0.00001);
        vec3 pp = to_hole - D * dot(to_hole, D);
        float pl = length(pp);
        if (pl > 0.00001 && b > 0.00001) {
            perp = pp / pl;
            has_bend = 1.0;
        }
    } else {
        b = length(CO);
    }
    float b_crit = 2.598 * rs_eff;
    float alpha = 2.0 * rs_eff / max(b, b_crit);
    vec3 Db = D;
    if (has_bend > 0.5) Db = bh_bend(D, perp, alpha);
    float alpha_r = alpha * (1.0 + u_fringe);
    float alpha_b = max(alpha * (1.0 - u_fringe), 0.0);
    vec3 Dr = D;
    vec3 Dbl = D;
    if (has_bend > 0.5) {
        Dr = bh_bend(D, perp, alpha_r);
        Dbl = bh_bend(D, perp, alpha_b);
    }
    float depth = texture(u_depth_tex, v_uv).r;
    float t_surf = 1000000.0;
    if (depth < 1.0) {
        vec4 ndc = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
        vec4 vv = u_inv_proj * ndc;
        vec3 vp2 = vv.xyz / max(abs(vv.w), 0.000001);
        vec4 wv = u_inv_view * vec4(vp2, 1.0);
        vec3 wp2 = wv.xyz / max(abs(wv.w), 0.000001);
        t_surf = dot(wp2 - O, D);
    }
    if (depth < 1.0 && t_ca > 0.0 && t_surf > 0.0 && t_surf < t_ca - max(rs * 0.5, 0.05)) {
        frag_color = vec4(original, 1.0);
        return;
    }
    vec2 uv_c = bh_project(Db);
    vec2 uv_r = bh_project(Dr);
    vec2 uv_bl = bh_project(Dbl);
    vec3 bg = vec3(texture(u_input_tex, clamp(uv_r, 0.0, 1.0)).r, texture(u_input_tex, clamp(uv_c, 0.0, 1.0)).g, texture(u_input_tex, clamp(uv_bl, 0.0, 1.0)).b);
    float aa = fwidth(b) * 1.2 + 0.002 * rs + 0.0005;
    float shadow = 1.0 - smoothstep(b_crit - aa, b_crit + aa, b);
    if (t_ca <= 0.0) shadow = 0.0;
    float pw = max(u_photon_width * rs, 0.0001);
    float dd = (b - b_crit) / pw;
    float ring = exp(-dd * dd) * u_photon_intensity;
    if (t_ca <= 0.0) ring = 0.0;
    vec3 e1 = cross(vec3(0.0, 1.0, 0.0), N);
    if (dot(e1, e1) < 0.001) e1 = cross(vec3(1.0, 0.0, 0.0), N);
    e1 = normalize(e1);
    vec3 e2 = normalize(cross(N, e1));
    float inner = max(u_disk_inner, rs * 1.05);
    float outer = max(u_disk_outer, inner + rs * 0.5 + 0.001);
    vec3 disk_col = vec3(0.0);
    float disk_alpha = 0.0;
    if (u_show_disk > 0.5 && t_ca > 0.0) {
        float denom1 = dot(D, N);
        float t1 = -1.0;
        vec3 hit1 = vec3(0.0);
        float r1 = -1.0;
        if (abs(denom1) > 0.00001) {
            float tt = dot(u_hole_pos - O, N) / denom1;
            if (tt > 0.0 && tt < t_ca) {
                vec3 hp = O + D * tt;
                float rr = length(hp - u_hole_pos);
                if (rr >= inner * 0.85 && rr <= outer) {
                    t1 = tt;
                    hit1 = hp;
                    r1 = rr;
                }
            }
        }
        vec3 Pl = O + D * t_ca;
        float denom2 = dot(Db, N);
        float t2 = -1.0;
        vec3 hit2 = vec3(0.0);
        float r2 = -1.0;
        if (abs(denom2) > 0.00001) {
            float tt = dot(u_hole_pos - Pl, N) / denom2;
            if (tt > 0.0) {
                vec3 hp = Pl + Db * tt;
                float rr = length(hp - u_hole_pos);
                if (rr >= inner * 0.85 && rr <= outer) {
                    t2 = t_ca + tt;
                    hit2 = hp;
                    r2 = rr;
                }
            }
        }
        float use_fg = 0.0;
        vec3 hit = vec3(0.0);
        float rh = -1.0;
        float th = -1.0;
        if (t1 > 0.0 && t2 > 0.0) {
            if (t1 <= t2) {
                use_fg = 1.0;
                hit = hit1;
                rh = r1;
                th = t1;
            } else {
                use_fg = 0.0;
                hit = hit2;
                rh = r2;
                th = t2;
            }
        } else if (t1 > 0.0) {
            use_fg = 1.0;
            hit = hit1;
            rh = r1;
            th = t1;
        } else if (t2 > 0.0) {
            use_fg = 0.0;
            hit = hit2;
            rh = r2;
            th = t2;
        }
        if (rh > 0.0) {
            vec3 rel = hit - u_hole_pos;
            float rr = max(rh, 0.0001);
            float lx = dot(rel, e1);
            float lz = dot(rel, e2);
            float omega = u_spin_speed * 2.0 * pow(inner / rr, 1.5);
            float ang = u_time * omega;
            float ca2 = cos(ang);
            float sa2 = sin(ang);
            vec2 rp = vec2(lx * ca2 - lz * sa2, lx * sa2 + lz * ca2);
            vec2 np2 = rp / max(rs, 0.0001);
            float n1 = bh_fbm(np2 * 1.6);
            float n2 = bh_fbm(np2 * 3.4 + n1 * 2.0);
            float turb = mix(1.0, clamp(n1 * 0.65 + n2 * 0.55, 0.0, 1.6), clamp(u_noise_amount, 0.0, 1.0));
            float q = clamp(inner / rr, 0.0, 1.0);
            float temp = pow(q, 0.8);
            vec3 dcol = mix(u_outer_color, u_inner_color, pow(temp, 0.7));
            dcol += vec3(1.0, 0.97, 0.92) * pow(temp, 3.0) * 2.0;
            vec3 radial = rel / rr;
            vec3 tang = cross(N, radial);
            if (dot(tang, tang) < 0.000001) tang = e1;
            tang = normalize(tang);
            vec3 to_cam = (O - hit) / max(length(O - hit), 0.0001);
            float beta = clamp(sqrt(rs / max(2.0 * rr, 0.0001)) * u_doppler, 0.0, 0.65);
            float appr = dot(tang, to_cam);
            float dop = 1.0 / max(1.0 - beta * appr, 0.25);
            float beam = pow(clamp(dop, 0.3, 3.2), 3.0);
            dcol *= beam;
            dcol = mix(dcol, dcol * vec3(0.75, 0.85, 1.25), clamp(appr * beta * 1.5, 0.0, 0.6));
            dcol = mix(dcol, dcol * vec3(1.25, 0.8, 0.65), clamp(-appr * beta * 1.5, 0.0, 0.6));
            float grav = sqrt(clamp(1.0 - rs / rr, 0.05, 1.0));
            dcol *= (0.35 + 0.65 * grav);
            float soft_in = rs * 0.18 + 0.001;
            float soft_out = rs * 0.6 + 0.002;
            float fin = smoothstep(inner * 0.85, inner * 0.85 + soft_in, rr);
            float fout = 1.0 - smoothstep(outer - soft_out, outer, rr);
            float plunge = smoothstep(rs * 0.9, inner, rr);
            float dalpha = clamp(fin * fout * (0.45 + 0.55 * turb), 0.0, 1.0);
            vec3 hdr = dcol * u_disk_brightness * (0.55 + 0.9 * turb) * plunge;
            if (depth < 1.0 && t_surf > 0.0 && t_surf < th - 0.02) {
                dalpha = 0.0;
            }
            float occ = 1.0;
            if (use_fg < 0.5) occ = 1.0 - shadow;
            disk_col = hdr;
            disk_alpha = dalpha * occ;
        }
    }
    float glow = exp(-max(b - b_crit, 0.0) / max(rs * 3.0, 0.0001)) * 0.12 * clamp(u_disk_brightness * 0.5, 0.0, 1.0);
    if (t_ca <= 0.0) glow = 0.0;
    vec3 ring_col = vec3(1.0, 0.93, 0.82) * ring;
    vec3 col = bg * (1.0 - shadow);
    col = mix(col, disk_col, clamp(disk_alpha, 0.0, 1.0));
    col += ring_col * (1.0 - shadow * 0.35);
    col += vec3(1.0, 0.8, 0.55) * glow * (1.0 - shadow);
    frag_color = vec4(col, 1.0);
}
"""


@ComponentRegistry.register
class BlackHole(GraphicsEffect):
    _allow_multiple = False
    _gizmo_icon_label = "BH"
    render_type = "screen"

    def __init__(self):
        super().__init__()
        self._schwarzschild_radius: float = 2.0
        self._lensing_strength: float = 1.0
        self._show_disk: bool = True
        self._disk_inner: float = 3.0
        self._disk_outer: float = 8.0
        self._disk_brightness: float = 2.2
        self._inner_color: tuple[float, float, float] = (0.7, 0.82, 1.0)
        self._outer_color: tuple[float, float, float] = (1.0, 0.45, 0.12)
        self._rotation_speed: float = 0.6
        self._doppler_strength: float = 1.0
        self._turbulence: float = 0.7
        self._photon_intensity: float = 3.0
        self._photon_width: float = 0.08
        self._fringe: float = 0.02
        self._ctx: Optional[moderngl.Context] = None
        self._prog: Optional[moderngl.Program] = None
        self._vao: Optional[moderngl.VertexArray] = None
        self._vbo: Optional[moderngl.Buffer] = None
        self._ibo: Optional[moderngl.Buffer] = None

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("", "Black Hole", FieldType.HEADER),
            InspectorField("_schwarzschild_radius", "Schwarzschild Radius", FieldType.SLIDER, min_val=0.2, max_val=12.0, step=0.1, decimals=2),
            InspectorField("_lensing_strength", "Lensing Strength", FieldType.SLIDER, min_val=0.0, max_val=2.5, step=0.05, decimals=2),
            InspectorField("", "Accretion Disk", FieldType.HEADER),
            InspectorField("_show_disk", "Show Disk", FieldType.BOOL),
            InspectorField("_disk_inner", "Disk Inner (Rs)", FieldType.SLIDER, min_val=1.6, max_val=6.0, step=0.1, decimals=2),
            InspectorField("_disk_outer", "Disk Outer (Rs)", FieldType.SLIDER, min_val=4.0, max_val=16.0, step=0.1, decimals=2),
            InspectorField("_disk_brightness", "Disk Brightness", FieldType.SLIDER, min_val=0.0, max_val=6.0, step=0.1, decimals=2),
            InspectorField("_inner_color", "Inner Color", FieldType.COLOR),
            InspectorField("_outer_color", "Outer Color", FieldType.COLOR),
            InspectorField("_rotation_speed", "Rotation Speed", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_doppler_strength", "Doppler Beaming", FieldType.SLIDER, min_val=0.0, max_val=2.0, step=0.05, decimals=2),
            InspectorField("_turbulence", "Turbulence", FieldType.SLIDER, min_val=0.0, max_val=1.0, step=0.05, decimals=2),
            InspectorField("", "Photon Ring", FieldType.HEADER),
            InspectorField("_photon_intensity", "Photon Intensity", FieldType.SLIDER, min_val=0.0, max_val=8.0, step=0.1, decimals=2),
            InspectorField("_photon_width", "Photon Width", FieldType.SLIDER, min_val=0.01, max_val=0.5, step=0.01, decimals=3),
            InspectorField("_fringe", "Chromatic Fringe", FieldType.SLIDER, min_val=0.0, max_val=0.1, step=0.005, decimals=3),
        ]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "_schwarzschild_radius": self._schwarzschild_radius,
            "_lensing_strength": self._lensing_strength,
            "_show_disk": self._show_disk,
            "_disk_inner": self._disk_inner,
            "_disk_outer": self._disk_outer,
            "_disk_brightness": self._disk_brightness,
            "_inner_color": list(self._inner_color),
            "_outer_color": list(self._outer_color),
            "_rotation_speed": self._rotation_speed,
            "_doppler_strength": self._doppler_strength,
            "_turbulence": self._turbulence,
            "_photon_intensity": self._photon_intensity,
            "_photon_width": self._photon_width,
            "_fringe": self._fringe,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> BlackHole:
        inst = super().deserialize(data)
        inst._schwarzschild_radius = float(data.get("_schwarzschild_radius", 2.0))
        inst._lensing_strength = float(data.get("_lensing_strength", 1.0))
        inst._show_disk = bool(data.get("_show_disk", True))
        inst._disk_inner = float(data.get("_disk_inner", 3.0))
        inst._disk_outer = float(data.get("_disk_outer", 8.0))
        inst._disk_brightness = float(data.get("_disk_brightness", 2.2))
        inst._inner_color = tuple(data.get("_inner_color", [0.7, 0.82, 1.0]))
        inst._outer_color = tuple(data.get("_outer_color", [1.0, 0.45, 0.12]))
        inst._rotation_speed = float(data.get("_rotation_speed", 0.6))
        inst._doppler_strength = float(data.get("_doppler_strength", 1.0))
        inst._turbulence = float(data.get("_turbulence", 0.7))
        inst._photon_intensity = float(data.get("_photon_intensity", 3.0))
        inst._photon_width = float(data.get("_photon_width", 0.08))
        inst._fringe = float(data.get("_fringe", 0.02))
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
            vertex_shader=BLACK_HOLE_VERT,
            fragment_shader=BLACK_HOLE_FRAG
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
        hole = (0.0, 0.0, 0.0)
        normal = (0.0, 1.0, 0.0)
        if tr is None:
            bypass = 1.0
        else:
            try:
                p = tr.position
                hole = (float(p.x), float(p.y), float(p.z))
            except Exception:
                bypass = 1.0
            try:
                u = tr.up
                normal = (float(u.x), float(u.y), float(u.z))
            except Exception:
                normal = (0.0, 1.0, 0.0)
        rs = max(float(self._schwarzschild_radius), 0.05)
        inner_w = max(float(self._disk_inner) * rs, rs * 1.05)
        outer_w = max(float(self._disk_outer) * rs, inner_w + 0.01)
        prog["u_input_tex"] = 0
        tex.use(0)
        prog["u_depth_tex"] = 1
        scene_depth_tex.use(1)
        prog["u_view"].write(view_mat.to_f32().tobytes())
        prog["u_proj"].write(proj_mat.to_f32().tobytes())
        prog["u_inv_view"].write(view_mat.inverted().to_f32().tobytes())
        prog["u_inv_proj"].write(proj_mat.inverted().to_f32().tobytes())
        if "u_camera_pos" in prog:
            prog["u_camera_pos"].value = (float(cam_pos.x), float(cam_pos.y), float(cam_pos.z))
        if "u_hole_pos" in prog:
            prog["u_hole_pos"].value = hole
        if "u_disk_normal" in prog:
            prog["u_disk_normal"].value = normal
        if "u_rs" in prog:
            prog["u_rs"].value = rs
        if "u_lensing" in prog:
            prog["u_lensing"].value = max(float(self._lensing_strength), 0.0)
        if "u_disk_inner" in prog:
            prog["u_disk_inner"].value = inner_w
        if "u_disk_outer" in prog:
            prog["u_disk_outer"].value = outer_w
        if "u_inner_color" in prog:
            prog["u_inner_color"].value = tuple(float(v) for v in self._inner_color)
        if "u_outer_color" in prog:
            prog["u_outer_color"].value = tuple(float(v) for v in self._outer_color)
        if "u_disk_brightness" in prog:
            prog["u_disk_brightness"].value = float(self._disk_brightness)
        if "u_spin_speed" in prog:
            prog["u_spin_speed"].value = float(self._rotation_speed)
        if "u_doppler" in prog:
            prog["u_doppler"].value = float(self._doppler_strength)
        if "u_time" in prog:
            prog["u_time"].value = float(time.perf_counter() % 3600.0)
        if "u_photon_intensity" in prog:
            prog["u_photon_intensity"].value = float(self._photon_intensity)
        if "u_photon_width" in prog:
            prog["u_photon_width"].value = float(self._photon_width)
        if "u_fringe" in prog:
            prog["u_fringe"].value = float(self._fringe)
        if "u_noise_amount" in prog:
            prog["u_noise_amount"].value = float(self._turbulence)
        if "u_show_disk" in prog:
            prog["u_show_disk"].value = 1.0 if self._show_disk else 0.0
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
    def schwarzschild_radius(self) -> float:
        return getattr(self, "_schwarzschild_radius", 2.0)

    @schwarzschild_radius.setter
    def schwarzschild_radius(self, v: float):
        self._schwarzschild_radius = float(v)

    @property
    def lensing_strength(self) -> float:
        return getattr(self, "_lensing_strength", 1.0)

    @lensing_strength.setter
    def lensing_strength(self, v: float):
        self._lensing_strength = float(v)

    @property
    def show_disk(self) -> bool:
        return getattr(self, "_show_disk", True)

    @show_disk.setter
    def show_disk(self, v: bool):
        self._show_disk = bool(v)

    @property
    def disk_brightness(self) -> float:
        return getattr(self, "_disk_brightness", 2.2)

    @disk_brightness.setter
    def disk_brightness(self, v: float):
        self._disk_brightness = float(v)

    @property
    def rotation_speed(self) -> float:
        return getattr(self, "_rotation_speed", 0.6)

    @rotation_speed.setter
    def rotation_speed(self, v: float):
        self._rotation_speed = float(v)

    @property
    def photon_intensity(self) -> float:
        return getattr(self, "_photon_intensity", 3.0)

    @photon_intensity.setter
    def photon_intensity(self, v: float):
        self._photon_intensity = float(v)
