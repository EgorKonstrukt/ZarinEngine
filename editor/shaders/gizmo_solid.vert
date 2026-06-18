#version 330 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec4 in_color;
uniform mat4 u_mvp;
out vec4 v_color;
void main() {
    v_color = in_color;
    gl_Position = u_mvp * vec4(in_position, 1.0);
}