# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
import threading
class _PollThread(threading.Thread):
    def __init__(self, callback, interval_ms, stop_event):
        super().__init__(daemon=True)
        self._callback = callback
        self._interval = max(0.001, float(interval_ms) / 1000.0)
        self._stop_event = stop_event
    def run(self):
        while not self._stop_event.is_set():
            try:
                self._callback()
            except Exception:
                pass
            self._stop_event.wait(self._interval)
