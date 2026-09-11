// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 430 core

in vec3 v_color;
in vec2 v_local;
in float v_alpha;

out vec4 frag_color;

void main() {
    float p2 = dot(v_local, v_local);
    if (p2 > 16.0) discard;

    float alpha = v_alpha * exp(-0.5 * p2);
    if (alpha < 0.004) discard;

    vec3 col = max(v_color, vec3(0.0));
    frag_color = vec4(col * alpha, alpha);
}
