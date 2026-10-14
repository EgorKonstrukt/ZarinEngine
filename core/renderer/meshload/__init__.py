# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations

from core.renderer.meshload.loading import _MeshLoaderLoading
from core.renderer.meshload.uploads import _MeshLoaderUploads


class MeshLoader(_MeshLoaderLoading, _MeshLoaderUploads):
    pass


__all__ = ["MeshLoader"]
