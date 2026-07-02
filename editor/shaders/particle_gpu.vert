// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core

struct Particle {
    vec4 position;
    vec4 velocity;
    vec4 color;
    vec4 meta;
    vec4 lifetime;
    vec4 start_color;
    vec4 start_meta;
};

layout(std430, binding = 0) buffer ParticleBuffer {
    Particle particles[];
};

uniform mat4 u_view_proj;
uniform vec3 u_camera_right;
uniform vec3 u_camera_up;

out vec4 v_color;
out vec2 v_uv;

void main() {
    int pid = gl_VertexID / 6;
    int corner = gl_VertexID % 6;

    Particle p = particles[pid];
    if (p.meta.w <= 0.0) {
        gl_Position = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    vec2 uv;
    if (corner == 0) uv = vec2(0.0, 0.0);
    else if (corner == 1) uv = vec2(1.0, 0.0);
    else if (corner == 2) uv = vec2(1.0, 1.0);
    else if (corner == 3) uv = vec2(0.0, 0.0);
    else if (corner == 4) uv = vec2(1.0, 1.0);
    else uv = vec2(0.0, 1.0);

    vec2 corner_uv = uv - vec2(0.5);
    float cos_a = cos(p.meta.z);
    float sin_a = sin(p.meta.z);
    vec2 rotated;
    rotated.x = corner_uv.x * cos_a - corner_uv.y * sin_a;
    rotated.y = corner_uv.x * sin_a + corner_uv.y * cos_a;

    vec3 world_pos = p.position.xyz
        + u_camera_right * rotated.x * p.meta.x
        + u_camera_up * rotated.y * p.meta.y;

    gl_Position = u_view_proj * vec4(world_pos, 1.0);
    v_color = p.color;
    v_uv = uv;
}
