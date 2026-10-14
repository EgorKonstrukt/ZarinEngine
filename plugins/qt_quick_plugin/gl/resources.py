# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
try:
    from core.foundation.logger import Logger
    _HAS_LOGGER = True
except Exception:
    Logger = None
    _HAS_LOGGER = False
try:
    import moderngl
    _HAS_GL = True
except Exception:
    moderngl = None
    _HAS_GL = False
QUICK_VERT = chr(35) + "version 330 core\nlayout(location = 0) in vec3 in_position;\nlayout(location = 1) in vec2 in_uv;\nuniform mat4 u_model;\nuniform mat4 u_view;\nuniform mat4 u_proj;\nout vec2 v_uv;\nvoid main() {\n    v_uv = in_uv;\n    gl_Position = u_proj * u_view * u_model * vec4(in_position, 1.0);\n}\n"
QUICK_FRAG = chr(35) + "version 330 core\nin vec2 v_uv;\nuniform sampler2D u_texture;\nuniform float u_opacity;\nuniform vec4 u_tint;\nout vec4 frag_color;\nvoid main() {\n    vec4 tex = texture(u_texture, v_uv);\n    vec3 col = tex.rgb * u_tint.rgb;\n    float alpha = tex.a * u_opacity * u_tint.a;\n    if (alpha < 0.01) {\n        discard;\n    }\n    frag_color = vec4(col, alpha);\n}\n"
def qimage_to_bytes(img):
    try:
        conv = img.convertToFormat(img.Format.Format_RGBA8888)
    except Exception:
        try:
            from PyQt6.QtGui import QImage as _QI
            conv = img.convertToFormat(_QI.Format.Format_RGBA8888)
        except Exception:
            return (None, 0, 0)
    try:
        w = int(conv.width())
        h = int(conv.height())
    except Exception:
        return (None, 0, 0)
    if w <= 0 or h <= 0:
        return (None, 0, 0)
    try:
        bits = conv.constBits()
        try:
            bits.setsize(conv.sizeInBytes())
        except Exception:
            pass
        try:
            raw = bytes(bits.asarray())
        except Exception:
            raw = bytes(bits)
        expect = w * h * 4
        if len(raw) < expect:
            return (None, 0, 0)
        return (raw[:expect], w, h)
    except Exception:
        pass
    try:
        ptr = conv.bits()
        try:
            ptr.setsize(conv.sizeInBytes())
        except Exception:
            pass
        raw = bytes(ptr.asarray())
        expect = w * h * 4
        if len(raw) < expect:
            return (None, 0, 0)
        return (raw[:expect], w, h)
    except Exception:
        return (None, 0, 0)
