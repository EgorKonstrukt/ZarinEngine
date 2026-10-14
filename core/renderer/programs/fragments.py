# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

PP_COPY_FRAG = "\n" + chr(35) + """version 330 core
uniform sampler2D u_input_tex;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    frag_color = vec4(texture(u_input_tex, v_uv).rgb, 1.0);
}
"""

PP_TONEMAP_FRAG = "\n" + chr(35) + """version 330 core
uniform sampler2D u_input_tex;
uniform float u_exposure;
in vec2 v_uv;
out vec4 frag_color;
vec3 tonemap_aces(vec3 c) {
    float a = 2.51;
    float b = 0.03;
    float c_ = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((c * (a * c + b)) / (c * (c_ * c + d) + e), 0.0, 1.0);
}
void main() {
    vec3 color = texture(u_input_tex, v_uv).rgb;
    color *= exp2(u_exposure);
    color = tonemap_aces(color);
    frag_color = vec4(color, 1.0);
}
"""

VELOCITY_FRAG = "\n" + chr(35) + """version 330 core
uniform sampler2D u_depth_tex;
uniform mat4 u_inv_view_proj;
uniform mat4 u_prev_view_proj;
uniform vec2 u_pixel_size;
in vec2 v_uv;
out vec2 frag_velocity;
void main() {
    float depth = texture(u_depth_tex, v_uv).r;
    if (depth >= 0.99999) {
        frag_velocity = vec2(0.0);
        return;
    }
    vec4 clip_pos = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 world_pos = u_inv_view_proj * clip_pos;
    world_pos /= world_pos.w;
    vec4 prev_clip = u_prev_view_proj * world_pos;
    vec2 prev_uv = prev_clip.xy / prev_clip.w * 0.5 + 0.5;
    vec2 velocity = v_uv - prev_uv;
    if (isnan(velocity.x) || isnan(velocity.y) || isinf(velocity.x) || isinf(velocity.y)) {
        frag_velocity = vec2(0.0);
        return;
    }
    float max_v = 64.0 * max(u_pixel_size.x, u_pixel_size.y);
    velocity = clamp(velocity, -vec2(max_v), vec2(max_v));
    frag_velocity = velocity;
}
"""

VELOCITY_GEOM_VERT = "\n" + chr(35) + """version 330 core
in vec3 in_position;
uniform mat4 u_view_proj;
uniform mat4 u_prev_view_proj;
uniform mat4 u_model;
uniform mat4 u_prev_model;
out vec2 v_velocity;
void main() {
    vec4 cur_clip = u_view_proj * u_model * vec4(in_position, 1.0);
    vec4 prev_clip = u_prev_view_proj * u_prev_model * vec4(in_position, 1.0);
    vec2 cur_ndc = cur_clip.xy / cur_clip.w;
    vec2 prev_ndc = prev_clip.xy / prev_clip.w;
    v_velocity = (prev_ndc - cur_ndc) * 0.5;
    gl_Position = cur_clip;
}
"""

VELOCITY_GEOM_FRAG = "\n" + chr(35) + """version 330 core
in vec2 v_velocity;
out vec2 frag_velocity;
void main() {
    vec2 vel = v_velocity;
    if (isnan(vel.x) || isnan(vel.y) || isinf(vel.x) || isinf(vel.y))
        vel = vec2(0.0);
    frag_velocity = vel;
}
"""
