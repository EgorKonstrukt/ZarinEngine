from __future__ import annotations
from typing import Optional

MAX_LAYERS = 16

DEFAULT_LAYER_NAMES = [
    "Default",
    "TransparentFX",
    "Ignore Raycast",
    "Water",
    "UI",
    "Player",
    "Enemy",
    "Projectile",
    "Trigger",
    "Ground",
    "Layer10",
    "Layer11",
    "Layer12",
    "Layer13",
    "Layer14",
    "Layer15",
]

def build_default_collision_matrix() -> list[int]:
    masks = []
    for i in range(MAX_LAYERS):
        mask = 0
        for j in range(MAX_LAYERS):
            if i == 2 or j == 2:
                continue
            if i == 4 or j == 4:
                if i == 4 and j == 4:
                    mask |= 1 << j
                continue
            mask |= 1 << j
        masks.append(mask)
    return masks

def get_layer_mask(layer_names: list[str], matrix: list[int], layer: int) -> int:
    if layer < 0 or layer >= MAX_LAYERS:
        return 0
    if layer < len(matrix):
        return matrix[layer]
    return 0xFFFF

def layer_mask_from_names(layer_names: list[str], indices: list[int]) -> int:
    mask = 0
    for i in indices:
        if 0 <= i < MAX_LAYERS:
            mask |= 1 << i
    return mask

def layer_names_from_mask(layer_names: list[str], mask: int) -> list[int]:
    result = []
    for i in range(MAX_LAYERS):
        if mask & (1 << i):
            result.append(i)
    return result
