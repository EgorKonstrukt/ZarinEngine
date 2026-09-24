// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/Unlit"
{
    Properties
    {
        [MainColor] _BaseColor("Base Color", Color) = (1, 1, 1, 1)
        [MainTexture] _BaseMap("Base Map", 2D) = "white" {}
        _Cutoff("Alpha Cutoff", Range(0, 1)) = 0.5
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" }

        Pass
        {
            GLSLPROGRAM
            #version 430 core
            layout(location = 0) in vec3 in_position;
            layout(location = 1) in vec3 in_normal;
            layout(location = 2) in vec2 in_uv;
            layout(location = 7) in vec4 in_bone_indices;
            layout(location = 8) in vec4 in_bone_weights;
            layout(std430, binding = 6) readonly buffer BoneMatrices { mat4 u_bone_matrices[]; };
            uniform mat4 u_model;
            uniform mat4 u_view;
            uniform mat4 u_proj;
            uniform mat3 u_normal_matrix;
            uniform int u_use_skinning;
            uniform int u_bone_count;
            out vec3 v_world_pos;
            out vec3 v_normal;
            out vec2 v_uv;
            out vec3 v_view_pos;
            void main() {
                vec3 skinned_pos = in_position;
                vec3 skinned_nrm = in_normal;
                if (u_use_skinning == 1) {
                    mat4 skin = mat4(0.0);
                    for (int i = 0; i < 4; i++) {
                        int bi = int(in_bone_indices[i] + 0.5);
                        float bw = in_bone_weights[i];
                        if (bi >= 0 && bi < u_bone_count && bw > 0.0) {
                            skin += bw * u_bone_matrices[bi];
                        }
                    }
                    skinned_pos = (skin * vec4(in_position, 1.0)).xyz;
                    skinned_nrm = mat3(skin) * in_normal;
                }
                vec4 world_pos = u_model * vec4(skinned_pos, 1.0);
                v_world_pos = world_pos.xyz;
                v_normal = normalize(u_normal_matrix * skinned_nrm);
                v_uv = in_uv;
                vec4 view_pos = u_view * world_pos;
                v_view_pos = view_pos.xyz;
                gl_Position = u_proj * u_view * world_pos;
            }

            // @FRAGMENT

            #version 330 core
            in vec3 v_world_pos;
            in vec3 v_normal;
            in vec2 v_uv;
            in vec3 v_view_pos;
            out vec4 frag_color;
            uniform vec4 _BaseColor;
            uniform sampler2D _BaseMap;
            uniform int _BaseMap_Active;
            uniform float _Cutoff;
            void main() {
                vec4 color = _BaseColor;
                if (_BaseMap_Active == 1) {
                    vec4 texColor = texture(_BaseMap, v_uv);
                    color *= texColor;
                }
                if (color.a < _Cutoff) discard;
                frag_color = color;
            }
            ENDGLSL
        }
    }
}
