# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from plugins.zarin_mcp.handlers.util import get_entity_by_id_or_name, serialize_component


def register_query(registry, engine):
    _scene = lambda: engine.scene

    @registry.tool(
        "scene_list_entities",
        "List entities with pagination & filtering. TIP: Use filter_name to find Counter/Spawner, limit/offset for huge scenes, include_components=false by default to avoid truncation. For huge scenes, prefer scene_get_hierarchy or entity_find.",
        {
            "type": "object",
            "properties": {
                "include_components": {
                    "type": "boolean",
                    "description": "Include full component data (heavy, causes truncation)",
                    "default": False,
                },
                "filter_name": {
                    "type": "string",
                    "description": "Substring filter (case-insensitive) for entity name, e.g. 'Counter' or 'Spawner'",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entities to return (0 = all, default 50 to avoid truncation)",
                    "default": 50,
                },
                "offset": {
                    "type": "integer",
                    "description": "Skip first N entities for pagination",
                    "default": 0,
                },
            },
        },
    )
    def scene_list_entities(include_components=False, filter_name="", limit=50, offset=0):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded", "help": "Call project_get_info to see project root, scene_get_hierarchy for tree view"}
        all_ents = s.get_all_entities()
        if filter_name:
            all_ents = [e for e in all_ents if filter_name.lower() in e.name.lower()]
        total = len(all_ents)
        if limit and limit > 0:
            all_ents = all_ents[offset:offset+limit]
        else:
            all_ents = all_ents[offset:]
        results = []
        for e in all_ents:
            entry = {
                "id": e.id,
                "name": e.name,
                "active": e.active,
                "component_count": len(e.get_all_components()),
                "component_types": [type(c).__name__ for c in e.get_all_components()],
                "child_count": len(e.children),
                "parent_id": e.parent.id if e.parent else None,
                "layer": e.layer,
                "tags": list(e.tags),
            }
            if include_components:
                entry["components"] = [serialize_component(c) for c in e.get_all_components()]
            results.append(entry)
        return {"entities": results, "count": len(results), "total_matched": total, "offset": offset, "limit": limit, "help": "Use filter_name='Counter' to find Counter, or scene_get_hierarchy for tree"}

    @registry.tool(
        "scene_get_entity",
        "Get full details of an entity by id or name",
        {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Entity UUID"},
                "entity_name": {"type": "string", "description": "Entity name fallback"},
            },
        },
    )
    def scene_get_entity(entity_id="", entity_name=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        e = get_entity_by_id_or_name(s, entity_id, entity_name)
        if e is None:
            return {"error": "Entity not found"}
        return {
            "id": e.id,
            "name": e.name,
            "active": e.active,
            "parent_id": e.parent.id if e.parent else None,
            "children": [{"id": c.id, "name": c.name} for c in e.children],
            "components": [serialize_component(c) for c in e.get_all_components()],
            "tags": list(e.tags),
            "layer": e.layer,
            "is_prefab_instance": e.is_prefab_instance,
            "prefab_guid": e.prefab_guid,
        }

    @registry.tool(
        "scene_get_hierarchy",
        "Get the full entity hierarchy tree",
        {"type": "object", "properties": {}},
    )
    def scene_get_hierarchy():
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        def build_tree(e):
            comps = [type(c).__name__ for c in e.get_all_components()]
            return {
                "id": e.id, "name": e.name, "active": e.active,
                "components": comps, "layer": e.layer,
                "children": [build_tree(c) for c in e.children],
            }
        roots = [build_tree(e) for e in s.get_root_entities()]
        return {"hierarchy": roots, "scene_name": s.name}

    @registry.tool(
        "scene_get_entities_by_component",
        "Find all entities with a specific component type",
        {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "description": "Component class name (e.g. MeshRenderer, Light)",
                }
            },
            "required": ["component_type"],
        },
    )
    def scene_get_entities_by_component(component_type=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        from core.ecs import ComponentRegistry
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component: {component_type}"}
        entities = s.get_entities_with_component(cls)
        return {
            "entities": [
                {"id": e.id, "name": e.name} for e in entities
            ],
            "count": len(entities),
        }

    @registry.tool(
        "scene_get_entities_by_tag",
        "Find all entities with a specific tag",
        {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Tag to search for"},
            },
            "required": ["tag"],
        },
    )
    def scene_get_entities_by_tag(tag=""):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        results = []
        for e in s.get_all_entities():
            if tag in e.tags:
                results.append({"id": e.id, "name": e.name})
        return {"entities": results, "count": len(results)}

    @registry.tool(
        "scene_find_entities",
        "Find entities by substring (case-insensitive) in name, tag, or component. BETTER than scene_list_entities for huge scenes.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Substring in name, e.g. 'Counter', 'Spawner'", "default": ""},
                "tag": {"type": "string", "description": "Tag to search", "default": ""},
                "component": {"type": "string", "description": "Component type, e.g. 'TextRenderer', 'Rigidbody'", "default": ""},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
        },
    )
    def scene_find_entities(name="", tag="", component="", limit=20):
        s = _scene()
        if s is None:
            return {"error": "No scene loaded"}
        results = []
        for e in s.get_all_entities():
            ok = True
            if name and name.lower() not in e.name.lower():
                ok = False
            if tag and tag not in e.tags:
                ok = False
            if component:
                from core.ecs import ComponentRegistry
                cls = ComponentRegistry.get(component)
                if cls is None or not e.has_component(cls):
                    ok = False
            if ok:
                results.append({"id": e.id, "name": e.name, "components": [type(c).__name__ for c in e.get_all_components()], "active": e.active})
                if len(results) >= limit:
                    break
        return {"entities": results, "count": len(results), "help": "Use scene_get_entity with id for full details"}
