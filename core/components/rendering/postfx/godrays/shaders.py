# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

GOD_RAYS_VERT = """
\x23version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

GOD_RAYS_FRAG = """
\x23version 330 core
uniform sampler2D u_scene_color;
uniform sampler2D u_depth_tex;
uniform vec2 u_light_uv;
uniform vec3 u_light_color;
uniform float u_light_intensity;
uniform float u_intensity;
uniform float u_exposure;
uniform float u_threshold;
uniform int u_num_samples;
in vec2 v_uv;
out vec4 frag_color;

bool uv_valid(vec2 uv) {
    return uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0;
}

void main() {
    if (!uv_valid(u_light_uv)) {
        frag_color = vec4(0.0);
        return;
    }

    // Adaptive threshold: keep only content clearly brighter than the sun's
    // own disc luminance, so the ordinary sky never re-adds itself (which
    // washed the whole screen white) regardless of exposure/sun intensity.
    vec3 sun_col = texture(u_scene_color, u_light_uv).rgb;
    float sun_lum = dot(sun_col, vec3(0.299, 0.587, 0.114));
    float threshold = max(sun_lum * u_threshold, 0.15);

    vec2 dir = u_light_uv - v_uv;
    float dist = length(dir);
    if (dist < 0.0005) {
        frag_color = vec4(0.0);
        return;
    }

    float d0 = texture(u_depth_tex, v_uv).r;
    vec2 delta = dir / float(max(u_num_samples, 1));

    // Per-pixel hash: shift the sample grid by up to half a step so a low
    // sample count reads as soft noise instead of square ray polygons.
    float rnd = fract(sin(dot(floor(v_uv * vec2(1024.0)), vec2(12.9898, 78.233))) * 43758.5453);
    vec2 sample_uv = v_uv + normalize(dir) * ((rnd - 0.5) * length(delta));

    float decay = 0.97;
    float weight = 1.0;
    vec3 accum = vec3(0.0);

    for (int i = 0; i < 128; i++) {
        if (i >= u_num_samples) break;
        sample_uv += delta;
        if (!uv_valid(sample_uv)) break;
        vec2 remaining = u_light_uv - sample_uv;
        if (dot(remaining, delta) < 0.0) break;

        // Geometry clearly closer to the camera than the start surface blocks
        // light: the ray stops there, so rays are occluded by buildings/clouds.
        float ds = texture(u_depth_tex, sample_uv).r;
        float closer = max(d0 - ds, 0.0);
        float occ = 1.0 - smoothstep(0.0, 0.003, closer);
        if (occ < 0.02) break;

        vec3 col = texture(u_scene_color, sample_uv).rgb;
        float lum = dot(col, vec3(0.299, 0.587, 0.114));
        float excess = max(lum - threshold, 0.0);
        if (excess > 0.0) {
            // Soft-knee the brightness so the HDR sun disc / glow stays
            // bounded (no white-out) while retaining a radial falloff.
            float bright = 3.0 * (1.0 - exp(-excess / 3.0));
            // Use the sampled hue only; col * bright would square the HDR
            // luminance and blow the screen out near the sun.
            vec3 chroma = col / max(lum, 1e-4);
            accum += chroma * bright * weight * u_exposure * occ;
        }
        weight *= decay;
    }

    vec3 tint = u_light_color * u_light_intensity;
    frag_color = vec4(max(vec3(0.0), min(accum * u_intensity * tint, vec3(1.0))), 1.0);
}
"""

GODRAYS_COPY_FRAG = """
\x23version 330 core
uniform sampler2D u_scene_color;
uniform sampler2D u_depth_tex;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    frag_color = vec4(texture(u_scene_color, v_uv).rgb, 1.0);
    // A hair below the source depth so every fragment passes the default
    // GL_LESS test against the cleared 1.0; gl_FragDepth is only written when
    // the depth test is enabled, so color and depth land in one pass.
    gl_FragDepth = max(texture(u_depth_tex, v_uv).r - 1e-5, 0.0);
}
"""
