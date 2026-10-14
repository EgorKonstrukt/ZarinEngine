# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import json
from typing import Optional, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget, QSizePolicy
from core.gui.wid import Panel, ANCHOR_STRETCH_ALL, WIDGET_REGISTRY, apply_fusion_style
from core.gui.canvasp.overlay import CanvasOverlayMixin
from core.gui.canvasp.events import CanvasEventsMixin


NATIVE_WIDGET_TYPES = {"Button", "Label", "Slider", "TextInput", "Toggle",
                       "ProgressBar", "Dropdown", "ScrollPanel", "Image", "Panel",
                       "RadioButton", "ListWidget", "TableWidget", "TreeWidget",
                       "TabWidget", "GroupBox", "SpinBox", "DoubleSpinBox",
                       "TextEdit", "Dial", "HtmlView",
                       "Splitter", "StackedWidget", "ToolBox", "Calendar",
                       "LCDNumber", "PlainText", "ScrollBar", "ToolButton", "FontCombo"}


class GuiCanvas(CanvasEventsMixin, CanvasOverlayMixin, QWidget):
    widget_selected = pyqtSignal(object)
    widget_changed = pyqtSignal(object)
    scene_modified = pyqtSignal()
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._screen_w = 1920
        self._screen_h = 1080
        self._root = Panel(0, 0, 100, 100, self)
        self._root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._root.setAutoFillBackground(False)
        self._root._anchor = ANCHOR_STRETCH_ALL
        self._selected_widget: Optional[QWidget] = None
        self._selected_widgets: list[QWidget] = []
        self._hovered_widget: Optional[QWidget] = None
        self._edit_mode = False
        self._drag_widget: Optional[QWidget] = None
        self._drag_handle = ""
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0
        self._drag_start_w = 0.0
        self._drag_start_h = 0.0
        self._drag_start_mx = 0
        self._drag_start_my = 0
        self._drag_start_positions: dict[int, tuple[int, int]] = {}
        self._selection_box_start: Optional[tuple[float, float]] = None
        self._selection_rect: Optional[tuple[float, float, float, float]] = None
        self._is_selecting = False
        self._snap_to_grid = True
        self._grid_size = 8
        self._show_grid = True
        self._show_selection = True
        self._auto_align = True
        self._guide_lines: list[tuple[float, float, float, float]] = []
        self._background_color = QColor(26, 26, 26)
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._is_panning = False
        self._pan_start_mx = 0
        self._pan_start_my = 0
        self._pan_start_px = 0.0
        self._pan_start_py = 0.0
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 100)
        apply_fusion_style(self)

    @property
    def root(self) -> Panel:
        return self._root

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, v: bool):
        self._edit_mode = v
        for child in self._root.children():
            if isinstance(child, QWidget):
                child.setEnabled(not v if hasattr(child, 'setEnabled') else True)
        self._update_all_anchors(self.width(), self.height())
        self._apply_z_order()
        self.update()

    @property
    def selected_widget(self) -> Optional[QWidget]:
        return self._selected_widget

    @selected_widget.setter
    def selected_widget(self, w: Optional[QWidget]):
        if self._selected_widget != w:
            self._selected_widget = w
            if w is None:
                self._selected_widgets.clear()
            elif w not in self._selected_widgets:
                self._selected_widgets[:] = [w]
            self.widget_selected.emit(w)
            self.update()

    @property
    def auto_align(self) -> bool:
        return self._auto_align

    @auto_align.setter
    def auto_align(self, v: bool):
        self._auto_align = v
        if not v:
            self._guide_lines = []
            self.update()

    @property
    def snap_to_grid(self) -> bool:
        return self._snap_to_grid

    @snap_to_grid.setter
    def snap_to_grid(self, v: bool):
        self._snap_to_grid = v

    @property
    def grid_size(self) -> int:
        return self._grid_size

    @grid_size.setter
    def grid_size(self, v: int):
        self._grid_size = max(1, v)

    @property
    def zoom(self) -> float:
        return self._zoom

    @zoom.setter
    def zoom(self, v: float):
        self._zoom = max(0.1, min(10.0, v))
        self._update_display()
        self.zoom_changed.emit(self._zoom)

    @property
    def screen_width(self) -> int:
        return self._screen_w

    @screen_width.setter
    def screen_width(self, v: int):
        self._screen_w = max(320, v)
        self._update_root_geometry()
        self.update()

    @property
    def screen_height(self) -> int:
        return self._screen_h

    @screen_height.setter
    def screen_height(self, v: int):
        self._screen_h = max(240, v)
        self._update_root_geometry()
        self.update()

    def _to_root(self, sx: float, sy: float) -> tuple[float, float]:
        return sx + self._pan_x, sy + self._pan_y

    def find_by_id(self, wid: str) -> Optional[QWidget]:
        for child in self._root.children():
            if isinstance(child, QWidget) and getattr(child, '_widget_id', None) == wid:
                return child
        return None

    def add_widget(self, widget: QWidget, parent_widget: Optional[QWidget] = None) -> QWidget:
        parent = parent_widget or self._root
        widget.setParent(parent)
        widget.setVisible(True)
        if hasattr(widget, 'update_anchor'):
            widget.update_anchor(self.width(), self.height())
        self._apply_z_order()
        self.update()
        return widget

    def remove_widget(self, widget: QWidget):
        if self._selected_widget is widget:
            self._selected_widget = None
        if widget in self._selected_widgets:
            self._selected_widgets.remove(widget)
        widget.setParent(None)
        widget.deleteLater()
        self.update()

    def clear(self):
        for child in list(self._root.children()):
            if isinstance(child, QWidget):
                child.setParent(None)
                child.deleteLater()
        self._selected_widget = None
        self._selected_widgets.clear()
        self.update()

    def get_all_widgets(self) -> list[QWidget]:
        return [c for c in self._root.children() if isinstance(c, QWidget)]

    def _apply_z_order(self):
        ordered: list[QWidget] = []
        def _collect(parent):
            for child in parent.children():
                if isinstance(child, QWidget):
                    ordered.append(child)
                    _collect(child)
        _collect(self._root)
        ordered.sort(key=lambda w: getattr(w, '_z_index', 0))
        for w in ordered:
            try:
                w.raise_()
            except RuntimeError:
                pass

    def _update_all_anchors(self, vw: float, vh: float):
        def _walk(parent):
            for child in parent.children():
                if not isinstance(child, QWidget):
                    continue
                if hasattr(child, 'update_anchor'):
                    try:
                        child.update_anchor(vw, vh)
                    except RuntimeError:
                        pass
                _walk(child)
        _walk(self._root)

    def serialize(self) -> dict:
        children_data = [self._serialize_widget(c) for c in self._root.children()
                         if isinstance(c, QWidget) and hasattr(c, 'serialize')]
        return {
            "canvas_w": self.width(),
            "canvas_h": self.height(),
            "children": children_data,
        }

    def _serialize_widget(self, widget: QWidget) -> dict:
        if not hasattr(widget, '_widget_id') or widget._widget_id is None:
            widget._widget_id = f"w{id(widget)}"
        data = widget.serialize()
        data["id"] = widget._widget_id
        data["children"] = [self._serialize_widget(c) for c in widget.children()
                             if isinstance(c, QWidget) and hasattr(c, 'serialize')]
        return data

    def deserialize(self, data: dict):
        self.clear()
        vw, vh = self.width(), self.height()
        for cd in data.get("children", []):
            self._deserialize_widget(cd, self._root, vw, vh)
        self._apply_z_order()
        self._update_root_geometry()
        self.update()

    def _deserialize_widget(self, cd: dict, parent_widget: QWidget, vw: float, vh: float):
        wtype = cd.get("type", "Button")
        cls = WIDGET_REGISTRY.get(wtype)
        if not cls or not hasattr(cls, 'deserialize'):
            return
        widget = cls.deserialize(cd)
        widget._widget_id = cd.get("id")
        widget.setParent(parent_widget)
        widget.setVisible(True)
        if hasattr(widget, 'update_anchor'):
            widget.update_anchor(vw, vh)
        for child_cd in cd.get("children", []):
            self._deserialize_widget(child_cd, widget, vw, vh)

    def save_to_file(self, path: str):
        with open(path, "w") as f:
            json.dump(self.serialize(), f, indent=2)

    def load_from_file(self, path: str):
        with open(path) as f:
            self.deserialize(json.load(f))
