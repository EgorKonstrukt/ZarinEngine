# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import re
from core.renderer.prec.flags import _get_enabled, _has_mark, _upgrade_version, _header_enabled, _inject_after_version, _transform_types, _collect_matrices
_OUT_RE = re.compile(r'^[ \t]*out[ \t]+(?:highp[ \t]+|mediump[ \t]+|lowp[ \t]+)?(vec[234]|float|int|uint)[ \t]+(\w+)[ \t]*;', re.MULTILINE)
_TEXTURE_RE = re.compile(r'\btexture\s*\(')
_TEXTURE_LOD_RE = re.compile(r'\btextureLod\s*\(')
_GL_POS_RE = re.compile(r'gl_Position[ \t]*=[ \t]*([^;]+);')
_GL_DEPTH_RE = re.compile(r'gl_FragDepth[ \t]*=[ \t]*([^;]+);')
def _wrap_array_line(line, n, w):
    res = ""
    i = 0
    L = len(line)
    while i < L:
        j = line.find(n, i)
        if j < 0:
            res = res + line[i:]
            break
        before = line[j - 1] if j > 0 else " "
        after_idx = j + len(n)
        if (before.isalnum() or before == "_") or (after_idx < L and (line[after_idx].isalnum() or line[after_idx] == "_")):
            res = res + line[i:after_idx]
            i = after_idx
            continue
        k = after_idx
        while k < L and (line[k] == " " or line[k] == "\t"):
            k = k + 1
        if k >= L or line[k] != "[":
            res = res + line[i:after_idx]
            i = after_idx
            continue
        depth = 0
        p = k
        while p < L:
            if line[p] == "[":
                depth = depth + 1
            elif line[p] == "]":
                depth = depth - 1
                if depth == 0:
                    break
            p = p + 1
        if depth != 0:
            res = res + line[i:]
            break
        inner = line[k:p + 1]
        res = res + line[i:j] + w + "(" + n + inner + ")"
        i = p + 1
    return res
def _wrap_matrices(src, matrices):
    lines = src.splitlines(True)
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith(chr(35)) or "uniform" in line or s.startswith("layout") or s.startswith("struct"):
            out.append(line)
            continue
        if (s.startswith("in ") or s.startswith("out ")) and "(" not in line:
            out.append(line)
            continue
        cur = line
        for n, (t, is_arr) in matrices.items():
            if n not in cur:
                continue
            if t == "mat4":
                w = "dmat4"
            elif t == "mat3":
                w = "dmat3"
            else:
                w = "dmat2"
            if is_arr:
                cur = _wrap_array_line(cur, n, w)
            else:
                pat = re.compile(r'(?<!dmat4\()(?<!dmat3\()(?<!dmat2\()\b' + re.escape(n) + r'\b')
                cur = pat.sub(w + "(" + n + ")", cur)
        out.append(cur)
    return "".join(out)
def _patch_imagestore(src):
    out = []
    i = 0
    L = len(src)
    key = "imageStore"
    while i < L:
        j = src.find(key, i)
        if j < 0:
            out.append(src[i:])
            break
        before = src[j - 1] if j > 0 else " "
        if before.isalnum() or before == "_":
            out.append(src[i:j + len(key)])
            i = j + len(key)
            continue
        k = j + len(key)
        while k < L and src[k] in " \t\r\n":
            k = k + 1
        if k >= L or src[k] != "(":
            out.append(src[i:k])
            i = k
            continue
        depth = 0
        args = []
        cur_start = k + 1
        p = k
        while p < L:
            c = src[p]
            if c == "(":
                depth = depth + 1
            elif c == ")":
                depth = depth - 1
                if depth == 0:
                    args.append(src[cur_start:p])
                    break
            elif c == "," and depth == 1:
                args.append(src[cur_start:p])
                cur_start = p + 1
            p = p + 1
        if depth != 0 or len(args) != 3:
            out.append(src[i:k + 1])
            i = k + 1
            continue
        a2 = args[2].strip()
        if a2.startswith("vec4("):
            out.append(src[i:j] + "imageStore(" + args[0] + "," + args[1] + "," + a2 + ")")
        else:
            out.append(src[i:j] + "imageStore(" + args[0] + "," + args[1] + ",vec4(" + a2 + "))")
        i = p + 1
    return "".join(out)
def _patch_outputs(src):
    outs = []
    for m in _OUT_RE.finditer(src):
        outs.append((m.group(1), m.group(2)))
    cur = src
    cur = cur.replace("gl_FragCoord", "dvec4(gl_FragCoord)")
    cur = cur.replace("dvec4(dvec4(gl_FragCoord))", "dvec4(gl_FragCoord)")
    cur = cur.replace("gl_PointCoord", "dvec2(gl_PointCoord)")
    cur = cur.replace("dvec2(dvec2(gl_PointCoord))", "dvec2(gl_PointCoord)")
    cur = _patch_imagestore(cur)
    def _pos_rep(m):
        inner = m.group(1).strip()
        if inner.startswith("vec4(") and inner.endswith(")"):
            return m.group(0)
        return "gl_Position=vec4(" + inner + ");"
    cur = _GL_POS_RE.sub(_pos_rep, cur)
    def _depth_rep(m):
        inner = m.group(1).strip()
        if inner.startswith("float(") and inner.endswith(")"):
            return m.group(0)
        return "gl_FragDepth=float(" + inner + ");"
    cur = _GL_DEPTH_RE.sub(_depth_rep, cur)
    for t, n in outs:
        if t == "vec4":
            conv = "vec4"
        elif t == "vec3":
            conv = "vec3"
        elif t == "vec2":
            conv = "vec2"
        elif t == "float":
            conv = "float"
        elif t == "int":
            conv = "int"
        else:
            conv = "uint"
        pat = re.compile(r'(?<![\w])' + re.escape(n) + r'[ \t]*=[ \t]*([^;]+);')
        def _mk(m, _c=conv, _n=n):
            inner = m.group(1).strip()
            if inner.startswith(_c + "(") and inner.endswith(")"):
                return m.group(0)
            return _n + "=" + _c + "(" + inner + ");"
        cur = pat.sub(_mk, cur)
    return cur
def _texture_replace(src):
    cur = _TEXTURE_LOD_RE.sub("zTexLod(", src)
    cur = _TEXTURE_RE.sub("zTex(", cur)
    return cur
def apply_precision(src, enabled=None):
    flag = _get_enabled(enabled)
    if not src:
        return src
    if _has_mark(src):
        return src
    if not flag:
        return _inject_after_version(src, chr(35) + "define ZARIN_HIGH_PRECISION 0\n")
    cur = src
    cur = _texture_replace(cur)
    cur = _upgrade_version(cur)
    cur = _transform_types(cur)
    matrices = _collect_matrices(src)
    if matrices:
        cur = _wrap_matrices(cur, matrices)
    cur = _patch_outputs(cur)
    cur = _inject_after_version(cur, _header_enabled())
    return cur
def apply_vertex_shader(src, enabled=None):
    return apply_precision(src, enabled)
def apply_fragment_shader(src, enabled=None):
    return apply_precision(src, enabled)
def apply_geometry_shader(src, enabled=None):
    return apply_precision(src, enabled)
def apply_compute_shader(src, enabled=None):
    return apply_precision(src, enabled)
def is_precision_mark_present(src):
    return _has_mark(src)
_hooks_installed = False
_precision_fallback_warned = False
def _note_float_fallback():
    global _precision_fallback_warned
    if _precision_fallback_warned:
        return
    _precision_fallback_warned = True
    try:
        if _get_enabled():
            from core.foundation.logger import Logger
            Logger.warning("High-precision shaders unsupported by GPU driver, using float fallback")
    except Exception:
        pass
def install_precision_hooks():
    global _hooks_installed
    if _hooks_installed:
        return True
    try:
        import moderngl
    except Exception:
        return False
    try:
        ctx_cls = moderngl.Context
    except Exception:
        return False
    try:
        orig_program = ctx_cls.program
    except Exception:
        orig_program = None
    try:
        orig_compute = ctx_cls.compute_shader
    except Exception:
        orig_compute = None
    if orig_program is None and orig_compute is None:
        return False
    if getattr(ctx_cls, "_zarin_precision_hooked", False):
        _hooks_installed = True
        return True
    def _wrapped_program(self, *args, **kwargs):
        originals = {}
        try:
            for stage_key in ("vertex_shader", "fragment_shader", "geometry_shader", "tess_control_shader", "tess_evaluation_shader"):
                stage_src = kwargs.get(stage_key)
                if isinstance(stage_src, str):
                    try:
                        new_src = apply_precision(stage_src)
                    except Exception:
                        continue
                    if new_src != stage_src:
                        originals[stage_key] = stage_src
                        kwargs[stage_key] = new_src
        except Exception:
            pass
        try:
            return orig_program(self, *args, **kwargs)
        except Exception:
            if not originals:
                raise
            for stage_key, stage_src in originals.items():
                kwargs[stage_key] = stage_src
            try:
                prog = orig_program(self, *args, **kwargs)
            except Exception:
                raise
            _note_float_fallback()
            return prog
    def _wrapped_compute(self, *args, **kwargs):
        orig_src = None
        src_is_arg = False
        try:
            if args and isinstance(args[0], str):
                try:
                    new_src = apply_precision(args[0])
                except Exception:
                    new_src = None
                if new_src is not None and new_src != args[0]:
                    orig_src = args[0]
                    src_is_arg = True
                    args = (new_src,) + args[1:]
            elif isinstance(kwargs.get("source"), str):
                try:
                    new_src = apply_precision(kwargs["source"])
                except Exception:
                    new_src = None
                if new_src is not None and new_src != kwargs["source"]:
                    orig_src = kwargs["source"]
                    kwargs["source"] = new_src
        except Exception:
            pass
        try:
            return orig_compute(self, *args, **kwargs)
        except Exception:
            if orig_src is None:
                raise
            try:
                if src_is_arg:
                    prog = orig_compute(self, *((orig_src,) + args[1:]), **kwargs)
                else:
                    kwargs["source"] = orig_src
                    prog = orig_compute(self, *args, **kwargs)
            except Exception:
                raise
            _note_float_fallback()
            return prog
    try:
        if orig_program is not None:
            ctx_cls.program = _wrapped_program
        if orig_compute is not None:
            ctx_cls.compute_shader = _wrapped_compute
        ctx_cls._zarin_precision_hooked = True
        _hooks_installed = True
        return True
    except Exception:
        return False
