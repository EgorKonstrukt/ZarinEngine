// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/Outline"
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
uniform mat4 u_mvp;
out vec4 clip_pos;
void main() {
    gl_Position = u_mvp * vec4(in_position, 1.0);
    clip_pos = gl_Position;
}

            // @FRAGMENT

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 330 core
uniform vec4 u_outline_color;
in vec4 clip_pos;
out vec4 frag_color;
void main() {
    frag_color = u_outline_color;
    gl_FragDepth = clip_pos.z / clip_pos.w;
}
            ENDGLSL
        }
    }
}
