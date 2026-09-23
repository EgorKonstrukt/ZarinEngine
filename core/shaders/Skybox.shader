// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/Skybox"
{
    Properties
    {
        _Exposure("Exposure (EV)", Float) = 0
        _Intensity("Intensity", Float) = 1
        _Tint("Tint", Color) = (1, 1, 1, 1)
        _Saturation("Saturation", Range(0, 2)) = 1
        _Blur("Background Blur", Range(0, 8)) = 0
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Background" }

        Pass
        {
            GLSLPROGRAM
            #version 330 core
            layout(location = 0) in vec3 in_position;
            uniform mat4 u_mvp;
            out vec3 v_dir;
            void main() {
                vec4 pos = u_mvp * vec4(in_position, 1.0);
                gl_Position = pos.xyww;
                v_dir = in_position;
            }

            // @FRAGMENT

            #version 330 core
            in vec3 v_dir;
            out vec4 frag_color;
            uniform sampler2D u_equirect;
            uniform float u_use_env;
            uniform float u_exposure;
            uniform float u_intensity;
            uniform vec3 u_tint;
            uniform float u_saturation;
            uniform float u_blur;
            uniform mat3 u_rotation;
            uniform float u_flip_y;
            const float PI = 3.14159265359;
            void main() {
                vec3 dir = normalize(u_rotation * normalize(v_dir));
                vec3 col;
                if (u_use_env > 0.5) {
                    vec2 uv = vec2(0.5 + atan(dir.z, dir.x) / 6.28318530718, acos(clamp(dir.y, -1.0, 1.0)) / PI);
                    if (u_flip_y > 0.5) {
                        uv.y = 1.0 - uv.y;
                    }
                    col = textureLod(u_equirect, uv, u_blur).rgb;
                } else {
                    float h = clamp(dir.y * 0.5 + 0.5, 0.0, 1.0);
                    col = mix(vec3(0.02, 0.02, 0.03), vec3(0.05, 0.07, 0.12), h);
                }
                col *= exp2(u_exposure) * u_intensity;
                float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
                col = mix(vec3(luma), col, u_saturation) * u_tint;
                frag_color = vec4(col, 1.0);
            }
            ENDGLSL
        }
    }
}
