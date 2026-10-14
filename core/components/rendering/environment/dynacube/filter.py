# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
from core.components.rendering.environment.dynacube.capture import _attach_cubemap_face, _restore_framebuffer, _FACE_BASIS
_FULLSCREEN_QUAD_VERT = (
    "\n"
    + chr(35) + "version 330 core\n"
    + "in vec2 in_position;\n"
    + "in vec2 in_uv;\n"
    + "out vec2 v_uv;\n"
    + "void main() {\n"
    + "    gl_Position = vec4(in_position, 0.0, 1.0);\n"
    + "    v_uv = in_uv;\n"
    + "}\n"
)
_IRRADIANCE_FRAG = (
    "\n"
    + chr(35) + "version 330 core\n"
    + "in vec2 v_uv;\n"
    + "out vec4 frag_color;\n"
    + "uniform samplerCube u_cubemap;\n"
    + "uniform vec3 u_face_x;\n"
    + "uniform vec3 u_face_y;\n"
    + "uniform vec3 u_face_z;\n"
    + "const float PI = 3.14159265359;\n"
    + "void main() {\n"
    + "    vec2 tc = v_uv * 2.0 - 1.0;\n"
    + "    vec3 dir = normalize(u_face_x * tc.x + u_face_y * tc.y + u_face_z);\n"
    + "    vec3 N = dir;\n"
    + "    vec3 up = abs(N.y) < 0.999 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);\n"
    + "    vec3 right = normalize(cross(up, N));\n"
    + "    up = cross(N, right);\n"
    + "    vec3 irradiance = vec3(0.0);\n"
    + "    float nrSamples = 0.0;\n"
    + "    for (float phi = 0.0; phi < 2.0 * PI; phi += 0.1) {\n"
    + "        for (float theta = 0.0; theta < 0.5 * PI; theta += 0.1) {\n"
    + "            vec3 tangent = vec3(sin(theta) * cos(phi), sin(theta) * sin(phi), cos(theta));\n"
    + "            vec3 sampleVec = tangent.x * right + tangent.y * up + tangent.z * N;\n"
    + "            irradiance += texture(u_cubemap, sampleVec).rgb * cos(theta) * sin(theta);\n"
    + "            nrSamples += 1.0;\n"
    + "        }\n"
    + "    }\n"
    + "    irradiance = PI * irradiance * (1.0 / nrSamples);\n"
    + "    frag_color = vec4(irradiance, 1.0);\n"
    + "}\n"
)
_PREFILTER_FRAG = (
    "\n"
    + chr(35) + "version 330 core\n"
    + "in vec2 v_uv;\n"
    + "out vec4 frag_color;\n"
    + "uniform samplerCube u_cubemap;\n"
    + "uniform vec3 u_face_x;\n"
    + "uniform vec3 u_face_y;\n"
    + "uniform vec3 u_face_z;\n"
    + "uniform float u_roughness;\n"
    + "const float PI = 3.14159265359;\n"
    + "float distribution_ggx(vec3 N, vec3 H, float roughness) {\n"
    + "    float a = roughness * roughness;\n"
    + "    float a2 = a * a;\n"
    + "    float NdotH = max(dot(N, H), 0.0);\n"
    + "    float NdotH2 = NdotH * NdotH;\n"
    + "    float denom = NdotH2 * (a2 - 1.0) + 1.0;\n"
    + "    return a2 / (PI * denom * denom);\n"
    + "}\n"
    + "vec2 hammersley(int i, int N) {\n"
    + "    uint bits = uint(i);\n"
    + "    bits = (bits << 16u) | (bits >> 16u);\n"
    + "    bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);\n"
    + "    bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);\n"
    + "    bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);\n"
    + "    bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);\n"
    + "    float rdi = float(bits) * 2.3283064365386963e-10;\n"
    + "    return vec2(float(i) / float(N), rdi);\n"
    + "}\n"
    + "vec3 importance_sample_ggx(vec2 Xi, vec3 N, float roughness) {\n"
    + "    float a = roughness * roughness;\n"
    + "    float phi = 2.0 * PI * Xi.x;\n"
    + "    float cosTheta = sqrt((1.0 - Xi.y) / (1.0 + (a * a - 1.0) * Xi.y));\n"
    + "    float sinTheta = sqrt(1.0 - cosTheta * cosTheta);\n"
    + "    vec3 H = vec3(cos(phi) * sinTheta, sin(phi) * sinTheta, cosTheta);\n"
    + "    vec3 up = abs(N.y) < 0.999 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);\n"
    + "    vec3 tangent = normalize(cross(up, N));\n"
    + "    vec3 bitangent = cross(N, tangent);\n"
    + "    return normalize(tangent * H.x + bitangent * H.y + N * H.z);\n"
    + "}\n"
    + "void main() {\n"
    + "    vec2 tc = v_uv * 2.0 - 1.0;\n"
    + "    vec3 N = normalize(u_face_x * tc.x + u_face_y * tc.y + u_face_z);\n"
    + "    vec3 R = N;\n"
    + "    vec3 V = R;\n"
    + "    const int SAMPLE_COUNT = 1024;\n"
    + "    vec3 prefilteredColor = vec3(0.0);\n"
    + "    float totalWeight = 0.0;\n"
    + "    for (int i = 0; i < SAMPLE_COUNT; ++i) {\n"
    + "        vec2 Xi = hammersley(i, SAMPLE_COUNT);\n"
    + "        vec3 H = importance_sample_ggx(Xi, N, u_roughness);\n"
    + "        vec3 L = normalize(2.0 * dot(V, H) * H - V);\n"
    + "        float NdotL = max(dot(N, L), 0.0);\n"
    + "        if (NdotL > 0.0) {\n"
    + "            prefilteredColor += texture(u_cubemap, L).rgb * NdotL;\n"
    + "            totalWeight += NdotL;\n"
    + "        }\n"
    + "    }\n"
    + "    prefilteredColor = prefilteredColor / max(totalWeight, 0.001);\n"
    + "    frag_color = vec4(prefilteredColor, 1.0);\n"
    + "}\n"
)
_BRDF_LUT_FRAG = (
    "\n"
    + chr(35) + "version 330 core\n"
    + "in vec2 v_uv;\n"
    + "out vec4 frag_color;\n"
    + "const float PI = 3.14159265359;\n"
    + "float distribution_ggx(vec3 N, vec3 H, float roughness) {\n"
    + "    float a = roughness * roughness;\n"
    + "    float a2 = a * a;\n"
    + "    float NdotH = max(dot(N, H), 0.0);\n"
    + "    float NdotH2 = NdotH * NdotH;\n"
    + "    float denom = NdotH2 * (a2 - 1.0) + 1.0;\n"
    + "    return a2 / (PI * denom * denom);\n"
    + "}\n"
    + "float geometry_schlick_ggx(float NdotV, float roughness) {\n"
    + "    float r = roughness + 1.0;\n"
    + "    float k = (r * r) / 8.0;\n"
    + "    return NdotV / (NdotV * (1.0 - k) + k);\n"
    + "}\n"
    + "float geometry_smith(vec3 N, vec3 V, vec3 L, float roughness) {\n"
    + "    float NdotV = max(dot(N, V), 0.0);\n"
    + "    float NdotL = max(dot(N, L), 0.0);\n"
    + "    return geometry_schlick_ggx(NdotV, roughness) * geometry_schlick_ggx(NdotL, roughness);\n"
    + "}\n"
    + "vec2 hammersley(int i, int N) {\n"
    + "    uint bits = uint(i);\n"
    + "    bits = (bits << 16u) | (bits >> 16u);\n"
    + "    bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);\n"
    + "    bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);\n"
    + "    bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);\n"
    + "    bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);\n"
    + "    float rdi = float(bits) * 2.3283064365386963e-10;\n"
    + "    return vec2(float(i) / float(N), rdi);\n"
    + "}\n"
    + "vec3 importance_sample_ggx(vec2 Xi, vec3 N, float roughness) {\n"
    + "    float a = roughness * roughness;\n"
    + "    float phi = 2.0 * PI * Xi.x;\n"
    + "    float cosTheta = sqrt((1.0 - Xi.y) / (1.0 + (a * a - 1.0) * Xi.y));\n"
    + "    float sinTheta = sqrt(1.0 - cosTheta * cosTheta);\n"
    + "    vec3 H = vec3(cos(phi) * sinTheta, sin(phi) * sinTheta, cosTheta);\n"
    + "    vec3 up = abs(N.y) < 0.999 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);\n"
    + "    vec3 tangent = normalize(cross(up, N));\n"
    + "    vec3 bitangent = cross(N, tangent);\n"
    + "    return normalize(tangent * H.x + bitangent * H.y + N * H.z);\n"
    + "}\n"
    + "void main() {\n"
    + "    float NdotV = v_uv.x;\n"
    + "    float roughness = v_uv.y;\n"
    + "    NdotV = max(NdotV, 0.0001);\n"
    + "    vec3 V = vec3(sqrt(1.0 - NdotV * NdotV), 0.0, NdotV);\n"
    + "    vec3 N = vec3(0.0, 0.0, 1.0);\n"
    + "    float A = 0.0;\n"
    + "    float B = 0.0;\n"
    + "    const int SAMPLE_COUNT = 1024;\n"
    + "    for (int i = 0; i < SAMPLE_COUNT; ++i) {\n"
    + "        vec2 Xi = hammersley(i, SAMPLE_COUNT);\n"
    + "        vec3 H = importance_sample_ggx(Xi, N, roughness);\n"
    + "        vec3 L = normalize(2.0 * dot(V, H) * H - V);\n"
    + "        float NdotL = max(L.z, 0.0);\n"
    + "        float NdotH = max(H.z, 0.0);\n"
    + "        float VdotH = max(dot(V, H), 0.0);\n"
    + "        if (NdotL > 0.0) {\n"
    + "            float G = geometry_smith(N, V, L, roughness);\n"
    + "            float Gvis = (G * VdotH) / (NdotH * NdotV);\n"
    + "            float Fc = pow(1.0 - VdotH, 5.0);\n"
    + "            A += (1.0 - Fc) * Gvis;\n"
    + "            B += Fc * Gvis;\n"
    + "        }\n"
    + "    }\n"
    + "    A /= float(SAMPLE_COUNT);\n"
    + "    B /= float(SAMPLE_COUNT);\n"
    + "    frag_color = vec4(A, B, 0.0, 1.0);\n"
    + "}\n"
)
class DynamicCubemapFilterMixin:
    def generate_irradiance(self, ctx: moderngl.Context):
        if self._irradiance_prog is None or self._cubemap_tex is None:
            return
        if self._irradiance_tex is None:
            return
        prev_fbo = None
        try:
            prev_fbo = ctx.fbo
        except Exception:
            prev_fbo = None
        prog = self._irradiance_prog
        irr_res = max(32, self.resolution // 4)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        vao = self._get_quad_vao(ctx, prog)
        if vao is None:
            _restore_framebuffer(ctx, prev_fbo)
            return
        try:
            self._cubemap_tex.use(0)
            prog["u_cubemap"].value = 0
        except Exception:
            _restore_framebuffer(ctx, prev_fbo)
            return
        for face in range(6):
            fx, fy, fz = _FACE_BASIS[face]
            fbo = self._irradiance_face_fbos[face]
            if fbo is None:
                continue
            fbo.use()
            fbo.viewport = (0, 0, irr_res, irr_res)
            if not _attach_cubemap_face(self._irradiance_tex.glo, face, 0):
                continue
            ctx.clear(0.0, 0.0, 0.0, 1.0)
            try:
                prog["u_face_x"].value = fx
                prog["u_face_y"].value = fy
                prog["u_face_z"].value = fz
            except Exception:
                continue
            self._cubemap_tex.use(0)
            vao.render(moderngl.TRIANGLES)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
    def generate_prefilter(self, ctx: moderngl.Context):
        if self._prefilter_prog is None or self._cubemap_tex is None:
            return
        prev_fbo = None
        try:
            prev_fbo = ctx.fbo
        except Exception:
            prev_fbo = None
        prog = self._prefilter_prog
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        vao = self._get_quad_vao(ctx, prog)
        if vao is None:
            ctx.enable(moderngl.DEPTH_TEST)
            ctx.enable(moderngl.CULL_FACE)
            _restore_framebuffer(ctx, prev_fbo)
            return
        try:
            self._cubemap_tex.use(0)
            prog["u_cubemap"].value = 0
        except Exception:
            ctx.enable(moderngl.DEPTH_TEST)
            ctx.enable(moderngl.CULL_FACE)
            _restore_framebuffer(ctx, prev_fbo)
            return
        for mip_idx, (mip_fbo, mip_tex, mip_res, mip_level) in enumerate(self._prefilter_fbos):
            roughness = mip_level / max(1, len(self._prefilter_fbos) - 1)
            for face in range(6):
                fx, fy, fz = _FACE_BASIS[face]
                mip_fbo.use()
                mip_fbo.viewport = (0, 0, mip_res, mip_res)
                if not _attach_cubemap_face(self._prefilter_tex.glo, face, mip_level):
                    continue
                ctx.clear(0.0, 0.0, 0.0, 1.0)
                try:
                    prog["u_roughness"].value = roughness
                    prog["u_face_x"].value = fx
                    prog["u_face_y"].value = fy
                    prog["u_face_z"].value = fz
                except Exception:
                    continue
                self._cubemap_tex.use(0)
                vao.render(moderngl.TRIANGLES)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
    def generate_brdf_lut(self, ctx: moderngl.Context):
        if self._brdf_prog is None or self._brdf_lut_fbo is None:
            return
        prev_fbo = None
        try:
            prev_fbo = ctx.fbo
        except Exception:
            prev_fbo = None
        brdf_res = 256
        self._brdf_lut_fbo.use()
        self._brdf_lut_fbo.viewport = (0, 0, brdf_res, brdf_res)
        ctx.clear(0.0, 0.0, 0.0, 1.0)
        ctx.disable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        vao = self._get_quad_vao(ctx, self._brdf_prog)
        if vao is not None:
            vao.render(moderngl.TRIANGLES)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.enable(moderngl.CULL_FACE)
        _restore_framebuffer(ctx, prev_fbo)
    def bind_ibl(self, prog: moderngl.Program, start_unit: int = 14):
        unit = start_unit
        if self._irradiance_tex is not None:
            self._irradiance_tex.use(unit)
            try:
                prog["u_irradiance_map"].value = unit
                prog["u_irradiance_map_Active"].value = 1
            except KeyError:
                pass
            unit += 1
        if self._prefilter_tex is not None:
            self._prefilter_tex.use(unit)
            try:
                prog["u_prefilter_map"].value = unit
                prog["u_prefilter_map_Active"].value = 1
            except KeyError:
                pass
            unit += 1
        if self._brdf_lut_tex is not None:
            self._brdf_lut_tex.use(unit)
            try:
                prog["u_brdf_lut"].value = unit
                prog["u_brdf_lut_Active"].value = 1
            except KeyError:
                pass
            unit += 1
        if "u_env_map_rotation" in prog:
            try:
                prog["u_env_map_rotation"].value = 0.0
            except Exception:
                pass
        return unit
