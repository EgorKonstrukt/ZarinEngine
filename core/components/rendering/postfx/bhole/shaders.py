# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

BLACK_HOLE_VERT = """
\x23version 330 core
in vec2 in_position;
out vec2 v_uv;
void main() {
    v_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""


BLACK_HOLE_FRAG = """
\x23version 330 core
uniform sampler2D u_input_tex;
uniform sampler2D u_depth_tex;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat4 u_inv_view;
uniform mat4 u_inv_proj;
uniform vec3 u_camera_pos;
uniform vec3 u_hole_pos;
uniform vec3 u_disk_normal;
uniform float u_rs;
uniform float u_lensing;
uniform float u_disk_inner;
uniform float u_disk_outer;
uniform vec3 u_inner_color;
uniform vec3 u_outer_color;
uniform float u_disk_brightness;
uniform float u_spin_speed;
uniform float u_doppler;
uniform float u_time;
uniform float u_photon_intensity;
uniform float u_photon_width;
uniform float u_fringe;
uniform float u_noise_amount;
uniform float u_show_disk;
uniform float u_bypass;
in vec2 v_uv;
out vec4 frag_color;
float bh_hash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
float bh_noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = bh_hash(i);
    float b = bh_hash(i + vec2(1.0, 0.0));
    float c = bh_hash(i + vec2(0.0, 1.0));
    float d = bh_hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float bh_fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    v += a * bh_noise(p);
    v += a * 0.5 * bh_noise(p * 2.03 + vec2(17.3, 9.1));
    v += a * 0.25 * bh_noise(p * 4.11 + vec2(5.7, 3.2));
    return v / 0.875;
}
vec3 bh_ray_dir(vec2 uv) {
    vec4 r = u_inv_proj * vec4(uv * 2.0 - 1.0, 1.0, 1.0);
    vec3 vd = r.xyz / max(abs(r.w), 0.000001);
    vec4 wd = u_inv_view * vec4(vd, 0.0);
    return normalize(wd.xyz);
}
vec2 bh_project(vec3 dir) {
    vec3 wp = u_camera_pos + dir * 1000.0;
    vec4 vp = u_view * vec4(wp, 1.0);
    vec4 cp = u_proj * vp;
    if (cp.w <= 0.0001) return vec2(-10.0, -10.0);
    return cp.xy / cp.w * 0.5 + 0.5;
}
vec3 bh_bend(vec3 d, vec3 perp, float alpha) {
    float ca = cos(alpha);
    float sa = sin(alpha);
    return normalize(d * ca + perp * sa);
}
void main() {
    vec3 original = texture(u_input_tex, v_uv).rgb;
    if (u_bypass > 0.5) {
        frag_color = vec4(original, 1.0);
        return;
    }
    float rs = max(u_rs, 0.0001);
    float rs_eff = max(rs * max(u_lensing, 0.0), 0.000001);
    vec3 N = u_disk_normal;
    if (dot(N, N) < 0.000001) N = vec3(0.0, 1.0, 0.0);
    N = normalize(N);
    vec3 D = bh_ray_dir(v_uv);
    vec3 O = u_camera_pos;
    vec3 CO = u_hole_pos - O;
    float t_ca = dot(CO, D);
    float b = 1000000.0;
    vec3 perp = vec3(0.0);
    float has_bend = 0.0;
    if (t_ca > 0.0) {
        vec3 closest = O + D * t_ca - u_hole_pos;
        b = length(closest);
        vec3 to_hole = -closest / max(b, 0.00001);
        vec3 pp = to_hole - D * dot(to_hole, D);
        float pl = length(pp);
        if (pl > 0.00001 && b > 0.00001) {
            perp = pp / pl;
            has_bend = 1.0;
        }
    } else {
        b = length(CO);
    }
    float b_crit = 2.598 * rs_eff;
    float alpha = 2.0 * rs_eff / max(b, b_crit);
    vec3 Db = D;
    if (has_bend > 0.5) Db = bh_bend(D, perp, alpha);
    float alpha_r = alpha * (1.0 + u_fringe);
    float alpha_b = max(alpha * (1.0 - u_fringe), 0.0);
    vec3 Dr = D;
    vec3 Dbl = D;
    if (has_bend > 0.5) {
        Dr = bh_bend(D, perp, alpha_r);
        Dbl = bh_bend(D, perp, alpha_b);
    }
    float depth = texture(u_depth_tex, v_uv).r;
    float t_surf = 1000000.0;
    if (depth < 1.0) {
        vec4 ndc = vec4(v_uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
        vec4 vv = u_inv_proj * ndc;
        vec3 vp2 = vv.xyz / max(abs(vv.w), 0.000001);
        vec4 wv = u_inv_view * vec4(vp2, 1.0);
        vec3 wp2 = wv.xyz / max(abs(wv.w), 0.000001);
        t_surf = dot(wp2 - O, D);
    }
    if (depth < 1.0 && t_ca > 0.0 && t_surf > 0.0 && t_surf < t_ca - max(rs * 0.5, 0.05)) {
        frag_color = vec4(original, 1.0);
        return;
    }
    vec2 uv_c = bh_project(Db);
    vec2 uv_r = bh_project(Dr);
    vec2 uv_bl = bh_project(Dbl);
    vec3 bg = vec3(texture(u_input_tex, clamp(uv_r, 0.0, 1.0)).r, texture(u_input_tex, clamp(uv_c, 0.0, 1.0)).g, texture(u_input_tex, clamp(uv_bl, 0.0, 1.0)).b);
    float aa = fwidth(b) * 1.2 + 0.002 * rs + 0.0005;
    float shadow = 1.0 - smoothstep(b_crit - aa, b_crit + aa, b);
    if (t_ca <= 0.0) shadow = 0.0;
    float pw = max(u_photon_width * rs, 0.0001);
    float dd = (b - b_crit) / pw;
    float ring = exp(-dd * dd) * u_photon_intensity;
    if (t_ca <= 0.0) ring = 0.0;
    vec3 e1 = cross(vec3(0.0, 1.0, 0.0), N);
    if (dot(e1, e1) < 0.001) e1 = cross(vec3(1.0, 0.0, 0.0), N);
    e1 = normalize(e1);
    vec3 e2 = normalize(cross(N, e1));
    float inner = max(u_disk_inner, rs * 1.05);
    float outer = max(u_disk_outer, inner + rs * 0.5 + 0.001);
    vec3 disk_col = vec3(0.0);
    float disk_alpha = 0.0;
    if (u_show_disk > 0.5 && t_ca > 0.0) {
        float denom1 = dot(D, N);
        float t1 = -1.0;
        vec3 hit1 = vec3(0.0);
        float r1 = -1.0;
        if (abs(denom1) > 0.00001) {
            float tt = dot(u_hole_pos - O, N) / denom1;
            if (tt > 0.0 && tt < t_ca) {
                vec3 hp = O + D * tt;
                float rr = length(hp - u_hole_pos);
                if (rr >= inner * 0.85 && rr <= outer) {
                    t1 = tt;
                    hit1 = hp;
                    r1 = rr;
                }
            }
        }
        vec3 Pl = O + D * t_ca;
        float denom2 = dot(Db, N);
        float t2 = -1.0;
        vec3 hit2 = vec3(0.0);
        float r2 = -1.0;
        if (abs(denom2) > 0.00001) {
            float tt = dot(u_hole_pos - Pl, N) / denom2;
            if (tt > 0.0) {
                vec3 hp = Pl + Db * tt;
                float rr = length(hp - u_hole_pos);
                if (rr >= inner * 0.85 && rr <= outer) {
                    t2 = t_ca + tt;
                    hit2 = hp;
                    r2 = rr;
                }
            }
        }
        float use_fg = 0.0;
        vec3 hit = vec3(0.0);
        float rh = -1.0;
        float th = -1.0;
        if (t1 > 0.0 && t2 > 0.0) {
            if (t1 <= t2) {
                use_fg = 1.0;
                hit = hit1;
                rh = r1;
                th = t1;
            } else {
                use_fg = 0.0;
                hit = hit2;
                rh = r2;
                th = t2;
            }
        } else if (t1 > 0.0) {
            use_fg = 1.0;
            hit = hit1;
            rh = r1;
            th = t1;
        } else if (t2 > 0.0) {
            use_fg = 0.0;
            hit = hit2;
            rh = r2;
            th = t2;
        }
        if (rh > 0.0) {
            vec3 rel = hit - u_hole_pos;
            float rr = max(rh, 0.0001);
            float lx = dot(rel, e1);
            float lz = dot(rel, e2);
            float omega = u_spin_speed * 2.0 * pow(inner / rr, 1.5);
            float ang = u_time * omega;
            float ca2 = cos(ang);
            float sa2 = sin(ang);
            vec2 rp = vec2(lx * ca2 - lz * sa2, lx * sa2 + lz * ca2);
            vec2 np2 = rp / max(rs, 0.0001);
            float n1 = bh_fbm(np2 * 1.6);
            float n2 = bh_fbm(np2 * 3.4 + n1 * 2.0);
            float turb = mix(1.0, clamp(n1 * 0.65 + n2 * 0.55, 0.0, 1.6), clamp(u_noise_amount, 0.0, 1.0));
            float q = clamp(inner / rr, 0.0, 1.0);
            float temp = pow(q, 0.8);
            vec3 dcol = mix(u_outer_color, u_inner_color, pow(temp, 0.7));
            dcol += vec3(1.0, 0.97, 0.92) * pow(temp, 3.0) * 2.0;
            vec3 radial = rel / rr;
            vec3 tang = cross(N, radial);
            if (dot(tang, tang) < 0.000001) tang = e1;
            tang = normalize(tang);
            vec3 to_cam = (O - hit) / max(length(O - hit), 0.0001);
            float beta = clamp(sqrt(rs / max(2.0 * rr, 0.0001)) * u_doppler, 0.0, 0.65);
            float appr = dot(tang, to_cam);
            float dop = 1.0 / max(1.0 - beta * appr, 0.25);
            float beam = pow(clamp(dop, 0.3, 3.2), 3.0);
            dcol *= beam;
            dcol = mix(dcol, dcol * vec3(0.75, 0.85, 1.25), clamp(appr * beta * 1.5, 0.0, 0.6));
            dcol = mix(dcol, dcol * vec3(1.25, 0.8, 0.65), clamp(-appr * beta * 1.5, 0.0, 0.6));
            float grav = sqrt(clamp(1.0 - rs / rr, 0.05, 1.0));
            dcol *= (0.35 + 0.65 * grav);
            float soft_in = rs * 0.18 + 0.001;
            float soft_out = rs * 0.6 + 0.002;
            float fin = smoothstep(inner * 0.85, inner * 0.85 + soft_in, rr);
            float fout = 1.0 - smoothstep(outer - soft_out, outer, rr);
            float plunge = smoothstep(rs * 0.9, inner, rr);
            float dalpha = clamp(fin * fout * (0.45 + 0.55 * turb), 0.0, 1.0);
            vec3 hdr = dcol * u_disk_brightness * (0.55 + 0.9 * turb) * plunge;
            if (depth < 1.0 && t_surf > 0.0 && t_surf < th - 0.02) {
                dalpha = 0.0;
            }
            float occ = 1.0;
            if (use_fg < 0.5) occ = 1.0 - shadow;
            disk_col = hdr;
            disk_alpha = dalpha * occ;
        }
    }
    float glow = exp(-max(b - b_crit, 0.0) / max(rs * 3.0, 0.0001)) * 0.12 * clamp(u_disk_brightness * 0.5, 0.0, 1.0);
    if (t_ca <= 0.0) glow = 0.0;
    vec3 ring_col = vec3(1.0, 0.93, 0.82) * ring;
    vec3 col = bg * (1.0 - shadow);
    col = mix(col, disk_col, clamp(disk_alpha, 0.0, 1.0));
    col += ring_col * (1.0 - shadow * 0.35);
    col += vec3(1.0, 0.8, 0.55) * glow * (1.0 - shadow);
    frag_color = vec4(col, 1.0);
}
"""
