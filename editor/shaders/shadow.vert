// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
layout(location = 0) in vec3 in_position;
uniform mat4 u_model;
uniform mat4 u_light_vp;
void main() {
    gl_Position = u_light_vp * u_model * vec4(in_position, 1.0);
}
