# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import moderngl
_INSTANCE_ATTRS = ("in_model0", "in_model1", "in_model2", "in_model3")
def _shadow_supports_instancing(prog: moderngl.Program) -> bool:
    try:
        locs = prog._attribute_locations
        for a in _INSTANCE_ATTRS:
            if locs.get(a, -1) < 0:
                return False
        return True
    except Exception:
        return False
def _make_shadow_instanced_vao(ctx: moderngl.Context, prog: moderngl.Program, mesh, instance_vbo: moderngl.Buffer, pos_vbo: moderngl.Buffer) -> moderngl.VertexArray:
    ibo = getattr(mesh, '_ibo', None)
    content = [(pos_vbo, '3f', 'in_position')]
    if _shadow_supports_instancing(prog):
        content.append((instance_vbo, '4f 4f 4f 4f /i', 'in_model0', 'in_model1', 'in_model2', 'in_model3'))
    if ibo is not None:
        return ctx.vertex_array(prog, content, ibo)
    return ctx.vertex_array(prog, content)
