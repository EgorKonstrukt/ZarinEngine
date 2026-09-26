// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/Default"
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
out vec3 v_world_pos;
out vec3 v_normal;
out vec2 v_uv;
out vec3 v_view_pos;
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
    vec4 world_pos = model * vec4(local_pos, 1.0);
    v_world_pos = world_pos.xyz;
    v_normal = normalize(nm * local_nrm);
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
    v_uv = tuv;
    vec4 view_pos = u_view * world_pos;
    v_view_pos = view_pos.xyz;
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
uniform int u_double_sided;
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
uniform sampler2D u_cascade_atlas;
uniform vec4 u_cascade_rects[4];
uniform mat4 u_light_space_matrices[CASCADE_COUNT];
uniform float u_cascade_splits[CASCADE_COUNT];
uniform float u_shadow_bias;
uniform float u_shadow_normal_bias;
uniform float u_shadow_slope_scale;
uniform int u_cascade_count;
uniform sampler2D u_point_shadow_atlas;
uniform mat4 u_point_shadow_vps[MAX_POINT_SHADOWS * 6];
uniform vec3 u_point_shadow_light_positions[MAX_POINT_SHADOWS];
uniform float u_point_shadow_light_ranges[MAX_POINT_SHADOWS];
uniform int u_point_shadow_count;
uniform int u_point_shadow_light_indices[MAX_POINT_SHADOWS];
uniform sampler2D u_spot_shadow_atlas;
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
uniform samplerCube u_irradiance_map;
uniform int u_irradiance_map_Active;
uniform samplerCube u_prefilter_map;
uniform int u_prefilter_map_Active;
uniform sampler2D u_brdf_lut;
uniform int u_brdf_lut_Active;
uniform float u_env_map_rotation;
float hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
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
vec3 shadow_receiver_normal() {
    vec3 n = normalize(v_normal);
    if (u_double_sided == 1 && !gl_FrontFacing) n = -n;
    return n;
}
vec3 shadow_dir_light_dir() {
    if (u_shadow_light_index < 0 || u_shadow_light_index >= MAX_LIGHTS) return vec3(0.0, 0.0, 1.0);
    return normalize(-u_lights[u_shadow_light_index].direction);
}
float sample_shadow_tiled(sampler2D atlas_map, vec2 origin, vec2 span, vec3 proj_coords, float bias);
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
    if (cascade_idx == 0) shadow = sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[0].xy, u_cascade_rects[0].zw, proj_coords, bias);
    else if (cascade_idx == 1) shadow = sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[1].xy, u_cascade_rects[1].zw, proj_coords, bias);
    else if (cascade_idx == 2) shadow = sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[2].xy, u_cascade_rects[2].zw, proj_coords, bias);
    else shadow = sample_shadow_tiled(u_cascade_atlas, u_cascade_rects[3].xy, u_cascade_rects[3].zw, proj_coords, bias);
    return mix(1.0, shadow, fade);
}
float sample_shadow_tiled(sampler2D atlas_map, vec2 origin, vec2 span, vec3 proj_coords, float bias) {
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
float fallback_point_shadow(int li, int face, vec3 proj_coords, float bias) {
    vec2 grid = vec2(6.0, float(MAX_POINT_SHADOWS));
    vec2 origin = vec2(float(face), float(li)) / grid;
    vec2 span = vec2(1.0) / grid;
    return sample_shadow_tiled(u_point_shadow_atlas, origin, span, proj_coords, bias);
}
float fallback_spot_shadow(int li, vec3 proj_coords, float bias) {
    vec2 grid = vec2(float(MAX_SPOT_SHADOWS), 1.0);
    vec2 origin = vec2(float(li), 0.0) / grid;
    vec2 span = vec2(1.0) / grid;
    return sample_shadow_tiled(u_spot_shadow_atlas, origin, span, proj_coords, bias);
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
vec3 ibl_contribution(vec3 N, vec3 V, vec3 albedo, float roughness, float metallic) {
    vec3 irradiance = u_ambient * albedo;
    vec3 specular_ibl = vec3(0.0);
    if (u_irradiance_map_Active == 1) {
        irradiance = texture(u_irradiance_map, N).rgb;
    }
    vec3 kS;
    if (u_prefilter_map_Active == 1 && u_brdf_lut_Active == 1) {
        vec3 R = reflect(-V, N);
        float NdotV = max(dot(N, V), 0.0);
        float prefilter_lod = roughness * 4.0;
        vec3 prefiltered = textureLod(u_prefilter_map, R, prefilter_lod).rgb;
        vec2 env_brdf = texture(u_brdf_lut, vec2(NdotV, roughness)).rg;
        float fresnel = pow(1.0 - NdotV, 5.0);
        kS = mix(vec3(0.04), albedo, metallic) * fresnel + vec3(1.0 - fresnel) * (1.0 - metallic);
        specular_ibl = prefiltered * (kS * env_brdf.x + env_brdf.y);
    } else {
        kS = vec3(0.0);
    }
    vec3 kD = (vec3(1.0) - kS) * (1.0 - metallic);
    vec3 diffuse_ibl = kD * irradiance * albedo;
    return diffuse_ibl + specular_ibl;
}
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
    float salpha = u_albedo_color.a;
    if (u_use_albedo_tex == 1) {
        vec4 texColor = texture(u_albedo_tex, v_uv);
        albedo *= texColor.rgb;
        salpha *= texColor.a;
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
    result += ibl_contribution(normal, view_dir, albedo, 1.0 - roughness, u_metallic);
    result += u_emission;
    frag_color = vec4(result, salpha);
}
            ENDGLSL
        }
    }
}
