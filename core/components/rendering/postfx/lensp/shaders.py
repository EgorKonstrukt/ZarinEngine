# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

FLARE_VERT = """
\x23version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

EXTRACT_FRAG = """
\x23version 330 core
uniform sampler2D u_scene_color;
uniform float u_threshold;
uniform float u_soft_threshold;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    vec3 c = texture(u_scene_color, v_uv).rgb;
    float lum = dot(c, vec3(0.299, 0.587, 0.114));
    float knee = u_threshold * u_soft_threshold;
    float soft = lum - u_threshold + knee;
    soft = clamp(soft, 0.0, 2.0 * knee);
    soft = soft * soft / (4.0 * knee + 0.0001);
    float bright = max(lum - u_threshold, soft);
    frag_color = vec4(c * (bright / max(lum, 0.0001)), 1.0);
}
"""

DOWNSAMPLE_FRAG = """
\x23version 330 core
uniform sampler2D u_src;
uniform vec2 u_texel;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    vec2 h = u_texel * 0.5;
    vec3 c0 = texture(u_src, v_uv + vec2(-h.x, -h.y)).rgb;
    vec3 c1 = texture(u_src, v_uv + vec2( h.x, -h.y)).rgb;
    vec3 c2 = texture(u_src, v_uv + vec2(-h.x,  h.y)).rgb;
    vec3 c3 = texture(u_src, v_uv + vec2( h.x,  h.y)).rgb;
    frag_color = vec4((c0 + c1 + c2 + c3) * 0.25, 1.0);
}
"""

FLARE_FRAG = """
\x23version 330 core
const int GHOSTS = 7;

uniform sampler2D u_bright_tex;
uniform sampler2D u_glow_tex;
uniform vec2 u_texel;
uniform float u_intensity;
uniform float u_scale;
uniform float u_glow;
uniform float u_ghost_intensity;
uniform float u_anamorphic;
uniform float u_chromatic;

in vec2 v_uv;
out vec4 frag_color;

// Ghost train: each element is the bright map re-sampled around the screen
// center at scale s = 1 / a (a = position multiplier along the center-light
// axis), so bright regions are ghosted as continuous scaled copies -- no
// discrete light detection, exactly like a bloom downsample chain.
const float G_A[GHOSTS] = float[]( 1.5,  1.0,  0.5,  0.25,  0.10, -0.5, -1.0 );
const float G_W[GHOSTS] = float[]( 0.14, 0.30, 0.40, 0.25,  0.16, 0.12, 0.08 );
const float G_TEX[GHOSTS] = float[]( 0.0,  1.0,  0.0,  1.0,   1.0,  0.0,  1.0 );
const vec3 G_T[GHOSTS] = vec3[](
    vec3(1.00, 0.97, 0.90),
    vec3(1.00, 0.98, 0.92),
    vec3(1.00, 0.93, 0.80),
    vec3(0.92, 0.97, 1.00),
    vec3(0.90, 0.98, 1.00),
    vec3(1.00, 0.92, 0.80),
    vec3(0.94, 0.96, 1.00)
);

float edge_fade(vec2 coord) {
    return smoothstep(0.0, 0.03, coord.x) * (1.0 - smoothstep(0.97, 1.0, coord.x))
         * smoothstep(0.0, 0.03, coord.y) * (1.0 - smoothstep(0.97, 1.0, coord.y));
}

vec3 sample_ghost(float s, float tint_w) {
    vec2 c = vec2(0.5, 0.5);
    vec2 coord = c + (v_uv - c) * s;
    float fade = edge_fade(coord);
    vec2 pc = clamp(coord, vec2(0.001), vec2(0.999));
    return texture(u_bright_tex, pc).rgb * fade * tint_w;
}

vec3 sample_ghost_chrom(float s, float dc) {
    vec2 c = vec2(0.5, 0.5);
    vec2 cr = c + (v_uv - c) * (s + dc);
    vec2 cg = c + (v_uv - c) * s;
    vec2 cb = c + (v_uv - c) * (s - dc);
    float fr = edge_fade(cr);
    float fg = edge_fade(cg);
    float fb = edge_fade(cb);
    vec3 col;
    col.r = texture(u_bright_tex, clamp(cr, vec2(0.001), vec2(0.999))).r * fr;
    col.g = texture(u_bright_tex, clamp(cg, vec2(0.001), vec2(0.999))).g * fg;
    col.b = texture(u_bright_tex, clamp(cb, vec2(0.001), vec2(0.999))).b * fb;
    return col;
}

void main() {
    vec3 acc = vec3(0.0);

    // Glow: the bloom-style wide soft pass at identity position.
    vec3 glow_col = texture(u_glow_tex, v_uv).rgb;
    acc += glow_col * u_glow * vec3(1.0, 0.99, 0.97);

    // Ghost train with a light chromatic split on the main warm ghosts.
    float dc = u_chromatic * 0.02;
    for (int i = 0; i < GHOSTS; i++) {
        float s = 1.0 / G_A[i];
        float w = G_W[i] * u_ghost_intensity;
        vec3 col;
        if (i == 2 || i == 3 || i == 5) {
            col = sample_ghost_chrom(s, dc);
        } else {
            col = sample_ghost(s, 1.0);
        }
        acc += col * G_T[i] * w;
    }

    // Anamorphic streak: horizontal gaussian smear of the bright pass.
    if (u_anamorphic > 0.001) {
        vec3 st = vec3(0.0);
        float wsum = 0.0;
        for (int k = -6; k <= 6; k++) {
            float kk = float(k);
            vec2 p = v_uv + vec2(kk * 1.5 * u_texel.x, 0.0);
            vec3 tc = texture(u_glow_tex, clamp(p, vec2(0.0), vec2(1.0))).rgb;
            float wgt = exp(-(kk * kk) / (2.0 * 4.0));
            st += tc * wgt;
            wsum += wgt;
        }
        acc += st / wsum * u_anamorphic;
    }

    frag_color = vec4(max(acc * u_intensity * u_scale, vec3(0.0)), 1.0);
}
"""
