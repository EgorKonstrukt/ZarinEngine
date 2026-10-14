# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

VR_VERT = """
#version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

VR_FRAG = """
#version 330 core

uniform sampler2D u_depth_tex;
uniform sampler3D u_grid;
uniform mat4 u_inv_view_proj;
uniform vec3 u_cam_pos;
uniform vec3 u_grid_min;
uniform vec3 u_grid_dims;
uniform float u_cell_size;
uniform vec3 u_vox_color;
uniform float u_vox_emission;
uniform float u_vox_rim;
uniform float u_amount;
uniform float u_opacity;
uniform vec3 u_light_dir;
uniform int u_max_steps;

in vec2 v_uv;
out vec4 frag_color;

bool solidAt(ivec3 c) {
    if (any(lessThan(c, ivec3(0))) || any(greaterThanEqual(c, ivec3(u_grid_dims))))
        return false;
    return texelFetch(u_grid, c, 0).r > 0.5;
}

vec3 cellNormal(ivec3 c) {
    vec3 n = vec3(0.0);
    if (!solidAt(c + ivec3(1, 0, 0))) n += vec3(1.0, 0.0, 0.0);
    if (!solidAt(c + ivec3(-1, 0, 0))) n += vec3(-1.0, 0.0, 0.0);
    if (!solidAt(c + ivec3(0, 1, 0))) n += vec3(0.0, 1.0, 0.0);
    if (!solidAt(c + ivec3(0, -1, 0))) n += vec3(0.0, -1.0, 0.0);
    if (!solidAt(c + ivec3(0, 0, 1))) n += vec3(0.0, 0.0, 1.0);
    if (!solidAt(c + ivec3(0, 0, -1))) n += vec3(0.0, 0.0, -1.0);
    return length(n) > 0.0001 ? normalize(n) : vec3(0.0, 1.0, 0.0);
}

void main() {
    ivec3 dims = ivec3(u_grid_dims);
    float cell = u_cell_size;
    vec3 gmin = u_grid_min;
    vec3 gmax = gmin + u_grid_dims * cell;

    float depth = texture(u_depth_tex, v_uv).r;
    vec2 ndc = v_uv * 2.0 - 1.0;

    vec4 nearH = u_inv_view_proj * vec4(ndc, -1.0, 1.0);
    vec4 farH  = u_inv_view_proj * vec4(ndc,  1.0, 1.0);
    vec3 nearP = nearH.xyz / nearH.w;
    vec3 farP  = farH.xyz / farH.w;

    vec3 ro = u_cam_pos;
    vec3 rd = normalize(farP - nearP);

    vec3 invD = 1.0 / rd;
    vec3 t0 = (gmin - ro) * invD;
    vec3 t1 = (gmax - ro) * invD;
    vec3 tmin = min(t0, t1);
    vec3 tmax = max(t0, t1);
    float tenter = max(max(tmin.x, tmin.y), tmin.z);
    float texit  = min(min(tmax.x, tmax.y), tmax.z);
    if (texit < 0.0 || tenter > texit) {
        frag_color = vec4(0.0);
        return;
    }

    float maxd;
    if (depth < 1.0) {
        vec4 sH = u_inv_view_proj * vec4(ndc, depth * 2.0 - 1.0, 1.0);
        vec3 sp = sH.xyz / sH.w;
        maxd = length(sp - ro);
    } else {
        maxd = 1e6;
    }

    float t = max(tenter, 0.0);
    float tstop = min(texit, maxd);
    if (tstop < t) {
        frag_color = vec4(0.0);
        return;
    }

    float stepSize = max(cell * 0.5, 1e-4);
    int steps = int(ceil((tstop - t) / stepSize));
    steps = min(steps, u_max_steps);

    vec3 col = vec3(0.0);
    float alpha = 0.0;
    for (int i = 0; i < steps; i++) {
        vec3 p = ro + rd * (t + float(i) * stepSize);
        vec3 rel = (p - gmin) / cell;
        ivec3 c = ivec3(floor(rel));
        if (all(greaterThanEqual(c, ivec3(0))) && all(lessThan(c, dims))) {
            if (texelFetch(u_grid, c, 0).r > 0.5) {
                vec3 n = cellNormal(c);
                vec3 L = normalize(u_light_dir);
                float diff = max(dot(n, L), 0.0);
                vec3 V = normalize(ro - p);
                float rim = pow(1.0 - max(dot(n, V), 0.0), max(u_vox_rim, 0.0001));
                col = u_vox_color * (0.25 + 0.75 * diff)
                    + u_vox_color * u_vox_emission
                    + vec3(rim) * u_vox_color;
                alpha = clamp(u_opacity * u_amount, 0.0, 1.0);
                break;
            }
        }
    }
    frag_color = vec4(col, alpha);
}
"""
