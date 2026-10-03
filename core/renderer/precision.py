# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

import re
import time

RTC_KEY = "rendering.high_precision_rtc"
GPU_DOUBLE_KEY = "rendering.high_precision_gpu"

_FLAG_CACHE: dict = {}
_FLAG_TTL = 2.0
_FLAG_SUB_ID = None


def _drop_flag_cache(key, value):
    try:
        if key == RTC_KEY or key == GPU_DOUBLE_KEY:
            _FLAG_CACHE.pop(key, None)
    except Exception:
        pass


def _ensure_flag_subscription(cfg):
    global _FLAG_SUB_ID
    try:
        if id(cfg) == _FLAG_SUB_ID:
            return
        cfg.on_changed(_drop_flag_cache)
        _FLAG_SUB_ID = id(cfg)
    except Exception:
        pass


def _read_flag_uncached(key, default):
    try:
        from core.config.config import get_global_config
        cfg = get_global_config()
        if cfg is None:
            return default
        _ensure_flag_subscription(cfg)
        return bool(cfg.get(key, default))
    except Exception:
        return default


def _read_flag(key, default):
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    try:
        hit = _FLAG_CACHE.get(key)
        if hit is not None and (now - hit[1]) < _FLAG_TTL:
            return hit[0]
    except Exception:
        pass
    val = _read_flag_uncached(key, default)
    try:
        if len(_FLAG_CACHE) > 8:
            _FLAG_CACHE.clear()
        _FLAG_CACHE[key] = (val, now)
    except Exception:
        pass
    return val

_MARK = "ZARIN_HIGH_PRECISION"

_VERSION_LINE_RE = re.compile(r'^[ \t]*#[ \t]*version[ \t]+(\d+)[^\n]*', re.MULTILINE)
_VERSION_NUM_RE = re.compile(r'#[ \t]*version[ \t]+(\d+)')
_OUT_RE = re.compile(r'^[ \t]*out[ \t]+(?:highp[ \t]+|mediump[ \t]+|lowp[ \t]+)?(vec[234]|float|int|uint)[ \t]+(\w+)[ \t]*;', re.MULTILINE)
_UNIFORM_MAT_RE = re.compile(r'uniform[ \t]+(?:highp[ \t]+|mediump[ \t]+|lowp[ \t]+)?(mat[234])[ \t]+(\w+)[ \t]*(\[[^\]]*\])?[ \t]*;')
_BUFFER_BLOCK_RE = re.compile(r'buffer[ \t]+\w+[ \t]*\{([^}]*)\}', re.DOTALL)
_MAT_DECL_RE = re.compile(r'\b(mat[234])[ \t]+(\w+)[ \t]*(\[[^\]]*\])?[ \t]*;')
_FLOAT_RE = re.compile(r'\bfloat\b')
_VEC2_RE = re.compile(r'\bvec2\b')
_VEC3_RE = re.compile(r'\bvec3\b')
_VEC4_RE = re.compile(r'\bvec4\b')
_MAT2_RE = re.compile(r'\bmat2\b')
_MAT3_RE = re.compile(r'\bmat3\b')
_MAT4_RE = re.compile(r'\bmat4\b')
_TEXTURE_RE = re.compile(r'\btexture\s*\(')
_TEXTURE_LOD_RE = re.compile(r'\btextureLod\s*\(')
_GL_POS_RE = re.compile(r'gl_Position[ \t]*=[ \t]*([^;]+);')
_GL_DEPTH_RE = re.compile(r'gl_FragDepth[ \t]*=[ \t]*([^;]+);')


def _get_enabled(enabled=None):
    if enabled is not None:
        return bool(enabled)
    return _read_flag(GPU_DOUBLE_KEY, False)


def is_gpu_double_enabled(enabled=None):
    return _get_enabled(enabled)


def is_rtc_enabled(enabled=None):
    if enabled is not None:
        return bool(enabled)
    return _read_flag(RTC_KEY, False)


def _has_mark(src):
    return _MARK in src


def _upgrade_version(src):
    def _rep(m):
        try:
            v = int(m.group(1))
        except Exception:
            return m.group(0)
        if v >= 430:
            return m.group(0)
        return m.group(0).replace(m.group(1), "430", 1)
    return _VERSION_LINE_RE.sub(_rep, src, count=1)


def _header_enabled():
    return (
        "#define ZARIN_HIGH_PRECISION 1\n"
        "#define ZARIN_FLOAT64 1\n"
        "vec4 zTex(sampler2D s, vec2 uv) { return texture(s, uv); }\n"
        "vec4 zTex(sampler2D s, dvec2 uv) { return texture(s, vec2(uv)); }\n"
        "vec4 zTex(samplerCube s, vec3 d) { return texture(s, d); }\n"
        "vec4 zTex(samplerCube s, dvec3 d) { return texture(s, vec3(d)); }\n"
        "vec4 zTex(sampler2DArray s, vec3 uv) { return texture(s, uv); }\n"
        "vec4 zTex(sampler2DArray s, dvec3 uv) { return texture(s, vec3(uv)); }\n"
        "vec4 zTexLod(sampler2D s, vec2 uv, float lod) { return textureLod(s, uv, lod); }\n"
        "vec4 zTexLod(sampler2D s, dvec2 uv, double lod) { return textureLod(s, vec2(uv), float(lod)); }\n"
        "vec4 zTexLod(samplerCube s, vec3 d, float lod) { return textureLod(s, d, lod); }\n"
        "vec4 zTexLod(samplerCube s, dvec3 d, double lod) { return textureLod(s, vec3(d), float(lod)); }\n"
        "vec4 zTexLod(sampler2DArray s, vec3 uv, float lod) { return textureLod(s, uv, lod); }\n"
        "vec4 zTexLod(sampler2DArray s, dvec3 uv, double lod) { return textureLod(s, vec3(uv), float(lod)); }\n"
    )


def _inject_after_version(src, addition):
    m = _VERSION_LINE_RE.search(src)
    if m:
        pos = m.end()
        return src[:pos] + "\n" + addition + src[pos:]
    return addition + src


def _transform_one_line(line):
    line = _MAT2_RE.sub("dmat2", line)
    line = _MAT3_RE.sub("dmat3", line)
    line = _MAT4_RE.sub("dmat4", line)
    line = _VEC2_RE.sub("dvec2", line)
    line = _VEC3_RE.sub("dvec3", line)
    line = _VEC4_RE.sub("dvec4", line)
    line = _FLOAT_RE.sub("double", line)
    return line


def _transform_types(src):
    lines = src.splitlines(True)
    out = []
    in_block = False
    depth = 0
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            out.append(line)
            continue
        if not in_block:
            if ("buffer" in line and "{" in line) or (s.startswith("struct") and "{" in line):
                in_block = True
                depth = line.count("{") - line.count("}")
                out.append(line)
                if depth <= 0:
                    in_block = False
                continue
            if "uniform" in line:
                out.append(line)
                continue
            if s.startswith("layout"):
                out.append(line)
                continue
            if (s.startswith("in ") or s.startswith("in\t") or s.startswith("out ") or s.startswith("out\t") or s.startswith("attribute") or s.startswith("varying")) and "(" not in line:
                out.append(line)
                continue
            out.append(_transform_one_line(line))
        else:
            depth = depth + line.count("{") - line.count("}")
            out.append(line)
            if depth <= 0:
                in_block = False
    return "".join(out)


def _collect_matrices(src):
    result = {}
    for m in _UNIFORM_MAT_RE.finditer(src):
        t = m.group(1)
        n = m.group(2)
        arr = m.group(3)
        result[n] = (t, bool(arr))
    for b in _BUFFER_BLOCK_RE.finditer(src):
        body = b.group(1)
        for m in _MAT_DECL_RE.finditer(body):
            t = m.group(1)
            n = m.group(2)
            arr = m.group(3)
            if n not in result:
                result[n] = (t, bool(arr))
    return result


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
        if s.startswith("#") or "uniform" in line or s.startswith("layout") or s.startswith("struct"):
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
        return _inject_after_version(src, "#define ZARIN_HIGH_PRECISION 0\n")
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
