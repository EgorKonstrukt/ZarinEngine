# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun
from __future__ import annotations
from core.gui.wid.base import ANCHOR_TOP_LEFT, ANCHOR_TOP_CENTER, ANCHOR_TOP_RIGHT, ANCHOR_CENTER_LEFT, ANCHOR_CENTER, ANCHOR_CENTER_RIGHT, ANCHOR_BOTTOM_LEFT, ANCHOR_BOTTOM_CENTER, ANCHOR_BOTTOM_RIGHT, ANCHOR_STRETCH_ALL, ANCHOR_STRETCH_WIDTH, ANCHOR_STRETCH_HEIGHT, GuiWidget, AnchorPresetSelector, apply_fusion_style, get_widget_base_style, get_widget_extra_rules, get_widget_type_for_object
from core.gui.wid.text import Label, TextInput, PlainText, TextEdit
from core.gui.wid.buttons import Button, Toggle, RadioButton, ToolButton
from core.gui.wid.sliders import Slider, ScrollBar, ProgressBar, Dial, SpinBox, DoubleSpinBox
from core.gui.wid.lists import ListWidget, TreeWidget, TableWidget, Dropdown, FontCombo
from core.gui.wid.containers import Panel, GroupBox, TabWidget, StackedWidget, Splitter, ScrollPanel, MdiSubWindow, MdiArea, ToolBox
from core.gui.wid.views import Image, HtmlView, Calendar, LCDNumber, ChartPlotter
WIDGET_REGISTRY = {"Panel": Panel, "Label": Label, "Button": Button, "Slider": Slider, "TextInput": TextInput, "Toggle": Toggle, "ProgressBar": ProgressBar, "Dropdown": Dropdown, "ScrollPanel": ScrollPanel, "Image": Image, "RadioButton": RadioButton, "ListWidget": ListWidget, "TableWidget": TableWidget, "TreeWidget": TreeWidget, "TabWidget": TabWidget, "GroupBox": GroupBox, "SpinBox": SpinBox, "DoubleSpinBox": DoubleSpinBox, "TextEdit": TextEdit, "HtmlView": HtmlView, "Dial": Dial, "Splitter": Splitter, "StackedWidget": StackedWidget, "ToolBox": ToolBox, "Calendar": Calendar, "LCDNumber": LCDNumber, "PlainText": PlainText, "ScrollBar": ScrollBar, "ToolButton": ToolButton, "FontCombo": FontCombo, "MdiArea": MdiArea, "MdiSubWindow": MdiSubWindow, "Chart": ChartPlotter, "ChartPlotter": ChartPlotter}
__all__ = ["ANCHOR_TOP_LEFT", "ANCHOR_TOP_CENTER", "ANCHOR_TOP_RIGHT", "ANCHOR_CENTER_LEFT", "ANCHOR_CENTER", "ANCHOR_CENTER_RIGHT", "ANCHOR_BOTTOM_LEFT", "ANCHOR_BOTTOM_CENTER", "ANCHOR_BOTTOM_RIGHT", "ANCHOR_STRETCH_ALL", "ANCHOR_STRETCH_WIDTH", "ANCHOR_STRETCH_HEIGHT", "GuiWidget", "AnchorPresetSelector", "Panel", "Label", "Button", "Slider", "TextInput", "Toggle", "ProgressBar", "Dropdown", "ScrollPanel", "Image", "RadioButton", "ListWidget", "TableWidget", "TreeWidget", "TabWidget", "GroupBox", "SpinBox", "DoubleSpinBox", "TextEdit", "HtmlView", "Dial", "Splitter", "StackedWidget", "ToolBox", "Calendar", "LCDNumber", "PlainText", "ScrollBar", "ToolButton", "FontCombo", "MdiSubWindow", "MdiArea", "ChartPlotter", "WIDGET_REGISTRY", "apply_fusion_style", "get_widget_base_style", "get_widget_extra_rules", "get_widget_type_for_object"]
