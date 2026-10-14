# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
SVGF_ATROUS_FRAG = """
\x23version 330 core
uniform sampler2D u_color;
uniform sampler2D u_depth;
uniform sampler2D u_moment;
uniform vec2 u_pixel;
uniform float u_step_size;
uniform float u_phi_depth;
uniform float u_phi_normal;
uniform float u_phi_luma;
in vec2 v_uv;
out vec4 frag_color;

float svgf_luma(vec3 c) {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

vec3 svgf_normal_from_depth(vec2 uv, float d0) {
    vec2 texel = vec2(1.0) / max(vec2(textureSize(u_depth, 0)), vec2(1.0));
    float dx = texture(u_depth, uv + vec2(texel.x, 0.0)).r - texture(u_depth, uv - vec2(texel.x, 0.0)).r;
    float dy = texture(u_depth, uv + vec2(0.0, texel.y)).r - texture(u_depth, uv - vec2(0.0, texel.y)).r;
    vec3 n = normalize(vec3(-dx, -dy, 0.02));
    return n;
}

void main() {
    vec3 c_center = texture(u_color, v_uv).rgb;
    float d_center = texture(u_depth, v_uv).r;
    float luma_center = svgf_luma(c_center);

    vec2 moment_center = texture(u_moment, v_uv).rg;
    float variance = max(moment_center.g - moment_center.r * moment_center.r, 0.0);

    vec3 n_center = svgf_normal_from_depth(v_uv, d_center);

    float sigma_luma = u_phi_luma * sqrt(variance + 1e-6);
    float w_total = 1.0;
    vec3 result = c_center;

    float kernel[5];
    kernel[0] = 1.0 / 16.0;
    kernel[1] = 4.0 / 16.0;
    kernel[2] = 6.0 / 16.0;
    kernel[3] = 4.0 / 16.0;
    kernel[4] = 1.0 / 16.0;

    for (int x = -2; x <= 2; x++) {
        for (int y = -2; y <= 2; y++) {
            if (x == 0 && y == 0) continue;
            vec2 ouv = v_uv + vec2(float(x), float(y)) * u_pixel * u_step_size;
            ouv = clamp(ouv, vec2(0.0), vec2(1.0));

            vec3 c_sample = texture(u_color, ouv).rgb;
            float d_sample = texture(u_depth, ouv).r;
            float luma_sample = svgf_luma(c_sample);

            float w_depth = exp(-abs(d_center - d_sample) / (u_phi_depth * abs(d_center) + 1e-4));
            float w_luma = exp(-abs(luma_center - luma_sample) / (sigma_luma + 1e-4));

            vec3 n_sample = svgf_normal_from_depth(ouv, d_sample);
            float w_normal = pow(max(dot(n_center, n_sample), 0.0), u_phi_normal);

            int ix = x + 2;
            int iy = y + 2;
            float w_kernel = kernel[ix] * kernel[iy];
            float w = w_kernel * w_depth * w_luma * w_normal;

            result += w * c_sample;
            w_total += w;
        }
    }

    frag_color = vec4(result / w_total, luma_center);
}
"""
