#version 460 core
layout(location = 0) in vec3 in_position;
uniform mat4 u_mvp;
out vec3 v_uv;
void main() {
    vec4 pos = u_mvp * vec4(in_position, 1.0);
    gl_Position = pos.xyww;
    v_uv = in_position;
}
