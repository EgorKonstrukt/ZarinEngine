// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
in vec4 v_color;
in vec2 v_uv;
uniform sampler2D u_texture;
uniform bool u_use_texture;
uniform vec4 u_albedo;

out vec4 frag_color;

void main() {
    vec4 tex_color;
    if (u_use_texture) {
        tex_color = texture(u_texture, v_uv);
    } else {
        tex_color = vec4(1.0);
    }
    frag_color = tex_color * v_color;
}