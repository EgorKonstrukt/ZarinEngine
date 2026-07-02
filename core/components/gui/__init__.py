# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.components.gui.base_widget_component import GuiWidgetComponentBase
    from core.components.gui.panel_component import PanelComponent
    from core.components.gui.label_component import LabelComponent
    from core.components.gui.button_component import ButtonComponent
    from core.components.gui.slider_component import SliderComponent
    from core.components.gui.textinput_component import TextInputComponent
    from core.components.gui.toggle_component import ToggleComponent
    from core.components.gui.progressbar_component import ProgressBarComponent
    from core.components.gui.dropdown_component import DropdownComponent
    from core.components.gui.scrollpanel_component import ScrollPanelComponent
    from core.components.gui.image_component import ImageComponent
    from core.components.gui.radiobutton_component import RadioButtonComponent
    from core.components.gui.listwidget_component import ListWidgetComponent
    from core.components.gui.tablewidget_component import TableWidgetComponent
    from core.components.gui.treewidget_component import TreeWidgetComponent
    from core.components.gui.tabwidget_component import TabWidgetComponent
    from core.components.gui.groupbox_component import GroupBoxComponent
    from core.components.gui.spinbox_component import SpinBoxComponent
    from core.components.gui.doublespinbox_component import DoubleSpinBoxComponent
    from core.components.gui.textedit_component import TextEditComponent
    from core.components.gui.dial_component import DialComponent
    from core.components.gui.html_component import HtmlComponent
    from core.components.gui.splitter_component import SplitterComponent
    from core.components.gui.stacked_component import StackedComponent
    from core.components.gui.toolbox_component import ToolBoxComponent
    from core.components.gui.calendar_component import CalendarComponent
    from core.components.gui.lcd_component import LCDComponent
    from core.components.gui.plaintext_component import PlainTextComponent
    from core.components.gui.scrollbar_component import ScrollBarComponent
    from core.components.gui.toolbutton_component import ToolButtonComponent
    from core.components.gui.fontcombo_component import FontComboComponent
    from core.components.gui.mdiarea_component import MdiAreaComponent
    from core.components.gui.tooltip_component import TooltipComponent
    from core.components.gui.layout_element_component import LayoutElementComponent
    from core.components.gui.horizontal_layout_component import (
        HorizontalLayoutComponent, VerticalLayoutComponent, GridLayoutComponent,
    )

_LAZY_IMPORTS: dict[str, str] = {
    "GuiWidgetComponentBase": "core.components.gui.base_widget_component",
    "PanelComponent": "core.components.gui.panel_component",
    "LabelComponent": "core.components.gui.label_component",
    "ButtonComponent": "core.components.gui.button_component",
    "SliderComponent": "core.components.gui.slider_component",
    "TextInputComponent": "core.components.gui.textinput_component",
    "ToggleComponent": "core.components.gui.toggle_component",
    "ProgressBarComponent": "core.components.gui.progressbar_component",
    "DropdownComponent": "core.components.gui.dropdown_component",
    "ScrollPanelComponent": "core.components.gui.scrollpanel_component",
    "ImageComponent": "core.components.gui.image_component",
    "RadioButtonComponent": "core.components.gui.radiobutton_component",
    "ListWidgetComponent": "core.components.gui.listwidget_component",
    "TableWidgetComponent": "core.components.gui.tablewidget_component",
    "TreeWidgetComponent": "core.components.gui.treewidget_component",
    "TabWidgetComponent": "core.components.gui.tabwidget_component",
    "GroupBoxComponent": "core.components.gui.groupbox_component",
    "SpinBoxComponent": "core.components.gui.spinbox_component",
    "DoubleSpinBoxComponent": "core.components.gui.doublespinbox_component",
    "TextEditComponent": "core.components.gui.textedit_component",
    "DialComponent": "core.components.gui.dial_component",
    "HtmlComponent": "core.components.gui.html_component",
    "SplitterComponent": "core.components.gui.splitter_component",
    "StackedComponent": "core.components.gui.stacked_component",
    "ToolBoxComponent": "core.components.gui.toolbox_component",
    "CalendarComponent": "core.components.gui.calendar_component",
    "LCDComponent": "core.components.gui.lcd_component",
    "PlainTextComponent": "core.components.gui.plaintext_component",
    "ScrollBarComponent": "core.components.gui.scrollbar_component",
    "ToolButtonComponent": "core.components.gui.toolbutton_component",
    "FontComboComponent": "core.components.gui.fontcombo_component",
    "MdiAreaComponent": "core.components.gui.mdiarea_component",
    "TooltipComponent": "core.components.gui.tooltip_component",
    "LayoutElementComponent": "core.components.gui.layout_element_component",
    "HorizontalLayoutComponent": "core.components.gui.horizontal_layout_component",
    "VerticalLayoutComponent": "core.components.gui.horizontal_layout_component",
    "GridLayoutComponent": "core.components.gui.horizontal_layout_component",
}

def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        mod = importlib.import_module(_LAZY_IMPORTS[name])
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return list(_LAZY_IMPORTS.keys())


def _build_component_map() -> dict:
    from core.components.gui.panel_component import PanelComponent
    from core.components.gui.label_component import LabelComponent
    from core.components.gui.button_component import ButtonComponent
    from core.components.gui.slider_component import SliderComponent
    from core.components.gui.textinput_component import TextInputComponent
    from core.components.gui.toggle_component import ToggleComponent
    from core.components.gui.progressbar_component import ProgressBarComponent
    from core.components.gui.dropdown_component import DropdownComponent
    from core.components.gui.scrollpanel_component import ScrollPanelComponent
    from core.components.gui.image_component import ImageComponent
    from core.components.gui.radiobutton_component import RadioButtonComponent
    from core.components.gui.listwidget_component import ListWidgetComponent
    from core.components.gui.tablewidget_component import TableWidgetComponent
    from core.components.gui.treewidget_component import TreeWidgetComponent
    from core.components.gui.tabwidget_component import TabWidgetComponent
    from core.components.gui.groupbox_component import GroupBoxComponent
    from core.components.gui.spinbox_component import SpinBoxComponent
    from core.components.gui.doublespinbox_component import DoubleSpinBoxComponent
    from core.components.gui.textedit_component import TextEditComponent
    from core.components.gui.dial_component import DialComponent
    from core.components.gui.html_component import HtmlComponent
    from core.components.gui.splitter_component import SplitterComponent
    from core.components.gui.stacked_component import StackedComponent
    from core.components.gui.toolbox_component import ToolBoxComponent
    from core.components.gui.calendar_component import CalendarComponent
    from core.components.gui.lcd_component import LCDComponent
    from core.components.gui.plaintext_component import PlainTextComponent
    from core.components.gui.scrollbar_component import ScrollBarComponent
    from core.components.gui.toolbutton_component import ToolButtonComponent
    from core.components.gui.fontcombo_component import FontComboComponent
    from core.components.gui.mdiarea_component import MdiAreaComponent
    return {
        "panel": PanelComponent,
        "label": LabelComponent,
        "button": ButtonComponent,
        "slider": SliderComponent,
        "textinput": TextInputComponent,
        "toggle": ToggleComponent,
        "progressbar": ProgressBarComponent,
        "dropdown": DropdownComponent,
        "scrollpanel": ScrollPanelComponent,
        "image": ImageComponent,
        "radiobutton": RadioButtonComponent,
        "listwidget": ListWidgetComponent,
        "tablewidget": TableWidgetComponent,
        "treewidget": TreeWidgetComponent,
        "tabwidget": TabWidgetComponent,
        "groupbox": GroupBoxComponent,
        "spinbox": SpinBoxComponent,
        "doublespinbox": DoubleSpinBoxComponent,
        "textedit": TextEditComponent,
        "dial": DialComponent,
        "html": HtmlComponent,
        "splitter": SplitterComponent,
        "stackedwidget": StackedComponent,
        "toolbox": ToolBoxComponent,
        "calendar": CalendarComponent,
        "lcdnumber": LCDComponent,
        "plaintext": PlainTextComponent,
        "scrollbar": ScrollBarComponent,
        "toolbutton": ToolButtonComponent,
        "fontcombo": FontComboComponent,
        "mdiarea": MdiAreaComponent,
    }

GUI_COMPONENT_MAP = None

def _ensure_component_map() -> dict:
    global GUI_COMPONENT_MAP
    if GUI_COMPONENT_MAP is None:
        GUI_COMPONENT_MAP = _build_component_map()
    return GUI_COMPONENT_MAP

LAYOUT_COMP_NAMES = ["HorizontalLayoutComponent", "VerticalLayoutComponent", "GridLayoutComponent"]
LAYOUT_ELEMENT_NAME = "LayoutElementComponent"

__all__ = [
    "GuiWidgetComponentBase",
    "PanelComponent", "LabelComponent", "ButtonComponent", "SliderComponent",
    "TextInputComponent", "ToggleComponent", "ProgressBarComponent",
    "DropdownComponent", "ScrollPanelComponent", "ImageComponent",
    "RadioButtonComponent", "ListWidgetComponent", "TableWidgetComponent",
    "TreeWidgetComponent", "TabWidgetComponent", "GroupBoxComponent",
    "SpinBoxComponent", "DoubleSpinBoxComponent", "TextEditComponent",
    "DialComponent", "HtmlComponent", "SplitterComponent", "StackedComponent",
    "ToolBoxComponent", "CalendarComponent", "LCDComponent", "PlainTextComponent",
    "ScrollBarComponent", "ToolButtonComponent", "FontComboComponent",
    "MdiAreaComponent", "TooltipComponent", "LayoutElementComponent",
    "HorizontalLayoutComponent", "VerticalLayoutComponent", "GridLayoutComponent",
    "GUI_COMPONENT_MAP", "_ensure_component_map",
]
