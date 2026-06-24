Shader "Zarin/PBR"
{
    Properties
    {
        [MainColor] _BaseColor("Base Color", Color) = (1, 1, 1, 1)
        [MainTexture] _BaseMap("Base Map", 2D) = "white" {}
        _Metallic("Metallic", Range(0, 1)) = 0
        _Smoothness("Smoothness", Range(0, 1)) = 0.5
        _EmissionColor("Emission Color", Color) = (0, 0, 0, 0)
        _EmissionIntensity("Emission Intensity", Float) = 0
        _NormalMap("Normal Map", 2D) = "bump" {}
        _OcclusionMap("Occlusion Map", 2D) = "white" {}
        _OcclusionStrength("Occlusion Strength", Range(0, 1)) = 1
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" }

        Pass
        {
            GLSLPROGRAM
            #version 460 core
            layout(location = 0) in vec3 in_position;
            layout(location = 1) in vec3 in_normal;
            layout(location = 2) in vec2 in_uv;
            layout(location = 3) in vec4 in_model0;
            layout(location = 4) in vec4 in_model1;
            layout(location = 5) in vec4 in_model2;
            layout(location = 6) in vec4 in_model3;
            uniform int u_use_instancing;
            uniform mat4 u_model;
            uniform mat4 u_view;
            uniform mat4 u_proj;
            uniform mat3 u_normal_matrix;
            out vec3 v_world_pos;
            out vec3 v_normal;
            out vec2 v_uv;
            out vec3 v_view_pos;
            void main() {
                mat4 inst_model = mat4(in_model0, in_model1, in_model2, in_model3);
                mat4 _model = (u_use_instancing == 1) ? inst_model : u_model;
                mat3 _normal_matrix = (u_use_instancing == 1) ? transpose(inverse(mat3(_model))) : u_normal_matrix;
                vec4 world_pos = _model * vec4(in_position, 1.0);
                v_world_pos = world_pos.xyz;
                v_normal = normalize(_normal_matrix * in_normal);
                v_uv = in_uv;
                vec4 view_pos = u_view * world_pos;
                v_view_pos = view_pos.xyz;
                gl_Position = u_proj * u_view * world_pos;
            }

            // @FRAGMENT

            #version 460 core
            #define MAX_LIGHTS 8
            #define CASCADE_COUNT 3
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
            };
            uniform vec4 _BaseColor;
            uniform float _Metallic;
            uniform float _Smoothness;
            uniform vec3 _EmissionColor;
            uniform float _EmissionIntensity;
            uniform sampler2D _BaseMap;
            uniform int _BaseMap_Active;
            uniform sampler2D _NormalMap;
            uniform int _NormalMap_Active;
            uniform sampler2D _OcclusionMap;
            uniform int _OcclusionMap_Active;
            uniform float _OcclusionStrength;
            uniform vec3 u_camera_pos;
            uniform Light u_lights[MAX_LIGHTS];
            uniform int u_light_count;
            uniform vec3 u_ambient;
            uniform int u_shadow_light_index;
            uniform sampler2D u_shadow_map_0;
            uniform sampler2D u_shadow_map_1;
            uniform sampler2D u_shadow_map_2;
            uniform mat4 u_light_space_matrices[CASCADE_COUNT];
            uniform float u_cascade_splits[CASCADE_COUNT];
            uniform float u_shadow_bias;
            uniform int u_cascade_count;
            uniform sampler2D u_point_shadow_map_0;
            uniform sampler2D u_point_shadow_map_1;
            uniform sampler2D u_point_shadow_map_2;
            uniform sampler2D u_point_shadow_map_3;
            uniform sampler2D u_point_shadow_map_4;
            uniform sampler2D u_point_shadow_map_5;
            uniform mat4 u_point_light_vps[6];
            uniform vec3 u_point_light_pos;
            uniform float u_point_light_range;
            uniform int u_point_shadow_count;
            uniform int u_point_shadow_light_index;
            uniform sampler2D u_spot_shadow_map;
            uniform mat4 u_spot_light_vp;
            uniform int u_spot_shadow_count;
            uniform int u_spot_shadow_light_index;

            float sample_shadow(sampler2D shadow_map, vec3 proj_coords) {
                float current_depth = proj_coords.z - u_shadow_bias;
                float result = 0.0;
                vec2 texel_size = 1.0 / vec2(textureSize(shadow_map, 0));
                for (int x = -1; x <= 1; x++) {
                    for (int y = -1; y <= 1; y++) {
                        float pcf_depth = texture(shadow_map, proj_coords.xy + vec2(x, y) * texel_size).r;
                        result += current_depth > pcf_depth ? 1.0 : 0.0;
                    }
                }
                return 1.0 - result / 9.0;
            }

            float compute_shadow() {
                if (u_cascade_count <= 0) return 1.0;
                int cascade_idx = 0;
                float frag_depth = abs(v_view_pos.z);
                for (int i = 0; i < CASCADE_COUNT - 1; i++) {
                    if (frag_depth > u_cascade_splits[i]) cascade_idx = i + 1;
                }
                vec4 light_space_pos = u_light_space_matrices[cascade_idx] * vec4(v_world_pos, 1.0);
                vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
                proj_coords = proj_coords * 0.5 + 0.5;
                if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
                if (cascade_idx == 0) return sample_shadow(u_shadow_map_0, proj_coords);
                else if (cascade_idx == 1) return sample_shadow(u_shadow_map_1, proj_coords);
                return sample_shadow(u_shadow_map_2, proj_coords);
            }

            float compute_point_shadow() {
                if (u_point_shadow_count <= 0) return 1.0;
                vec3 dir = v_world_pos - u_point_light_pos;
                vec3 abs_dir = abs(dir);
                int face = 0;
                if (abs_dir.x >= abs_dir.y && abs_dir.x >= abs_dir.z) face = dir.x >= 0 ? 0 : 1;
                else if (abs_dir.y >= abs_dir.z) face = dir.y >= 0 ? 2 : 3;
                else face = dir.z >= 0 ? 4 : 5;
                vec4 light_space_pos = u_point_light_vps[face] * vec4(v_world_pos, 1.0);
                vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
                proj_coords = proj_coords * 0.5 + 0.5;
                if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
                if (face == 0) return sample_shadow(u_point_shadow_map_0, proj_coords);
                else if (face == 1) return sample_shadow(u_point_shadow_map_1, proj_coords);
                else if (face == 2) return sample_shadow(u_point_shadow_map_2, proj_coords);
                else if (face == 3) return sample_shadow(u_point_shadow_map_3, proj_coords);
                else if (face == 4) return sample_shadow(u_point_shadow_map_4, proj_coords);
                return sample_shadow(u_point_shadow_map_5, proj_coords);
            }

            float compute_spot_shadow() {
                if (u_spot_shadow_count <= 0) return 1.0;
                vec4 light_space_pos = u_spot_light_vp * vec4(v_world_pos, 1.0);
                vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
                proj_coords = proj_coords * 0.5 + 0.5;
                if (proj_coords.x < 0.0 || proj_coords.x > 1.0 || proj_coords.y < 0.0 || proj_coords.y > 1.0 || proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
                return sample_shadow(u_spot_shadow_map, proj_coords);
            }

            float distribution_ggx(vec3 N, vec3 H, float roughness) {
                float a = roughness * roughness;
                float a2 = a * a;
                float NdotH = max(dot(N, H), 0.0);
                float NdotH2 = NdotH * NdotH;
                float denom = NdotH2 * (a2 - 1.0) + 1.0;
                return a2 / (PI * denom * denom);
            }

            float geometry_schlick_ggx(float NdotV, float roughness) {
                float r = roughness + 1.0;
                float k = r * r / 8.0;
                return NdotV / (NdotV * (1.0 - k) + k);
            }

            float geometry_smith(vec3 N, vec3 V, vec3 L, float roughness) {
                float NdotV = max(dot(N, V), 0.0);
                float NdotL = max(dot(N, L), 0.0);
                return geometry_schlick_ggx(NdotV, roughness) * geometry_schlick_ggx(NdotL, roughness);
            }

            vec3 fresnel_schlick(float cos_theta, vec3 F0) {
                return F0 + (1.0 - F0) * pow(clamp(1.0 - cos_theta, 0.0, 1.0), 5.0);
            }

            vec3 calc_light_pbr(Light light, vec3 N, vec3 V, vec3 albedo, float roughness, float metallic, vec3 F0, float shadow_factor) {
                vec3 light_dir;
                float attenuation = 1.0;
                if (light.type == 0) {
                    light_dir = normalize(-light.direction);
                } else {
                    vec3 to_light = light.position - v_world_pos;
                    float dist = length(to_light);
                    light_dir = normalize(to_light);
                    attenuation = clamp(1.0 - dist / light.range, 0.0, 1.0);
                    attenuation *= attenuation;
                    if (light.type == 2) {
                        float theta = dot(light_dir, normalize(-light.direction));
                        float inner = cos(radians(light.spot_inner_angle));
                        float outer = cos(radians(light.spot_angle));
                        float eps = inner - outer;
                        attenuation *= clamp((theta - outer) / eps, 0.0, 1.0);
                    }
                }
                vec3 L = light_dir;
                float NdotL = max(dot(N, L), 0.0);
                vec3 H = normalize(V + L);
                vec3 radiance = light.color * light.intensity * attenuation * shadow_factor;
                vec3 F = fresnel_schlick(max(dot(H, V), 0.0), F0);
                float NDF = distribution_ggx(N, H, roughness);
                float G = geometry_smith(N, V, L, roughness);
                vec3 kS = F;
                vec3 kD = (1.0 - kS) * (1.0 - metallic);
                vec3 numerator = NDF * G * F;
                float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
                vec3 specular = numerator / denominator;
                vec3 diffuse = kD * albedo / PI;
                return (diffuse + specular) * radiance * NdotL;
            }

            vec3 get_normal_from_map() {
                vec3 tangent_normal = texture(_NormalMap, v_uv).rgb * 2.0 - 1.0;
                vec3 N = normalize(v_normal);
                vec3 T = normalize(dFdx(v_world_pos));
                vec3 B = normalize(cross(N, T));
                return normalize(T * tangent_normal.x + B * tangent_normal.y + N * tangent_normal.z);
            }

            void main() {
                vec3 albedo = _BaseColor.rgb;
                if (_BaseMap_Active == 1) {
                    vec4 texColor = texture(_BaseMap, v_uv);
                    albedo *= texColor.rgb;
                }
                vec3 N = normalize(v_normal);
                if (_NormalMap_Active == 1) {
                    N = get_normal_from_map();
                }
                float roughness = 1.0 - _Smoothness;
                roughness = max(roughness, 0.001);
                float metallic = _Metallic;
                vec3 F0 = mix(vec3(0.04), albedo, metallic);
                vec3 V = normalize(u_camera_pos - v_world_pos);
                float occlusion = 1.0;
                if (_OcclusionMap_Active == 1) {
                    occlusion = texture(_OcclusionMap, v_uv).r;
                    occlusion = mix(1.0, occlusion, _OcclusionStrength);
                }
                vec3 result = u_ambient * albedo * occlusion;
                float shadow_factor = compute_shadow();
                float point_shadow_factor = compute_point_shadow();
                float spot_shadow_factor = compute_spot_shadow();
                for (int i = 0; i < u_light_count && i < MAX_LIGHTS; i++) {
                    float sf = 1.0;
                    if (i == u_shadow_light_index) sf = min(sf, shadow_factor);
                    if (i == u_point_shadow_light_index) sf = min(sf, point_shadow_factor);
                    if (i == u_spot_shadow_light_index) sf = min(sf, spot_shadow_factor);
                    result += calc_light_pbr(u_lights[i], N, V, albedo, roughness, metallic, F0, sf);
                }
                vec3 emission = _EmissionColor * _EmissionIntensity;
                result += emission;
                result = result / (result + vec3(1.0));
                result = pow(result, vec3(1.0 / 2.2));
                frag_color = vec4(result, _BaseColor.a);
            }
            ENDGLSL
        }
    }
}
