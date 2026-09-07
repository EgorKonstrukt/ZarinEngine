# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from plugins.qt_quick_plugin.components.quick_view import QuickView
from plugins.qt_quick_plugin.components.quick_controls import (
    QuickButton,
    QuickLabel,
    QuickSlider,
    QuickTextField,
    QuickCheckBox,
    QuickProgressBar,
    QuickSwitch,
    QuickDial,
    QuickComboBox,
    QuickSpinBox,
    QuickPanel,
    QuickImageView,
)

QUICK_ALL_TYPES = [
    QuickButton,
    QuickLabel,
    QuickSlider,
    QuickTextField,
    QuickCheckBox,
    QuickProgressBar,
    QuickSwitch,
    QuickDial,
    QuickComboBox,
    QuickSpinBox,
    QuickPanel,
    QuickImageView,
]

QUICK_BY_NAME = {c.__name__: c for c in QUICK_ALL_TYPES}
QUICK_BY_NAME["QuickView"] = QuickView


def collect_quick_views(scene) -> list:
    out = []
    if scene is None:
        return out
    try:
        entities = scene.get_all_entities()
    except Exception:
        return out
    for ent in entities:
        try:
            if not getattr(ent, "_active", True):
                continue
            for comp in ent.get_all_components():
                if isinstance(comp, QuickView) and getattr(comp, "enabled", True):
                    out.append(comp)
        except Exception:
            continue
    try:
        out.sort(key=lambda c: int(getattr(c, "render_order", 0)))
    except Exception:
        pass
    return out
