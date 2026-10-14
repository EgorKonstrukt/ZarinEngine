# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.ecs import ComponentRegistry
from core.components.rendering.renderers.raytrace.component import RaytraceComponent
from core.components.rendering.renderers.raytrace.component import _INST_STRIDE, _MAX_INSTANCES, _MAX_LIGHTS, _MAT_STRIDE, _MAX_ALBEDO_LAYERS
from core.components.rendering.renderers.raytrace.dispatch import RaytraceDispatchMixin
from core.components.rendering.renderers.raytrace.denoise import RaytraceDenoiseMixin
@ComponentRegistry.register
class RaytracingRenderer(RaytraceDispatchMixin, RaytraceDenoiseMixin, RaytraceComponent):
    _allow_multiple = False
__all__ = ["RaytracingRenderer", "RaytraceComponent", "RaytraceDispatchMixin", "RaytraceDenoiseMixin"]
