// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 460 core
uniform vec4 u_outline_color;
in vec4 clip_pos;
out vec4 frag_color;
void main() {
    frag_color = u_outline_color;
    gl_FragDepth = clip_pos.z / clip_pos.w;
}
