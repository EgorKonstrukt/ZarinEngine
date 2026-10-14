# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from core.renderer.prec.flags import RTC_KEY, GPU_DOUBLE_KEY, is_gpu_double_enabled, is_rtc_enabled
from core.renderer.prec.rewrite import apply_precision, apply_vertex_shader, apply_fragment_shader, apply_geometry_shader, apply_compute_shader, is_precision_mark_present, install_precision_hooks
__all__ = ["RTC_KEY", "GPU_DOUBLE_KEY", "is_gpu_double_enabled", "is_rtc_enabled", "apply_precision", "apply_vertex_shader", "apply_fragment_shader", "apply_geometry_shader", "apply_compute_shader", "is_precision_mark_present", "install_precision_hooks"]
