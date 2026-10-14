# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

import copy
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from nodmod.effects import decode_mod_effect
from nodmod.types import Note
from nodmod.views import CellView, EffectView, RowView, SampleView, SongView
from .header import SongHeaderMixin
from .patterns import SongPatternsMixin
from .samples import SongSamplesMixin

class Song(SongHeaderMixin, SongPatternsMixin, SongSamplesMixin, ABC):
    pass
