#version 460 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec2 in_uv;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform vec2 u_viewport_size;
uniform float u_screen_space;
uniform float u_billboard;
uniform vec3 u_offset;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    vec4 world_pos = u_model * vec4(in_position + u_offset, 1.0);
    if (u_billboard > 0.5) {
        vec3 cam_right = vec3(u_view[0][0], u_view[1][0], u_view[2][0]);
        vec3 cam_up = vec3(u_view[0][1], u_view[1][1], u_view[2][1]);
        vec3 cam_fwd = vec3(u_view[0][2], u_view[1][2], u_view[2][2]);
        vec3 scale;
        scale.x = length(u_model[0].xyz);
        scale.y = length(u_model[1].xyz);
        scale.z = length(u_model[2].xyz);
        vec3 local_pos = (in_position + u_offset) * scale;
        vec3 center = u_model[3].xyz;
        world_pos.xyz = center + cam_right * local_pos.x + cam_up * local_pos.y + cam_fwd * local_pos.z;
    }
    if (u_screen_space > 0.5) {
        vec4 clip = u_proj * u_view * world_pos;
        vec3 ndc = clip.xyz / clip.w;
        vec2 screen = (ndc.xy * 0.5 + 0.5) * u_viewport_size;
        mat4 ortho = mat4(1.0);
        ortho[0][0] = 2.0 / u_viewport_size.x;
        ortho[1][1] = -2.0 / u_viewport_size.y;
        ortho[3][0] = -1.0;
        ortho[3][1] = 1.0;
        vec3 scale2;
        scale2.x = length(u_model[0].xyz);
        scale2.y = length(u_model[1].xyz);
        scale2.z = length(u_model[2].xyz);
        vec4 screen_pos = vec4(screen + (in_position.xy + u_offset.xy) * scale2.xy, 0.0, 1.0);
        gl_Position = ortho * screen_pos;
    } else {
        gl_Position = u_proj * u_view * world_pos;
    }
}
