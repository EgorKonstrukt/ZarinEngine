from __future__ import annotations
import os
import moderngl
from typing import Optional
from core.logger import Logger
from editor.renderer.mesh_data import SHADER_DIR


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

    def _compile_vert_frag(self, shader_path: str) -> Optional[moderngl.Program]:
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
            prog = self._ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
            self._cache[shader_path] = prog
            return prog
        except Exception as e:
            Logger.error(f"Failed to compile shader '{shader_path}': {e}", e)
            self._cache[shader_path] = None
            return None

    def _compile_shader_file(self, shader_path: str) -> Optional[moderngl.Program]:
        """Compile a .shader file containing GLSLPROGRAM...ENDGLSL blocks."""
        from core.material import _extract_glsl_from_shader
        try:
            with open(shader_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            Logger.error(f"Failed to read '{shader_path}': {e}", e)
            self._cache[shader_path] = None
            return None
        result = _extract_glsl_from_shader(text)
        if not result:
            Logger.error(f"No valid GLSL found in '{shader_path}'")
            self._cache[shader_path] = None
            return None
        vert_src, frag_src = result
        try:
            prog = self._ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
            self._cache[shader_path] = prog
            return prog
        except Exception as e:
            Logger.error(f"Failed to compile shader '{shader_path}': {e}", e)
            self._cache[shader_path] = None
            return None

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
