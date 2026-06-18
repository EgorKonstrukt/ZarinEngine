#version 460 core
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec4 u_color;
uniform float u_alpha;
out vec4 frag_color;
void main() {
    vec4 tex = texture(u_texture, v_uv);
    float a = tex.a * u_alpha;
    frag_color = vec4(tex.rgb * u_color.rgb, a);
}
