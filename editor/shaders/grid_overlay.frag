#version 460 core
uniform sampler2D u_depth_tex;
uniform vec3 u_camera_pos;
uniform float u_grid_size;
uniform float u_grid_step_major;
uniform float u_grid_step_super;
uniform float u_grid_2d;
uniform vec3 u_view_dir;
uniform mat4 u_inv_vp;
in vec2 v_uv;
out vec4 frag_color;

void main() {
    float depth = texture(u_depth_tex, v_uv).r;
    if (depth < 1.0) discard;

    vec4 clip_pos = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 world_pos4 = u_inv_vp * clip_pos;
    vec3 world_pos = world_pos4.xyz / world_pos4.w;

    vec2 pos2d;
    vec2 cam_offset;
    if (u_grid_2d > 0.5) {
        pos2d = world_pos.xy;
        cam_offset = u_camera_pos.xy;
    } else {
        pos2d = world_pos.xz;
        cam_offset = u_camera_pos.xz;
    }

    vec2 offset = pos2d - cam_offset;
    float dist = length(offset);
    float fadeStart = max(u_grid_size * 5.0, 20.0);
    float fadeEnd = max(u_grid_size * 50.0, 100.0);
    float fade = 1.0 - smoothstep(fadeStart, fadeEnd, dist);

    vec2 pos = pos2d / u_grid_size;

    vec2 fw = max(fwidth(pos), vec2(2e-5));
    vec2 coord = abs(fract(pos - 0.5) - 0.5) / fw;
    float minorLine = min(coord.x, coord.y);
    float minorAlpha = 1.0 - smoothstep(0.0, 1.0, minorLine);

    vec2 majorPos = pos / u_grid_step_major;
    vec2 majorFw = max(fwidth(majorPos), vec2(2e-5));
    vec2 majorCoord = abs(fract(majorPos - 0.5) - 0.5) / majorFw;
    float majorLine = min(majorCoord.x, majorCoord.y);
    float majorAlpha = 1.0 - smoothstep(0.0, 1.0, majorLine);

    vec2 superPos = pos / u_grid_step_super;
    vec2 superFw = max(fwidth(superPos), vec2(2e-5));
    vec2 superCoord = abs(fract(superPos - 0.5) - 0.5) / superFw;
    float superLine = min(superCoord.x, superCoord.y);
    float superAlpha = 1.0 - smoothstep(0.0, 1.0, superLine);

    vec3 color;
    float alpha;
    if (superAlpha > minorAlpha && superAlpha > majorAlpha) {
        color = vec3(0.7, 0.7, 0.7);
        alpha = superAlpha * 0.9;
    } else if (majorAlpha > minorAlpha) {
        color = vec3(0.6, 0.6, 0.6);
        alpha = majorAlpha * 0.7;
    } else {
        color = vec3(0.5, 0.5, 0.5);
        alpha = minorAlpha * 0.5;
    }

    frag_color = vec4(color, alpha * fade);
}
