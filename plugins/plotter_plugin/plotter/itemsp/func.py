# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from typing import Callable, List, Optional, Tuple, Union, TYPE_CHECKING
from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtGui import QColor, QPen
if TYPE_CHECKING:
    from ..chart import ChartWidget

try:
    import numpy as _np_items
    _NP_ITEMS = True
except ImportError:
    _np_items = None
    _NP_ITEMS = False

class _FunctionItem:
    def __init__(self, chart: "ChartWidget", fn: Callable[[List[float]], List[float]],
                 pen: QPen, label: str = "", resolution: float = 1.0):
        self._chart = chart
        self.fn = fn
        self.pen = pen
        self.label = label
        self.visible = True
        self.fill_under = False
        self.fill_alpha = 30
        self.resolution = resolution
        self._cached_xs: List[float] = []
        self._cached_ys: List[Optional[float]] = []
        self._cache_key: Optional[Tuple] = None
        self._adaptive: bool = False
        self._expr: str = ""
        self._extra: dict = {}

    @property
    def xs(self) -> List[float]:
        return self._cached_xs

    @property
    def ys(self) -> List[Optional[float]]:
        return self._cached_ys

    def evaluate(self, x_lo: float, x_hi: float, pixel_width: int,
                 pixel_height: int = 600) -> Tuple[List[float], List[Optional[float]]]:
        n_pts = max(4, int(pixel_width * min(self.resolution, 1.0)))
        key = (round(x_lo, 12), round(x_hi, 12), n_pts)
        if key == self._cache_key:
            return self._cached_xs, self._cached_ys
        from ..mathx import linspace as _linspace
        if _NP_ITEMS:
            xs_base = _np_items.linspace(x_lo, x_hi, n_pts, dtype=_np_items.float64).tolist()
        else:
            xs_base = _linspace(x_lo, x_hi, n_pts)
        if self._adaptive and self._expr:
            try:
                from ..math_engine import sample_y_adaptive
                xs_ad, ys_ad = sample_y_adaptive(self._expr, xs_base, self._extra)
                self._cached_xs = xs_ad
                self._cached_ys = ys_ad
                self._cache_key = key
                return self._cached_xs, self._cached_ys
            except Exception:
                pass
        try:
            raw = self.fn(xs_base)
        except Exception:
            self._cached_xs = xs_base
            self._cached_ys = [None] * len(xs_base)
            self._cache_key = key
            return self._cached_xs, self._cached_ys
        if _NP_ITEMS:
            raw_arr = _np_items.array(
                [v if v is not None else _np_items.nan for v in raw], dtype=_np_items.float64
            )
            fin = _np_items.isfinite(raw_arr)
            ys: List[Optional[float]] = [
                float(raw_arr[i]) if fin[i] else None for i in range(len(raw_arr))
            ]
        else:
            _isfinite = math.isfinite
            ys = []
            for v in raw:
                if v is None:
                    ys.append(None)
                else:
                    fv = v if type(v) is float else float(v)
                    ys.append(fv if _isfinite(fv) else None)
        self._cached_xs = xs_base
        self._cached_ys = ys
        self._cache_key = key
        return self._cached_xs, self._cached_ys

    def invalidateCache(self):
        self._cache_key = None

    def setFunction(self, fn: Callable[[List[float]], List[float]]):
        self.fn = fn
        self.invalidateCache()
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def setFillUnder(self, enabled: bool, alpha: int = 30):
        self.fill_under = enabled
        self.fill_alpha = alpha
        self._chart.update()

    def setPen(self, pen: QPen):
        self.pen = pen
        self._chart.update()

    def setResolution(self, resolution: float):
        self.resolution = max(0.1, resolution)
        self.invalidateCache()
        self._chart.update()


class _RulerItem:
    def __init__(self, chart: "ChartWidget", pen: QPen, handle_radius: int = 6):
        self._chart = chart
        self.pen = pen
        self.handle_radius = handle_radius
        self.visible = False
        self.draggable = True
        self.x0: float = 0.0
        self.y0: float = 0.0
        self.x1: float = 1.0
        self.y1: float = 1.0
        self.changed: Optional[Callable[[], None]] = None

    @property
    def distance(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def dx(self) -> float:
        return self.x1 - self.x0

    @property
    def dy(self) -> float:
        return self.y1 - self.y0

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.y1 - self.y0, self.x1 - self.x0))

    @property
    def midpoint(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def setPoints(self, x0: float, y0: float, x1: float, y1: float):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        if self.changed is not None:
            self.changed()
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setDraggable(self, v: bool):
        self.draggable = v

    def setPen(self, pen: QPen):
        self.pen = pen
        self._chart.update()
