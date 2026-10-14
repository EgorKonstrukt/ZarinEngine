# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os
from typing import Any
from core.foundation.logger import Logger


def open_file_with_plugin(engine: Any, path: str) -> bool:
    try:
        reg = getattr(engine, "plugin_ui_registry", None) or {}
    except Exception:
        return False
    ext = os.path.splitext(path or "")[1].lower()
    if not ext:
        return False
    for opener in reg.get("file_openers", []):
        try:
            registered = [str(e).lower() for e in opener.get("extensions", [])]
        except Exception:
            continue
        if ext not in registered:
            continue
        handler = opener.get("handler")
        if not callable(handler):
            continue
        try:
            handler(path)
            return True
        except Exception as e:
            Logger.error(f"[Plugin] File opener '{opener.get('label', '?')}' failed for '{path}': {e}", e)
            return False
    return False
