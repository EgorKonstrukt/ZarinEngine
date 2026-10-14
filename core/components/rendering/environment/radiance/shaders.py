# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
_FULLSCREEN_VERT = (
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
_FULLSCREEN_FRAG = (
    "\n"
    + chr(35) + "version 330 core\n"
    + "in vec2 v_uv;\n"
    + "uniform sampler2D u_tex;\n"
    + "out vec4 frag_color;\n"
    + "void main() {\n"
    + "    frag_color = texture(u_tex, v_uv);\n"
    + "}\n"
)
