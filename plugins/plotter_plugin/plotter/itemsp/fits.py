# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import math
from typing import Callable, List, Optional, Tuple, Union, TYPE_CHECKING
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPen
if TYPE_CHECKING:
    from ..chart import ChartWidget

try:
    import numpy as _np_items
    _NP_ITEMS = True
except ImportError:
    _np_items = None
    _NP_ITEMS = False

class _FitWorker(QThread):
    result_ready = pyqtSignal(object, list, list)

    def __init__(self, fit_item: "_FitItem", x_lo: float, x_hi: float, n_pts: int):
        super().__init__()
        self._fit_item = fit_item
        self._x_lo = x_lo
        self._x_hi = x_hi
        self._n_pts = n_pts

    def run(self):
        from ..mathx import get_fit_mode, linspace
        mode = get_fit_mode(self._fit_item.mode_key)
        if mode is None or not self._fit_item.source.xs:
            self.result_ready.emit(self._fit_item, [], [])
            return
        x_eval = linspace(self._x_lo, self._x_hi, self._n_pts)
        result = mode.evaluate(list(self._fit_item.source.xs), list(self._fit_item.source.ys), x_eval)
        if result is None:
            self.result_ready.emit(self._fit_item, [], [])
        else:
            self.result_ready.emit(self._fit_item, x_eval, result)


class _FitItem:
    def __init__(self, chart: "ChartWidget", source: "_LineItem | _ScatterItem",
                 mode_key: str, pen: QPen, label: str = ""):
        self._chart = chart
        self.source = source
        self.mode_key = mode_key
        self.pen = pen
        self.label = label
        self.visible = True
        self.show_formula = False
        self._xs: List[float] = []
        self._ys: List[float] = []
        self._worker: Optional[_FitWorker] = None
        self._pending_range: Optional[Tuple[float, float, int]] = None

    def _recompute(self, x_range_lo: float, x_range_hi: float,
                   n_pts: int = 400, threaded: bool = False):
        if not threaded:
            from ..mathx import get_fit_mode, linspace
            mode = get_fit_mode(self.mode_key)
            if mode is None or not self.source.xs:
                self._xs = []
                self._ys = []
                return
            x_eval = linspace(x_range_lo, x_range_hi, n_pts)
            result = mode.evaluate(list(self.source.xs), list(self.source.ys), x_eval)
            if result is None:
                self._xs = []
                self._ys = []
            else:
                self._xs = x_eval
                self._ys = result
            return
        self._pending_range = (x_range_lo, x_range_hi, n_pts)
        if self._worker is None or not self._worker.isRunning():
            self._start_worker(x_range_lo, x_range_hi, n_pts)

    def _start_worker(self, x_lo: float, x_hi: float, n_pts: int):
        self._worker = _FitWorker(self, x_lo, x_hi, n_pts)
        self._worker.result_ready.connect(self._on_worker_result)
        self._worker.start()

    def _on_worker_result(self, fit_item: "_FitItem", xs: List[float], ys: List[float]):
        if fit_item is not self:
            return
        self._xs = xs
        self._ys = ys
        self._chart._canvas.update()
        if self._pending_range is not None:
            lo, hi, n = self._pending_range
            if (self._worker is not None and
                    (abs(lo - self._worker._x_lo) > 1e-10 or
                     abs(hi - self._worker._x_hi) > 1e-10)):
                self._start_worker(lo, hi, n)
            else:
                self._pending_range = None

    def getData(self, x_lo: Optional[float] = None, x_hi: Optional[float] = None,
                n_pts: int = 400) -> Tuple[List[float], List[float]]:
        lo = x_lo if x_lo is not None else (min(self.source.xs) if self.source.xs else 0.0)
        hi = x_hi if x_hi is not None else (max(self.source.xs) if self.source.xs else 1.0)
        self._recompute(lo, hi, n_pts, threaded=False)
        return list(self._xs), list(self._ys)

    def evaluate(self, x: Union[float, List[float]]) -> Union[Optional[float], List[Optional[float]]]:
        scalar = isinstance(x, (int, float))
        x_list = [float(x)] if scalar else [float(v) for v in x]
        if not x_list:
            return []
        from ..mathx import get_fit_mode, _sort_unique
        mode = get_fit_mode(self.mode_key)
        if mode is None or not self.source.xs:
            return None if scalar else [None] * len(x_list)
        xs_s, ys_s = _sort_unique(list(self.source.xs), list(self.source.ys))
        if len(xs_s) < mode.min_points:
            return None if scalar else [None] * len(x_list)
        result = mode.fn(xs_s, ys_s, x_list)
        return result[0] if scalar else result

    def getFormula(self) -> str:
        from ..mathx import get_fit_mode
        mode = get_fit_mode(self.mode_key)
        if mode is None or not self.source.xs:
            return ""
        return mode.formula(list(self.source.xs), list(self.source.ys))

    def getRSquared(self) -> Optional[float]:
        from ..mathx import get_fit_mode, r_squared
        mode = get_fit_mode(self.mode_key)
        if mode is None or not self.source.xs or len(self._xs) < 2:
            return None
        return r_squared(list(self._xs), self._ys, self._ys)

    def asDict(self, x_lo: Optional[float] = None, x_hi: Optional[float] = None,
               n_pts: int = 400) -> dict:
        xs, ys = self.getData(x_lo, x_hi, n_pts)
        return {"x": xs, "y": ys}

    def asTuples(self, x_lo: Optional[float] = None, x_hi: Optional[float] = None,
                 n_pts: int = 400) -> List[Tuple[float, float]]:
        xs, ys = self.getData(x_lo, x_hi, n_pts)
        return list(zip(xs, ys))

    def setModeKey(self, key: str):
        self.mode_key = key
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def setShowFormula(self, v: bool):
        self.show_formula = v
        self._chart.update()

    @property
    def xs(self) -> List[float]:
        return self._xs

    @property
    def ys(self) -> List[float]:
        return self._ys


class _DerivativeItem:
    def __init__(self, chart: "ChartWidget", source: "_LineItem | _ScatterItem",
                 order: int = 1, pen: QPen = None, label: str = ""):
        from PyQt6.QtGui import QPen as _QPen
        self._chart = chart
        self.source = source
        self.order = order
        self.pen = pen or _QPen()
        self.label = label
        self.visible = True
        self._xs: List[float] = []
        self._ys: List[float] = []

    def recompute(self):
        from ..mathx import derivative, second_derivative, _sort_unique
        xs, ys = _sort_unique(list(self.source.xs), list(self.source.ys))
        if len(xs) < 2:
            self._xs, self._ys = [], []
            return
        if self.order == 2:
            self._xs, self._ys = second_derivative(xs, ys)
        else:
            self._xs, self._ys = derivative(xs, ys)
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def setPen(self, pen: QPen):
        self.pen = pen
        self._chart.update()

    @property
    def xs(self) -> List[float]:
        return self._xs

    @property
    def ys(self) -> List[float]:
        return self._ys

    @property
    def x_range(self) -> Optional[Tuple[float, float]]:
        return (min(self._xs), max(self._xs)) if self._xs else None

    @property
    def y_range(self) -> Optional[Tuple[float, float]]:
        return (min(self._ys), max(self._ys)) if self._ys else None


class _IntegralItem:
    def __init__(self, chart: "ChartWidget", source: "_LineItem | _ScatterItem",
                 pen: QPen = None, label: str = ""):
        from PyQt6.QtGui import QPen as _QPen
        self._chart = chart
        self.source = source
        self.pen = pen or _QPen()
        self.label = label
        self.visible = True
        self._xs: List[float] = []
        self._ys: List[float] = []

    def recompute(self):
        from ..mathx import cumulative_integral, _sort_unique
        xs, ys = _sort_unique(list(self.source.xs), list(self.source.ys))
        if len(xs) < 2:
            self._xs, self._ys = [], []
            return
        self._xs, self._ys = cumulative_integral(xs, ys)
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def setPen(self, pen: QPen):
        self.pen = pen
        self._chart.update()

    @property
    def xs(self) -> List[float]:
        return self._xs

    @property
    def ys(self) -> List[float]:
        return self._ys

    @property
    def x_range(self) -> Optional[Tuple[float, float]]:
        return (min(self._xs), max(self._xs)) if self._xs else None

    @property
    def y_range(self) -> Optional[Tuple[float, float]]:
        return (min(self._ys), max(self._ys)) if self._ys else None
