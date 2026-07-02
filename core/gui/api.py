# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from typing import Optional, Any, Callable
from PyQt6.QtWidgets import QWidget
from core.gui.canvas import GuiCanvas
from core.gui.widgets import (
    Panel, Label, Button, Slider, TextInput, Image,
    Toggle, ProgressBar, Dropdown, ScrollPanel, MdiArea,
    ANCHOR_TOP_LEFT, ANCHOR_TOP_CENTER, ANCHOR_TOP_RIGHT,
    ANCHOR_CENTER_LEFT, ANCHOR_CENTER, ANCHOR_CENTER_RIGHT,
    ANCHOR_BOTTOM_LEFT, ANCHOR_BOTTOM_CENTER, ANCHOR_BOTTOM_RIGHT,
    ANCHOR_STRETCH_ALL, ANCHOR_STRETCH_WIDTH, ANCHOR_STRETCH_HEIGHT,
)


class GuiApi:
    _instances: dict[str, GuiApi] = {}

    def __init__(self, name: str = "default", w: float = 800, h: float = 600, canvas: Optional[GuiCanvas] = None):
        self._name = name
        self._canvas = canvas if canvas is not None else GuiCanvas(w=w, h=h)
        GuiApi._instances[name] = self

    @property
    def canvas(self) -> GuiCanvas:
        return self._canvas

    @staticmethod
    def get(name: str = "default") -> GuiApi:
        return GuiApi._instances.get(name)

    def panel(self, x=0, y=0, w=200, h=200, parent=None, **kwargs) -> Panel:
        wgt = Panel(x, y, w, h)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def label(self, x=0, y=0, w=100, h=30, text="Label", parent=None, **kwargs) -> Label:
        wgt = Label(x, y, w, h, text)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def button(self, x=0, y=0, w=100, h=40, text="Button", parent=None, **kwargs) -> Button:
        wgt = Button(x, y, w, h, text)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def slider(self, x=0, y=0, w=200, h=30, min_val=0, max_val=100, parent=None, **kwargs) -> Slider:
        wgt = Slider(x, y, w, h, min_val, max_val)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def input(self, x=0, y=0, w=200, h=36, placeholder="", parent=None, **kwargs) -> TextInput:
        wgt = TextInput(x, y, w, h, placeholder)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def image(self, x=0, y=0, w=100, h=100, source="", parent=None, **kwargs) -> Image:
        wgt = Image(x, y, w, h, source)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def toggle(self, x=0, y=0, w=100, h=30, text="Toggle", checked=False, parent=None, **kwargs) -> Toggle:
        wgt = Toggle(x, y, w, h, text)
        wgt.setChecked(checked)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def progress(self, x=0, y=0, w=200, h=24, min_val=0, max_val=100, parent=None, **kwargs) -> ProgressBar:
        wgt = ProgressBar(x, y, w, h, min_val, max_val)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def dropdown(self, x=0, y=0, w=200, h=32, items=None, parent=None, **kwargs) -> Dropdown:
        wgt = Dropdown(x, y, w, h, items)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def scroll(self, x=0, y=0, w=200, h=200, parent=None, **kwargs) -> ScrollPanel:
        wgt = ScrollPanel(x, y, w, h)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def mdi_area(self, x=0, y=0, w=400, h=300, parent=None, **kwargs) -> MdiArea:
        wgt = MdiArea(x, y, w, h)
        self._apply_kwargs(wgt, kwargs)
        self._canvas.add_widget(wgt, parent)
        return wgt

    def clear(self):
        self._canvas.clear()

    def save(self, path: str):
        self._canvas.save_to_file(path)

    def load(self, path: str):
        self._canvas.load_from_file(path)

    def _apply_kwargs(self, widget: QWidget, kwargs: dict):
        for key, value in kwargs.items():
            if hasattr(widget, key):
                try:
                    setattr(widget, key, value)
                except AttributeError:
                    pass
