# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.components.rendering.environment.skyp import ProceduralSky
from core.components.rendering.environment.skybox import Skybox
class SkySelectMixin:
    def _select_sky_component(self, scene, snap) -> None:
        try:
            for ent in scene.get_entities_with_component(Skybox):
                if ent.active:
                    sb = ent.get_component(Skybox)
                    if sb and sb.enabled and sb.skybox_path:
                        snap.sky_component = sb
                        snap.sky_entity = ent
                        return
        except Exception:
            pass
        snap.sky_component = None
        snap.sky_entity = None
        try:
            for ent in scene.get_entities_with_component(ProceduralSky):
                if ent.active:
                    snap.sky_component = ent.get_component(ProceduralSky)
                    snap.sky_entity = ent
                    break
        except Exception:
            pass
