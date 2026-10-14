# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.renderer.shaderp.fallback import downgrade_to_330, program_with_fallback
from core.renderer.shaderp.manager import ShaderManager
__all__ = ["downgrade_to_330", "program_with_fallback", "ShaderManager"]
