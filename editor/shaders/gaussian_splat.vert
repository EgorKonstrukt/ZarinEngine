// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 430 core

layout(std430, binding = 0) buffer SplatBuffer {
    float splat[];
};

layout(std430, binding = 1) buffer SortedIndexBuffer {
    uint sorted_idx[];
};

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform vec2 u_viewport;
uniform vec3 u_camera_pos;
uniform int u_sh_degree;
uniform float u_opacity_threshold;

out vec3 v_color;
out vec2 v_local;
out float v_alpha;

#define STRIDE 59
#define SIGMA_COVER 3.0

mat3 quat_to_mat3(float qx, float qy, float qz, float qw) {
    return mat3(
        1.0 - 2.0 * (qy * qy + qz * qz), 2.0 * (qx * qy + qw * qz),     2.0 * (qx * qz - qw * qy),
        2.0 * (qx * qy - qw * qz),         1.0 - 2.0 * (qx * qx + qz * qz), 2.0 * (qy * qz + qw * qx),
        2.0 * (qx * qz + qw * qy),         2.0 * (qy * qz - qw * qx),         1.0 - 2.0 * (qx * qx + qy * qy)
    );
}

vec3 eval_sh(int base, vec3 dir) {
    vec3 result = vec3(splat[base + 3], splat[base + 4], splat[base + 5]);
    if (u_sh_degree < 1) return max(result, vec3(0.0));

    float xx = dir.x * dir.x;
    float yy = dir.y * dir.y;
    float zz = dir.z * dir.z;

    int r = base + 6;
    result += vec3(splat[r], splat[r + 1], splat[r + 2]) * dir.y;
    result += vec3(splat[r + 3], splat[r + 4], splat[r + 5]) * dir.z;
    result += vec3(splat[r + 6], splat[r + 7], splat[r + 8]) * dir.x;
    if (u_sh_degree < 2) return max(result, vec3(0.0));

    r = base + 15;
    result += vec3(splat[r], splat[r + 1], splat[r + 2]) * (dir.x * dir.y);
    result += vec3(splat[r + 3], splat[r + 4], splat[r + 5]) * (dir.y * dir.z);
    result += vec3(splat[r + 6], splat[r + 7], splat[r + 8]) * (2.0 * zz - xx - yy);
    result += vec3(splat[r + 9], splat[r + 10], splat[r + 11]) * (dir.x * dir.z);
    result += vec3(splat[r + 12], splat[r + 13], splat[r + 14]) * (xx - yy);
    if (u_sh_degree < 3) return max(result, vec3(0.0));

    r = base + 30;
    result += vec3(splat[r], splat[r + 1], splat[r + 2]) * (dir.y * (3.0 * zz - xx - yy));
    result += vec3(splat[r + 3], splat[r + 4], splat[r + 5]) * (dir.x * dir.z * dir.y);
    result += vec3(splat[r + 6], splat[r + 7], splat[r + 8]) * (dir.y * (xx - zz));
    result += vec3(splat[r + 9], splat[r + 10], splat[r + 11]) * (dir.z * (xx + yy - 2.0 * zz));
    result += vec3(splat[r + 12], splat[r + 13], splat[r + 14]) * (dir.x * (xx - 3.0 * yy));
    result += vec3(splat[r + 15], splat[r + 16], splat[r + 17]) * (dir.x * (5.0 * zz - xx - yy));
    result += vec3(splat[r + 18], splat[r + 19], splat[r + 20]) * (dir.z * (xx - yy));

    return max(result, vec3(0.0));
}

const vec2 QUAD_OFFSETS[4] = vec2[4](
    vec2(-1.0, -1.0),
    vec2( 1.0, -1.0),
    vec2(-1.0,  1.0),
    vec2( 1.0,  1.0)
);

void main() {
    uint vid = sorted_idx[gl_InstanceID];
    int base = int(vid) * STRIDE;

    float opa = splat[base + 51];
    if (opa <= u_opacity_threshold) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        return;
    }

    vec4 world_pos = u_model * vec4(splat[base], splat[base + 1], splat[base + 2], 1.0);
    vec4 view_pos = u_view * world_pos;
    float view_depth = -view_pos.z;
    if (view_depth < 0.2) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        return;
    }

    vec3 dir = normalize(world_pos.xyz - u_camera_pos);
    v_color = eval_sh(base, dir);
    v_alpha = opa;

    float sx = splat[base + 52];
    float sy = splat[base + 53];
    float sz = splat[base + 54];

    mat3 R = quat_to_mat3(splat[base + 55], splat[base + 56], splat[base + 57], splat[base + 58]);
    mat3 S = mat3(sx, 0.0, 0.0, 0.0, sy, 0.0, 0.0, 0.0, sz);
    mat3 W = mat3(u_view[0].xyz, u_view[1].xyz, u_view[2].xyz);
    mat3 T = W * mat3(u_model) * R * S;
    mat3 Vrk = T * transpose(T);

    float inv_z = 1.0 / view_pos.z;
    mat3 J = mat3(
        u_proj[0][0] * inv_z, 0.0, -u_proj[0][0] * view_pos.x * inv_z * inv_z,
        0.0, u_proj[1][1] * inv_z, -u_proj[1][1] * view_pos.y * inv_z * inv_z,
        0.0, 0.0, inv_z
    );

    mat3 cov2d = transpose(J) * Vrk * J;

    float pixel_scale = max(u_viewport.x, u_viewport.y) * 0.5;
    float aa = 0.3 / max(pixel_scale, 1.0);
    aa *= aa;
    float a = cov2d[0][0] + aa;
    float b = cov2d[0][1];
    float c = cov2d[1][1] + aa;

    float det = a * c - b * b;
    if (!(det > 0.0)) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        return;
    }

    float mid = 0.5 * (a + c);
    float delta = sqrt(max(mid * mid - det, 0.0));
    float l1 = mid + delta;
    float l2 = mid - delta;
    if (!(l1 > 0.0) || !(l2 > 0.0)) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        return;
    }

    float r1 = sqrt(l1);
    float r2 = sqrt(l2);

    float pixel_radius = r1 * pixel_scale;
    if (pixel_radius < 0.35) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        return;
    }

    float angle = 0.5 * atan(2.0 * b, a - c);
    vec2 v1 = vec2(cos(angle), sin(angle));
    vec2 v2 = vec2(-sin(angle), cos(angle));

    vec2 off = QUAD_OFFSETS[gl_VertexID];

    vec4 clip_pos = u_proj * view_pos;
    vec2 ndc_center = clip_pos.xy / clip_pos.w;
    float bound = max(r1, r2) * SIGMA_COVER;
    if (ndc_center.x < -1.0 - bound || ndc_center.x > 1.0 + bound ||
        ndc_center.y < -1.0 - bound || ndc_center.y > 1.0 + bound) {
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        return;
    }

    vec2 d = (off.x * v1 * r1 + off.y * v2 * r2) * SIGMA_COVER;
    vec2 screen = ndc_center + d;
    v_local = off * SIGMA_COVER;

    gl_Position = vec4(screen * clip_pos.w, clip_pos.z, clip_pos.w);
}
