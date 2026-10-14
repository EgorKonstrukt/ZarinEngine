# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import re
import moderngl
from core.foundation.logger import Logger
from core.renderer.prec import apply_precision
_HASH = chr(35)
_SSBO_BLOCK_RE = re.compile(
    r'layout\s*\([^)]*std430[^)]*\)[^;]*?buffer\s+\w+\s*\{[^}]*\}\s*;',
    re.DOTALL
)
_VERSION_RE = re.compile(r'^[ \t]*' + _HASH + r'[ \t]*version[ \t]+\d+[^\n]*', re.MULTILINE)
def _shader_glsl_version(src: str) -> int:
    m = re.search(_HASH + r'[ \t]*version[ \t]+(\d+)', src)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0
def downgrade_to_330(src: str) -> str:
    out = _VERSION_RE.sub(_HASH + 'version 330 core', src, count=1)
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
    orig_v = vertex_shader
    orig_f = fragment_shader
    orig_g = geometry_shader
    try:
        vert_p = apply_precision(vertex_shader) if vertex_shader is not None else None
    except Exception:
        vert_p = vertex_shader
    try:
        frag_p = apply_precision(fragment_shader) if fragment_shader is not None else None
    except Exception:
        frag_p = fragment_shader
    try:
        geom_p = apply_precision(geometry_shader) if geometry_shader is not None else None
    except Exception:
        geom_p = geometry_shader
    first_err = None
    try:
        if geom_p is not None:
            return ctx.program(vertex_shader=vert_p,
                               fragment_shader=frag_p,
                               geometry_shader=geom_p)
        return ctx.program(vertex_shader=vert_p,
                           fragment_shader=frag_p)
    except Exception as e_first:
        first_err = e_first
    try:
        if geom_p is not None and (vert_p != orig_v or frag_p != orig_f or geom_p != orig_g):
            try:
                if orig_g is not None:
                    return ctx.program(vertex_shader=orig_v,
                                       fragment_shader=orig_f,
                                       geometry_shader=orig_g)
                return ctx.program(vertex_shader=orig_v,
                                   fragment_shader=orig_f)
            except Exception:
                pass
        elif vert_p != orig_v or frag_p != orig_f:
            try:
                return ctx.program(vertex_shader=orig_v,
                                   fragment_shader=orig_f)
            except Exception:
                pass
    except Exception:
        pass
    try:
        vert_fb = downgrade_to_330(orig_v)
        frag_fb = downgrade_to_330(orig_f)
        geom_fb = downgrade_to_330(orig_g) if orig_g is not None else None
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
        for _src in (vertex_shader, fragment_shader, geometry_shader):
            if _src and re.search(r'\bbuffer\s+\w+\s*\{', _src):
                if first_err is not None:
                    Logger.warning(f"Shader '{label}' high-precision attempt: {first_err}")
                Logger.warning(f"Shader '{label}' requires OpenGL 4.3+ storage buffers, feature unavailable")
                return None
        if first_err is not None:
            Logger.error(f"Failed to compile shader '{label}': {e} | high-precision attempt: {first_err}", e)
        else:
            Logger.error(f"Failed to compile shader '{label}': {e}", e)
        return None
