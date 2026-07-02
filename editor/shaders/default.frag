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
    vec3 right;
    vec3 up;
    float area_width;
    float area_height;
    int area_type;
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
uniform sampler2D u_area_shadow_map;
uniform mat4 u_area_light_vp;
uniform float u_area_light_size;
uniform float u_area_light_fov_scale;
uniform vec2 u_area_light_near_far;
uniform int u_area_shadow_light_index;
float hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float sample_shadow(sampler2D shadow_map, vec3 proj_coords) {
    float current_depth = proj_coords.z - u_shadow_bias;
    float result = 0.0;
    vec2 texel_size = 1.0 / vec2(textureSize(shadow_map, 0));
    float radius = 0.75;
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
            float pcf_depth = texture(shadow_map, proj_coords.xy + vec2(x, y) * texel_size * radius).r;
            result += (current_depth > pcf_depth ? 1.0 : 0.0) * weight;
            weight_sum += weight;
        }
    }
    float lit = 1.0 - result / weight_sum;
    return smoothstep(0.12, 0.88, lit);
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
float area_pcss(sampler2D shadow_map, vec3 proj_coords, float z_view) {
    vec2 texel_size = 1.0 / vec2(textureSize(shadow_map, 0));
    float z_ndc = proj_coords.z;
    float near_z = u_area_light_near_far.x;
    float far_z = u_area_light_near_far.y;
    float a = hash(gl_FragCoord.xy) * 6.2831853;
    float ca = cos(a);
    float sa = sin(a);
    float proj_light_size = u_area_light_size * u_area_light_fov_scale / max(z_view, 0.001);
    float search_step = max(proj_light_size * 0.25, texel_size.x * 2.0);
    float blocker_sum = 0.0;
    float blocker_count = 0.0;
    for (int x = -2; x <= 2; x++) {
        for (int y = -2; y <= 2; y++) {
            vec2 off = vec2(float(x), float(y));
            vec2 rot = vec2(off.x * ca - off.y * sa, off.x * sa + off.y * ca);
            vec2 uv = proj_coords.xy + rot * search_step;
            float d = texture(shadow_map, uv).r;
            if (d < z_ndc - u_shadow_bias) {
                blocker_sum += d;
                blocker_count += 1.0;
            }
        }
    }
    if (blocker_count < 1.0) return 1.0;
    float avg_blocker_ndc = blocker_sum / blocker_count;
    float avg_blocker_z = 2.0 * near_z * far_z / max(far_z + near_z - (avg_blocker_ndc * 2.0 - 1.0) * (far_z - near_z), 0.001);
    float penumbra_world = u_area_light_size * (z_view - avg_blocker_z) / max(avg_blocker_z, 0.001);
    float proj_penumbra = penumbra_world * u_area_light_fov_scale / max(z_view, 0.001);
    proj_penumbra = max(proj_penumbra, texel_size.x);
    float filter_texels = proj_penumbra / texel_size.x;
    int k = clamp(int(filter_texels * 0.3), 2, 9);
    float pcf_step = proj_penumbra / max(float(k + k), 1.0);
    float result = 0.0;
    float wsum = 0.0;
    for (int x = -k; x <= k; x++) {
        for (int y = -k; y <= k; y++) {
            float w = 1.0;
            if (x == 0) w += 1.0;
            if (y == 0) w += 1.0;
            vec2 off = vec2(float(x), float(y));
            vec2 rot = vec2(off.x * ca - off.y * sa, off.x * sa + off.y * ca);
            vec2 uv = proj_coords.xy + rot * pcf_step;
            float d = texture(shadow_map, uv).r;
            result += (z_ndc - u_shadow_bias > d ? 1.0 : 0.0) * w;
            wsum += w;
        }
    }
    float shadow = 1.0 - result / max(wsum, 1.0);
    return smoothstep(0.05, 0.65, shadow);
}
float compute_area_shadow() {
    if (u_area_shadow_light_index < 0) return 1.0;
    vec4 light_space_pos = u_area_light_vp * vec4(v_world_pos, 1.0);
    vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
    proj_coords = proj_coords * 0.5 + 0.5;
    if (any(lessThan(proj_coords, vec3(0.0))) || any(greaterThan(proj_coords, vec3(1.0)))) return 1.0;
    float z_ndc = proj_coords.z * 2.0 - 1.0;
    float near_z = u_area_light_near_far.x;
    float far_z = u_area_light_near_far.y;
    float z_view = 2.0 * near_z * far_z / max(far_z + near_z - z_ndc * (far_z - near_z), 0.001);
    return area_pcss(u_area_shadow_map, proj_coords, z_view);
}
float projected_solid_angle(vec3 verts[4], vec3 n) {
    vec3 clipped[8];
    int cnt = 0;
    for (int i = 0; i < 4; i++) {
        vec3 a = verts[i];
        vec3 b = verts[(i + 1) % 4];
        float da = dot(a, n);
        float db = dot(b, n);
        if (da > 0.0) {
            clipped[cnt] = a;
            cnt++;
        }
        if ((da > 0.0) != (db > 0.0)) {
            float t = da / max(da - db, 1e-8);
            vec3 inter = normalize(a + t * (b - a));
            clipped[cnt] = inter;
            cnt++;
        }
    }
    if (cnt < 3) return 0.0;
    float sum = 0.0;
    for (int i = 0; i < cnt; i++) {
        vec3 a = clipped[i];
        vec3 b = clipped[(i + 1) % cnt];
        float ang = acos(clamp(dot(a, b), -1.0, 1.0));
        vec3 e = normalize(cross(a, b));
        sum += ang * max(0.0, dot(e, n));
    }
    return sum * 0.5;
}
vec3 calc_area_light(Light light, vec3 normal, vec3 view_dir, vec3 albedo) {
    vec3 right = light.right;
    vec3 up = light.up;
    float hw = light.area_width * 0.5;
    float hh = light.area_height * 0.5;
    vec3 c = light.position;
    vec3 verts[4];
    verts[0] = c - right * hw - up * hh;
    verts[1] = c + right * hw - up * hh;
    verts[2] = c + right * hw + up * hh;
    verts[3] = c - right * hw + up * hh;
    vec3 tangent = normalize(cross(normal, abs(normal.y) < 0.999 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
    vec3 bitangent = cross(normal, tangent);
    vec3 ts_verts[4];
    for (int i = 0; i < 4; i++) {
        vec3 d = verts[i] - v_world_pos;
        ts_verts[i] = normalize(vec3(dot(d, tangent), dot(d, bitangent), dot(d, normal)));
    }
    float ff = projected_solid_angle(ts_verts, vec3(0.0, 0.0, 1.0));
    vec3 diffuse = (ff / PI) * albedo * light.color * light.intensity;
    vec3 specular = vec3(0.0);
    vec3 ref = reflect(-view_dir, normal);
    float denom = dot(ref, -light.direction);
    if (denom > 0.0) {
        float t = dot(c - v_world_pos, -light.direction) / denom;
        vec3 hit = v_world_pos + ref * t;
        vec3 local = hit - c;
        float u = clamp(dot(local, right) / hw, -1.0, 1.0);
        float v = clamp(dot(local, up) / hh, -1.0, 1.0);
        vec3 rep = c + right * u * hw + up * v * hh;
        vec3 to_rep = rep - v_world_pos;
        float d = length(to_rep);
        vec3 ld = to_rep / d;
        vec3 h = normalize(ld + view_dir);
        float sp = pow(max(dot(normal, h), 0.0), max(1.0, u_smoothness * 128.0));
        float att = clamp(1.0 - d / light.range, 0.0, 1.0);
        att *= att;
        specular = sp * light.color * light.intensity * u_metallic * att;
    }
    return diffuse + specular;
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
        if (u_lights[i].type == 3) {
            float area_sf = 1.0;
            if (i == u_area_shadow_light_index) area_sf = compute_area_shadow();
            result += calc_area_light(u_lights[i], normal, view_dir, albedo) * area_sf;
        } else {
            result += calc_light(u_lights[i], normal, view_dir, albedo, sf);
        }
    }
    result += u_emission;
    frag_color = vec4(result, u_albedo_color.a);
}
