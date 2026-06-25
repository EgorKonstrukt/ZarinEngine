#version 460 core
in vec2 v_uv;
uniform sampler2D u_texture;
uniform vec4 u_color;
uniform float u_solid;
out vec4 frag_color;
void main() {
    float alpha = u_solid > 0.5 ? 1.0 : texture(u_texture, v_uv).a;
    vec4 result = vec4(u_color.rgb, u_color.a * alpha);
    if (result.a < 0.01) discard;
    frag_color = result;
}
