# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.NodeGraphQt import BaseNode


class _ShaderNode(BaseNode):
    __identifier__ = 'zarin.shader'
    NODE_CATEGORY = "shader"

    def __init__(self):
        super().__init__()


class _InputNode(_ShaderNode):
    NODE_CATEGORY = "shader/input"


class _OutputNode(_ShaderNode):
    NODE_CATEGORY = "shader/output"


class _MathNode(_ShaderNode):
    NODE_CATEGORY = "shader/math"


class _TextureNode(_ShaderNode):
    NODE_CATEGORY = "shader/texture"


class _VectorNode(_ShaderNode):
    NODE_CATEGORY = "shader/vector"
