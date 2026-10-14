# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.components.rendering.deform.blendshapes import BlendShapes
class BlendSigMixin:
    def _blend_snapshot_sig(self, scene) -> tuple:
        try:
            ents = scene.get_entities_with_component(BlendShapes)
        except Exception:
            return ()
        if not ents:
            return ()
        out = []
        for ent in ents:
            try:
                if not ent.active:
                    continue
                bs = ent.get_component(BlendShapes)
                if bs is None or not getattr(bs, "enabled", True):
                    continue
                items = []
                for s in bs.shapes:
                    try:
                        items.append((str(s.get("name", "")), float(s.get("weight", 0.0))))
                    except (TypeError, ValueError):
                        continue
                out.append((ent.id, tuple(sorted(items))))
            except Exception:
                continue
        return tuple(out)
