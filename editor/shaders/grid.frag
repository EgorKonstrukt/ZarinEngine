#version 460 core
in vec3 v_world_pos;
out vec4 frag_color;
uniform vec3 u_camera_pos;
uniform float u_grid_size;
uniform float u_grid_2d;
uniform sampler2D u_scene_depth;
uniform vec2 u_viewport_size;

void main() {
    vec2 screen_uv = gl_FragCoord.xy / u_viewport_size;
    float stored_depth = texture(u_scene_depth, screen_uv).r;
    if (stored_depth < gl_FragCoord.z - 0.0001) discard;

    vec2 pos2d;
    vec2 cam_offset;
    if (u_grid_2d > 0.5) {
        pos2d = v_world_pos.xy;
        cam_offset = u_camera_pos.xy;
    } else {
        pos2d = v_world_pos.xz;
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

    vec2 majorPos = pos / 10.0;
    vec2 majorFw = max(fwidth(majorPos), vec2(2e-5));
    vec2 majorCoord = abs(fract(majorPos - 0.5) - 0.5) / majorFw;
    float majorLine = min(majorCoord.x, majorCoord.y);
    float majorAlpha = 1.0 - smoothstep(0.0, 1.0, majorLine);

    vec2 superPos = pos / 50.0;
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
