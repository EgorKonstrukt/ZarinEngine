Shader "Zarin/Clouds"
{
    Properties
    {
        _Coverage("Cloud Coverage", Range(0, 1)) = 0.5
        _Density("Cloud Density", Float) = 1.0
        _Speed("Wind Speed", Float) = 0.1
        _Height("Cloud Height", Float) = 50.0
        _Thickness("Cloud Thickness", Float) = 20.0
        _Scale("Noise Scale", Float) = 0.02
        _Opacity("Opacity", Range(0, 1)) = 0.9
    }

    SubShader
    {
        Pass
        {
            GLSLPROGRAM
            #version 460 core
            layout(location = 0) in vec3 in_position;
            layout(location = 2) in vec2 in_uv;
            out vec2 v_uv;
            void main() {
                v_uv = in_uv;
                gl_Position = vec4(in_position.xy, 0.0, 1.0);
            }

            // @FRAGMENT

            #version 460 core
            in vec2 v_uv;
            out vec4 frag_color;

            uniform float u_time;
            uniform vec3 _SunDirection;
            uniform float _Coverage;
            uniform float _Density;
            uniform float _Speed;
            uniform float _Scale;
            uniform float _Opacity;
            uniform vec3 u_cam_pos;
            uniform mat4 u_inv_view_proj;

            float hash(vec2 p) {
                return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }

            float hash(vec3 p) {
                p = fract(p * 0.3183099 + 0.1);
                p *= 17.0;
                return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
            }

            float noise2d(vec2 p) {
                vec2 i = floor(p);
                vec2 f = fract(p);
                f = f * f * (3.0 - 2.0 * f);
                return mix(mix(hash(i), hash(i + vec2(1,0)), f.x),
                           mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), f.x), f.y);
            }

            float fbm2d(vec2 p, int octaves) {
                float v = 0.0, amp = 1.0, freq = 1.0;
                for (int i = 0; i < 8; i++) {
                    if (i >= octaves) break;
                    v += amp * noise2d(p * freq);
                    amp *= 0.5;
                    freq *= 2.0;
                }
                return v;
            }

            void main() {
                vec4 ndc = vec4(v_uv * 2.0 - 1.0, 1.0, 1.0);
                vec4 world_pos = u_inv_view_proj * ndc;
                vec3 ray_dir = normalize(world_pos.xyz / world_pos.w - u_cam_pos);

                vec3 sun_dir = normalize(_SunDirection);

                float height_fade = max(ray_dir.y, 0.0);
                height_fade = 1.0 - pow(1.0 - height_fade, 3.0);

                vec2 wind = vec2(u_time * _Speed * 0.001, u_time * _Speed * 0.0003);
                vec2 uv = v_uv * 4.0 + wind;

                float n = fbm2d(uv, 5);
                float cloud = smoothstep(1.0 - _Coverage * 0.8, 1.2, n);
                cloud *= _Density * _Opacity * height_fade;

                float sun_light = max(0.0, dot(ray_dir, sun_dir)) * 0.5 + 0.3;
                vec3 base_col = mix(vec3(0.6, 0.6, 0.75), vec3(1.0, 0.95, 0.9), sun_light);

                frag_color = vec4(base_col, cloud);
            }
            ENDGLSL
        }
    }
}
