#version 460 core
layout(location = 0) in vec3 in_position;
uniform mat4 u_mvp;
uniform mat4 u_model;
out vec3 v_world_pos;
void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    v_world_pos = world_pos.xyz;
    gl_Position = u_mvp * vec4(in_position, 1.0);
}
