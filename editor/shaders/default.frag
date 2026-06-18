#version 330 core
#define MAX_LIGHTS 8
#define CASCADE_COUNT 3
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
            float pcf_depth = texture(shadow_map, proj_coords.xy + vec2(x, y) * texel_size * 4.0).r;
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
    if (proj_coords.z < 0.0 || proj_coords.z > 1.0) return 1.0;
    vec2 border = 1.0 - abs(proj_coords.xy - 0.5) * 2.0;
    float fade = clamp(border.x * border.y * 20.0, 0.0, 1.0);
    float shadow;
    if (cascade_idx == 0) shadow = sample_shadow(u_shadow_map_0, proj_coords);
    else if (cascade_idx == 1) shadow = sample_shadow(u_shadow_map_1, proj_coords);
    else shadow = sample_shadow(u_shadow_map_2, proj_coords);
    return mix(1.0, shadow, fade);
}
float compute_point_shadow() {
    if (u_point_shadow_count <= 0) return 1.0;
    vec3 dir = v_world_pos - u_point_light_pos;
    vec3 abs_dir = abs(dir);
    int face = 0;
    if (abs_dir.x >= abs_dir.y && abs_dir.x >= abs_dir.z) {
        face = dir.x >= 0 ? 0 : 1;
    } else if (abs_dir.y >= abs_dir.z) {
        face = dir.y >= 0 ? 2 : 3;
    } else {
        face = dir.z >= 0 ? 4 : 5;
    }
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
vec3 calc_light(Light light, vec3 normal, vec3 view_dir, vec3 albedo, float shadow_factor) {
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
    if (u_use_albedo_tex == 1) {
        vec4 texColor = texture(u_albedo_tex, v_uv);
        albedo *= texColor.rgb;
    }
    vec3 normal = normalize(v_normal);
    if (u_use_normal_tex == 1) {
        vec3 tangentNormal = texture(u_normal_tex, v_uv).rgb * 2.0 - 1.0;
        normal = normalize(normal + tangentNormal * 0.5);
    }
    float roughness = u_smoothness;
    if (u_use_roughness_tex == 1) {
        float r = texture(u_roughness_tex, v_uv).r;
        roughness = mix(roughness, r, 0.5);
    }
    vec3 view_dir = normalize(u_camera_pos - v_world_pos);
    vec3 result = u_ambient * albedo;
    float shadow_factor = compute_shadow();
    float point_shadow_factor = compute_point_shadow();
    float spot_shadow_factor = compute_spot_shadow();
    for (int i = 0; i < u_light_count && i < MAX_LIGHTS; i++) {
        float sf = 1.0;
        if (i == u_shadow_light_index) sf = min(sf, shadow_factor);
        if (i == u_point_shadow_light_index) sf = min(sf, point_shadow_factor);
        if (i == u_spot_shadow_light_index) sf = min(sf, spot_shadow_factor);
        result += calc_light(u_lights[i], normal, view_dir, albedo, sf);
    }
    result += u_emission;
    frag_color = vec4(result, u_albedo_color.a);
}
