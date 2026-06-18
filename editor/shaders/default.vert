#version 330 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_uv;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat3 u_normal_matrix;
out vec3 v_world_pos;
out vec3 v_normal;
out vec2 v_uv;
out vec3 v_view_pos;
void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    v_world_pos = world_pos.xyz;
    v_normal = normalize(u_normal_matrix * in_normal);
    v_uv = in_uv;
    vec4 view_pos = u_view * world_pos;
    v_view_pos = view_pos.xyz;
    gl_Position = u_proj * u_view * world_pos;
}
