// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec4 u_color;
uniform float u_solid;
uniform float u_clip_alpha;
out vec4 frag_color;
void main() {
    float alpha = u_solid > 0.5 ? 1.0 : texture(u_texture, v_uv).a;
    vec4 result = vec4(u_color.rgb, u_color.a * alpha);
    if (result.a < u_clip_alpha) discard;
    frag_color = result;
}
