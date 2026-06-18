#version 460 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec2 in_uv;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform vec2 u_flip;
out vec2 v_uv;
void main() {
    vec2 uv = in_uv;
    if (u_flip.x > 0.5) uv.x = 1.0 - uv.x;
    if (u_flip.y > 0.5) uv.y = 1.0 - uv.y;
    v_uv = uv;
    gl_Position = u_proj * u_view * u_model * vec4(in_position, 1.0);
}
