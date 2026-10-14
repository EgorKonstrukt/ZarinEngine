# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import numpy as np


NP_RNG = np.random.RandomState(42)


def _generate_kernel(count: int) -> list[np.ndarray]:
    kernel = []
    for i in range(count):
        theta = NP_RNG.uniform(0, 2 * np.pi)
        phi = NP_RNG.uniform(0, np.pi * 0.5)
        x = np.sin(phi) * np.cos(theta)
        y = np.sin(phi) * np.sin(theta)
        z = np.cos(phi)
        v = np.array([x, y, z])
        scale = i / count
        v *= 0.1 + 0.9 * scale * scale
        kernel.append(v)
    return kernel


def _kernel_glsl(kernel: list[np.ndarray]) -> str:
    parts = []
    for v in kernel:
        parts.append(f"    vec3({v[0]:.6f}, {v[1]:.6f}, {v[2]:.6f})")
    return ",\n".join(parts)


SSAO_VERT = """
\x23version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""


def _build_ao_frag(kernel_size: int) -> str:
    kernel = _generate_kernel(kernel_size)
    k_glsl = _kernel_glsl(kernel)
    return f"""\x23version 330 core
uniform sampler2D u_depth_tex;
uniform sampler2D u_noise_tex;
uniform mat4 u_proj;
uniform mat4 u_inv_proj;
uniform vec2 u_pixel_size;
uniform vec2 u_resolution;
uniform float u_radius;
uniform float u_power;
uniform float u_bias;

in vec2 v_uv;
out float frag_ao;

const int MAX_K = {kernel_size};
const vec3 KERNEL[MAX_K] = vec3[MAX_K](
{k_glsl}
);

vec3 view_pos(vec2 uv, float depth) {{
    vec4 ndc = vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 v = u_inv_proj * ndc;
    return v.xyz / v.w;
}}

vec3 view_normal(vec2 uv) {{
    float d = texture(u_depth_tex, uv).r;
    vec3 c = view_pos(uv, d);
    vec2 off = u_pixel_size;
    vec3 r = view_pos(uv + vec2(off.x, 0.0), texture(u_depth_tex, uv + vec2(off.x, 0.0)).r);
    vec3 u = view_pos(uv + vec2(0.0, off.y), texture(u_depth_tex, uv + vec2(0.0, off.y)).r);
    return normalize(cross(r - c, u - c));
}}

void main() {{
    float depth = texture(u_depth_tex, v_uv).r;
    if (depth >= 1.0) {{
        frag_ao = 1.0;
        return;
    }}
    vec3 pos = view_pos(v_uv, depth);
    vec3 normal = view_normal(v_uv);
    vec3 random = texture(u_noise_tex, v_uv * u_resolution / 4.0).xyz;
    vec3 tangent = normalize(random - normal * dot(random, normal));
    vec3 bitangent = cross(normal, tangent);
    mat3 tbn = mat3(tangent, bitangent, normal);
    float occlusion = 0.0;
    for (int i = 0; i < MAX_K; i++) {{
        vec3 sample_pos = tbn * KERNEL[i];
        sample_pos = pos + sample_pos * u_radius;
        vec4 offset = u_proj * vec4(sample_pos, 1.0);
        offset.xyz /= offset.w;
        vec2 uv = offset.xy * 0.5 + 0.5;
        if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) continue;
        float sample_depth = texture(u_depth_tex, uv).r;
        vec3 sample_pos_check = view_pos(uv, sample_depth);
        float range_check = smoothstep(0.0, 1.0, u_radius / abs(pos.z - sample_pos_check.z + 0.001));
        occlusion += step(sample_pos_check.z + u_bias, sample_pos.z) * range_check;
    }}
    float ao = 1.0 - (occlusion / float(MAX_K));
    ao = pow(max(ao, 0.0), u_power);
    frag_ao = ao;
}}
"""


COMP_FRAG = """
\x23version 330 core
uniform sampler2D u_input_tex;
uniform sampler2D u_ao_tex;
uniform sampler2D u_depth_tex;
uniform vec2 u_pixel_size;
uniform float u_bilateral_sigma;
uniform float u_intensity;
uniform float u_bilateral_radius;

in vec2 v_uv;
out vec4 frag_color;

void main() {
    vec3 scene_color = texture(u_input_tex, v_uv).rgb;
    float center_ao = texture(u_ao_tex, v_uv).r;
    float center_depth = texture(u_depth_tex, v_uv).r;
    float ao_sum = center_ao;
    float weight_sum = 1.0;
    int r = int(min(u_bilateral_radius, 6.0));
    for (int y = -6; y <= 6; y++) {
        if (abs(y) > r) continue;
        for (int x = -6; x <= 6; x++) {
            if (abs(x) > r) continue;
            if (x == 0 && y == 0) continue;
            vec2 uv = v_uv + vec2(float(x), float(y)) * u_pixel_size;
            if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) continue;
            float d = texture(u_depth_tex, uv).r;
            float depth_w = exp(-abs(d - center_depth) * u_bilateral_sigma);
            float spatial_w = exp(-float(x*x + y*y) / 4.5);
            float w = depth_w * spatial_w;
            ao_sum += texture(u_ao_tex, uv).r * w;
            weight_sum += w;
        }
    }
    float ao = ao_sum / weight_sum;
    ao = mix(1.0, ao, u_intensity);
    frag_color = vec4(scene_color * ao, 1.0);
}
"""
