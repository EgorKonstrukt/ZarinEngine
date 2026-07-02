# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from enum import Enum


class RenderMode(Enum):
    SHADED = "shaded"
    SHADED_WIREFRAME = "shaded_wireframe"
    FLAT = "flat"
