// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
in vec3 in_position;
in vec4 in_color;
in vec2 in_texcoord;
in vec2 in_size;
in float in_rotation;

uniform mat4 u_view_proj;
uniform vec3 u_camera_right;
uniform vec3 u_camera_up;
uniform vec3 u_camera_forward;

out vec4 v_color;
out vec2 v_uv;

void main() {
    vec2 corner = in_texcoord - vec2(0.5);
    float cos_a = cos(in_rotation);
    float sin_a = sin(in_rotation);
    vec2 rotated;
    rotated.x = corner.x * cos_a - corner.y * sin_a;
    rotated.y = corner.x * sin_a + corner.y * cos_a;
    vec3 world_pos = in_position
        + u_camera_right * rotated.x * in_size.x
        + u_camera_up * rotated.y * in_size.y;
    gl_Position = u_view_proj * vec4(world_pos, 1.0);
    v_color = in_color;
    v_uv = in_texcoord;
}