// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/ShadowOverlay"
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
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}

            // @FRAGMENT

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 330 core
#define CASCADE_COUNT 4
#define MAX_POINT_SHADOWS 4
#define MAX_SPOT_SHADOWS 4
uniform sampler2D u_scene_color;
uniform sampler2D u_depth_tex;
uniform mat4 u_inv_vp;
uniform sampler2D u_cascade_atlas;
uniform vec4 u_cascade_rects[4];
uniform mat4 u_light_space_matrices[CASCADE_COUNT];
uniform float u_cascade_splits[CASCADE_COUNT];
uniform int u_cascade_count;
uniform float u_shadow_bias;
uniform mat4 u_view;
uniform sampler2D u_point_shadow_atlas;
uniform mat4 u_point_shadow_vps[MAX_POINT_SHADOWS * 6];
uniform vec3 u_point_shadow_light_positions[MAX_POINT_SHADOWS];
uniform float u_point_shadow_light_ranges[MAX_POINT_SHADOWS];
uniform int u_point_shadow_count;
uniform sampler2D u_spot_shadow_atlas;
uniform mat4 u_spot_shadow_vps[MAX_SPOT_SHADOWS];
uniform int u_spot_shadow_count;
in vec2 v_uv;
out vec4 frag_color;
float sample_shadow(sampler2D shadow_map, vec3 proj_coords) {
    float slope_bias = clamp(fwidth(proj_coords.z) * 2.0, 0.0, 0.01);
    float bias = u_shadow_bias + slope_bias;
    float current_depth = proj_coords.z - bias;
    float result = 0.0;
    vec2 texel_size = 1.0 / vec2(textureSize(shadow_map, 0));
    float radius = 1.0;
    float rot = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) * 6.2831853;
    float ca = cos(rot);
    float sa = sin(rot);
    float weight_sum = 0.0;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            float weight = 1.0;
            if (x == 0)
            {
                weight += 1.0;
            }
            if (y == 0)
            {
                weight += 1.0;
            }
            vec2 o = vec2(float(x), float(y));
            vec2 ro = vec2(o.x * ca - o.y * sa, o.x * sa + o.y * ca);
            vec2 uv = clamp(proj_coords.xy + ro * texel_size * radius, vec2(0.001), vec2(0.999));
            float pcf_depth = texture(shadow_map, uv).r;
            result += (current_depth > pcf_depth ? 1.0 : 0.0) * weight;
            weight_sum += weight;
        }
    }
    float lit = 1.0 - result / weight_sum;
    return smoothstep(0.12, 0.88, lit);
}
float sample_shadow_tiled(sampler2D atlas_map, vec2 origin, vec2 span, vec3 proj_coords);
float compute_directional_shadow(vec3 world_pos) {
    if (u_cascade_count <= 0) return 1.0;
    int cascade_idx = 0;
    vec4 view_pos = u_view * vec4(world_pos, 1.0);
    float frag_depth = abs(view_pos.z);
    for (int i = 0; i < CASCADE_COUNT - 1; i++) {
        if (frag_depth > u_cascade_splits[i]) cascade_idx = i + 1;
    }
    vec4 light_space_pos = u_light_space_matrices[cascade_idx] * vec4(world_pos, 1.0);
    vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
    proj_coords = proj_coords * 0.5 + 0.5;
    if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
    if (cascade_idx == 0) return sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[0].xy, u_cascade_rects[0].zw, proj_coords);
    else if (cascade_idx == 1) return sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[1].xy, u_cascade_rects[1].zw, proj_coords);
    else if (cascade_idx == 2) return sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[2].xy, u_cascade_rects[2].zw, proj_coords);
    return sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[3].xy, u_cascade_rects[3].zw, proj_coords);
}
float sample_shadow_tiled(sampler2D atlas_map, vec2 origin, vec2 span, vec3 proj_coords) {
    float slope_bias = clamp(fwidth(proj_coords.z) * 2.0, 0.0, 0.01);
    float bias = u_shadow_bias + slope_bias;
    float current_depth = proj_coords.z - bias;
    float result = 0.0;
    vec2 texel_size = 1.0 / vec2(textureSize(atlas_map, 0));
    float radius = 1.0;
    float rot = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) * 6.2831853;
    float ca = cos(rot);
    float sa = sin(rot);
    float weight_sum = 0.0;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            float weight = 1.0;
            if (x == 0)
            {
                weight += 1.0;
            }
            if (y == 0)
            {
                weight += 1.0;
            }
            vec2 o = vec2(float(x), float(y));
            vec2 ro = vec2(o.x * ca - o.y * sa, o.x * sa + o.y * ca);
            vec2 uv = origin + clamp(proj_coords.xy + ro * texel_size * radius, vec2(0.001), vec2(0.999)) * span;
            float pcf_depth = texture(atlas_map, uv).r;
            result += (current_depth > pcf_depth ? 1.0 : 0.0) * weight;
            weight_sum += weight;
        }
    }
    float lit = 1.0 - result / weight_sum;
    return smoothstep(0.12, 0.88, lit);
}
float fallback_point_shadow(int li, int face, vec3 proj_coords) {
    vec2 grid = vec2(6.0, float(MAX_POINT_SHADOWS));
    vec2 origin = vec2(float(face), float(li)) / grid;
    vec2 span = vec2(1.0) / grid;
    return sample_shadow_tiled(u_point_shadow_atlas, origin, span, proj_coords);
}
float fallback_spot_shadow(int li, vec3 proj_coords) {
    vec2 grid = vec2(float(MAX_SPOT_SHADOWS), 1.0);
    vec2 origin = vec2(float(li), 0.0) / grid;
    vec2 span = vec2(1.0) / grid;
    return sample_shadow_tiled(u_spot_shadow_atlas, origin, span, proj_coords);
}
float compute_point_shadow_pass(vec3 world_pos) {
    if (u_point_shadow_count <= 0) return 1.0;
    float result = 1.0;
    for (int li = 0; li < u_point_shadow_count; li++) {
        vec3 light_pos = u_point_shadow_light_positions[li];
        vec3 dir = world_pos - light_pos;
        vec3 abs_dir = abs(dir);
        int face = 0;
        if (abs_dir.x >= abs_dir.y && abs_dir.x >= abs_dir.z) face = dir.x >= 0 ? 0 : 1;
        else if (abs_dir.y >= abs_dir.z) face = dir.y >= 0 ? 2 : 3;
        else face = dir.z >= 0 ? 4 : 5;
        int base = li * 6;
        vec4 light_space_pos = u_point_shadow_vps[base + face] * vec4(world_pos, 1.0);
        vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
        proj_coords = proj_coords * 0.5 + 0.5;
        if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) continue;
        float d = length(world_pos - light_pos);
        float range = u_point_shadow_light_ranges[li];
        if (d > range) continue;
        result = min(result, fallback_point_shadow(li, face, proj_coords));
    }
    return result;
}
float compute_spot_shadow_pass(vec3 world_pos) {
    if (u_spot_shadow_count <= 0) return 1.0;
    float result = 1.0;
    for (int li = 0; li < u_spot_shadow_count; li++) {
        vec4 light_space_pos = u_spot_shadow_vps[li] * vec4(world_pos, 1.0);
        vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
        proj_coords = proj_coords * 0.5 + 0.5;
        if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) continue;
        result = min(result, fallback_spot_shadow(li, proj_coords));
    }
    return result;
}
void main() {
    vec3 scene_color = texture(u_scene_color, v_uv).rgb;
    float depth = texture(u_depth_tex, v_uv).r;
    if (depth >= 1.0) {
        frag_color = vec4(scene_color, 1.0);
        return;
    }
    vec4 clip_pos = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 world_pos4 = u_inv_vp * clip_pos;
    vec3 world_pos = world_pos4.xyz / world_pos4.w;
    float shadow = min(min(compute_directional_shadow(world_pos), compute_point_shadow_pass(world_pos)), compute_spot_shadow_pass(world_pos));
    float visibility = mix(0.46, 1.0, shadow);
    frag_color = vec4(scene_color * visibility, 1.0);
}
            ENDGLSL
        }
    }
}
