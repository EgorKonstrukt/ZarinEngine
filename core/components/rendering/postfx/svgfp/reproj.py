# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
SVGF_REPROJ_FRAG = """
\x23version 330 core
uniform sampler2D u_current;
uniform sampler2D u_depth;
uniform sampler2D u_velocity;
uniform sampler2D u_history;
uniform sampler2D u_moment;
uniform vec2 u_pixel;
uniform float u_has_velocity;
uniform float u_has_history;
uniform float u_disocclusion;
uniform float u_stability;
in vec2 v_uv;
layout(location = 0) out vec4 out_color;
layout(location = 1) out vec2 out_moment;

float svgf_luma(vec3 c) {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

vec3 svgf_rgb_to_ycocg(vec3 c) {
    return vec3(
        dot(c, vec3(0.25, 0.5, 0.25)),
        dot(c, vec3(0.5, 0.0, -0.5)),
        dot(c, vec3(-0.25, 0.5, -0.25))
    );
}

vec3 svgf_ycocg_to_rgb(vec3 c) {
    return vec3(c.x + c.y - c.z, c.x + c.z, c.x - c.y - c.z);
}

vec3 svgf_clip_to_box(vec3 history, vec3 center, vec3 extents) {
    vec3 v = history - center;
    vec3 unit = v / max(extents, vec3(1e-5));
    float ma = max(unit.x, max(unit.y, unit.z));
    float mi = min(unit.x, min(unit.y, unit.z));
    float m = max(ma, -mi);
    return m > 1.0 ? center + v / m : history;
}

vec2 svgf_dilate_velocity(vec2 uv, float curD, out float nearestD) {
    vec2 bestMotion = texture(u_velocity, uv).rg;
    nearestD = curD;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            if (x == 0 && y == 0) continue;
            vec2 suv = uv + vec2(float(x), float(y)) * u_pixel;
            float d = texture(u_depth, suv).r;
            if (d < nearestD) {
                nearestD = d;
                bestMotion = texture(u_velocity, suv).rg;
            }
        }
    }
    return bestMotion;
}

void main() {
    vec3 cur = texture(u_current, v_uv).rgb;
    float curD = texture(u_depth, v_uv).r;
    float curLuma = svgf_luma(cur);

    if (u_has_history < 0.5) {
        out_color = vec4(cur, 1.0);
        out_moment = vec2(curLuma, curLuma * curLuma);
        return;
    }

    float nearestD;
    vec2 motion = vec2(0.0);
    if (u_has_velocity > 0.5) {
        motion = svgf_dilate_velocity(v_uv, curD, nearestD);
    }
    vec2 prev_uv = v_uv - motion;

    vec3 mn = cur;
    vec3 mx = cur;
    float lumaSum = curLuma;
    float lumaSqSum = curLuma * curLuma;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            if (x == 0 && y == 0) continue;
            vec2 ouv = v_uv + vec2(float(x), float(y)) * u_pixel;
            vec3 c = texture(u_current, ouv).rgb;
            mn = min(mn, c);
            mx = max(mx, c);
            float l = svgf_luma(c);
            lumaSum += l;
            lumaSqSum += l * l;
        }
    }

    vec3 centerY = svgf_rgb_to_ycocg((mn + mx) * 0.5);
    float meanLuma = lumaSum / 9.0;
    float varLuma = max(lumaSqSum / 9.0 - meanLuma * meanLuma, 0.0);
    float stdLuma = sqrt(varLuma);
    vec3 extents = max(vec3(stdLuma * 1.5), vec3(1e-4));

    vec3 hist = texture(u_history, prev_uv).rgb;
    vec3 histY = svgf_rgb_to_ycocg(hist);
    vec3 histYClipped = svgf_clip_to_box(histY, centerY, extents);
    vec3 histClipped = clamp(svgf_ycocg_to_rgb(histYClipped), mn, mx);

    float blend = u_stability;
    if (any(lessThan(prev_uv, vec2(0.0))) || any(greaterThan(prev_uv, vec2(1.0)))) {
        blend = 0.0;
    } else {
        float prevD = texture(u_depth, prev_uv).r;
        float ddepth = abs(curD - prevD);
        float diso = smoothstep(0.0, max(u_disocclusion, 1e-4), ddepth);
        blend = mix(u_stability, 0.0, diso);
    }

    vec3 result = mix(cur, histClipped, clamp(blend, 0.0, 1.0));
    if (any(isnan(result)) || any(isinf(result))) {
        result = cur;
    }

    vec2 momentPrev = texture(u_moment, prev_uv).rg;
    float resultLuma = svgf_luma(result);

    float newMomentLuma = mix(curLuma, momentPrev.r, blend);
    float newMomentLumaSq = mix(curLuma * curLuma, momentPrev.g, blend);

    out_color = vec4(result, 1.0);
    out_moment = vec2(newMomentLuma, newMomentLumaSq);
}
"""
