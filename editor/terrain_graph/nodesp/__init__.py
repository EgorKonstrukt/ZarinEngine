# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from editor.terrain_graph.nodesp.base import _TerrainNode
from editor.terrain_graph.nodesp.generators import BillowNoiseNode, ConstantNode, ContinentMaskNode, DuneNode, PerlinNoiseNode, RidgedNoiseNode, VoronoiNode
from editor.terrain_graph.nodesp.filters import ClampNode, DomainWarpNode, ErosionNode, HeightBiasNode, InvertNode, NormalizeNode, PlateauNode, RemapNode, RiverNode, SharpenNode, SlopeMaskNode, SmoothNode, StrataNode, TerraceNode
from editor.terrain_graph.nodesp.output import AddNode, BlendNode, HeightOutputNode, MaxNode, MinNode, MultiplyNode, SubtractNode

ALL_NODES = [
    PerlinNoiseNode,
    RidgedNoiseNode,
    BillowNoiseNode,
    VoronoiNode,
    ConstantNode,
    DomainWarpNode,
    ErosionNode,
    TerraceNode,
    PlateauNode,
    ContinentMaskNode,
    SlopeMaskNode,
    DuneNode,
    StrataNode,
    SharpenNode,
    SmoothNode,
    NormalizeNode,
    InvertNode,
    HeightBiasNode,
    RiverNode,
    AddNode,
    SubtractNode,
    MultiplyNode,
    BlendNode,
    MaxNode,
    MinNode,
    ClampNode,
    RemapNode,
    HeightOutputNode,
]

__all__ = [
    "_TerrainNode",
    "PerlinNoiseNode",
    "RidgedNoiseNode",
    "BillowNoiseNode",
    "VoronoiNode",
    "ConstantNode",
    "DomainWarpNode",
    "ErosionNode",
    "TerraceNode",
    "PlateauNode",
    "ContinentMaskNode",
    "SlopeMaskNode",
    "DuneNode",
    "StrataNode",
    "SharpenNode",
    "SmoothNode",
    "NormalizeNode",
    "InvertNode",
    "HeightBiasNode",
    "RiverNode",
    "AddNode",
    "SubtractNode",
    "MultiplyNode",
    "BlendNode",
    "MaxNode",
    "MinNode",
    "ClampNode",
    "RemapNode",
    "HeightOutputNode",
    "ALL_NODES",
]
