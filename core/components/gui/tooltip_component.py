from __future__ import annotations
import html
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import InspectorField, FieldType


@ComponentRegistry.register
class TooltipComponent(Component):
    _icon = "Tooltip.png"
    _allow_multiple = False

    text: str = ""
    _duration: float = 0.0
    _rich_text: bool = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for k, v in kwargs.items():
            if hasattr(self.__class__, k):
                setattr(self, k, v)

    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("text", "Tooltip Text", FieldType.STRING),
            InspectorField("_duration", "Duration (sec)", FieldType.FLOAT, min_val=0, max_val=60, step=0.1, decimals=1),
            InspectorField("_rich_text", "Rich Text", FieldType.BOOL),
        ]

    def on_update(self, dt: float):
        if not self.enabled:
            return
        key = (self.text, self._duration, self._rich_text)
        prev = getattr(self, '_prev_key', None)
        if key == prev:
            return
        from core.components.gui import GUI_COMPONENT_MAP
        for name, comp_cls in GUI_COMPONENT_MAP.items():
            comp = self.entity.get_component_by_name(comp_cls.__name__)
            if comp and getattr(comp, '_widget_ref', None):
                try:
                    w = comp._widget_ref
                    tip = self.text if self._rich_text else html.escape(self.text)
                    w.setToolTip(tip)
                    if self._duration > 0:
                        w.setToolTipDuration(int(self._duration * 1000))
                    self._prev_key = key
                except RuntimeError:
                    pass
                return

    def serialize(self) -> dict:
        d = super().serialize()
        d["text"] = self.text
        d["_duration"] = self._duration
        d["_rich_text"] = self._rich_text
        return d

    @classmethod
    def deserialize(cls, data: dict) -> TooltipComponent:
        inst: TooltipComponent = super().deserialize(data)
        inst.text = data.get("text", "")
        inst._duration = data.get("_duration", 0.0)
        inst._rich_text = data.get("_rich_text", True)
        return inst
