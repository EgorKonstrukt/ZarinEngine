// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/Icon"
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
layout(location = 2) in float in_alpha;
uniform mat4 u_mvp;
out vec2 v_uv;
out float v_alpha;
void main() {
    v_uv = in_uv;
    v_alpha = in_alpha;
    gl_Position = u_mvp * vec4(in_position, 1.0);
}

            // @FRAGMENT

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 330 core
in vec2 v_uv;
in float v_alpha;
uniform sampler2D u_texture;
uniform vec4 u_color;
uniform float u_alpha;
out vec4 frag_color;
void main() {
    vec4 tex = texture(u_texture, v_uv);
    float a = tex.a * u_alpha * v_alpha;
    frag_color = vec4(tex.rgb * u_color.rgb, a);
}
            ENDGLSL
        }
    }
}
