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
from core.renderer.meshd import SHADER_DIR
from core.renderer.prec import apply_precision
from core.renderer.shaderp.fallback import _HASH, _shader_glsl_version, program_with_fallback
_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_SHADER_SUBDIRS = ("materials", "internal", "compute", "include", "legacy")
def _resolve_shader_path(shader_path: str) -> str:
    if os.path.exists(shader_path):
        return shader_path
    shader_name = os.path.basename(shader_path)
    for sub in _SHADER_SUBDIRS:
        c = os.path.join(_ENGINE_ROOT, "core", "shaders", sub, shader_name)
        if os.path.exists(c):
            return c
    candidates = [
        os.path.join(_ENGINE_ROOT, shader_path),
        os.path.join(_ENGINE_ROOT, "core", "shaders", shader_path),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return shader_path
class ShaderManager:
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
            resolved_shader = _resolve_shader_path(shader_path if shader_path.endswith(".shader") else shader_path + ".shader")
            if os.path.exists(resolved_shader):
                prog = self._compile_shader_file_visit(resolved_shader, set())
                old = self._cache.get(shader_path)
                if old is not None and old is not prog:
                    try:
                        old.release()
                    except Exception:
                        pass
                self._cache[shader_path] = prog
                return prog
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
            vert_src = self._inject_uv_override(vert_src)
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
        return self._compile_shader_file_visit(shader_path, set())
    def _compile_shader_file_visit(self, shader_path: str,
                                   visited: set[str]) -> Optional[moderngl.Program]:
        task_id = self._compile_task(shader_path)
        task_start(task_id, f"Compiling shader {os.path.basename(shader_path)}...", fraction=None)
        try:
            from core.assets.matp import _extract_all_subshaders
            resolved = _resolve_shader_path(shader_path)
            norm = os.path.normpath(os.path.abspath(resolved)) if os.path.exists(resolved) else resolved
            if norm in visited:
                return None
            visited.add(norm)
            if shader_path in self._cache:
                return self._cache[shader_path]
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
                vert_src = self._inject_uv_override(vert_src)
                frag_src = self._inject_area_shadows(frag_src)
                frag_src = self._inject_caustics(frag_src)
                try:
                    vert_src = apply_precision(vert_src)
                except Exception:
                    pass
                try:
                    frag_src = apply_precision(frag_src)
                except Exception:
                    pass
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
            vert_src = self._inject_uv_override(vert_src)
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
            injection = ("layout(location = 3) in vec4 in_model0;\n" "layout(location = 4) in vec4 in_model1;\n" "layout(location = 5) in vec4 in_model2;\n" "layout(location = 6) in vec4 in_model3;\n" "layout(std430, binding = 4) readonly buffer InstanceModels { mat4 _ssbo_models[]; };\n" "layout(std430, binding = 5) readonly buffer InstanceIndices { int _ssbo_indices[]; };\n" "uniform int u_use_instancing;\n" "uniform mat4 u_model;\n" "uniform mat3 u_normal_matrix;\n" "mat4 _resolve_model() {\n" "    if (u_use_instancing == 1) return mat4(in_model0, in_model1, in_model2, in_model3);\n" "    if (u_use_instancing == 2) return _ssbo_models[_ssbo_indices[gl_InstanceID]];\n" "    return u_model;\n" "}\n" "mat3 _resolve_normal_matrix() {\n" "    if (u_use_instancing >= 1) return mat3(_resolve_model());\n" "    return u_normal_matrix;\n" "}\n" "\n")
        else:
            injection = ("layout(location = 3) in vec4 in_model0;\n" "layout(location = 4) in vec4 in_model1;\n" "layout(location = 5) in vec4 in_model2;\n" "layout(location = 6) in vec4 in_model3;\n" "uniform int u_use_instancing;\n" "uniform mat4 u_model;\n" "uniform mat3 u_normal_matrix;\n" "mat4 _resolve_model() {\n" "    if (u_use_instancing == 1) return mat4(in_model0, in_model1, in_model2, in_model3);\n" "    return u_model;\n" "}\n" "mat3 _resolve_normal_matrix() {\n" "    if (u_use_instancing >= 1) return mat3(_resolve_model());\n" "    return u_normal_matrix;\n" "}\n" "\n")
        ver_match = re.search(r'^[ \t]*' + _HASH + r'[ \t]*version[ \t]+\d+\w*[^\n]*\n', src, re.MULTILINE)
        if ver_match:
            pos = ver_match.end()
            return src[:pos] + injection + src[pos:]
        idx = src.find("\n")
        if idx >= 0:
            return src[:idx+1] + injection + src[idx+1:]
        return injection + src
    @staticmethod
    def _inject_uv_override(src: str) -> str:
        if "u_uv_scale" in src:
            return src
        if "in_uv" not in src:
            return src
        m = re.search(r'void\s+main\s*\([^)]*\)\s*\{', src)
        if not m:
            return src
        model_expr = None
        if "_resolve_model()" in src:
            model_expr = "_resolve_model()"
        elif re.search(r'\bu_model\b', src):
            model_expr = "u_model"
        use_world = model_expr is not None and re.search(r'\bin_normal\b', src) is not None
        decl = "uniform vec2 u_uv_scale;\nuniform vec2 u_uv_offset;\nuniform float u_uv_world_scale;\n"
        ver_match = re.search(r'^[ \t]*' + _HASH + r'[ \t]*version[ \t]+\d+\w*[^\n]*\n', src, re.MULTILINE)
        if ver_match:
            pos = ver_match.end()
            src = src[:pos] + decl + src[pos:]
            m = re.search(r'void\s+main\s*\([^)]*\)\s*\{', src)
            if not m:
                return src
        else:
            src = decl + src
            m = re.search(r'void\s+main\s*\([^)]*\)\s*\{', src)
            if not m:
                return src
        head = src[:m.end()]
        tail = src[m.end():]
        block = "\nvec2 _uv_ov = in_uv * u_uv_scale + u_uv_offset;\n"
        if use_world:
            block += "if (u_uv_world_scale > 0.5) {\n"
            block += "vec3 _uv_an = abs(in_normal);\n"
            block += "vec3 _uv_msc = vec3(length(" + model_expr + "[0].xyz), length(" + model_expr + "[1].xyz), length(" + model_expr + "[2].xyz));\n"
            block += "vec2 _uv_fs = vec2(_uv_msc.x, _uv_msc.y);\n"
            block += "if (_uv_an.y > _uv_an.x && _uv_an.y > _uv_an.z) { _uv_fs = vec2(_uv_msc.x, _uv_msc.z); }\n"
            block += "else if (_uv_an.x > _uv_an.z) { _uv_fs = vec2(_uv_msc.z, _uv_msc.y); }\n"
            block += "_uv_ov *= _uv_fs;\n}\n"
        tail = re.sub(r'\bin_uv\b', '_uv_ov', tail)
        return head + block + tail
    _INCLUDE_CANDIDATES = ("include", "")
    @staticmethod
    def _read_include(filename: str) -> str | None:
        for sub in ShaderManager._INCLUDE_CANDIDATES:
            include_path = os.path.join(_ENGINE_ROOT, "core", "shaders", sub, filename) if sub else os.path.join(_ENGINE_ROOT, "core", "shaders", filename)
            try:
                with open(include_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                continue
        return None
    @staticmethod
    def _inject_block(src: str, marker: str, include_src: str | None, missing_text: str) -> str:
        if marker not in src:
            return src
        if include_src is None:
            replacement = missing_text
        else:
            replacement = include_src
            if not replacement.endswith("\n"):
                replacement = replacement + "\n"
        lines = src.splitlines(True)
        out = []
        for line in lines:
            if line.strip() == marker:
                out.append(replacement)
            else:
                out.append(line)
        return "".join(out)
    @staticmethod
    def _inject_area_shadows(src: str) -> str:
        marker = "// @SHADOW_INCLUDE"
        if marker not in src:
            return src
        include_src = ShaderManager._read_include("area_shadows.glsl")
        if include_src is None:
            Logger.warning("Failed to read area_shadows.glsl")
        return ShaderManager._inject_block(src, marker, include_src, "// area shadows include failed to load\n")
    @staticmethod
    def _inject_caustics(src: str) -> str:
        marker = "// @CAUSTICS_INCLUDE"
        if marker not in src:
            return src
        include_src = ShaderManager._read_include("caustics.glsl")
        if include_src is None:
            Logger.warning("Failed to read caustics.glsl")
        return ShaderManager._inject_block(src, marker, include_src, "// caustics include failed to load\n")
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
