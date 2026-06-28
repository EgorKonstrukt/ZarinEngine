#version 460 core
layout(location = 0) in vec3 a_unit_start;
layout(location = 1) in vec3 a_unit_end;
layout(location = 2) in float a_t;
layout(location = 3) in float a_side;
in vec4 i_row0;
in vec4 i_row1;
in vec4 i_row2;
in vec4 i_row3;
in vec4 i_color;

uniform mat4 u_mvp;
uniform float u_thickness_ndc_x;
uniform float u_thickness_ndc_y;

out vec4 v_color;
out float v_fade;

void main() {
    mat4 model = mat4(i_row0, i_row1, i_row2, i_row3);
    vec4 ws_start = model * vec4(a_unit_start, 1.0);
    vec4 ws_end   = model * vec4(a_unit_end, 1.0);
    vec4 clip_start = u_mvp * ws_start;
    vec4 clip_end   = u_mvp * ws_end;
    vec4 clipPos = mix(clip_start, clip_end, a_t);
    vec2 dxy = clip_end.xy - clip_start.xy;
    float len = length(dxy);
    vec2 perp;
    if (len > 1e-6) {
        vec2 dir = dxy / len;
        perp = vec2(-dir.y, dir.x);
    } else {
        perp = vec2(1.0, 0.0);
    }
    clipPos.xy += perp * a_side * vec2(u_thickness_ndc_x, u_thickness_ndc_y) * clipPos.w;
    gl_Position = clipPos;
    v_color = i_color;
    vec3 ws_mid = (ws_start.xyz + ws_end.xyz) * 0.5;
    v_fade = ws_mid.z;
}
