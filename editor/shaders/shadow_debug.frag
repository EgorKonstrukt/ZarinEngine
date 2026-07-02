// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
in vec2 v_uv;
out vec4 frag_color;
uniform sampler2D u_debug_tex;
void main() {
    float d = texture(u_debug_tex, v_uv).r;
    frag_color = vec4(d, d, d, 1.0);
}
