#version 330 core
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec4 u_color;
uniform float u_alpha_cutoff;
out vec4 frag_color;
void main() {
    vec4 tex = texture(u_texture, v_uv);
    vec4 result = tex * u_color;
    if (result.a < u_alpha_cutoff) discard;
    frag_color = result;
}
