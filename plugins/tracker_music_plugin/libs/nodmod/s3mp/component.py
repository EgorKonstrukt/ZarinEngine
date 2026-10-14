# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import copy
import array
import os
import struct
import sys
from nodmod import Pattern
from nodmod import S3MNote
from nodmod import S3MSample
from nodmod import Song
from nodmod.views import PlaybackRowView
from .header import S3MSongHeaderMixin
from .patterns import S3MSongPatternsMixin
from .samples import S3MSongSamplesMixin

class S3MSong(S3MSongHeaderMixin, S3MSongPatternsMixin, S3MSongSamplesMixin, Song):
    pass
