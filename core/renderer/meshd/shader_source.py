# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.renderer.prec import apply_precision
from core.renderer.meshd.shader_paths import _find_in_shaders, _resolve_shader_file


def read_shader(name: str) -> str:
    path = _resolve_shader_file(name)
    with open(path, "r", encoding="utf-8") as f:
        return apply_precision(f.read())


def _to_pascal(base: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in base.split("_") if part)


def _split_shader_block(text: str) -> tuple[str, str] | None:
    start = text.find("GLSLPROGRAM")
    if start < 0:
        return None
    start += len("GLSLPROGRAM")
    end = text.find("ENDGLSL", start)
    if end < 0:
        return None
    block = text[start:end]
    marker = "// @FRAGMENT"
    idx = block.find(marker)
    if idx < 0:
        return None
    return block[:idx].strip(), block[idx + len(marker):].strip()


_SHADER_NAME_OVERRIDES = {"skybox": "SkyboxLegacy"}


def read_shader_pair(base: str) -> tuple[str, str]:
    pascal = _SHADER_NAME_OVERRIDES.get(base, _to_pascal(base))
    for candidate in (f"{pascal}.shader", f"{base}.shader"):
        path = _find_in_shaders(candidate)
        if path is not None:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            split = _split_shader_block(text)
            if split is not None:
                vert_src, frag_src = split
                try:
                    from core.renderer.shaderp import ShaderManager
                    frag_src = ShaderManager._inject_area_shadows(frag_src)
                    frag_src = ShaderManager._inject_caustics(frag_src)
                except Exception:
                    pass
                return (vert_src, frag_src)
    vert_name: str | None = None
    frag_name: str | None = None
    if base == "particle_gpu":
        vert_name, frag_name = "particle_gpu.vert", "particle.frag"
    elif base in ("underwater", "caustics"):
        vert_name, frag_name = "shadow_overlay.vert", f"{base}.frag"
    else:
        vert_name, frag_name = f"{base}.vert", f"{base}.frag"
    return read_shader(vert_name), read_shader(frag_name)


def read_compute_source(base: str) -> str:
    pascal = _to_pascal(base)
    for candidate in (f"{pascal}.compute", f"{base}.compute", f"{base}.comp"):
        full = _find_in_shaders(candidate)
        if full is not None:
            with open(full, "r", encoding="utf-8") as f:
                text = f.read()
            if candidate.endswith(".compute"):
                split_start = text.find("GLSLPROGRAM")
                if split_start >= 0:
                    split_start += len("GLSLPROGRAM")
                    split_end = text.find("ENDGLSL", split_start)
                    if split_end >= 0:
                        return apply_precision(text[split_start:split_end].strip())
            return apply_precision(text)
    return read_shader(f"{base}.comp")
