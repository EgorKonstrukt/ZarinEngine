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
_VERSION_LINE_RE = re.compile(r'^[ \t]*' + chr(35) + r'[ \t]*version[ \t]+(\d+)[^\n]*', re.MULTILINE)
_VERSION_NUM_RE = re.compile(chr(35) + r'[ \t]*version[ \t]+(\d+)')
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
        chr(35) + "define ZARIN_HIGH_PRECISION 1\n"
        + chr(35) + "define ZARIN_FLOAT64 1\n"
        + "vec4 zTex(sampler2D s, vec2 uv) { return texture(s, uv); }\n"
        + "vec4 zTex(sampler2D s, dvec2 uv) { return texture(s, vec2(uv)); }\n"
        + "vec4 zTex(samplerCube s, vec3 d) { return texture(s, d); }\n"
        + "vec4 zTex(samplerCube s, dvec3 d) { return texture(s, vec3(d)); }\n"
        + "vec4 zTex(sampler2DArray s, vec3 uv) { return texture(s, uv); }\n"
        + "vec4 zTex(sampler2DArray s, dvec3 uv) { return texture(s, vec3(uv)); }\n"
        + "vec4 zTexLod(sampler2D s, vec2 uv, float lod) { return textureLod(s, uv, lod); }\n"
        + "vec4 zTexLod(sampler2D s, dvec2 uv, double lod) { return textureLod(s, vec2(uv), float(lod)); }\n"
        + "vec4 zTexLod(samplerCube s, vec3 d, float lod) { return textureLod(s, d, lod); }\n"
        + "vec4 zTexLod(samplerCube s, dvec3 d, double lod) { return textureLod(s, vec3(d), float(lod)); }\n"
        + "vec4 zTexLod(sampler2DArray s, vec3 uv, float lod) { return textureLod(s, uv, lod); }\n"
        + "vec4 zTexLod(sampler2DArray s, dvec3 uv, double lod) { return textureLod(s, vec3(uv), float(lod)); }\n"
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
        if s.startswith(chr(35)):
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
