# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import enum
class PhysBoneIntegration(enum.Enum):
    SIMPLIFIED = "simplified"
    ADVANCED = "advanced"
class PhysBoneMultiChild(enum.Enum):
    IGNORE = "ignore"
    FIRST_CHILD = "first"
    AVERAGE = "average"
class PhysBoneImmobileType(enum.Enum):
    ALL_MOTION = "all"
    WORLD_TRANSLATION = "translation"
class PhysBoneLimitType(enum.Enum):
    NONE = "none"
    ANGLE = "angle"
    HINGE = "hinge"
