// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/Gizmo"
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
uniform mat4 u_model;
out vec3 v_world_pos;
void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    v_world_pos = world_pos.xyz;
    gl_Position = u_mvp * vec4(in_position, 1.0);
}

            // @FRAGMENT

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 330 core
in vec3 v_world_pos;
uniform vec4 u_color;
uniform vec3 u_camera_pos;
out vec4 frag_color;
void main() {
    float dist = length(v_world_pos.xz - u_camera_pos.xz);
    float fade = 1.0 - smoothstep(20.0, 80.0, dist);
    frag_color = vec4(u_color.rgb * fade, u_color.a * fade);
}
            ENDGLSL
        }
    }
}
