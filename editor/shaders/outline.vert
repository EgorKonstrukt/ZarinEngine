#version 330 core
layout(location = 0) in vec3 in_position;
uniform mat4 u_mvp;
out vec4 clip_pos;
void main() {
    gl_Position = u_mvp * vec4(in_position, 1.0);
    clip_pos = gl_Position;
}
