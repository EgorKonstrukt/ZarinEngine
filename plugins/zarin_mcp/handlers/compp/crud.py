# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from plugins.zarin_mcp.handlers.util import (
    get_entity_by_id_or_name,
    serialize_component,
    component_inspector_fields,
    coerce_value,
    value_to_json,
)


def register_crud(registry, engine):
    _scene = lambda: engine.scene

    @registry.tool(
        "component_list_types",
        "List component types with FILTERING to avoid truncation. Use search='Rigidbody' or category='Physics' or limit=20. HUGE list (190+ types) truncated otherwise.",
        {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Substring filter for component name, e.g. 'Rigidbody', 'Collider', 'Text'", "default": ""},
                "category": {"type": "string", "description": "Filter by category: Animation, Audio, Constraints, Gizmo, GUI, Light, Network, Physics, Rendering, Scripting, Transform, etc", "default": ""},
                "limit": {"type": "integer", "description": "Max to return (default 30)", "default": 30},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
            },
        },
    )
    def component_list_types(search="", category="", limit=30, offset=0):
        from core.ecs import ComponentRegistry
        all_comps = ComponentRegistry.all()
        cats = ComponentRegistry.all_categories()
        items = []
        for name, cls in sorted(all_comps.items()):
            cat = cats.get(name, ["Other"])[0] if cats.get(name) else "Other"
            if category and category.lower() not in cat.lower():
                continue
            if search and search.lower() not in name.lower():
                continue
            module = getattr(cls, "__module__", "")
            items.append((name, {"category": cat, "module": module, "allow_multiple": getattr(cls, "_allow_multiple", False)}))
        total = len(items)
        if limit and limit > 0:
            items = items[offset:offset+limit]
        else:
            items = items[offset:]
        result = {name: info for name, info in items}
        return {"component_types": result, "count": len(result), "total_matched": total, "offset": offset, "limit": limit, "help": "Use search='Text' to find TextRenderer, category='Physics' for Rigidbody/BoxCollider, limit=20"}

    @registry.tool(
        "component_add",
        "Add a component to an entity, optionally with initial property values",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "component_type": {"type": "string", "description": "Component class name"},
                "properties": {
                    "type": "object",
                    "description": "Optional initial property values to set after adding",
                    "default": {},
                },
            },
            "required": ["entity_id", "component_type"],
        },
    )
    def component_add(entity_id="", component_type="", properties=None):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        if component_type != "Transform" and e.has_component(cls) and not getattr(cls, "_allow_multiple", False):
            return {"error": f"Entity already has {component_type}"}
        try:
            inst = cls()
            e.add_component(inst)
        except Exception as ex:
            return {"error": f"Failed to add component: {ex}"}
        fields = component_inspector_fields(component_type)
        applied = {}
        errors = {}
        for k, v in (properties or {}).items():
            if not hasattr(inst, k):
                errors[k] = "no such property"
                continue
            try:
                setattr(inst, k, coerce_value(inst, k, v, fields.get(k)))
                applied[k] = value_to_json(getattr(inst, k))
            except Exception as ex:
                errors[k] = str(ex)
        result = {"message": f"Added {component_type} to '{e.name}'", "component": serialize_component(inst)}
        if applied:
            result["properties_applied"] = applied
        if errors:
            result["property_errors"] = errors
        return result

    @registry.tool(
        "component_remove",
        "Remove a component from an entity",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "component_type": {"type": "string", "description": "Component class name to remove"},
            },
            "required": ["entity_id", "component_type"],
        },
    )
    def component_remove(entity_id="", component_type=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        if not e.has_component(cls):
            return {"error": f"Entity has no {component_type}"}
        if component_type == "Transform":
            return {"error": "Cannot remove Transform"}
        e.remove_component(cls)
        return {"message": f"Removed {component_type} from '{e.name}'"}

    @registry.tool(
        "component_get",
        "Get all properties of a component on an entity",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "component_type": {"type": "string", "description": "Component class name"},
            },
            "required": ["entity_id", "component_type"],
        },
    )
    def component_get(entity_id="", component_type=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        comp = e.get_component(cls)
        if comp is None:
            return {"error": f"Entity has no {component_type}"}
        return {"component": serialize_component(comp)}

    @registry.tool(
        "component_set_property",
        "Set a property on a component. Values are coerced to the property type (numbers, bools, vectors, enums). For transform use transform_* tools.",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "component_type": {"type": "string", "description": "Component class name"},
                "property": {"type": "string", "description": "Property name"},
                "value": {"description": "Value (number, string, bool, or array for vectors/colors)"},
            },
            "required": ["entity_id", "component_type", "property", "value"],
        },
    )
    def component_set_property(entity_id="", component_type="", property="", value=None):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        comp = e.get_component(cls)
        if comp is None:
            return {"error": f"Entity has no {component_type}"}
        if not hasattr(comp, property):
            return {"error": f"{component_type} has no property '{property}'"}
        fields = component_inspector_fields(component_type)
        try:
            new_value = coerce_value(comp, property, value, fields.get(property))
            setattr(comp, property, new_value)
            return {
                "message": f"Set {component_type}.{property}",
                "value": value_to_json(getattr(comp, property)),
            }
        except Exception as ex:
            return {"error": f"Failed to set property: {ex}"}

    @registry.tool(
        "component_set_properties",
        "Set multiple properties on a component in one call",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "component_type": {"type": "string", "description": "Component class name"},
                "properties": {
                    "type": "object",
                    "description": "Property name -> value map",
                },
            },
            "required": ["entity_id", "component_type", "properties"],
        },
    )
    def component_set_properties(entity_id="", component_type="", properties=None):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        comp = e.get_component(cls)
        if comp is None:
            return {"error": f"Entity has no {component_type}"}
        fields = component_inspector_fields(component_type)
        applied = {}
        errors = {}
        for k, v in (properties or {}).items():
            if not hasattr(comp, k):
                errors[k] = "no such property"
                continue
            try:
                setattr(comp, k, coerce_value(comp, k, v, fields.get(k)))
                applied[k] = value_to_json(getattr(comp, k))
            except Exception as ex:
                errors[k] = str(ex)
        result = {"message": f"Set {len(applied)} properties on {component_type} of '{e.name}'", "applied": applied}
        if errors:
            result["errors"] = errors
        return result

    @registry.tool(
        "component_has",
        "Check whether an entity has a specific component",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "component_type": {"type": "string", "description": "Component class name"},
            },
            "required": ["entity_id", "component_type"],
        },
    )
    def component_has(entity_id="", component_type=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        return {
            "entity": e.name,
            "component_type": component_type,
            "has": e.has_component(cls),
        }

    @registry.tool(
        "component_list",
        "List all components on an entity with keys and enabled state",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
            },
            "required": ["entity_id"],
        },
    )
    def component_list(entity_id=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id)
        if e is None:
            return {"error": "Entity not found"}
        comps = []
        for c in e.get_all_components():
            comps.append({
                "type": type(c).__name__,
                "key": getattr(c, "_key", ""),
                "enabled": bool(getattr(c, "enabled", True)),
            })
        return {"entity": e.name, "components": comps, "count": len(comps)}
