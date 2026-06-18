#version 330 core
uniform vec4 u_outline_color;
in vec4 clip_pos;
out vec4 frag_color;
void main() {
    frag_color = u_outline_color;
    gl_FragDepth = clip_pos.z / clip_pos.w;
}
