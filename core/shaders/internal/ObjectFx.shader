// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/ObjectFx"
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

#version 430 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_uv;
layout(location = 3) in vec4 in_model0;
layout(location = 4) in vec4 in_model1;
layout(location = 5) in vec4 in_model2;
layout(location = 6) in vec4 in_model3;
layout(location = 7) in vec4 in_bone_indices;
layout(location = 8) in vec4 in_bone_weights;
layout(std430, binding = 4) readonly buffer InstanceModels {
    mat4 models[];
};
layout(std430, binding = 5) readonly buffer InstanceIndices {
    int indices[];
};
layout(std430, binding = 6) readonly buffer BoneMatrices {
    mat4 u_bone_matrices[];
};
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat3 u_normal_matrix;
uniform int u_use_instancing;
uniform int u_use_skinning;
uniform int u_bone_count;
uniform vec2 u_uv_scale;
uniform vec2 u_uv_offset;
uniform float u_uv_world_scale;
uniform float u_time;
uniform float u_disint_amount;
uniform vec3 u_disint_dir;
uniform float u_disint_cell;
uniform float u_disint_noise_scale;
uniform float u_disint_speed;
uniform float u_disint_drag;
uniform float u_disint_gravity;
uniform float u_disint_rot;
uniform float u_disint_twist;
uniform float u_disint_sp_variance;
uniform float u_disint_outward;
uniform float u_disint_scatter;
uniform float u_disint_jitter;
uniform float u_wind_amount;
uniform vec3 u_wind_dir;
uniform float u_wind_speed;
uniform float u_wind_strength;
uniform float u_glitch_amount;
uniform float u_glitch_intensity;
uniform float u_glitch_speed;
uniform float u_glitch_block;
uniform vec3 u_obj_center;
uniform float u_obj_scale;
out vec3 gs_world_pos;
out vec3 gs_normal;
out vec2 gs_uv;
out vec3 gs_view_pos;
out vec3 gs_local_pos;

float hash31(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float value_noise3(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash31(i + vec3(0.0, 0.0, 0.0));
    float n100 = hash31(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash31(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash31(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash31(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash31(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash31(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash31(i + vec3(1.0, 1.0, 1.0));
    float nx00 = mix(n000, n100, f.x);
    float nx10 = mix(n010, n110, f.x);
    float nx01 = mix(n001, n101, f.x);
    float nx11 = mix(n011, n111, f.x);
    float nxy0 = mix(nx00, nx10, f.y);
    float nxy1 = mix(nx01, nx11, f.y);
    return mix(nxy0, nxy1, f.z);
}

void main() {
    mat4 model = u_model;
    mat3 nm = u_normal_matrix;
    if (u_use_instancing == 1) {
        mat4 inst_model = mat4(in_model0, in_model1, in_model2, in_model3);
        model = inst_model;
        nm = mat3(model);
    } else if (u_use_instancing == 2 || u_use_instancing == 3) {
        int idx = indices[gl_InstanceID];
        model = models[idx];
        nm = mat3(model);
    }
    vec3 local_pos = in_position;
    vec3 local_nrm = in_normal;
    if (u_use_skinning == 1) {
        mat4 skin = mat4(0.0);
        for (int i = 0; i < 4; i++) {
            int bi = int(in_bone_indices[i] + 0.5);
            float bw = in_bone_weights[i];
            if (bi >= 0 && bi < u_bone_count && bw > 0.0) {
                skin += bw * u_bone_matrices[bi];
            }
        }
        local_pos = (skin * vec4(in_position, 1.0)).xyz;
        local_nrm = mat3(skin) * in_normal;
    }

    if (u_wind_amount > 0.0) {
        float phase = u_time * u_wind_speed;
        float h = clamp(in_position.y / max(0.001, u_obj_scale) * 0.5 + 0.5, 0.0, 1.0);
        float sway = sin(phase + (in_position.x + in_position.z) * 0.5) * u_wind_strength * h * h * u_wind_amount;
        vec3 wdir = normalize(u_wind_dir + vec3(1e-4, 0.0, 1e-4));
        local_pos += wdir * sway;
    }
    if (u_glitch_amount > 0.0) {
        float blk = floor(in_position.y / max(0.01, u_glitch_block) + u_time * u_glitch_speed);
        float r = hash31(vec3(blk, 1.7, 3.3));
        if (r < u_glitch_amount) {
            float off = (hash31(vec3(blk, 9.1, 2.2)) - 0.5) * u_glitch_intensity * u_obj_scale;
            local_pos.x += off;
        }
    }
    vec4 world_pos = model * vec4(local_pos, 1.0);
    gs_world_pos = world_pos.xyz;
    gs_normal = normalize(nm * local_nrm);
    vec2 tuv = in_uv * u_uv_scale + u_uv_offset;
    if (u_uv_world_scale > 0.5) {
        vec3 an = abs(local_nrm);
        vec3 msc = vec3(length(model[0].xyz), length(model[1].xyz), length(model[2].xyz));
        vec2 fs = vec2(msc.x, msc.y);
        if (an.y > an.x && an.y > an.z) {
            fs = vec2(msc.x, msc.z);
        } else if (an.x > an.z) {
            fs = vec2(msc.z, msc.y);
        }
        tuv *= fs;
    }
    gs_uv = tuv;
    gs_local_pos = in_position;
    vec4 view_pos = u_view * world_pos;
    gs_view_pos = view_pos.xyz;
    gl_Position = u_proj * u_view * world_pos;
}

            // @FRAGMENT

// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

#version 330 core
#define MAX_LIGHTS 8
#define CASCADE_COUNT 4
#define MAX_POINT_SHADOWS 4
#define MAX_SPOT_SHADOWS 4
#define PI 3.14159265359
in vec3 v_world_pos;
in vec3 v_normal;
in vec2 v_uv;
in vec3 v_view_pos;
in vec3 v_local_pos;
out vec4 frag_color;
struct Light {
    int type;
    vec3 position;
    vec3 direction;
    vec3 color;
    float intensity;
    float range;
    float spot_angle;
    float spot_inner_angle;
    vec3 right;
    vec3 up;
    float area_width;
    float area_height;
    int area_type;
    int area_samples;
    float area_double_sided;
};
uniform vec4 u_albedo_color;
uniform float u_metallic;
uniform float u_smoothness;
uniform vec3 u_emission;
uniform vec3 u_camera_pos;
uniform Light u_lights[MAX_LIGHTS];
uniform int u_light_count;
uniform vec3 u_ambient;
uniform int u_shadow_light_index;
uniform sampler2D u_albedo_tex;
uniform int u_use_albedo_tex;
uniform sampler2D u_normal_tex;
uniform int u_use_normal_tex;
uniform sampler2D u_roughness_tex;
uniform int u_use_roughness_tex;
uniform sampler2D u_shadow_map_0;
uniform sampler2D u_shadow_map_1;
uniform sampler2D u_shadow_map_2;
uniform sampler2D u_shadow_map_3;
uniform mat4 u_light_space_matrices[CASCADE_COUNT];
uniform float u_cascade_splits[CASCADE_COUNT];
uniform float u_shadow_bias;
uniform float u_shadow_normal_bias;
uniform float u_shadow_slope_scale;
uniform int u_cascade_count;
uniform sampler2D u_point_shadow_maps[MAX_POINT_SHADOWS * 6];
uniform mat4 u_point_shadow_vps[MAX_POINT_SHADOWS * 6];
uniform vec3 u_point_shadow_light_positions[MAX_POINT_SHADOWS];
uniform float u_point_shadow_light_ranges[MAX_POINT_SHADOWS];
uniform int u_point_shadow_count;
uniform int u_point_shadow_light_indices[MAX_POINT_SHADOWS];
uniform sampler2D u_spot_shadow_maps[MAX_SPOT_SHADOWS];
uniform mat4 u_spot_shadow_vps[MAX_SPOT_SHADOWS];
uniform int u_spot_shadow_count;
uniform int u_spot_shadow_light_indices[MAX_SPOT_SHADOWS];
uniform sampler2D u_area_shadow_map;
uniform mat4 u_area_light_vp;
uniform sampler2D u_area_shadow_map_back;
uniform mat4 u_area_light_vp_back;
uniform float u_area_shadow_back;
uniform float u_area_light_size;
uniform float u_area_light_fov_scale;
uniform vec2 u_area_light_near_far;
uniform int u_area_shadow_light_index;
uniform float u_area_shadow_bias;

uniform float u_time;
uniform float u_dissolve_amount;
uniform float u_dissolve_edge;
uniform vec3 u_dissolve_color;
uniform float u_dissolve_edge_emission;
uniform float u_dissolve_noise_scale;
uniform float u_dissolve_noise_strength;
uniform vec3 u_dissolve_dir;
uniform float u_dissolve_invert;
uniform float u_disint_amount;
uniform float u_disint_cell;
uniform float u_disint_noise_scale;
uniform float u_disint_edge;
uniform vec3 u_disint_edge_color;
uniform float u_disint_edge_emission;
uniform float u_disint_stagger;
uniform float u_disint_thr_scale;
uniform float u_disint_fade;
uniform float u_holo_amount;
uniform vec3 u_holo_color;
uniform float u_holo_scan;
uniform float u_holo_speed;
uniform float u_holo_flicker;
uniform float u_holo_rim;
uniform float u_frost_amount;
uniform vec3 u_frost_color;
uniform float u_frost_coverage;
uniform float u_frost_rim;
uniform float u_frost_crack;
uniform float u_frost_sparkle;
uniform vec3 u_frost_dir;
uniform float u_frost_animate;
uniform float u_pulse_amount;
uniform vec3 u_pulse_color;
uniform float u_pulse_speed;
uniform float u_pulse_strength;
uniform float u_glitch_amount;
uniform float u_glitch_speed;
uniform float u_glitch_block;
uniform float u_glitch_rgb;
uniform vec3 u_obj_center;
uniform float u_obj_scale;
uniform int u_double_sided;
// @FX_UNIFORMS

float hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float hash31(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float value_noise3(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash31(i + vec3(0.0, 0.0, 0.0));
    float n100 = hash31(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash31(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash31(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash31(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash31(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash31(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash31(i + vec3(1.0, 1.0, 1.0));
    float nx00 = mix(n000, n100, f.x);
    float nx10 = mix(n010, n110, f.x);
    float nx01 = mix(n001, n101, f.x);
    float nx11 = mix(n011, n111, f.x);
    float nxy0 = mix(nx00, nx10, f.y);
    float nxy1 = mix(nx01, nx11, f.y);
    return mix(nxy0, nxy1, f.z);
}
float fbm3(vec3 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 4; i++) {
        v += a * value_noise3(p);
        p *= 2.02;
        a *= 0.5;
    }
    return v;
}
float sample_shadow(sampler2D shadow_map, vec3 proj_coords, float bias) {
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
            if (x == 0) {
                weight += 1.0;
            }
            if (y == 0) {
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
vec3 shadow_receiver_normal() {
    vec3 n = normalize(v_normal);
    if (u_double_sided == 1 && !gl_FrontFacing) n = -n;
    return n;
}
vec3 shadow_dir_light_dir() {
    if (u_shadow_light_index < 0 || u_shadow_light_index >= MAX_LIGHTS) return vec3(0.0, 0.0, 1.0);
    return normalize(-u_lights[u_shadow_light_index].direction);
}
float compute_shadow() {
    if (u_cascade_count <= 0) return 1.0;
    int cascade_idx = 0;
    float frag_depth = abs(v_view_pos.z);
    for (int i = 0; i < CASCADE_COUNT - 1; i++) {
        if (frag_depth > u_cascade_splits[i]) cascade_idx = i + 1;
    }
    vec3 N = shadow_receiver_normal();
    vec3 L = shadow_dir_light_dir();
    float slope = 1.0 - clamp(dot(N, L), 0.0, 1.0);
    float cascade_scale = 1.0 + float(cascade_idx) * 0.75;
    vec3 bpos = v_world_pos + N * (u_shadow_normal_bias * cascade_scale * (0.35 + 0.65 * slope));
    vec4 light_space_pos = u_light_space_matrices[cascade_idx] * vec4(bpos, 1.0);
    vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
    proj_coords = proj_coords * 0.5 + 0.5;
    if (proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
    vec2 border = 1.0 - abs(proj_coords.xy - 0.5) * 2.0;
    float fade = clamp(border.x * border.y * 20.0, 0.0, 1.0);
    float bias = (u_shadow_bias + u_shadow_slope_scale * slope) * cascade_scale;
    float shadow;
    if (cascade_idx == 0) shadow = sample_shadow(u_shadow_map_0, proj_coords, bias);
    else if (cascade_idx == 1) shadow = sample_shadow(u_shadow_map_1, proj_coords, bias);
    else if (cascade_idx == 2) shadow = sample_shadow(u_shadow_map_2, proj_coords, bias);
    else shadow = sample_shadow(u_shadow_map_3, proj_coords, bias);
    return mix(1.0, shadow, fade);
}
float fallback_point_shadow(int li, int face, vec3 proj_coords, float bias) {
    if (li == 0) {
        if (face == 0) return sample_shadow(u_point_shadow_maps[0], proj_coords, bias);
        else if (face == 1) return sample_shadow(u_point_shadow_maps[1], proj_coords, bias);
        else if (face == 2) return sample_shadow(u_point_shadow_maps[2], proj_coords, bias);
        else if (face == 3) return sample_shadow(u_point_shadow_maps[3], proj_coords, bias);
        else if (face == 4) return sample_shadow(u_point_shadow_maps[4], proj_coords, bias);
        else return sample_shadow(u_point_shadow_maps[5], proj_coords, bias);
    } else if (li == 1) {
        if (face == 0) return sample_shadow(u_point_shadow_maps[6], proj_coords, bias);
        else if (face == 1) return sample_shadow(u_point_shadow_maps[7], proj_coords, bias);
        else if (face == 2) return sample_shadow(u_point_shadow_maps[8], proj_coords, bias);
        else if (face == 3) return sample_shadow(u_point_shadow_maps[9], proj_coords, bias);
        else if (face == 4) return sample_shadow(u_point_shadow_maps[10], proj_coords, bias);
        else return sample_shadow(u_point_shadow_maps[11], proj_coords, bias);
    } else if (li == 2) {
        if (face == 0) return sample_shadow(u_point_shadow_maps[12], proj_coords, bias);
        else if (face == 1) return sample_shadow(u_point_shadow_maps[13], proj_coords, bias);
        else if (face == 2) return sample_shadow(u_point_shadow_maps[14], proj_coords, bias);
        else if (face == 3) return sample_shadow(u_point_shadow_maps[15], proj_coords, bias);
        else if (face == 4) return sample_shadow(u_point_shadow_maps[16], proj_coords, bias);
        else return sample_shadow(u_point_shadow_maps[17], proj_coords, bias);
    } else {
        if (face == 0) return sample_shadow(u_point_shadow_maps[18], proj_coords, bias);
        else if (face == 1) return sample_shadow(u_point_shadow_maps[19], proj_coords, bias);
        else if (face == 2) return sample_shadow(u_point_shadow_maps[20], proj_coords, bias);
        else if (face == 3) return sample_shadow(u_point_shadow_maps[21], proj_coords, bias);
        else if (face == 4) return sample_shadow(u_point_shadow_maps[22], proj_coords, bias);
        else return sample_shadow(u_point_shadow_maps[23], proj_coords, bias);
    }
}
float fallback_spot_shadow(int li, vec3 proj_coords, float bias) {
    if (li == 0) return sample_shadow(u_spot_shadow_maps[0], proj_coords, bias);
    else if (li == 1) return sample_shadow(u_spot_shadow_maps[1], proj_coords, bias);
    else if (li == 2) return sample_shadow(u_spot_shadow_maps[2], proj_coords, bias);
    else return sample_shadow(u_spot_shadow_maps[3], proj_coords, bias);
}
float compute_point_shadow_for_light(int li) {
    vec3 N = shadow_receiver_normal();
    vec3 toL = u_point_shadow_light_positions[li] - v_world_pos;
    float dist = max(length(toL), 1e-4);
    vec3 L = toL / dist;
    float slope = 1.0 - clamp(dot(N, L), 0.0, 1.0);
    vec3 bpos = v_world_pos + N * (u_shadow_normal_bias * (0.35 + 0.65 * slope));
    vec3 dir = bpos - u_point_shadow_light_positions[li];
    vec3 abs_dir = abs(dir);
    int face = 0;
    if (abs_dir.x >= abs_dir.y && abs_dir.x >= abs_dir.z) {
        face = dir.x >= 0 ? 0 : 1;
    } else if (abs_dir.y >= abs_dir.z) {
        face = dir.y >= 0 ? 2 : 3;
    } else {
        face = dir.z >= 0 ? 4 : 5;
    }
    int base = li * 6;
    vec4 light_space_pos = u_point_shadow_vps[base + face] * vec4(bpos, 1.0);
    vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
    proj_coords = proj_coords * 0.5 + 0.5;
    if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
    float bias = u_shadow_bias + u_shadow_slope_scale * slope;
    return fallback_point_shadow(li, face, proj_coords, bias);
}
float compute_spot_shadow_for_light(int li) {
    vec3 N = shadow_receiver_normal();
    vec3 bpos = v_world_pos + N * (u_shadow_normal_bias * 0.65);
    vec4 light_space_pos = u_spot_shadow_vps[li] * vec4(bpos, 1.0);
    vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
    proj_coords = proj_coords * 0.5 + 0.5;
    if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
    float bias = u_shadow_bias + u_shadow_slope_scale * 0.5;
    return fallback_spot_shadow(li, proj_coords, bias);
}
// @SHADOW_INCLUDE
vec3 calc_area_light(Light light, vec3 normal, vec3 view_dir, vec3 albedo) {
    vec3 right = light.right;
    vec3 up = light.up;
    float hw = light.area_width * 0.5;
    float hh = light.area_height * 0.5;
    vec3 c = light.position;
    vec3 lightN = normalize(cross(light.up, light.right));
    int S = max(1, light.area_samples);
    bool ds = light.area_double_sided > 0.5;
    float inv_n = 1.0 / float(S * S);
    vec3 diff = vec3(0.0);
    vec3 spec = vec3(0.0);
    float r1 = 1.0 / float(S);
    float r2 = 1.0 / float(S);
    for (int i = 0; i < S; i++) {
        for (int j = 0; j < S; j++) {
            float jx = hash(gl_FragCoord.xy + vec2(float(i), float(j))) - 0.5;
            float jy = hash(gl_FragCoord.xy + vec2(float(j), float(i))) - 0.5;
            float u = (float(i) + 0.5 + jx) * r2 * 2.0 - 1.0;
            float v = (float(j) + 0.5 + jy) * r1 * 2.0 - 1.0;
            if (light.area_type == 1) {
                float a = u;
                float b = v;
                float phi_val, r;
                if (abs(a) > abs(b)) {
                    r = a;
                    phi_val = (PI / 4.0) * (b / max(a, 1e-6));
                } else {
                    r = b;
                    phi_val = (PI / 2.0) - (PI / 4.0) * (a / max(b, 1e-6));
                }
                u = r * cos(phi_val);
                v = r * sin(phi_val);
            }
            vec3 sp = c + right * u * hw + up * v * hh;
            vec3 to_sp = sp - v_world_pos;
            float dist = max(length(to_sp), 1e-4);
            vec3 ld = to_sp / dist;
            float eNdL = dot(-ld, lightN);
            if (!ds) {
                if (eNdL <= 0.0) continue;
            } else {
                eNdL = abs(eNdL);
            }
            float NdL = dot(normal, ld);
            if (!ds) {
                NdL = max(NdL, 0.0);
                if (NdL <= 0.0) continue;
            } else {
                NdL = abs(NdL);
            }
            float range_fade = clamp(1.0 - pow(dist / max(light.range, 1e-4), 4.0), 0.0, 1.0);
            float att = range_fade * range_fade / (dist * dist + 1.0);
            vec3 contrib = light.color * light.intensity * att * inv_n * eNdL;
            diff += contrib * NdL;
            vec3 h = normalize(ld + view_dir);
            float NdH = max(dot(normal, h), 0.0);
            spec += contrib * pow(NdH, max(1.0, u_smoothness * 128.0));
        }
    }
    return diff * albedo + spec * u_metallic;
}
vec3 calc_light(Light light, vec3 normal, vec3 view_dir, vec3 albedo, float shadow_factor) {
    vec3 light_dir;
    float attenuation = 1.0;
    if (light.type == 0) {
        light_dir = normalize(-light.direction);
    } else {
        vec3 to_light = light.position - v_world_pos;
        float dist = length(to_light);
        light_dir = to_light / dist;
        float range_fade = clamp(1.0 - pow(dist / max(light.range, 1e-4), 4.0), 0.0, 1.0);
        attenuation = range_fade * range_fade / (dist * dist + 1.0);
        if (light.type == 2) {
            float theta = dot(light_dir, normalize(-light.direction));
            float inner = cos(radians(light.spot_inner_angle));
            float outer = cos(radians(light.spot_angle));
            float eps = inner - outer;
            attenuation *= clamp((theta - outer) / eps, 0.0, 1.0);
        }
    }
    float diff = max(dot(normal, light_dir), 0.0);
    vec3 diffuse = diff * albedo * light.color * light.intensity * shadow_factor;
    vec3 reflect_dir = reflect(-light_dir, normal);
    float spec_pow = max(1.0, u_smoothness * 128.0);
    float spec = pow(max(dot(view_dir, reflect_dir), 0.0), spec_pow);
    vec3 specular = spec * light.color * light.intensity * u_metallic * shadow_factor;
    return (diffuse + specular) * attenuation;
}
void main() {
    vec3 albedo = u_albedo_color.rgb;
    float tex_a = 1.0;
    if (u_use_albedo_tex == 1) {
        vec4 texColor = texture(u_albedo_tex, v_uv);
        albedo *= texColor.rgb;
        tex_a = texColor.a;
    }
    vec3 normal = normalize(v_normal);
    if (u_use_normal_tex == 1) {
        vec3 tangentNormal = texture(u_normal_tex, v_uv).rgb * 2.0 - 1.0;
        normal = normalize(normal + tangentNormal * 0.5);
    }
    if (u_double_sided == 1 && !gl_FrontFacing) normal = -normal;
    float roughness = u_smoothness;
    if (u_use_roughness_tex == 1) {
        float r = texture(u_roughness_tex, v_uv).r;
        roughness = mix(roughness, r, 0.5);
    }
    vec3 view_dir = normalize(u_camera_pos - v_world_pos);
    vec3 result = u_ambient * albedo;
    float shadow_factor = compute_shadow();
    for (int i = 0; i < u_light_count && i < MAX_LIGHTS; i++) {
        float sf = 1.0;
        if (i == u_shadow_light_index) sf = min(sf, shadow_factor);
        for (int pi = 0; pi < u_point_shadow_count; pi++) {
            if (i == u_point_shadow_light_indices[pi]) { sf = min(sf, compute_point_shadow_for_light(pi)); break; }
        }
        for (int si = 0; si < u_spot_shadow_count; si++) {
            if (i == u_spot_shadow_light_indices[si]) { sf = min(sf, compute_spot_shadow_for_light(si)); break; }
        }
        if (u_lights[i].type == 3) {
            float area_sf = 1.0;
            if (i == u_area_shadow_light_index) area_sf = compute_area_shadow();
            result += calc_area_light(u_lights[i], normal, view_dir, albedo) * area_sf;
        } else {
            result += calc_light(u_lights[i], normal, view_dir, albedo, sf);
        }
    }
    result += u_emission;

    float fx_alpha = u_albedo_color.a * tex_a;
    if (u_dissolve_amount > 0.0) {
        vec3 d = normalize(u_dissolve_dir + vec3(1e-5));
        float grad = dot(d, v_local_pos) * 0.5 + 0.5;
        float n = value_noise3(v_local_pos * u_dissolve_noise_scale);
        float field = mix(grad, n, clamp(u_dissolve_noise_strength, 0.0, 1.0));
        if (u_dissolve_invert > 0.5) field = 1.0 - field;
        float thr = u_dissolve_amount;
        if (field < thr) discard;
        float edge = thr + max(0.0001, u_dissolve_edge);
        if (field < edge) {
            float t = (field - thr) / (edge - thr);
            result = mix(u_dissolve_color * u_dissolve_edge_emission, result, t);
        }
    }
    if (u_disint_amount > 0.0) {
        vec3 cell = floor((v_local_pos - u_obj_center) / max(0.001, u_disint_cell));
        float h = hash31(cell);
        float n = value_noise3(v_local_pos * max(0.1, u_disint_noise_scale));
        float thr = u_disint_amount * u_disint_thr_scale - h * u_disint_stagger;
        if (n < thr) discard;
        float edge = thr + max(0.0001, u_disint_edge);
        if (n < edge) {
            float t = (n - thr) / (edge - thr);
            result = mix(u_disint_edge_color * u_disint_edge_emission, result, t);
        }
        if (u_disint_fade > 0.0) {
            float released = u_disint_amount * u_disint_thr_scale - h * u_disint_stagger;
            float f = clamp(released / max(0.0001, u_disint_fade), 0.0, 1.0);
            fx_alpha *= 1.0 - f;
        }
    }

    if (u_holo_amount > 0.0) {
        vec3 V = normalize(u_camera_pos - v_world_pos);
        float fres = pow(1.0 - max(dot(normalize(v_normal), V), 0.0), u_holo_rim);
        float scan = 0.5 + 0.5 * sin(v_world_pos.y * u_holo_scan + u_time * u_holo_speed);
        float fl = 1.0 - u_holo_flicker * (0.5 + 0.5 * sin(u_time * 37.0 + v_world_pos.x * 4.0));
        vec3 holo = u_holo_color * (fres * 1.5 + scan * 0.5) * u_holo_amount * fl;
        result = mix(result, result + holo, u_holo_amount);
        fx_alpha = clamp(fx_alpha + fres * u_holo_amount * 0.6, 0.0, 1.0);
    }
    if (u_frost_amount > 0.0) {
        float animT = (u_frost_animate > 0.5) ? u_time : 0.0;
        vec3 V = normalize(u_camera_pos - v_world_pos);
        float fres = pow(1.0 - max(dot(normalize(v_normal), V), 0.0), u_frost_rim);

        float fbm = fbm3(v_local_pos * u_frost_crack + vec3(0.0, 0.0, animT * 0.05));
        vec3 fdir = normalize(u_frost_dir + vec3(0.0, 1e-4, 0.0));
        float along = clamp(dot(v_local_pos, fdir) / max(0.001, u_obj_scale) * 0.5 + 0.5, 0.0, 1.0);
        float front = u_frost_amount * (1.0 + u_frost_coverage);
        float local = clamp(front - (1.0 - along) * (1.0 - u_frost_coverage), 0.0, 1.0);
        float mask = clamp(local * (0.35 + 0.75 * fbm), 0.0, 1.0);

        vec3 icy = u_frost_color;
        float sp = value_noise3(v_local_pos * u_frost_crack * 6.0 + vec3(animT * 2.0));
        float glint = smoothstep(0.82, 1.0, sp) * u_frost_sparkle * mask;

        vec3 frosted = mix(result, icy, mask * 0.9);
        frosted += icy * fres * u_frost_amount * 0.8;
        frosted += vec3(1.0) * glint;
        result = mix(result, frosted, u_frost_amount);
    }
    if (u_pulse_amount > 0.0) {
        float p = 0.5 + 0.5 * sin(u_time * u_pulse_speed);
        result += u_pulse_color * p * u_pulse_strength * u_pulse_amount;
    }
    if (u_glitch_amount > 0.0) {
        float blk = floor(v_local_pos.y / max(0.01, u_glitch_block) + u_time * u_glitch_speed);
        float r = hash31(vec3(blk, 4.2, 7.7));
        if (r < u_glitch_amount) {
            float mode = hash31(vec3(blk, 2.2, 8.8));
            vec3 g = result;
            if (mode < 0.34) g = result.gbr;
            else if (mode < 0.67) g = result.brg;
            g *= 1.0 + u_glitch_rgb * (r / max(0.001, u_glitch_amount));
            result = mix(result, g, u_glitch_amount);
        }
    }

    // @FX_MAIN
    frag_color = vec4(result, fx_alpha);
}
            ENDGLSL
        }
    }
}
