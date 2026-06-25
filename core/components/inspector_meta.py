from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Type


class FieldType(Enum):
    FLOAT = "float"
    VEC2 = "vec2"
    VEC3 = "vec3"
    BOOL = "bool"
    ENUM = "enum"
    STRING = "string"
    RESOURCE_PATH = "resource_path"
    INT = "int"
    GAMEOBJECT = "gameobject"
    RESOURCE = "resource"
    COLOR = "color"
    CURVE = "curve"
    LIST = "list"
    BUTTON = "button"
    ANCHOR = "anchor"
    HEADER = "header"
    SLIDER = "slider"
    INT_SLIDER = "int_slider"
    LAYER = "layer"
    LAYER_MASK = "layer_mask"
    ASSET = "asset"
    TEXTAREA = "textarea"


@dataclass
class ListElementField:
    name: str
    label: str
    field_type: FieldType
    min_val: float = -100000000000000000.0
    max_val: float = 100000000000000000.0
    step: float = 0.1
    decimals: int = 4
    enum_class: Optional[Type[Enum]] = None


@dataclass
class InspectorField:
    name: str
    label: str
    field_type: FieldType
    enum_class: Optional[Type[Enum]] = None
    file_filter: str = ""
    resource_type: str = ""
    toggle_field: str = ""
    min_val: float = -100000000000000000.0
    max_val: float = 100000000000000000.0
    step: float = 0.1
    decimals: int = 4
    readonly: bool = False
    element_fields: list[ListElementField] = field(default_factory=list)

@dataclass
class ComponentInspectorMeta:
    categories: list[str] = field(default_factory=list)
