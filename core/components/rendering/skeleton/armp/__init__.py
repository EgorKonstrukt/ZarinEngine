# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.ecs import ComponentRegistry as _ComponentRegistry
from core.components.rendering.skeleton.armp.bone import Bone
from core.components.rendering.skeleton.armp.bone import _ArmatureBase
from core.components.rendering.skeleton.armp.skinning import _ArmatureSkin


@_ComponentRegistry.register
class Armature(_ArmatureSkin, _ArmatureBase):
    pass


__all__ = ["Bone", "Armature"]
