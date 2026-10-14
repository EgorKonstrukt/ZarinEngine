# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.shader_graph.nodesp.base import _ShaderNode, _InputNode, _OutputNode, _MathNode, _TextureNode, _VectorNode
from editor.shader_graph.nodesp.inputs_outputs import _VertexPositionNode, _UVNode, _NormalNode, _TimeNode, _ColorNode, _FloatNode, _Texture2DNode, _VertexOutputNode, _FragmentOutputNode
from editor.shader_graph.nodesp.math_vector import _AddNode, _MultiplyNode, _SubtractNode, _LerpNode, _NormalizeNode, _DotProductNode, _FresnelNode, _StepNode, _ClampNode

ALL_NODES = [
    _VertexPositionNode,
    _UVNode,
    _NormalNode,
    _TimeNode,
    _ColorNode,
    _FloatNode,
    _Texture2DNode,
    _AddNode,
    _MultiplyNode,
    _SubtractNode,
    _LerpNode,
    _NormalizeNode,
    _DotProductNode,
    _FresnelNode,
    _StepNode,
    _ClampNode,
    _VertexOutputNode,
    _FragmentOutputNode,
]

__all__ = [
    "_ShaderNode",
    "_InputNode",
    "_OutputNode",
    "_MathNode",
    "_TextureNode",
    "_VectorNode",
    "_VertexPositionNode",
    "_UVNode",
    "_NormalNode",
    "_TimeNode",
    "_ColorNode",
    "_FloatNode",
    "_Texture2DNode",
    "_AddNode",
    "_MultiplyNode",
    "_SubtractNode",
    "_LerpNode",
    "_NormalizeNode",
    "_DotProductNode",
    "_FresnelNode",
    "_StepNode",
    "_ClampNode",
    "_VertexOutputNode",
    "_FragmentOutputNode",
    "ALL_NODES",
]
