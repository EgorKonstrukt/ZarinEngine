# MIT License
#
# Copyright (c) 2026 Zarrakun
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations
import csv
from PySide6.QtWidgets import QFileDialog
from PySide6.QtGui import QPixmap
from ..i18n import tr

class _ChartExportMixin:
    def exportCsv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("chart_widget.csv_title"), "chart_data.csv",
            tr("chart_widget.csv_filter"))
        if not path:
            return
        series = []
        for i, it in enumerate(self._lines + self._lines_r2):
            if it.xs:
                n = it.label or f"line{i}"
                series.append((f"{n}_x", f"{n}_y", it.xs, it.ys))
        for i, it in enumerate(self._scatters + self._scatters_r2):
            if it.xs:
                n = it.label or f"scatter{i}"
                series.append((f"{n}_x", f"{n}_y", it.xs, it.ys))
        if not series:
            return
        max_rows = max(len(s[2]) for s in series)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([col for s in series for col in (s[0], s[1])])
            for row in range(max_rows):
                w.writerow([
                    v for s in series
                    for v in (s[2][row] if row < len(s[2]) else "",
                              s[3][row] if row < len(s[3]) else "")
                ])

    def exportImage(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("chart_widget.img_title"), "chart.png",
            tr("chart_widget.img_filter"))
        if not path:
            return
        self.grab().save(path)

    def grabImage(self) -> QPixmap:
        return self.grab()
