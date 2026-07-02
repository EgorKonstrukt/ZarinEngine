// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
in vec3 v_world_pos;
uniform vec4 u_color;
uniform vec3 u_camera_pos;
out vec4 frag_color;
void main() {
    float dist = length(v_world_pos.xz - u_camera_pos.xz);
    float fade = 1.0 - smoothstep(20.0, 80.0, dist);
    frag_color = vec4(u_color.rgb * fade, u_color.a * fade);
}
