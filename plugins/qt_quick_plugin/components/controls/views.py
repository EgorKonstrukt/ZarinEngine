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
            InspectorField("", "Quick Text Field", FieldType.HEADER),
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
            InspectorField("", "Quick Combo Box", FieldType.HEADER),
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
            InspectorField("", "Quick Panel", FieldType.HEADER),
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
            InspectorField("", "Quick Image View", FieldType.HEADER),
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
