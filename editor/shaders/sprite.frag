// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec4 u_color;
uniform float u_alpha_cutoff;
out vec4 frag_color;
void main() {
    vec4 tex = texture(u_texture, v_uv);
    vec4 result = tex * u_color;
    if (result.a < u_alpha_cutoff) discard;
    frag_color = result;
}
