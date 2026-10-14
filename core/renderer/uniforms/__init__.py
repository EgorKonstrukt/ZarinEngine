# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.renderer.uniforms.scene import SceneUniformsCoreMixin
from core.renderer.uniforms.transparency import TransparencySortMixin
class SceneUniformsMixin(SceneUniformsCoreMixin, TransparencySortMixin):
    pass
__all__ = ["SceneUniformsMixin", "SceneUniformsCoreMixin", "TransparencySortMixin"]
