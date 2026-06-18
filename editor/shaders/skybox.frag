#version 460 core
in vec3 v_uv;
out vec4 frag_color;

uniform vec3 u_sun_direction;
uniform vec3 u_sun_color;
uniform float u_sun_intensity;
uniform float u_sun_size;
uniform float u_sun_convergence;

void main() {
    vec3 dir = normalize(v_uv);
    vec3 sun_dir = normalize(u_sun_direction);
    float cos_theta = max(dir.y, 0.0);
    float cos_gamma = dot(dir, sun_dir);
    float sun_height = sun_dir.y;

    float optical_depth = 1.0 / max(cos_theta, 0.005);

    float rayleigh_phase = 0.75 * (1.0 + cos_gamma * cos_gamma);
    vec3 rayleigh = vec3(0.55, 0.65, 0.90) * rayleigh_phase;

    float g = 0.76;
    float gg = g * g;
    float mie_phase = (1.0 - gg) / max(pow(1.0 + gg - 2.0 * g * cos_gamma, 1.5), 0.001);
    vec3 mie = vec3(1.0, 0.80, 0.50) * mie_phase;

    vec3 color = (rayleigh * 0.10 + mie * 0.05) * (1.0 - exp(-optical_depth * 0.4));

    vec3 sky_top = vec3(0.08, 0.18, 0.45);
    vec3 sky_horizon = vec3(0.75, 0.80, 0.90);
    vec3 sky_sunset = vec3(1.0, 0.50, 0.18);
    vec3 horizon_color = mix(sky_sunset, sky_horizon, smoothstep(0.0, 0.3, sun_height));

    float height_gradient = 1.0 - pow(1.0 - cos_theta, 4.0);
    vec3 base_sky = mix(horizon_color, sky_top, height_gradient);

    color = max(color + base_sky * 0.3, 0.0);

    float sun_start = 1.0 - u_sun_size * 3.0;
    float sun_end = 1.0 - u_sun_size * (1.0 - u_sun_convergence * 0.8);
    float sun_disk = smoothstep(sun_start, sun_end, cos_gamma);
    color += u_sun_color * u_sun_intensity * sun_disk;

    float night = smoothstep(0.05, -0.4, sun_height);
    color *= (1.0 - night * 0.85);

    frag_color = vec4(color, 1.0);
}
