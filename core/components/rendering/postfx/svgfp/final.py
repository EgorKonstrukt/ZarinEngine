# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
SVGF_FINAL_FRAG = """
\x23version 330 core
uniform sampler2D u_input;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    frag_color = texture(u_input, v_uv);
}
"""
