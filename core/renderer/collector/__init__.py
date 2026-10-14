# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.renderer.collector.blend import BlendSigMixin
from core.renderer.collector.sky import SkySelectMixin
from core.renderer.collector.snapshot import SnapshotCoreMixin
from core.renderer.collector.interactors import InteractorsMixin
from core.renderer.collector.refresh import SnapshotRefreshMixin
class SceneCollectorMixin(BlendSigMixin, SkySelectMixin, SnapshotCoreMixin, InteractorsMixin, SnapshotRefreshMixin):
    pass
__all__ = ["SceneCollectorMixin", "BlendSigMixin", "SkySelectMixin", "SnapshotCoreMixin", "InteractorsMixin", "SnapshotRefreshMixin"]
