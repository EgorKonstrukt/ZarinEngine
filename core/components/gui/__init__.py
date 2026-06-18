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
from core.components.gui.layout_element_component import LayoutElementComponent
from core.components.gui.horizontal_layout_component import (
    HorizontalLayoutComponent, VerticalLayoutComponent, GridLayoutComponent,
)


GUI_COMPONENT_MAP = {
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

LAYOUT_COMP_NAMES = ["HorizontalLayoutComponent", "VerticalLayoutComponent", "GridLayoutComponent"]
LAYOUT_ELEMENT_NAME = "LayoutElementComponent"

__all__ = [
    "GuiWidgetComponentBase",
    "PanelComponent",
    "LabelComponent",
    "ButtonComponent",
    "SliderComponent",
    "TextInputComponent",
    "ToggleComponent",
    "ProgressBarComponent",
    "DropdownComponent",
    "ScrollPanelComponent",
    "ImageComponent",
    "RadioButtonComponent",
    "ListWidgetComponent",
    "TableWidgetComponent",
    "TreeWidgetComponent",
    "TabWidgetComponent",
    "GroupBoxComponent",
    "SpinBoxComponent",
    "DoubleSpinBoxComponent",
    "TextEditComponent",
    "DialComponent",
    "HtmlComponent",
    "SplitterComponent",
    "StackedComponent",
    "ToolBoxComponent",
    "CalendarComponent",
    "LCDComponent",
    "PlainTextComponent",
    "ScrollBarComponent",
    "ToolButtonComponent",
    "FontComboComponent",
    "MdiAreaComponent",
    "LayoutElementComponent",
    "HorizontalLayoutComponent",
    "VerticalLayoutComponent",
    "GridLayoutComponent",
    "GUI_COMPONENT_MAP",
]
