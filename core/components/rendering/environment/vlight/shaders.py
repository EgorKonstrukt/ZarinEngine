# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

VOLUMETRIC_VERT = "\n" + chr(35) + """version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

VOLUMETRIC_FRAG = "\n" + chr(35) + """version 330 core

uniform sampler2D u_depth_tex;
uniform mat4 u_inv_view_proj;
uniform vec3 u_camera_pos;
uniform float u_intensity;
uniform float u_density;
uniform float u_scattering;
uniform int u_step_count;

const int MAX_LIGHTS = 8;
const int MAX_PROJECTORS = 4;

uniform int   u_light_type[MAX_LIGHTS];
uniform vec3  u_light_pos[MAX_LIGHTS];
uniform vec3  u_light_dir[MAX_LIGHTS];
uniform vec3  u_light_col[MAX_LIGHTS];
uniform float u_light_int[MAX_LIGHTS];
uniform float u_light_range[MAX_LIGHTS];
uniform float u_light_spot_outer[MAX_LIGHTS];
uniform float u_light_spot_inner[MAX_LIGHTS];
uniform int   u_light_count;

uniform vec3  u_proj_pos[MAX_PROJECTORS];
uniform vec3  u_proj_dir[MAX_PROJECTORS];
uniform vec3  u_proj_col[MAX_PROJECTORS];
uniform float u_proj_int[MAX_PROJECTORS];
uniform float u_proj_range[MAX_PROJECTORS];
uniform float u_proj_angle[MAX_PROJECTORS];
uniform int   u_proj_count;

in vec2 v_uv;
out vec4 frag_color;

vec3 eval_light(vec3 pos, int i) {
    int tp = u_light_type[i];
    if (tp == 0) {
        return u_light_col[i] * u_light_int[i];
    }
    vec3 L = u_light_pos[i] - pos;
    float dist = length(L);
    if (dist > u_light_range[i]) return vec3(0.0);
    float atten = 1.0 / (1.0 + dist * dist * 0.01);
    if (tp == 1 || tp == 3) {
        return u_light_col[i] * u_light_int[i] * atten;
    }
    if (tp == 2) {
        vec3 dir = normalize(L);
        float half_rad = u_light_spot_outer[i] * 0.5;
        float cos_outer = cos(half_rad * 0.0174532925);
        float cos_ang = dot(dir, normalize(u_light_dir[i]));
        if (cos_ang < cos_outer) return vec3(0.0);
        float cos_inner = cos(u_light_spot_inner[i] * 0.0174532925);
        if (cos_inner > cos_outer) cos_inner = cos_outer;
        float spot = smoothstep(cos_outer, cos_inner, cos_ang);
        return u_light_col[i] * u_light_int[i] * atten * spot;
    }
    return vec3(0.0);
}

vec3 eval_projector(vec3 pos, int i) {
    vec3 L = pos - u_proj_pos[i];
    float dist = length(L);
    if (dist > u_proj_range[i]) return vec3(0.0);
    float half_rad = u_proj_angle[i] * 0.5;
    float cos_outer = cos(half_rad * 0.0174532925);
    vec3 Ln = normalize(-L);
    float cos_ang = dot(Ln, normalize(u_proj_dir[i]));
    if (cos_ang < cos_outer) return vec3(0.0);
    float atten = 1.0 / (1.0 + dist * dist * 0.01);
    float spot = max(0.0, cos_ang - cos_outer) / (1.0 - cos_outer);
    return u_proj_col[i] * u_proj_int[i] * atten * spot;
}

void main() {
    float depth = texture(u_depth_tex, v_uv).r;
    if (depth >= 1.0) {
        discard;
    }
    vec4 clip = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 world = u_inv_view_proj * clip;
    vec3 surface_pos = world.xyz / world.w;
    vec3 view_dir = normalize(surface_pos - u_camera_pos);
    float march_dist = length(surface_pos - u_camera_pos);
    if (march_dist < 0.001) {
        discard;
    }
    float step_size = march_dist / float(max(u_step_count, 1));
    vec3 march_pos = u_camera_pos + view_dir * step_size * 0.5;
    vec3 accum = vec3(0.0);
    float transmittance = 1.0;

    for (int s = 0; s < u_step_count; s++) {
        float step_t = u_density * step_size;
        float step_trans = exp(-step_t);
        vec3 scatter = vec3(0.0);
        for (int li = 0; li < u_light_count; li++) {
            scatter += eval_light(march_pos, li);
        }
        for (int pj = 0; pj < u_proj_count; pj++) {
            scatter += eval_projector(march_pos, pj);
        }
        accum += scatter * u_scattering * (1.0 - step_trans) * transmittance;
        transmittance *= step_trans;
        march_pos += view_dir * step_size;
    }

    frag_color = vec4(accum * u_intensity, 1.0);
}
"""
