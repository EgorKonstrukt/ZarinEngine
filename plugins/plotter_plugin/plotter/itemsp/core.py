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

class _InfLine:
    def __init__(self, chart: "ChartWidget", horizontal: bool, value: float, pen: QPen):
        self._chart = chart
        self.horizontal = horizontal
        self.value = value
        self.pen = pen
        self.visible = False
        self.draggable = True
        self.label: str = ""

    def setValue(self, v: float):
        self.value = v
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setDraggable(self, v: bool):
        self.draggable = v

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()


class _LineItem:
    def __init__(self, chart: "ChartWidget", pen: QPen, label: str = ""):
        self._chart = chart
        self.xs: List[float] = []
        self.ys: List[float] = []
        self.pen = pen
        self.label = label
        self.visible = True
        self.raw_visible = True
        self.fill_under = False
        self.fill_alpha = 40
        self.step_mode = False
        self.point_symbol: str = "none"
        self.point_size: int = 6

    def setData(self, xs=None, ys=None):
        self.xs = list(xs) if xs is not None else []
        self.ys = list(ys) if ys is not None else []
        self._chart._schedule_autofit()

    def appendPoint(self, x: float, y: float):
        self.xs.append(x)
        self.ys.append(y)
        self._chart._schedule_autofit()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setRawVisible(self, v: bool):
        self.raw_visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def setFillUnder(self, enabled: bool, alpha: int = 40):
        self.fill_under = enabled
        self.fill_alpha = alpha
        self._chart.update()

    def setStepMode(self, enabled: bool):
        self.step_mode = enabled
        self._chart.update()

    def setPointSymbol(self, symbol: str, size: int = 6):
        self.point_symbol = symbol
        self.point_size = size
        self._chart.update()

    def setPen(self, pen: QPen):
        self.pen = pen
        self._chart.update()

    @property
    def x_range(self) -> Optional[Tuple[float, float]]:
        if not self.xs:
            return None
        return (min(self.xs), max(self.xs))

    @property
    def y_range(self) -> Optional[Tuple[float, float]]:
        if not self.ys:
            return None
        return (min(self.ys), max(self.ys))

    def clear(self):
        self.xs = []
        self.ys = []
        self._chart._schedule_autofit()


class _ScatterItem(QObject):
    point_clicked = Signal(float, float, int)

    def __init__(self, chart: "ChartWidget", size: int, color: QColor, label: str = ""):
        super().__init__()
        self._chart = chart
        self.xs: List[float] = []
        self.ys: List[float] = []
        self.size = size
        self.color = color
        self.label = label
        self.visible = True
        self.raw_visible = True
        self.error_xs: Optional[List[float]] = None
        self.error_ys: Optional[List[float]] = None
        self.annotations: Optional[List[str]] = None
        self.selected_idx: Optional[int] = None
        self.symbol: str = "circle"

    def setData(self, x=None, y=None, **_):
        self.xs = list(x) if x is not None else []
        self.ys = list(y) if y is not None else []
        self.selected_idx = None
        self._chart._schedule_autofit()

    def appendPoint(self, x: float, y: float):
        self.xs.append(x)
        self.ys.append(y)
        self._chart._schedule_autofit()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setRawVisible(self, v: bool):
        self.raw_visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def setErrorBars(self, error_x: Optional[List[float]] = None,
                     error_y: Optional[List[float]] = None):
        self.error_xs = list(error_x) if error_x is not None else None
        self.error_ys = list(error_y) if error_y is not None else None
        self._chart.update()

    def setAnnotations(self, labels: Optional[List[str]]):
        self.annotations = list(labels) if labels is not None else None
        self._chart.update()

    def selectPoint(self, idx: Optional[int]):
        self.selected_idx = idx
        self._chart.update()

    def setSymbol(self, symbol: str):
        self.symbol = symbol
        self._chart.update()

    def setColor(self, color: QColor):
        self.color = color
        self._chart.update()

    def setSize(self, size: int):
        self.size = size
        self._chart.update()

    def clear(self):
        self.xs = []
        self.ys = []
        self.selected_idx = None
        self._chart._schedule_autofit()

    @property
    def x_range(self) -> Optional[Tuple[float, float]]:
        if not self.xs:
            return None
        return (min(self.xs), max(self.xs))

    @property
    def y_range(self) -> Optional[Tuple[float, float]]:
        if not self.ys:
            return None
        return (min(self.ys), max(self.ys))


def _screen_decimate(xs, ys, x_lo: float, x_hi: float,
                     pixel_width: int, pixel_height: int) -> tuple:
    try:
        import numpy as _np
    except ImportError:
        return xs, ys
    n = len(xs)
    if n <= pixel_width * 2:
        return xs, ys
    xs_arr = _np.asarray(xs, dtype=_np.float64)
    none_mask = _np.array([v is None for v in ys], dtype=bool)
    ys_arr = _np.array([0.0 if v is None else v for v in ys], dtype=_np.float64)
    x_range = x_hi - x_lo
    y_fin = ys_arr[~none_mask]
    y_range = float(_np.ptp(y_fin)) if len(y_fin) >= 2 else 1.0
    if x_range <= 0 or y_range <= 0:
        return xs, ys
    px = (xs_arr - x_lo) / x_range * pixel_width
    py = ys_arr / y_range * pixel_height
    dpx = _np.diff(px)
    dpy = _np.diff(py)
    dist_sq = dpx * dpx + dpy * dpy
    none_transition = none_mask[:-1] | none_mask[1:]
    keep_mask = _np.ones(n, dtype=bool)
    redundant = (dist_sq < 0.25) & ~none_transition
    keep_mask[1:][redundant] = False
    keep_mask[none_mask] = True
    idx = _np.where(keep_mask)[0]
    xs_out = xs_arr[idx].tolist()
    ys_out: list = [ys[int(i)] for i in idx]
    return xs_out, ys_out
