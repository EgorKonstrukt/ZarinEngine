#version 460 core
in vec3 v_world_pos;
out vec4 frag_color;
uniform vec3 u_camera_pos;
uniform float u_grid_size;
uniform float u_grid_alpha_minor;
uniform float u_grid_alpha_major;
uniform float u_grid_alpha_super;
uniform float u_grid_step_major;
uniform float u_grid_step_super;
uniform float u_grid_2d;
uniform float u_grid_opacity;
uniform sampler2D u_scene_color;
uniform vec2 u_viewport_size;

float grid_line(vec2 pos, float spacing, float width) {
    vec2 p = pos / spacing;
    vec2 fw = max(fwidth(p), vec2(1e-5));
    vec2 c = abs(fract(p) - 0.5) / fw;
    return 1.0 - smoothstep(0.0, width, min(c.x, c.y));
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_viewport_size;

    vec2 pos;
    vec2 cam;
    if (u_grid_2d > 0.5) {
        pos = v_world_pos.xy;
        cam = u_camera_pos.xy;
    } else {
        pos = v_world_pos.xz;
        cam = u_camera_pos.xz;
    }

    float dist = length(pos - cam);
    float fade_end = max(u_grid_size * 80.0, 100.0);
    float fade = 1.0 - smoothstep(u_grid_size * 4.0, fade_end, dist);
    if (fade < 0.01) discard;

    float spacing = max(u_grid_size, 1e-5);
    float minor = grid_line(pos, spacing, 1.5) * u_grid_alpha_minor;
    float major = grid_line(pos, spacing * u_grid_step_major, 2.5) * u_grid_alpha_major;
    float super = grid_line(pos, spacing * u_grid_step_super, 4.0) * u_grid_alpha_super;

    vec3 bg = texture(u_scene_color, uv).rgb;
    float bg_lum = dot(bg, vec3(0.299, 0.587, 0.114));
    float dark_mix = smoothstep(0.25, 0.65, bg_lum);

    vec3 grid_base;
    float alpha;
    if (super > major && super > minor) {
        grid_base = mix(vec3(0.95), vec3(0.02), dark_mix);
        alpha = super;
    } else if (major > minor) {
        grid_base = mix(vec3(0.85), vec3(0.06), dark_mix);
        alpha = major;
    } else {
        grid_base = mix(vec3(0.55), vec3(0.20), dark_mix);
        alpha = minor;
    }

    float axis_len = spacing * 8.0;
    bool near_origin = dist < axis_len * 2.0;

    float x_aa = (1.0 - smoothstep(0.0, fwidth(pos.x) * 3.0, abs(pos.x)))
               * (1.0 - smoothstep(0.0, axis_len, abs(pos.y))) * 0.7;

    float z_aa = (1.0 - smoothstep(0.0, fwidth(pos.y) * 3.0, abs(pos.y)))
               * (1.0 - smoothstep(0.0, axis_len, abs(pos.x))) * 0.7;

    if (near_origin) {
        vec3 axis_col = mix(vec3(0.05, 0.05, 0.05), vec3(0.95, 0.95, 0.95), dark_mix);
        vec3 x_c = mix(axis_col, vec3(1.0, 0.2, 0.2), 1.0 - dark_mix);
        vec3 z_c = mix(axis_col, vec3(0.2, 0.4, 1.0), 1.0 - dark_mix);

        if (x_aa > z_aa) {
            grid_base = mix(grid_base, x_c, x_aa / max(x_aa + alpha, 0.001));
            alpha = max(alpha, x_aa);
        }
        if (z_aa > x_aa) {
            grid_base = mix(grid_base, z_c, z_aa / max(z_aa + alpha, 0.001));
            alpha = max(alpha, z_aa);
        }
    }

    frag_color = vec4(grid_base, alpha * fade * u_grid_opacity);
}
