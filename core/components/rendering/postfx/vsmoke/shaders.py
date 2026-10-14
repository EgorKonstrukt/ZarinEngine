# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

VOLUMETRIC_SMOKE_VERT = """
\x23version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""


VOLUMETRIC_SMOKE_FRAG = """
\x23version 330 core
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
