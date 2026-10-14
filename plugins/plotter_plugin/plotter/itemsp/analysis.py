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

class _HistogramItem:
    def __init__(self, chart: "ChartWidget", color: QColor = None,
                 bins: int = 20, label: str = ""):
        from PyQt6.QtGui import QColor as _QColor
        self._chart = chart
        self.color = color or _QColor(100, 149, 237)
        self.bins = bins
        self.label = label
        self.visible = True
        self.normalize = False
        self._centers: List[float] = []
        self._counts: List[float] = []
        self._raw: List[float] = []

    def setData(self, data: List[float]):
        from ..mathx import histogram
        self._raw = list(data)
        self._centers, self._counts = histogram(self._raw, self.bins)
        if self.normalize and self._counts:
            total = sum(self._counts)
            self._counts = [c / total if total > 0 else 0.0 for c in self._counts]
        self._chart._schedule_autofit()

    def setBins(self, bins: int):
        self.bins = max(1, bins)
        if self._raw:
            self.setData(self._raw)

    def setNormalize(self, enabled: bool):
        self.normalize = enabled
        if self._raw:
            self.setData(self._raw)

    def setColor(self, color: QColor):
        self.color = color
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def clear(self):
        self._raw = []
        self._centers = []
        self._counts = []
        self._chart._schedule_autofit()

    @property
    def centers(self) -> List[float]:
        return self._centers

    @property
    def counts(self) -> List[float]:
        return self._counts

    @property
    def x_range(self) -> Optional[Tuple[float, float]]:
        return (min(self._centers), max(self._centers)) if self._centers else None

    @property
    def y_range(self) -> Optional[Tuple[float, float]]:
        return (0.0, max(self._counts)) if self._counts else None


class _SpectrumItem:
    def __init__(self, chart: "ChartWidget", source: "_LineItem | _ScatterItem",
                 pen: QPen = None, label: str = ""):
        from PyQt6.QtGui import QPen as _QPen
        self._chart = chart
        self.source = source
        self.pen = pen or _QPen()
        self.label = label
        self.visible = True
        self.log_scale = False
        self._freqs: List[float] = []
        self._amps: List[float] = []

    def recompute(self):
        from ..mathx import fft_spectrum_numpy, _sort_unique
        xs, ys = _sort_unique(list(self.source.xs), list(self.source.ys))
        if len(xs) < 4:
            self._freqs, self._amps = [], []
            return
        self._freqs, self._amps = fft_spectrum_numpy(xs, ys)
        if self.log_scale:
            self._amps = [math.log10(max(a, 1e-30)) for a in self._amps]
        self._chart.update()

    def setLogScale(self, enabled: bool):
        self.log_scale = enabled
        self.recompute()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def setPen(self, pen: QPen):
        self.pen = pen
        self._chart.update()

    def dominantFrequency(self) -> Optional[float]:
        if not self._amps:
            return None
        idx = max(range(len(self._amps)), key=lambda i: self._amps[i])
        return self._freqs[idx] if self._freqs else None

    @property
    def freqs(self) -> List[float]:
        return self._freqs

    @property
    def amps(self) -> List[float]:
        return self._amps

    @property
    def x_range(self) -> Optional[Tuple[float, float]]:
        return (min(self._freqs), max(self._freqs)) if self._freqs else None

    @property
    def y_range(self) -> Optional[Tuple[float, float]]:
        return (0.0, max(self._amps)) if self._amps else None


class _ErrorBandItem:
    def __init__(self, chart: "ChartWidget", color: QColor = None,
                 alpha: int = 50, label: str = ""):
        from PyQt6.QtGui import QColor as _QColor
        self._chart = chart
        self.color = color or _QColor(100, 180, 255)
        self.alpha = alpha
        self.label = label
        self.visible = True
        self.xs: List[float] = []
        self.ys_lo: List[float] = []
        self.ys_hi: List[float] = []

    def setData(self, xs: List[float], ys_lo: List[float], ys_hi: List[float]):
        self.xs = list(xs)
        self.ys_lo = list(ys_lo)
        self.ys_hi = list(ys_hi)
        self._chart._schedule_autofit()

    def setFromMeanStd(self, xs: List[float], ys: List[float], n_sigma: float = 1.0):
        from ..mathx import moving_std
        window = max(3, len(ys) // 10)
        stds = moving_std(ys, window)
        self.xs = list(xs)
        self.ys_lo = [y - n_sigma * s for y, s in zip(ys, stds)]
        self.ys_hi = [y + n_sigma * s for y, s in zip(ys, stds)]
        self._chart._schedule_autofit()

    def setColor(self, color: QColor, alpha: int = 50):
        self.color = color
        self.alpha = alpha
        self._chart.update()

    def setVisible(self, v: bool):
        self.visible = v
        self._chart.update()

    def setLabel(self, label: str):
        self.label = label
        self._chart.update()

    def clear(self):
        self.xs = []
        self.ys_lo = []
        self.ys_hi = []
        self._chart._schedule_autofit()

    @property
    def x_range(self) -> Optional[Tuple[float, float]]:
        return (min(self.xs), max(self.xs)) if self.xs else None

    @property
    def y_range(self) -> Optional[Tuple[float, float]]:
        if not self.ys_lo and not self.ys_hi:
            return None
        return (min(self.ys_lo + self.ys_hi), max(self.ys_lo + self.ys_hi))
