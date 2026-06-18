#version 330 core
in vec2 v_uv;
out vec4 frag_color;
uniform sampler2D u_debug_tex;
void main() {
    float d = texture(u_debug_tex, v_uv).r;
    frag_color = vec4(d, d, d, 1.0);
}
