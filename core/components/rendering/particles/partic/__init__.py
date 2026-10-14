# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.ecs import ComponentRegistry
from core.components.rendering.particles.partic.component import ShapeType
from core.components.rendering.particles.partic.component import ParticleRenderMode
from core.components.rendering.particles.partic.component import SimulationSpace
from core.components.rendering.particles.partic.component import ParticleSortMode
from core.components.rendering.particles.partic.component import PARTICLE_DTYPE
from core.components.rendering.particles.partic.component import ParticleSystemBase
from core.components.rendering.particles.partic.emit import ParticleEmitMixin
from core.components.rendering.particles.partic.simulate import ParticleSimulateMixin
from core.components.rendering.particles.partic.simulate import _build_curve_cache
from core.components.rendering.particles.partic.simulate import _build_gradient_cache
from core.components.rendering.particles.partic.simulate import _sample_curve
from core.components.rendering.particles.partic.simulate import _presample_curve
from core.components.rendering.particles.partic.simulate import _presample_gradient
from core.components.rendering.particles.partic.render import ParticleRenderMixin


@ComponentRegistry.register
class ParticleSystem(ParticleEmitMixin, ParticleSimulateMixin, ParticleRenderMixin, ParticleSystemBase):
    pass


__all__ = ["ShapeType", "ParticleRenderMode", "SimulationSpace", "ParticleSortMode", "PARTICLE_DTYPE", "ParticleSystemBase", "ParticleEmitMixin", "ParticleSimulateMixin", "ParticleRenderMixin", "ParticleSystem", "_build_curve_cache", "_build_gradient_cache", "_sample_curve", "_presample_curve", "_presample_gradient"]
