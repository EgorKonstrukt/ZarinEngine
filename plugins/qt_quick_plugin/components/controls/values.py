# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.ecs import ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from plugins.qt_quick_plugin.components.quick_view import QuickView


@ComponentRegistry.register
class QuickSlider(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 128
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.25
    TO_QML = {"value": "sliderValue", "minimum": "sliderMin", "maximum": "sliderMax", "step": "sliderStep"}
    FROM_QML = {"sliderValue": "value"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("", "Quick Slider", FieldType.HEADER),
            InspectorField("value", "Value", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.01, decimals=3),
            InspectorField("minimum", "Min", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.1, decimals=3),
            InspectorField("maximum", "Max", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.1, decimals=3),
            InspectorField("step", "Step", FieldType.FLOAT, min_val=0.001, max_val=1000.0, step=0.01, decimals=3),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickSlider.DEFAULT_W)
        self.height_px = int(QuickSlider.DEFAULT_H)
        self.size_x = float(QuickSlider.DEFAULT_SX)
        self.size_y = float(QuickSlider.DEFAULT_SY)
        self.value: float = 0.5
        self.minimum: float = 0.0
        self.maximum: float = 1.0
        self.step: float = 0.01
        self._change_listeners: list = []

    def add_on_changed(self, fn):
        if callable(fn) and fn not in self._change_listeners:
            self._change_listeners.append(fn)

    def _notify_changed(self):
        for fn in list(self._change_listeners):
            try:
                fn(self, float(self.value))
            except Exception:
                pass

    def set_normalized(self, t: float):
        try:
            t = max(0.0, min(1.0, float(t)))
        except Exception:
            t = 0.0
        self.value = float(self.minimum) + t * (float(self.maximum) - float(self.minimum))
        self._dirty = True
        self._notify_changed()

    def get_normalized(self) -> float:
        span = float(self.maximum) - float(self.minimum)
        if abs(span) < 1e-9:
            return 0.0
        return (float(self.value) - float(self.minimum)) / span

    def get_value(self):
        return float(self.value)

    def set_value(self, v: float):
        self.value = float(v)
        self._dirty = True
        self._notify_changed()

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"value": float(self.value), "minimum": float(self.minimum), "maximum": float(self.maximum), "step": float(self.step)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.value = float(data.get("value", 0.5))
        inst.minimum = float(data.get("minimum", 0.0))
        inst.maximum = float(data.get("maximum", 1.0))
        inst.step = float(data.get("step", 0.01))
        inst._change_listeners = []
        return inst


@ComponentRegistry.register
class QuickProgressBar(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 96
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.2
    TO_QML = {"value": "barValue", "minimum": "barMin", "maximum": "barMax", "indeterminate": "barBusy"}
    FROM_QML = {}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("", "Quick Progress Bar", FieldType.HEADER),
            InspectorField("value", "Value", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.01, decimals=3),
            InspectorField("minimum", "Min", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.1, decimals=3),
            InspectorField("maximum", "Max", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.1, decimals=3),
            InspectorField("indeterminate", "Busy", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickProgressBar.DEFAULT_W)
        self.height_px = int(QuickProgressBar.DEFAULT_H)
        self.size_x = float(QuickProgressBar.DEFAULT_SX)
        self.size_y = float(QuickProgressBar.DEFAULT_SY)
        self.interactive = False
        self.value: float = 0.5
        self.minimum: float = 0.0
        self.maximum: float = 1.0
        self.indeterminate: bool = False

    def set_normalized(self, t: float):
        try:
            t = max(0.0, min(1.0, float(t)))
        except Exception:
            t = 0.0
        self.value = float(self.minimum) + t * (float(self.maximum) - float(self.minimum))
        self._dirty = True

    def get_value(self):
        return float(self.value)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"value": float(self.value), "minimum": float(self.minimum), "maximum": float(self.maximum), "indeterminate": bool(self.indeterminate)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.value = float(data.get("value", 0.5))
        inst.minimum = float(data.get("minimum", 0.0))
        inst.maximum = float(data.get("maximum", 1.0))
        inst.indeterminate = bool(data.get("indeterminate", False))
        return inst


@ComponentRegistry.register
class QuickDial(QuickView):
    DEFAULT_W = 256
    DEFAULT_H = 256
    DEFAULT_SX = 0.5
    DEFAULT_SY = 0.5
    TO_QML = {"value": "dialValue", "minimum": "dialMin", "maximum": "dialMax", "step": "dialStep"}
    FROM_QML = {"dialValue": "value"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("", "Quick Dial", FieldType.HEADER),
            InspectorField("value", "Value", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.01, decimals=3),
            InspectorField("minimum", "Min", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.1, decimals=3),
            InspectorField("maximum", "Max", FieldType.FLOAT, min_val=-100000.0, max_val=100000.0, step=0.1, decimals=3),
            InspectorField("step", "Step", FieldType.FLOAT, min_val=0.001, max_val=1000.0, step=0.01, decimals=3),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickDial.DEFAULT_W)
        self.height_px = int(QuickDial.DEFAULT_H)
        self.size_x = float(QuickDial.DEFAULT_SX)
        self.size_y = float(QuickDial.DEFAULT_SY)
        self.value: float = 0.5
        self.minimum: float = 0.0
        self.maximum: float = 1.0
        self.step: float = 0.01
        self._change_listeners: list = []

    def add_on_changed(self, fn):
        if callable(fn) and fn not in self._change_listeners:
            self._change_listeners.append(fn)

    def _notify_changed(self):
        for fn in list(self._change_listeners):
            try:
                fn(self, float(self.value))
            except Exception:
                pass

    def get_value(self):
        return float(self.value)

    def set_value(self, v: float):
        self.value = float(v)
        self._dirty = True
        self._notify_changed()

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"value": float(self.value), "minimum": float(self.minimum), "maximum": float(self.maximum), "step": float(self.step)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.value = float(data.get("value", 0.5))
        inst.minimum = float(data.get("minimum", 0.0))
        inst.maximum = float(data.get("maximum", 1.0))
        inst.step = float(data.get("step", 0.01))
        inst._change_listeners = []
        return inst


@ComponentRegistry.register
class QuickSpinBox(QuickView):
    DEFAULT_W = 384
    DEFAULT_H = 128
    DEFAULT_SX = 0.75
    DEFAULT_SY = 0.25
    TO_QML = {"value": "spinValue", "minimum": "spinMin", "maximum": "spinMax"}
    FROM_QML = {"spinValue": "value"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("", "Quick Spin Box", FieldType.HEADER),
            InspectorField("value", "Value", FieldType.INT, min_val=-1000000, max_val=1000000, step=1),
            InspectorField("minimum", "Min", FieldType.INT, min_val=-1000000, max_val=1000000, step=1),
            InspectorField("maximum", "Max", FieldType.INT, min_val=-1000000, max_val=1000000, step=1),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickSpinBox.DEFAULT_W)
        self.height_px = int(QuickSpinBox.DEFAULT_H)
        self.size_x = float(QuickSpinBox.DEFAULT_SX)
        self.size_y = float(QuickSpinBox.DEFAULT_SY)
        self.value: int = 0
        self.minimum: int = -100
        self.maximum: int = 100
        self._change_listeners: list = []

    def add_on_changed(self, fn):
        if callable(fn) and fn not in self._change_listeners:
            self._change_listeners.append(fn)

    def _notify_changed(self):
        for fn in list(self._change_listeners):
            try:
                fn(self, int(self.value))
            except Exception:
                pass

    def get_value(self):
        return int(self.value)

    def set_value(self, v: int):
        self.value = int(v)
        self._dirty = True
        self._notify_changed()

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"value": int(self.value), "minimum": int(self.minimum), "maximum": int(self.maximum)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.value = int(data.get("value", 0))
        inst.minimum = int(data.get("minimum", -100))
        inst.maximum = int(data.get("maximum", 100))
        inst._change_listeners = []
        return inst
