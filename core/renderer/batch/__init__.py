# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.renderer.batch.batcher import RenderBatcher, resolve_normal_matrix
from core.renderer.batch.groups import _extract_frustum_planes_f32

__all__ = ["RenderBatcher"]
