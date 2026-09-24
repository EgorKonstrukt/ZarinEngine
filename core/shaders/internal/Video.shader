// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/Video"
{
    Properties
    {
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" }

        Pass
        {
            GLSLPROGRAM
// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 330 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec2 in_uv;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform vec2 u_flip;
out vec2 v_uv;
void main() {
    vec2 uv = in_uv;
    if (u_flip.x > 0.5) uv.x = 1.0 - uv.x;
    if (u_flip.y > 0.5) uv.y = 1.0 - uv.y;
    v_uv = uv;
    gl_Position = u_proj * u_view * u_model * vec4(in_position, 1.0);
}

            // @FRAGMENT

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 330 core
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
            ENDGLSL
        }
    }
}
