# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.ecs.ecs import ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from plugins.qt_quick_plugin.components.quick_view import QuickView


@ComponentRegistry.register
class QuickButton(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 160
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.32
    TO_QML = {"text": "buttonText", "font_size": "fontSize", "checkable": "checkable", "checked": "checked"}
    FROM_QML = {"clickCount": "click_count", "checked": "checked"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("text", "Text", FieldType.STRING),
            InspectorField("font_size", "Font Size", FieldType.INT, min_val=8, max_val=128, step=1),
            InspectorField("checkable", "Checkable", FieldType.BOOL),
            InspectorField("checked", "Checked", FieldType.BOOL),
            InspectorField("click_count", "Clicks", FieldType.INT, readonly=True),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickButton.DEFAULT_W)
        self.height_px = int(QuickButton.DEFAULT_H)
        self.size_x = float(QuickButton.DEFAULT_SX)
        self.size_y = float(QuickButton.DEFAULT_SY)
        self.text: str = "Button"
        self.font_size: int = 28
        self.checkable: bool = False
        self.checked: bool = False
        self.click_count: int = 0
        self._click_listeners: list = []

    def add_on_clicked(self, fn):
        if callable(fn) and fn not in self._click_listeners:
            self._click_listeners.append(fn)

    def remove_on_clicked(self, fn):
        try:
            self._click_listeners.remove(fn)
        except Exception:
            pass

    def _notify_clicked(self):
        for fn in list(self._click_listeners):
            try:
                fn(self)
            except Exception:
                pass

    def click(self):
        self.click_count = int(self.click_count) + 1
        if self.checkable:
            self.checked = not bool(self.checked)
        self._dirty = True
        self._notify_clicked()

    def get_value(self):
        return bool(self.checked) if self.checkable else int(self.click_count)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"text": self.text, "font_size": int(self.font_size), "checkable": bool(self.checkable), "checked": bool(self.checked), "click_count": int(self.click_count)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.text = str(data.get("text", "Button"))
        inst.font_size = int(data.get("font_size", 28))
        inst.checkable = bool(data.get("checkable", False))
        inst.checked = bool(data.get("checked", False))
        inst.click_count = int(data.get("click_count", 0))
        inst._click_listeners = []
        return inst


@ComponentRegistry.register
class QuickLabel(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 128
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.25
    TO_QML = {"text": "labelText", "font_size": "fontSize", "text_color": "textColor", "align": "hAlign"}
    FROM_QML = {}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("text", "Text", FieldType.TEXTAREA),
            InspectorField("font_size", "Font Size", FieldType.INT, min_val=8, max_val=256, step=1),
            InspectorField("text_color", "Color", FieldType.COLOR),
            InspectorField("align", "Align", FieldType.ENUM, enum_options=["Left", "Center", "Right"]),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickLabel.DEFAULT_W)
        self.height_px = int(QuickLabel.DEFAULT_H)
        self.size_x = float(QuickLabel.DEFAULT_SX)
        self.size_y = float(QuickLabel.DEFAULT_SY)
        self.interactive = False
        self.text: str = "Label"
        self.font_size: int = 32
        self.text_color: list = [1.0, 1.0, 1.0, 1.0]
        self.align: str = "Center"

    def set_text(self, value: str):
        self.text = str(value)
        self._dirty = True

    def get_value(self):
        return str(self.text)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"text": self.text, "font_size": int(self.font_size), "text_color": list(self.text_color), "align": str(self.align)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.text = str(data.get("text", "Label"))
        inst.font_size = int(data.get("font_size", 32))
        try:
            inst.text_color = list(data.get("text_color", [1.0, 1.0, 1.0, 1.0]))
        except Exception:
            inst.text_color = [1.0, 1.0, 1.0, 1.0]
        inst.align = str(data.get("align", "Center"))
        return inst


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
class QuickTextField(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 128
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.25
    TO_QML = {"text": "fieldText", "placeholder": "fieldPlaceholder", "max_length": "fieldMaxLen"}
    FROM_QML = {"fieldText": "text"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("text", "Text", FieldType.STRING),
            InspectorField("placeholder", "Placeholder", FieldType.STRING),
            InspectorField("max_length", "Max Length", FieldType.INT, min_val=1, max_val=4096, step=1),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickTextField.DEFAULT_W)
        self.height_px = int(QuickTextField.DEFAULT_H)
        self.size_x = float(QuickTextField.DEFAULT_SX)
        self.size_y = float(QuickTextField.DEFAULT_SY)
        self.text: str = ""
        self.placeholder: str = "Type here"
        self.max_length: int = 256
        self._change_listeners: list = []

    def add_on_changed(self, fn):
        if callable(fn) and fn not in self._change_listeners:
            self._change_listeners.append(fn)

    def _notify_changed(self):
        for fn in list(self._change_listeners):
            try:
                fn(self, str(self.text))
            except Exception:
                pass

    def set_text(self, value: str):
        self.text = str(value)[: int(self.max_length)]
        self._dirty = True
        self._notify_changed()

    def get_value(self):
        return str(self.text)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"text": self.text, "placeholder": self.placeholder, "max_length": int(self.max_length)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.text = str(data.get("text", ""))
        inst.placeholder = str(data.get("placeholder", "Type here"))
        inst.max_length = int(data.get("max_length", 256))
        inst._change_listeners = []
        return inst


@ComponentRegistry.register
class QuickCheckBox(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 128
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.25
    TO_QML = {"text": "boxText", "checked": "boxChecked"}
    FROM_QML = {"boxChecked": "checked"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("text", "Text", FieldType.STRING),
            InspectorField("checked", "Checked", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickCheckBox.DEFAULT_W)
        self.height_px = int(QuickCheckBox.DEFAULT_H)
        self.size_x = float(QuickCheckBox.DEFAULT_SX)
        self.size_y = float(QuickCheckBox.DEFAULT_SY)
        self.text: str = "Check"
        self.checked: bool = False
        self._change_listeners: list = []

    def add_on_changed(self, fn):
        if callable(fn) and fn not in self._change_listeners:
            self._change_listeners.append(fn)

    def _notify_changed(self):
        for fn in list(self._change_listeners):
            try:
                fn(self, bool(self.checked))
            except Exception:
                pass

    def toggle(self):
        self.checked = not bool(self.checked)
        self._dirty = True
        self._notify_changed()

    def get_value(self):
        return bool(self.checked)

    def set_value(self, v: bool):
        self.checked = bool(v)
        self._dirty = True
        self._notify_changed()

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"text": self.text, "checked": bool(self.checked)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.text = str(data.get("text", "Check"))
        inst.checked = bool(data.get("checked", False))
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
class QuickSwitch(QuickView):
    DEFAULT_W = 384
    DEFAULT_H = 128
    DEFAULT_SX = 0.75
    DEFAULT_SY = 0.25
    TO_QML = {"text": "switchText", "checked": "switchChecked"}
    FROM_QML = {"switchChecked": "checked"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("text", "Text", FieldType.STRING),
            InspectorField("checked", "Checked", FieldType.BOOL),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickSwitch.DEFAULT_W)
        self.height_px = int(QuickSwitch.DEFAULT_H)
        self.size_x = float(QuickSwitch.DEFAULT_SX)
        self.size_y = float(QuickSwitch.DEFAULT_SY)
        self.text: str = "Switch"
        self.checked: bool = False
        self._change_listeners: list = []

    def add_on_changed(self, fn):
        if callable(fn) and fn not in self._change_listeners:
            self._change_listeners.append(fn)

    def _notify_changed(self):
        for fn in list(self._change_listeners):
            try:
                fn(self, bool(self.checked))
            except Exception:
                pass

    def toggle(self):
        self.checked = not bool(self.checked)
        self._dirty = True
        self._notify_changed()

    def get_value(self):
        return bool(self.checked)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"text": self.text, "checked": bool(self.checked)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.text = str(data.get("text", "Switch"))
        inst.checked = bool(data.get("checked", False))
        inst._change_listeners = []
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
class QuickComboBox(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 128
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.25
    TO_QML = {"items_text": "comboItems", "current_index": "comboIndex"}
    FROM_QML = {"comboIndex": "current_index"}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("items_text", "Items | separated", FieldType.TEXTAREA),
            InspectorField("current_index", "Current Index", FieldType.INT, min_val=0, max_val=256, step=1),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickComboBox.DEFAULT_W)
        self.height_px = int(QuickComboBox.DEFAULT_H)
        self.size_x = float(QuickComboBox.DEFAULT_SX)
        self.size_y = float(QuickComboBox.DEFAULT_SY)
        self.items_text: str = "One|Two|Three"
        self.current_index: int = 0
        self._change_listeners: list = []

    def add_on_changed(self, fn):
        if callable(fn) and fn not in self._change_listeners:
            self._change_listeners.append(fn)

    def _notify_changed(self):
        for fn in list(self._change_listeners):
            try:
                fn(self, int(self.current_index))
            except Exception:
                pass

    def get_items(self) -> list:
        try:
            return [p for p in str(self.items_text).split("|") if p != ""]
        except Exception:
            return []

    def set_items(self, items: list):
        try:
            self.items_text = "|".join(str(x) for x in items)
        except Exception:
            self.items_text = ""
        self.current_index = 0
        self._dirty = True
        self._notify_changed()

    def current_text(self) -> str:
        items = self.get_items()
        try:
            return str(items[int(self.current_index)])
        except Exception:
            return ""

    def get_value(self):
        return int(self.current_index)

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"items_text": str(self.items_text), "current_index": int(self.current_index)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.items_text = str(data.get("items_text", "One|Two|Three"))
        inst.current_index = int(data.get("current_index", 0))
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


@ComponentRegistry.register
class QuickPanel(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 384
    DEFAULT_SX = 1.0
    DEFAULT_SY = 0.75
    TO_QML = {"title": "panelTitle", "radius": "panelRadius"}
    FROM_QML = {}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("title", "Title", FieldType.STRING),
            InspectorField("panel_color", "Panel Color", FieldType.COLOR),
            InspectorField("radius", "Radius", FieldType.INT, min_val=0, max_val=64, step=1),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickPanel.DEFAULT_W)
        self.height_px = int(QuickPanel.DEFAULT_H)
        self.size_x = float(QuickPanel.DEFAULT_SX)
        self.size_y = float(QuickPanel.DEFAULT_SY)
        self.interactive = False
        self.title: str = "Panel"
        self.panel_color: list = [0.16, 0.18, 0.22, 0.92]
        self.radius: int = 18

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"title": self.title, "panel_color": list(self.panel_color), "radius": int(self.radius)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.title = str(data.get("title", "Panel"))
        try:
            inst.panel_color = list(data.get("panel_color", [0.16, 0.18, 0.22, 0.92]))
        except Exception:
            inst.panel_color = [0.16, 0.18, 0.22, 0.92]
        inst.radius = int(data.get("radius", 18))
        return inst


@ComponentRegistry.register
class QuickImageView(QuickView):
    DEFAULT_W = 512
    DEFAULT_H = 512
    DEFAULT_SX = 1.0
    DEFAULT_SY = 1.0
    TO_QML = {"image_source": "imageSource", "fill_mode": "imageFill"}
    FROM_QML = {}

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return QuickView._inspector_fields() + [
            InspectorField("image_source", "Image", FieldType.RESOURCE_PATH, file_filter="Images (*.png *.jpg *.jpeg *.bmp *.svg)"),
            InspectorField("fill_mode", "Fill Mode", FieldType.ENUM, enum_options=["Stretch", "Fit", "Crop", "Tile", "Pad"]),
        ]

    def __init__(self):
        super().__init__()
        self.width_px = int(QuickImageView.DEFAULT_W)
        self.height_px = int(QuickImageView.DEFAULT_H)
        self.size_x = float(QuickImageView.DEFAULT_SX)
        self.size_y = float(QuickImageView.DEFAULT_SY)
        self.interactive = False
        self.image_source: str = ""
        self.fill_mode: str = "Fit"

    def fill_mode_index(self) -> int:
        order = ["Stretch", "Fit", "Crop", "Tile", "Pad"]
        try:
            return order.index(str(self.fill_mode))
        except Exception:
            return 1

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({"image_source": str(self.image_source), "fill_mode": str(self.fill_mode)})
        return d

    @classmethod
    def deserialize(cls, data: dict):
        inst = super().deserialize(data)
        inst.image_source = str(data.get("image_source", "") or "")
        inst.fill_mode = str(data.get("fill_mode", "Fit"))
        return inst
