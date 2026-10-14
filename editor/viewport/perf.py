# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import sys
import threading
import time
from collections import deque


class _BlockWatch:

    def __init__(self):
        self._samples = deque(maxlen=6000)
        self._gui_ident = None
        self._stop = threading.Event()
        self._thread = None

    def start(self, gui_ident):
        self._gui_ident = gui_ident
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="block-watch", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                fr = sys._current_frames().get(self._gui_ident)
                if fr is not None:
                    names = []
                    depth = 0
                    while fr is not None and depth < 8:
                        code = fr.f_code
                        fname = code.co_filename
                        cut = fname.rfind("\\")
                        if cut < 0:
                            cut = fname.rfind("/")
                        names.append(fname[cut + 1:] + ":" + code.co_name)
                        fr = fr.f_back
                        depth += 1
                    self._samples.append((time.perf_counter(), tuple(names)))
            except Exception:
                pass
            self._stop.wait(0.003)

    def heaviest(self, window_s):
        try:
            snap = list(self._samples)
        except Exception:
            return 0, []
        now = time.perf_counter()
        counts = {}
        total = 0
        for ts, key in snap:
            if now - ts <= window_s:
                total += 1
                counts[key] = counts.get(key, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:4]
        out = []
        for key, cnt in ranked:
            pct = int(round(cnt * 100.0 / max(1, total)))
            out.append((">".join(list(key)[:4]), pct))
        return total, out


__all__ = ["_BlockWatch"]
