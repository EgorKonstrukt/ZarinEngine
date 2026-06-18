from __future__ import annotations
from typing import Any, Callable


class GuiEvent:
    def __init__(self):
        self._handlers: list[Callable] = []
        self._once: list[Callable] = []

    def connect(self, handler: Callable):
        self._handlers.append(handler)

    def disconnect(self, handler: Callable):
        if handler in self._handlers:
            self._handlers.remove(handler)

    def emit(self, sender=None, **kwargs):
        for h in list(self._handlers):
            h(sender, **kwargs)
        for h in list(self._once):
            h(sender, **kwargs)
            self._once.remove(h)

    def once(self, handler: Callable):
        self._once.append(handler)


class ClickEvent(GuiEvent):
    pass


class ValueChangeEvent(GuiEvent):
    pass


class HoverEvent(GuiEvent):
    pass


class FocusEvent(GuiEvent):
    pass
