# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import os
import re
from typing import Optional

import moderngl

from core.foundation.logger import Logger
from core.foundation.progress import notify_error, task_complete, task_start
from core.renderer.mesh_data import SHADER_DIR

_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SSBO_BLOCK_RE = re.compile(
    r'layout\s*\([^)]*std430[^)]*\)[^;]*?buffer\s+\w+\s*\{[^}]*\}\s*;',
    re.DOTALL
)
_VERSION_RE = re.compile(r'^[ \t]*#[ \t]*version[ \t]+\d+[^\n]*', re.MULTILINE)


def _shader_glsl_version(src: str) -> int:
    m = re.search(r'#[ \t]*version[ \t]+(\d+)', src)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def downgrade_to_330(src: str) -> str:
    out = _VERSION_RE.sub('#version 330 core', src, count=1)
    out = _SSBO_BLOCK_RE.sub('', out)
    out = out.replace(
        '((u_use_instancing == 2 || u_use_instancing == 3) ? _ssbo_models[_ssbo_indices[gl_InstanceID]] : u_model)',
        'u_model')
    out = out.replace(
        '(u_use_instancing == 2 || u_use_instancing == 3) ? _ssbo_models[_ssbo_indices[gl_InstanceID]] : u_model',
        'u_model')
    out = out.replace(
        '((u_use_instancing == 2) ? _ssbo_models[_ssbo_indices[gl_InstanceID]] : u_model)',
        'u_model')
    out = out.replace(
        '(u_use_instancing == 2) ? _ssbo_models[_ssbo_indices[gl_InstanceID]] : u_model',
        'u_model')
    out = out.replace('int idx = indices[gl_InstanceID];', 'int idx = 0;')
    out = out.replace('model = models[idx];', 'model = u_model;')
    out = out.replace('skin += bw * u_bone_matrices[bi];', 'skin += bw * mat4(1.0);')
    out = out.replace('if (u_use_skinning == 1)', 'if (false)')
    return out


def program_with_fallback(ctx: moderngl.Context, vertex_shader: str,
                           fragment_shader: str, geometry_shader: str | None = None,
                           label: str = "shader") -> moderngl.Program | None:
    try:
        if geometry_shader is not None:
            return ctx.program(vertex_shader=vertex_shader,
                               fragment_shader=fragment_shader,
                               geometry_shader=geometry_shader)
        return ctx.program(vertex_shader=vertex_shader,
                           fragment_shader=fragment_shader)
    except Exception:
        pass
    try:
        vert_fb = downgrade_to_330(vertex_shader)
        frag_fb = downgrade_to_330(fragment_shader)
        geom_fb = downgrade_to_330(geometry_shader) if geometry_shader is not None else None
        if geom_fb is not None:
            prog = ctx.program(vertex_shader=vert_fb,
                               fragment_shader=frag_fb,
                               geometry_shader=geom_fb)
        else:
            prog = ctx.program(vertex_shader=vert_fb,
                               fragment_shader=frag_fb)
        Logger.warning(f"Shader '{label}' compiled with 330 fallback")
        return prog
    except Exception as e:
        Logger.error(f"Failed to compile shader '{label}': {e}", e)
        return None


def _resolve_shader_path(shader_path: str) -> str:
    if os.path.isabs(shader_path) or os.path.exists(shader_path):
        return shader_path
    candidates = [
        os.path.join(_ENGINE_ROOT, shader_path),
        os.path.join(_ENGINE_ROOT, "core", "shaders", shader_path),
    ]
    shader_name = os.path.basename(shader_path)
    if shader_name != shader_path:
        candidates.append(os.path.join(_ENGINE_ROOT, "core", "shaders", shader_name))
    for c in candidates:
        if os.path.exists(c):
            return c
    return shader_path


class ShaderManager:
    """Compiles, caches and retrieves shader programs."""

    def __init__(self, ctx: moderngl.Context):
        self._ctx = ctx
        self._cache: dict[str, Optional[moderngl.Program]] = {}

    def get_or_compile(self, shader_path: str) -> Optional[moderngl.Program]:
        if not shader_path:
            return None
        if shader_path in self._cache:
            return self._cache[shader_path]
        ext = os.path.splitext(shader_path)[1].lower()
        if ext == ".shader":
            return self._compile_shader_file(shader_path)
        return self._compile_vert_frag(shader_path)

    def _compile_task(self, shader_path: str) -> str:
        return f"shader:{shader_path}"

    def _compile_vert_frag(self, shader_path: str) -> Optional[moderngl.Program]:
        task_id = self._compile_task(shader_path)
        task_start(task_id, f"Compiling shader {os.path.basename(shader_path)}...", fraction=None)
        try:
            base = os.path.join(SHADER_DIR, shader_path)
            vert_file = f"{base}.vert"
            frag_file = f"{base}.frag"
            if not os.path.exists(vert_file):
                vert_file = f"{base}_vert.glsl"
            if not os.path.exists(frag_file):
                frag_file = f"{base}_frag.glsl"
            with open(vert_file, "r") as f:
                vert_src = f.read()
            with open(frag_file, "r") as f:
                frag_src = f.read()
            vert_src = self._inject_instancing_vertex(vert_src)
            frag_src = self._inject_area_shadows(frag_src)
            frag_src = self._inject_caustics(frag_src)
            prog = program_with_fallback(self._ctx, vert_src, frag_src,
                                         label=os.path.basename(shader_path))
            self._cache[shader_path] = prog
            if prog is None:
                notify_error(f"Failed to compile shader {os.path.basename(shader_path)}")
            return prog
        except Exception as e:
            Logger.error(f"Failed to compile shader '{shader_path}': {e}", e)
            notify_error(f"Failed to compile shader {os.path.basename(shader_path)}")
            self._cache[shader_path] = None
            return None
        finally:
            task_complete(task_id)

    def _compile_shader_file(self, shader_path: str) -> Optional[moderngl.Program]:
        """Compile a .shader file containing GLSLPROGRAM...ENDGLSL blocks."""
        return self._compile_shader_file_visit(shader_path, set())

    def _compile_shader_file_visit(self, shader_path: str,
                                   visited: set[str]) -> Optional[moderngl.Program]:
        task_id = self._compile_task(shader_path)
        task_start(task_id, f"Compiling shader {os.path.basename(shader_path)}...", fraction=None)
        try:
            from core.assets.material import _extract_all_subshaders
            resolved = _resolve_shader_path(shader_path)
            norm = os.path.normpath(os.path.abspath(resolved)) if os.path.exists(resolved) else resolved
            if norm in visited:
                return None
            visited.add(norm)
            try:
                with open(resolved, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                Logger.error(f"Failed to read '{shader_path}': {e}", e)
                notify_error(f"Failed to compile shader {os.path.basename(shader_path)}")
                self._cache[shader_path] = None
                return None
            subshaders = _extract_all_subshaders(text)
            if not subshaders:
                Logger.error(f"No valid GLSL found in '{shader_path}'")
                notify_error(f"No valid GLSL in {os.path.basename(shader_path)}")
                self._cache[shader_path] = None
                return None
            for vert_src, frag_src in subshaders:
                vert_src = self._inject_instancing_vertex(vert_src)
                frag_src = self._inject_area_shadows(frag_src)
                frag_src = self._inject_caustics(frag_src)
                try:
                    prog = self._ctx.program(vertex_shader=vert_src,
                                             fragment_shader=frag_src)
                    self._cache[shader_path] = prog
                    return prog
                except Exception:
                    continue
            fallback_match = re.search(r'Fallback\s+"([^"]*)"', text)
            if fallback_match:
                fallback_name = fallback_match.group(1).strip()
                if fallback_name and fallback_name.lower() != "none":
                    fallback_file = fallback_name.split("/")[-1]
                    if not fallback_file.lower().endswith(".shader"):
                        fallback_file += ".shader"
                    fallback_prog = self._compile_shader_file_visit(fallback_file, visited)
                    if fallback_prog is not None:
                        self._cache[shader_path] = fallback_prog
                        return fallback_prog
            vert_src, frag_src = subshaders[0]
            vert_src = self._inject_instancing_vertex(vert_src)
            frag_src = self._inject_area_shadows(frag_src)
            frag_src = self._inject_caustics(frag_src)
            prog = program_with_fallback(self._ctx, vert_src, frag_src,
                                         label=os.path.basename(shader_path))
            self._cache[shader_path] = prog
            if prog is None:
                Logger.error(f"Failed to compile shader '{shader_path}'")
                notify_error(f"Failed to compile shader {os.path.basename(shader_path)}")
            return prog
        finally:
            task_complete(task_id)

    @staticmethod
    def _inject_instancing_vertex(src: str) -> str:
        if "in_model0" in src:
            return src
        if "u_model" not in src and "u_normal_matrix" not in src:
            return src
        src = src.replace("uniform mat4 u_model;", "")
        src = src.replace("uniform mat3 u_normal_matrix;", "")
        src = re.sub(r'\bu_model\b', '_resolve_model()', src)
        src = re.sub(r'\bu_normal_matrix\b', '_resolve_normal_matrix()', src)
        if _shader_glsl_version(src) >= 430:
            injection = """layout(location = 3) in vec4 in_model0;
layout(location = 4) in vec4 in_model1;
layout(location = 5) in vec4 in_model2;
layout(location = 6) in vec4 in_model3;
layout(std430, binding = 4) readonly buffer InstanceModels { mat4 _ssbo_models[]; };
layout(std430, binding = 5) readonly buffer InstanceIndices { int _ssbo_indices[]; };
uniform int u_use_instancing;
uniform mat4 u_model;
uniform mat3 u_normal_matrix;
mat4 _resolve_model() {
    if (u_use_instancing == 1) return mat4(in_model0, in_model1, in_model2, in_model3);
    if (u_use_instancing == 2) return _ssbo_models[_ssbo_indices[gl_InstanceID]];
    return u_model;
}
mat3 _resolve_normal_matrix() {
    if (u_use_instancing >= 1) return transpose(inverse(mat3(_resolve_model())));
    return u_normal_matrix;
}

"""
        else:
            injection = """layout(location = 3) in vec4 in_model0;
layout(location = 4) in vec4 in_model1;
layout(location = 5) in vec4 in_model2;
layout(location = 6) in vec4 in_model3;
uniform int u_use_instancing;
uniform mat4 u_model;
uniform mat3 u_normal_matrix;
mat4 _resolve_model() {
    if (u_use_instancing == 1) return mat4(in_model0, in_model1, in_model2, in_model3);
    return u_model;
}
mat3 _resolve_normal_matrix() {
    if (u_use_instancing >= 1) return transpose(inverse(mat3(_resolve_model())));
    return u_normal_matrix;
}

"""
        ver_match = re.search(r'^[ \t]*#[ \t]*version[ \t]+\d+\w*[^\n]*\n', src, re.MULTILINE)
        if ver_match:
            pos = ver_match.end()
            return src[:pos] + injection + src[pos:]
        idx = src.find("\n")
        if idx >= 0:
            return src[:idx+1] + injection + src[idx+1:]
        return injection + src

    @staticmethod
    def _inject_area_shadows(src: str) -> str:
        marker = "// @SHADOW_INCLUDE"
        if marker not in src:
            return src
        include_path = os.path.join(_ENGINE_ROOT, "core", "shaders", "area_shadows.glsl")
        try:
            with open(include_path, "r", encoding="utf-8") as f:
                include_src = f.read()
        except Exception as e:
            Logger.warning(f"Failed to read area_shadows.glsl: {e}")
            return src.replace(marker, "// area shadows include failed to load")
        return src.replace(marker, include_src)

    @staticmethod
    def _inject_caustics(src: str) -> str:
        marker = "// @CAUSTICS_INCLUDE"
        if marker not in src:
            return src
        include_path = os.path.join(_ENGINE_ROOT, "core", "shaders", "caustics.glsl")
        try:
            with open(include_path, "r", encoding="utf-8") as f:
                include_src = f.read()
        except Exception as e:
            Logger.warning(f"Failed to read caustics.glsl: {e}")
            return src.replace(marker, "// caustics include failed to load")
        return src.replace(marker, include_src)

    def store(self, key: str, prog: moderngl.Program):
        self._cache[key] = prog

    def release(self):
        for prog in self._cache.values():
            if prog:
                try:
                    prog.release()
                except Exception:
                    pass
        self._cache.clear()
