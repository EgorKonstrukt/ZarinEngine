#version 460 core
in vec4 v_color;
in float v_fade;
uniform vec3 u_camera_pos;
out vec4 fragColor;
void main() {
    float dist = length(v_fade - u_camera_pos.z);
    float fade = 1.0 - smoothstep(20.0, 80.0, dist);
    fragColor = vec4(v_color.rgb * fade, v_color.a * fade);
}
