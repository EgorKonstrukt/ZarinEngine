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
            InspectorField("", "Quick Button", FieldType.HEADER),
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
            InspectorField("", "Quick Label", FieldType.HEADER),
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
            InspectorField("", "Quick Check Box", FieldType.HEADER),
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
            InspectorField("", "Quick Switch", FieldType.HEADER),
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
