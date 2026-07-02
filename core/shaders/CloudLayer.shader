// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (c) 2026 Zarrakun

Shader "Zarin/CloudLayer"
{
    Properties
    {
        _Coverage("Cloud Coverage", Range(0, 1)) = 0.78
        _Density("Cloud Density", Float) = 1.12
        _Speed("Wind Speed", Float) = 0.38
        _WindDirection("Wind Direction", Float) = 22.0
        _Height("Cloud Height", Float) = 82.0
        _Thickness("Cloud Thickness", Float) = 42.0
        _Scale("Noise Scale", Float) = 0.014
        _Opacity("Opacity", Range(0, 1)) = 0.68
        _ShadowStrength("Shadow Strength", Range(0, 1)) = 0.52
        _Scattering("Scattering", Range(0, 2)) = 1.22
        _Absorption("Absorption", Range(0, 4)) = 0.92
        _Softness("Softness", Range(0.02, 0.8)) = 0.28
        _DetailStrength("Detail Strength", Range(0, 1)) = 0.92
        _Evolution("Evolution", Range(0, 2)) = 1.1
        _Contrast("Contrast", Range(0.2, 2.5)) = 1.7
        _SilverLining("Silver Lining", Range(0, 2)) = 1.35
        _Seed("Seed", Float) = 11.3
        _Tint("Tint", Color) = (0.86, 0.92, 1.0, 1.0)
    }
    SubShader
    {
        Pass
        {
            GLSLPROGRAM
            #version 460 core
            layout(location = 0) in vec3 in_position;
            layout(location = 2) in vec2 in_uv;
            uniform mat4 u_model;
            uniform mat4 u_view;
            uniform mat4 u_proj;
            out vec2 v_uv;
            out vec3 v_world_pos;
            out vec3 v_view_pos;
            void main()
            {
                vec4 world_pos = u_model * vec4(in_position, 1.0);
                vec4 view_pos = u_view * world_pos;
                v_uv = in_uv;
                v_world_pos = world_pos.xyz;
                v_view_pos = view_pos.xyz;
                gl_Position = u_proj * view_pos;
            }

            // @FRAGMENT

            #version 460 core
            in vec2 v_uv;
            in vec3 v_world_pos;
            in vec3 v_view_pos;
            out vec4 frag_color;
            uniform float u_time;
            uniform vec3 u_cam_pos;
            uniform vec3 _SunDirection;
            uniform vec3 _SunColor;
            uniform float _SunIntensity;
            uniform float _Coverage;
            uniform float _Density;
            uniform float _Speed;
            uniform float _WindDirection;
            uniform float _Height;
            uniform float _Thickness;
            uniform float _Scale;
            uniform float _Opacity;
            uniform float _ShadowStrength;
            uniform float _Scattering;
            uniform float _Absorption;
            uniform float _Softness;
            uniform float _DetailStrength;
            uniform float _Evolution;
            uniform float _Contrast;
            uniform float _SilverLining;
            uniform float _Seed;
            uniform vec3 _Tint;
            float hash(vec2 p)
            {
                return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }
            float hash(vec3 p)
            {
                p = fract(p * 0.3183099 + 0.1);
                p *= 17.0;
                return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
            }
            float noise2d(vec2 p)
            {
                vec2 i = floor(p);
                vec2 f = fract(p);
                f = f * f * (3.0 - 2.0 * f);
                float a = hash(i);
                float b = hash(i + vec2(1.0, 0.0));
                float c = hash(i + vec2(0.0, 1.0));
                float d = hash(i + vec2(1.0, 1.0));
                return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
            }
            float noise3d(vec3 p)
            {
                vec3 i = floor(p);
                vec3 f = fract(p);
                f = f * f * (3.0 - 2.0 * f);
                float n000 = hash(i + vec3(0.0, 0.0, 0.0));
                float n100 = hash(i + vec3(1.0, 0.0, 0.0));
                float n010 = hash(i + vec3(0.0, 1.0, 0.0));
                float n110 = hash(i + vec3(1.0, 1.0, 0.0));
                float n001 = hash(i + vec3(0.0, 0.0, 1.0));
                float n101 = hash(i + vec3(1.0, 0.0, 1.0));
                float n011 = hash(i + vec3(0.0, 1.0, 1.0));
                float n111 = hash(i + vec3(1.0, 1.0, 1.0));
                float x00 = mix(n000, n100, f.x);
                float x10 = mix(n010, n110, f.x);
                float x01 = mix(n001, n101, f.x);
                float x11 = mix(n011, n111, f.x);
                float y0 = mix(x00, x10, f.y);
                float y1 = mix(x01, x11, f.y);
                return mix(y0, y1, f.z);
            }
            float fbm3d(vec3 p, int octaves)
            {
                float v = 0.0;
                float amp = 0.5;
                float freq = 1.0;
                for (int i = 0; i < 8; i++)
                {
                    if (i >= octaves)
                    {
                        break;
                    }
                    v += amp * noise3d(p * freq);
                    freq *= 2.03;
                    amp *= 0.52;
                }
                return v;
            }
            float cloud_shape(vec3 p)
            {
                vec3 q = p + vec3(_Seed * 1.37, _Seed * 0.53, _Seed * 2.11);
                float broad = fbm3d(q * 0.34, 5);
                float base = fbm3d(q, 5);
                float detail = fbm3d(q * 3.5 + vec3(15.0, 3.0, 9.0), 4);
                float curl = fbm3d(vec3(q.x * 0.74 + q.z * 0.14, q.y * 0.68, q.z * 1.26 - q.x * 0.08), 4);
                float cells = noise2d(q.xz * 0.38 + vec2(_Seed * 0.21, _Seed * 0.13));
                float c = clamp(_Coverage, 0.0, 1.0);
                float threshold = mix(0.56, 0.20, c);
                float edge = mix(0.075, 0.055, c) + _Softness * mix(0.025, 0.060, c);
                float shape = broad * 0.50 + base * 0.44 + curl * 0.20 + (detail - 0.5) * _DetailStrength * 0.56;
                shape += (cells - 0.5) * 0.20;
                shape = clamp((shape - 0.5) * _Contrast + 0.5, 0.0, 1.0);
                float cloud = smoothstep(threshold, threshold + edge, shape);
                float cluster = smoothstep(mix(0.66, 0.38, c), mix(0.86, 0.68, c), broad * 0.72 + base * 0.20 + cells * 0.22);
                float broken = smoothstep(mix(0.38, 0.30, c), mix(0.78, 0.66, c), base * 0.62 + curl * 0.28 + cells * 0.18);
                float erosion = 1.0 - smoothstep(0.58, 0.94, detail + curl * 0.18);
                float puffs = smoothstep(0.34, 0.78, broad + cells * 0.18);
                cloud = clamp(cloud * mix(cluster * broken, 1.0, smoothstep(0.34, 0.76, c)), 0.0, 1.0);
                cloud = clamp(cloud * mix(0.66, 1.24, erosion) * mix(0.82, 1.22, puffs), 0.0, 1.0);
                return pow(cloud, mix(1.35, 0.68, c));
            }
            vec3 cloud_color(float density, float phase, float shadow, float top_light)
            {
                vec3 tint = mix(_Tint, vec3(1.0), 0.72);
                vec3 shade_col = tint * mix(vec3(0.58, 0.66, 0.78), vec3(0.72, 0.80, 0.90), top_light);
                vec3 mid_col = tint * vec3(0.88, 0.93, 0.98);
                vec3 lit_col = mix(tint * vec3(1.04, 1.05, 1.04), _SunColor * (0.88 + _SunIntensity * 0.16), clamp(phase, 0.0, 1.0));
                float core = smoothstep(0.18, 0.72, density);
                vec3 col = mix(shade_col, mid_col, core);
                col = mix(col, lit_col, clamp(phase * 0.76 + shadow * 0.24, 0.0, 1.0));
                col *= mix(0.68, 1.0, shadow);
                return col;
            }
            void main()
            {
                vec3 ray_dir = normalize(v_world_pos - u_cam_pos);
                float view_abs = abs(ray_dir.y);
                float bottom_visibility = smoothstep(0.04, 0.26, ray_dir.y);
                float top_visibility = smoothstep(0.05, 0.24, -ray_dir.y);
                float layer_visibility = max(bottom_visibility, top_visibility);
                layer_visibility *= smoothstep(0.06, 0.20, view_abs);
                float distance_to_camera = length(v_world_pos - u_cam_pos);
                float distance_fade = 1.0 - smoothstep(360.0, 980.0, distance_to_camera);
                float wind_angle = radians(_WindDirection);
                vec2 wind_dir = vec2(cos(wind_angle), sin(wind_angle));
                vec2 wind_side = vec2(-wind_dir.y, wind_dir.x);
                float wind_speed = max(_Speed, 0.0);
                vec2 wind = wind_dir * u_time * wind_speed * 18.0 + wind_side * sin(u_time * wind_speed * 0.7 + _Seed) * _Evolution * 9.0;
                float evolve = u_time * wind_speed * _Evolution;
                float thickness = max(_Thickness, 1.0);
                float transmittance = 1.0;
                vec3 premul = vec3(0.0);
                float density_sum = 0.0;
                float light_sum = 0.0;
                float step_len = thickness / max(view_abs, 0.18) / 8.0;
                float jitter = noise2d(v_uv * 96.0 + vec2(_Seed, u_time * 0.03));
                vec3 sun_dir = normalize(_SunDirection);
                float forward = pow(max(dot(ray_dir, sun_dir), 0.0), 5.0);
                float sun_height = clamp(sun_dir.y * 0.5 + 0.5, 0.0, 1.0);
                for (int i = 0; i < 8; i++)
                {
                    float slice = (float(i) + jitter) / 8.0;
                    float centered = slice - 0.5;
                    float height_offset = centered * thickness;
                    vec3 p = v_world_pos + ray_dir * (height_offset / max(view_abs, 0.18));
                    float h = clamp((p.y - _Height) / thickness, 0.0, 1.0);
                    float height_mask = smoothstep(0.0, max(_Softness, 0.12), h) * (1.0 - smoothstep(1.0 - max(_Softness, 0.12), 1.0, h));
                    vec3 sample_pos = vec3((p.x + wind.x + wind_side.x * centered * thickness * 0.16) * _Scale, p.y * _Scale * 0.26 + evolve * 0.07 + centered * 0.11, (p.z + wind.y + wind_side.y * centered * thickness * 0.16) * _Scale);
                    float density = cloud_shape(sample_pos) * height_mask * _Density;
                    float sample_alpha = 1.0 - exp(-density * step_len * max(_Absorption, 0.001) * 0.030);
                    float light_depth = 0.48 + slice * 0.52;
                    float phase = clamp(light_depth * 0.46 + sun_height * 0.20 + forward * _Scattering * 0.34, 0.0, 1.0);
                    vec3 sample_col = cloud_color(density, phase, 1.0, light_depth);
                    premul += transmittance * sample_alpha * sample_col;
                    transmittance *= 1.0 - sample_alpha;
                    density_sum += density;
                    light_sum += density * light_depth;
                }
                float layer_edge = smoothstep(0.0, 0.06, v_uv.x) * (1.0 - smoothstep(0.94, 1.0, v_uv.x));
                layer_edge *= smoothstep(0.0, 0.06, v_uv.y) * (1.0 - smoothstep(0.94, 1.0, v_uv.y));
                float cloud_alpha = 1.0 - transmittance;
                float alpha = cloud_alpha * _Opacity * layer_visibility * distance_fade * layer_edge;
                alpha = clamp(alpha, 0.0, 0.72);
                if (alpha <= 0.005)
                {
                    discard;
                }
                float top_side = smoothstep(0.02, 0.20, -ray_dir.y);
                float average_light = light_sum / max(density_sum, 0.001);
                float self_shadow = mix(1.0, exp(-cloud_alpha * _Absorption * mix(1.35, 0.62, top_side)), _ShadowStrength);
                vec3 col = premul / max(cloud_alpha, 0.001);
                col = mix(col, mix(_Tint, vec3(1.0), 0.72) * vec3(0.94, 0.98, 1.03), clamp(average_light * top_side * 0.28, 0.0, 0.28));
                col *= self_shadow;
                col += _SunColor * forward * _Scattering * _SilverLining * 0.18;
                frag_color = vec4(col, alpha);
            }
            ENDGLSL
        }
    }
}
