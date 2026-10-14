# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from typing import Any
from core.foundation.logger import Logger
from core.ecs.pool import general as _get_pool


class EngineEventsMixin:
    def _defer_gui(self, fn):
        poster = getattr(self, "_gui_poster", None)
        if poster is not None:
            poster(fn)
        else:
            fn()
    def on(self, event: str, callback):
        self._event_listeners.setdefault(event, []).append(callback)
    def off(self, event: str, callback):
        if event in self._event_listeners:
            try:
                self._event_listeners[event].remove(callback)
            except ValueError:
                pass
    def _emit_event(self, event: str, data: Any):
        cbs = self._event_listeners.get(event, [])
        from concurrent.futures import as_completed
        if len(cbs) >= 10:
            futures = [_get_pool().submit(cb, data) for cb in cbs]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    Logger.error(f"Event callback error '{event}': {e}")
        else:
            for cb in cbs:
                try:
                    cb(data)
                except Exception as e:
                    Logger.error(f"Event callback error '{event}': {e}", e)
    @property
    def collab_manager(self):
        return self._collab_manager
    @collab_manager.setter
    def collab_manager(self, v):
        self._collab_manager = v
    @property
    def plugin_ui_registry(self) -> dict:
        return self._plugin_ui_registry
