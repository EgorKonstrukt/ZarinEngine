# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from plugins.zarin_mcp.handlers.util import (
    get_entity_by_id_or_name,
    component_inspector_fields,
    value_to_json,
    value_type_name,
)


def register_transform(registry, engine):
    _scene = lambda: engine.scene

    @registry.tool(
        "component_get_properties",
        "Describe the editable properties of a component type (names, types, defaults, enum options, ranges)",
        {
            "type": "object",
            "properties": {
                "component_type": {"type": "string", "description": "Component class name"},
            },
            "required": ["component_type"],
        },
    )
    def component_get_properties(component_type=""):
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        try:
            inst = cls()
        except Exception as ex:
            return {"error": f"Failed to instantiate {component_type}: {ex}"}
        fields = component_inspector_fields(component_type)
        properties = []
        if fields:
            for fname, f in fields.items():
                current = getattr(inst, fname, None)
                entry = {
                    "name": fname,
                    "label": getattr(f, "label", fname),
                    "field_type": f.field_type.value,
                    "value_type": value_type_name(current),
                    "value": value_to_json(current),
                    "readonly": bool(getattr(f, "readonly", False)),
                }
                if f.enum_class is not None:
                    entry["enum_options"] = [m.name for m in f.enum_class]
                if getattr(f, "min_val", -1e18) > -1e17:
                    entry["min"] = f.min_val
                if getattr(f, "max_val", 1e18) < 1e17:
                    entry["max"] = f.max_val
                if f.field_type.name in ("FLOAT", "INT", "SLIDER", "INT_SLIDER"):
                    entry["step"] = f.step
                if getattr(f, "description", ""):
                    entry["description"] = f.description
                properties.append(entry)
        else:
            descr_map = dict(vars(type(inst)))
            for attr in dir(inst):
                if attr.startswith("_"):
                    continue
                val = getattr(inst, attr, None)
                if callable(val):
                    continue
                descr = descr_map.get(attr)
                readonly = isinstance(descr, property) and descr.fset is None
                properties.append({
                    "name": attr,
                    "value_type": value_type_name(val),
                    "value": value_to_json(val),
                    "readonly": readonly,
                })
        return {"component_type": component_type, "properties": properties, "count": len(properties)}

    @registry.tool(
        "component_move",
        "Re-order a component on an entity (move up/down)",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "component_key": {"type": "string", "description": "Component key (e.g. 'MeshFilter')"},
                "direction": {
                    "type": "integer",
                    "description": "1 = move down, -1 = move up",
                },
            },
            "required": ["entity_id", "component_key", "direction"],
        },
    )
    def component_move(entity_id="", component_key="", direction=0):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        try:
            e.move_component(component_key, direction)
            return {"message": f"Moved component '{component_key}' on '{e.name}'"}
        except Exception as ex:
            return {"error": f"Failed to move component: {ex}"}

    @registry.tool(
        "transform_get",
        "Get entity transform (position, rotation, scale, direction vectors)",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
            },
            "required": ["entity_id"],
        },
    )
    def transform_get(entity_id=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.transform
        if t is None:
            return {"error": "Entity has no Transform"}
        return {
            "position": [t.position.x, t.position.y, t.position.z],
            "local_position": [t.local_position.x, t.local_position.y, t.local_position.z],
            "local_euler": [t.local_euler_angles.x, t.local_euler_angles.y, t.local_euler_angles.z],
            "local_scale": [t.local_scale.x, t.local_scale.y, t.local_scale.z],
            "forward": [t.forward.x, t.forward.y, t.forward.z],
            "up": [t.up.x, t.up.y, t.up.z],
            "right": [t.right.x, t.right.y, t.right.z],
        }

    @registry.tool(
        "transform_set_position",
        "Set entity world position [x, y, z]",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[x, y, z] world position",
                },
            },
            "required": ["entity_id", "position"],
        },
    )
    def transform_set_position(entity_id="", position=None):
        if position is None:
            position = [0, 0, 0]
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.transform
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.maths.math3d import Vec3
        t.position = Vec3(*position)
        return {"message": f"Set position to {position}"}

    @registry.tool(
        "transform_set_local_position",
        "Set entity local position [x, y, z]",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[x, y, z] local position",
                },
            },
            "required": ["entity_id", "position"],
        },
    )
    def transform_set_local_position(entity_id="", position=None):
        if position is None:
            position = [0, 0, 0]
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.transform
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.maths.math3d import Vec3
        t.local_position = Vec3(*position)
        return {"message": f"Set local position to {position}"}

    @registry.tool(
        "transform_set_rotation",
        "Set entity local euler rotation [pitch, yaw, roll] in degrees",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "euler": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[pitch, yaw, roll] in degrees",
                },
            },
            "required": ["entity_id", "euler"],
        },
    )
    def transform_set_rotation(entity_id="", euler=None):
        if euler is None:
            euler = [0, 0, 0]
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.transform
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.maths.math3d import Vec3
        t.local_euler_angles = Vec3(*euler)
        return {"message": f"Set rotation to {euler}"}

    @registry.tool(
        "transform_set_scale",
        "Set entity local scale [sx, sy, sz]",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "scale": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[sx, sy, sz] scale factors",
                },
            },
            "required": ["entity_id", "scale"],
        },
    )
    def transform_set_scale(entity_id="", scale=None):
        if scale is None:
            scale = [1, 1, 1]
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.transform
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.maths.math3d import Vec3
        t.local_scale = Vec3(*scale)
        return {"message": f"Set scale to {scale}"}

    @registry.tool(
        "transform_look_at",
        "Make entity look at a target position",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "target": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[x, y, z] target world position",
                },
                "up": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[x, y, z] up vector, default [0,1,0]",
                },
            },
            "required": ["entity_id", "target"],
        },
    )
    def transform_look_at(entity_id="", target=None, up=None):
        if target is None:
            target = [0, 0, 0]
        if up is None:
            up = [0, 1, 0]
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.transform
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.maths.math3d import Vec3, Quat
        direction = Vec3(*target) - t.position
        if direction.length() < 1e-10:
            return {"error": "Target is at the same position as entity"}
        t.rotation = Quat.look_rotation(direction, Vec3(*up))
        return {"message": f"Look at {target}"}
