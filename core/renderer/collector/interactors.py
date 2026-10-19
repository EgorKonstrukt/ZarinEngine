# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.components.physics.sphere_collider import SphereCollider
from core.components.physics.box_collider import BoxCollider
from core.components.physics.capsule_collider import CapsuleCollider
from core.components.physics.rigidbody import Rigidbody
class InteractorsMixin:
    def _collect_interactors(self, snap, scene):
        try:
            if not scene._component_indices.get("Water"):
                snap.interactors = []
                return
        except Exception:
            pass
        try:
            rv = scene._render_version
            tvg = scene._transform_version
        except Exception:
            rv = tvg = None
        ck = getattr(self, "_inter_cache_key", None)
        if ck is not None and rv is not None and ck == (rv, tvg, id(scene)):
            return
        interactors = []
        collider_types = (SphereCollider, BoxCollider, CapsuleCollider)
        for ent in scene.get_entities_with_component(SphereCollider):
            c = ent.get_component(SphereCollider)
            if not c or not c.enabled or not ent.active:
                continue
            tr = ent.transform
            if not tr:
                continue
            rb = ent.get_component(Rigidbody)
            vel = rb.velocity if rb else None
            center = tr.position + c.scaled_center
            interactors.append((ent, center, c.scaled_radius, vel, c.scaled_radius))
        for ent in scene.get_entities_with_component(BoxCollider):
            c = ent.get_component(BoxCollider)
            if not c or not c.enabled or not ent.active:
                continue
            tr = ent.transform
            if not tr:
                continue
            rb = ent.get_component(Rigidbody)
            vel = rb.velocity if rb else None
            center = tr.position + c.scaled_center
            hsize = c.scaled_size * 0.5
            radius = max(hsize.x, hsize.z)
            if radius <= 0.0:
                continue
            interactors.append((ent, center, radius, vel, hsize.y))
        for ent in scene.get_entities_with_component(CapsuleCollider):
            c = ent.get_component(CapsuleCollider)
            if not c or not c.enabled or not ent.active:
                continue
            tr = ent.transform
            if not tr:
                continue
            rb = ent.get_component(Rigidbody)
            vel = rb.velocity if rb else None
            center = tr.position + c.scaled_center
            interactors.append((ent, center, c.scaled_radius, vel, c.scaled_radius))
        capped = sorted(interactors, key=lambda it: abs(it[1].y), reverse=False)[:64]
        snap.interactors = capped
        try:
            if rv is not None:
                self._inter_cache_key = (rv, tvg, id(scene))
        except Exception:
            pass
