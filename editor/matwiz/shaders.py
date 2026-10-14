# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
import re
from core.assets.matp import _project_root


def _collect_shaders(project_root: str) -> list[tuple[str, str]]:
    shaders = []
    engine_root = _project_root()
    dirs_to_scan = []
    shaders_dir = os.path.join(engine_root, "core", "shaders")
    if os.path.isdir(shaders_dir):
        dirs_to_scan.append(shaders_dir)
    if project_root:
        for root, _, files in os.walk(project_root):
            for f in files:
                if f.endswith(".shader"):
                    full = os.path.normpath(os.path.join(root, f))
                    shaders.append((f, full))
            break
    for d in dirs_to_scan:
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith(".shader"):
                    full = os.path.normpath(os.path.join(root, f))
                    shaders.append((f, full))
    seen = set()
    unique = []
    for name, path in shaders:
        if path not in seen:
            seen.add(path)
            unique.append((name, path))
    unique.sort(key=lambda x: x[0].lower())
    return unique


def _extract_shader_name(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read(2048)
        m = re.search(r'Shader\s+"([^"]+)"', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0]
