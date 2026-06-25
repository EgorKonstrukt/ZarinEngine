from __future__ import annotations
from enum import Enum
from core.ecs import Component, ComponentRegistry
from core.components.inspector_meta import FieldType, InspectorField
from core.font_atlas import get_default_font_path


class TextFilter(Enum):
    NEAREST = "nearest"
    LINEAR = "linear"
    TRILINEAR = "trilinear"


class TextAlign(Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


@ComponentRegistry.register
class TextRenderer(Component):
    _icon = "TextRenderer.png"
    _gizmo_icon_color = (60, 120, 220)
    _gizmo_icon_label = "T"
    _show_gizmo_icon: bool = True

    @classmethod
    def _inspector_fields(cls) -> list[InspectorField]:
        return [
            InspectorField("text", "Text", FieldType.TEXTAREA),
            InspectorField("font_path", "Font", FieldType.RESOURCE_PATH, file_filter="Fonts (*.ttf)"),
            InspectorField("font_size", "Font Size", FieldType.INT, min_val=1, max_val=512, step=1),
            InspectorField("color", "Color", FieldType.COLOR),
            InspectorField("alignment", "Alignment", FieldType.ENUM, enum_class=TextAlign),
            InspectorField("line_spacing", "Line Spacing", FieldType.FLOAT, min_val=0.5, max_val=5.0, step=0.1, decimals=1),
            InspectorField("bold", "Bold", FieldType.BOOL),
            InspectorField("italic", "Italic", FieldType.BOOL),
            InspectorField("underline", "Underline", FieldType.BOOL),
            InspectorField("strikethrough", "Strikethrough", FieldType.BOOL),
            InspectorField("shadow", "Shadow", FieldType.BOOL),
            InspectorField("shadow_offset", "Shadow Offset", FieldType.VEC2),
            InspectorField("shadow_color", "Shadow Color", FieldType.COLOR),
            InspectorField("use_3d", "3D Text", FieldType.BOOL),
            InspectorField("extrusion_depth", "Extrusion Depth", FieldType.FLOAT, min_val=0.001, max_val=1.0, step=0.001, decimals=4, toggle_field="use_3d"),
            InspectorField("extrusion_layers", "Extrusion Layers", FieldType.INT, min_val=1, max_val=32, step=1, toggle_field="use_3d"),
            InspectorField("extrusion_color", "Extrusion Color", FieldType.COLOR, toggle_field="use_3d"),
            InspectorField("atlas_resolution", "Atlas Resolution", FieldType.INT, min_val=32, max_val=512, step=16),
            InspectorField("font_world_space", "World Space", FieldType.BOOL),
            InspectorField("billboard", "Billboard", FieldType.BOOL),
            InspectorField("filter_mode", "Filter", FieldType.ENUM, enum_class=TextFilter),
            InspectorField("anisotropy", "Anisotropy", FieldType.FLOAT, min_val=0.0, max_val=16.0, step=1.0, decimals=1),
            InspectorField("shader", "Shader", FieldType.RESOURCE_PATH, file_filter="Shaders (*.shader)"),
        ]

    def __init__(self):
        super().__init__()
        self._text: str = "Text"
        self.font_path: str = get_default_font_path()
        self.font_size: int = 32
        self._color: list[float] = [1, 1, 1, 1]
        self.alignment: TextAlign = TextAlign.LEFT
        self.line_spacing: float = 1.2
        self.bold: bool = False
        self.italic: bool = False
        self.underline: bool = False
        self.strikethrough: bool = False
        self.shadow: bool = False
        self._shadow_offset: list[float] = [0.02, -0.02]
        self._shadow_color: list[float] = [0, 0, 0, 0.5]
        self.use_3d: bool = False
        self.extrusion_depth: float = 0.05
        self.extrusion_layers: int = 8
        self._extrusion_color: list[float] = [0.3, 0.3, 0.3]
        self.atlas_resolution: int = 128
        self.font_world_space: bool = True
        self.billboard: bool = False
        self.filter_mode: TextFilter = TextFilter.LINEAR
        self.anisotropy: float = 4.0
        self.shader: str = "text"

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, val):
        if val is None:
            self._text = "Text"
        elif isinstance(val, str):
            self._text = val.replace("\r", "")
        else:
            self._text = str(val).replace("\r", "")

    @property
    def color(self) -> list[float]:
        return self._color

    @color.setter
    def color(self, val):
        if val is None:
            self._color = [1, 1, 1, 1]
        elif len(val) == 3:
            self._color = [val[0], val[1], val[2], 1.0]
        elif len(val) >= 4:
            self._color = [val[0], val[1], val[2], val[3]]
        else:
            self._color = [1, 1, 1, 1]

    @property
    def shadow_offset(self) -> list[float]:
        return self._shadow_offset

    @shadow_offset.setter
    def shadow_offset(self, val):
        if val is None or len(val) < 2:
            self._shadow_offset = [0.02, -0.02]
        else:
            self._shadow_offset = [float(val[0]), float(val[1])]

    @property
    def shadow_color(self) -> list[float]:
        return self._shadow_color

    @shadow_color.setter
    def shadow_color(self, val):
        if val is None:
            self._shadow_color = [0, 0, 0, 0.5]
        elif len(val) == 3:
            self._shadow_color = [val[0], val[1], val[2], 0.5]
        elif len(val) >= 4:
            self._shadow_color = [val[0], val[1], val[2], val[3]]
        else:
            self._shadow_color = [0, 0, 0, 0.5]

    @property
    def extrusion_color(self) -> list[float]:
        return self._extrusion_color

    @extrusion_color.setter
    def extrusion_color(self, val):
        if val is None:
            self._extrusion_color = [0.3, 0.3, 0.3]
        elif len(val) == 3:
            self._extrusion_color = [val[0], val[1], val[2]]
        elif len(val) >= 4:
            self._extrusion_color = [val[0], val[1], val[2]]
        else:
            self._extrusion_color = [0.3, 0.3, 0.3]

    def serialize(self) -> dict:
        d = super().serialize()
        d.update({
            "text": self.text,
            "font_path": self.font_path,
            "font_size": self.font_size,
            "color": self.color,
            "alignment": self.alignment.value,
            "line_spacing": self.line_spacing,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "strikethrough": self.strikethrough,
            "shadow": self.shadow,
            "shadow_offset": self.shadow_offset,
            "shadow_color": self.shadow_color,
            "use_3d": self.use_3d,
            "extrusion_depth": self.extrusion_depth,
            "extrusion_layers": self.extrusion_layers,
            "extrusion_color": self.extrusion_color,
            "atlas_resolution": self.atlas_resolution,
            "font_world_space": self.font_world_space,
            "billboard": self.billboard,
            "filter_mode": self.filter_mode.value,
            "anisotropy": self.anisotropy,
            "shader": self.shader,
        })
        return d

    @classmethod
    def deserialize(cls, data: dict) -> TextRenderer:
        tr = cls()
        tr.enabled = data.get("enabled", True)
        tr.text = data.get("text", "Text")
        tr.font_path = data.get("font_path", "") or ""
        tr.font_size = data.get("font_size", 32)
        tr.color = data.get("color", [1, 1, 1, 1])
        try:
            tr.alignment = TextAlign(data.get("alignment", "left"))
        except (ValueError, KeyError):
            tr.alignment = TextAlign.LEFT
        tr.line_spacing = data.get("line_spacing", 1.2)
        tr.bold = data.get("bold", False)
        tr.italic = data.get("italic", False)
        tr.underline = data.get("underline", False)
        tr.strikethrough = data.get("strikethrough", False)
        tr.shadow = data.get("shadow", False)
        tr.shadow_offset = data.get("shadow_offset", [0.02, -0.02])
        tr.shadow_color = data.get("shadow_color", [0, 0, 0, 0.5])
        tr.use_3d = data.get("use_3d", False)
        tr.extrusion_depth = data.get("extrusion_depth", 0.05)
        tr.extrusion_layers = data.get("extrusion_layers", 8)
        tr.extrusion_color = data.get("extrusion_color", [0.3, 0.3, 0.3])
        tr.atlas_resolution = data.get("atlas_resolution", 128)
        tr.font_world_space = data.get("font_world_space", True)
        tr.billboard = data.get("billboard", False)
        try:
            tr.filter_mode = TextFilter(data.get("filter_mode", "linear"))
        except (ValueError, KeyError):
            tr.filter_mode = TextFilter.LINEAR
        tr.anisotropy = data.get("anisotropy", 4.0)
        tr.shader = data.get("shader", "text") or "text"
        return tr
