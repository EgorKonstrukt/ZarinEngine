from __future__ import annotations
from core.ecs import ComponentRegistry
from core.components.gui.base_widget_component import GuiWidgetComponentBase
from core.gui.widgets import TextInput
from core.components.inspector_meta import InspectorField, FieldType


@ComponentRegistry.register
class TextInputComponent(GuiWidgetComponentBase):
    _widget_class = TextInput
    _widget_obj_name = "GuiTextInput"
    _default_text = ""
    _default_w = 200.0
    _default_h = 36.0

    _placeholder: str = ""

    @classmethod
    def _inspector_fields(cls):
        return [
            InspectorField("_placeholder", "Placeholder", FieldType.STRING),
        ] + cls._common_inspector_fields()

    def _create_widget(self, canvas):
        if self._widget_ref:
            return
        super()._create_widget(canvas)
        if self._widget_ref and self._placeholder:
            try:
                self._widget_ref.setPlaceholderText(self._placeholder)
            except Exception:
                pass

    def sync_to_widget(self):
        super().sync_to_widget()
        w = self._widget_ref
        if w and self._placeholder:
            try:
                w.setPlaceholderText(self._placeholder)
            except Exception:
                pass

    def serialize(self) -> dict:
        d = super().serialize()
        d["_placeholder"] = self._placeholder
        return d

    @classmethod
    def deserialize(cls, data: dict) -> TextInputComponent:
        inst: TextInputComponent = super().deserialize(data)
        inst._placeholder = data.get("_placeholder", "")
        return inst
