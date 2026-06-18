import os
import glob
import traceback

from core.plugin_manager import PluginBase
from core.logger import Logger
from core.ecs import ComponentRegistry

from plugins.zarin_mcp.mcp_server import McpServer


class ZarinMCPPlugin(PluginBase):
    NAME = "ZarinMCP"
    VERSION = "1.0.0"
    DESCRIPTION = "MCP server providing LLMs full access to the engine and scene."
    SYSTEM = False

    def __init__(self):
        super().__init__()
        self._server: McpServer = None
        self._tools: dict = {}
        self._resources: dict = {}

    def initialize(self, engine):
        super().initialize(engine)
        self._build_tools()
        self._build_resources()
        self._server = McpServer(self._tools, self._resources, port=self.get_config("port", 9100))
        mcp_mode = os.environ.get("ZARIN_MCP_MODE", "") or getattr(engine, "_mcp_mode", "")
        if mcp_mode == "stdio":
            Logger.info("[ZarinMCP] Running in stdio MCP mode")
            self._server.run_stdio_forever()
        else:
            self._register_ui()
            self._server.start_sse()
            Logger.info(f"[ZarinMCP] SSE server on http://127.0.0.1:{self.get_config('port', 9100)}/sse")

    def shutdown(self):
        if self._server:
            self._server.stop()
        Logger.info("[ZarinMCP] Shutdown.")

    def _register_ui(self):
        self.add_menu_item("ZarinMCP", "Open MCP Server...", lambda: Logger.info(f"ZarinMCP running on port {self.get_config('port', 9100)}"))
        self.add_toolbar_button("MCP", lambda: Logger.info(f"ZarinMCP on port {self.get_config('port', 9100)}"),
                                tooltip="ZarinMCP Server Status")

    # -------------------------------------------------------------------------
    # Tool implementations
    # -------------------------------------------------------------------------
    def _build_tools(self):
        self._tools = {
            # ---- Scene ----
            "scene_list_entities": {
                "description": "List all entities in the current scene with their basic info (id, name, active, component count)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_components": {
                            "type": "boolean",
                            "description": "If true, include full component data for each entity",
                            "default": False,
                        }
                    },
                },
                "handler": self._tool_scene_list_entities,
            },
            "scene_get_entity": {
                "description": "Get detailed information about a specific entity by id or name",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                        "entity_name": {"type": "string", "description": "Entity name (used if entity_id not provided)"},
                    },
                    "required": [],
                },
                "handler": self._tool_scene_get_entity,
            },
            "scene_create_entity": {
                "description": "Create a new empty entity with a Transform component",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Entity name", "default": "GameObject"},
                        "parent_id": {"type": "string", "description": "Optional parent entity UUID"},
                    },
                },
                "handler": self._tool_scene_create_entity,
            },
            "scene_delete_entity": {
                "description": "Delete an entity from the scene by id",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID to delete"},
                    },
                    "required": ["entity_id"],
                },
                "handler": self._tool_scene_delete_entity,
            },
            "scene_rename_entity": {
                "description": "Rename an entity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                        "new_name": {"type": "string", "description": "New name"},
                    },
                    "required": ["entity_id", "new_name"],
                },
                "handler": self._tool_scene_rename_entity,
            },
            "scene_create_primitive": {
                "description": "Create a 3D primitive object (cube, sphere, or plane) with MeshFilter and MeshRenderer",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "mesh": {"type": "string", "description": "Primitive type: cube, sphere, or plane"},
                        "name": {"type": "string", "description": "Optional name", "default": ""},
                    },
                    "required": ["mesh"],
                },
                "handler": self._tool_scene_create_primitive,
            },
            "scene_create_light": {
                "description": "Create a light (directional, point, or spot)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "light_type": {"type": "string", "description": "directional, point, or spot"},
                    },
                    "required": ["light_type"],
                },
                "handler": self._tool_scene_create_light,
            },
            "scene_create_camera": {
                "description": "Create a Camera entity",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_scene_create_camera,
            },
            "scene_save": {
                "description": "Save the current scene to its file path",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_scene_save,
            },
            "scene_load": {
                "description": "Load a scene file from the project. Lists available scenes if called without path.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to .scene file (relative to project root)"},
                    },
                },
                "handler": self._tool_scene_load,
            },
            "scene_new": {
                "description": "Create a new empty scene",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Scene name", "default": "NewScene"},
                    },
                },
                "handler": self._tool_scene_new,
            },
            "scene_get_hierarchy": {
                "description": "Get the full entity hierarchy tree (parent-child relationships)",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_scene_hierarchy,
            },

            # ---- Component ----
            "component_list_types": {
                "description": "List all registered component types with their categories",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_component_list_types,
            },
            "component_add": {
                "description": "Add a component to an entity by component type name",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                        "component_type": {"type": "string", "description": "Component class name (e.g. MeshFilter, Light, Camera)"},
                    },
                    "required": ["entity_id", "component_type"],
                },
                "handler": self._tool_component_add,
            },
            "component_remove": {
                "description": "Remove a component from an entity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                        "component_type": {"type": "string", "description": "Component class name to remove"},
                    },
                    "required": ["entity_id", "component_type"],
                },
                "handler": self._tool_component_remove,
            },
            "component_get": {
                "description": "Get all properties of a component on an entity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                        "component_type": {"type": "string", "description": "Component class name"},
                    },
                    "required": ["entity_id", "component_type"],
                },
                "handler": self._tool_component_get,
            },
            "component_set_property": {
                "description": "Set a property on a component. For transform, use transform_set_position/rotation/scale.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                        "component_type": {"type": "string", "description": "Component class name"},
                        "property": {"type": "string", "description": "Property name"},
                        "value": {"description": "Value (number, string, bool, or array for vectors)"},
                    },
                    "required": ["entity_id", "component_type", "property", "value"],
                },
                "handler": self._tool_component_set_property,
            },

            # ---- Transform ----
            "transform_get": {
                "description": "Get entity transform (position, rotation in euler, scale, world matrix)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                    },
                    "required": ["entity_id"],
                },
                "handler": self._tool_transform_get,
            },
            "transform_set_position": {
                "description": "Set entity world position as [x, y, z]",
                "inputSchema": {
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
                "handler": self._tool_transform_set_position,
            },
            "transform_set_rotation": {
                "description": "Set entity local rotation as euler angles [x, y, z] in degrees",
                "inputSchema": {
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
                "handler": self._tool_transform_set_rotation,
            },
            "transform_set_scale": {
                "description": "Set entity local scale as [x, y, z]",
                "inputSchema": {
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
                "handler": self._tool_transform_set_scale,
            },

            # ---- Project ----
            "project_get_info": {
                "description": "Get project information (root path, name)",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_project_info,
            },
            "project_get_settings": {
                "description": "Get project settings",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_project_settings,
            },
            "project_set_settings": {
                "description": "Set a project setting value. Use dot notation for nested keys (e.g. 'physics.gravity_x')",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Setting key (dot notation)"},
                        "value": {"description": "Value"},
                    },
                    "required": ["key", "value"],
                },
                "handler": self._tool_project_set_settings,
            },
            "project_list_scenes": {
                "description": "List all .scene files in the project",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_project_list_scenes,
            },

            # ---- Engine ----
            "engine_get_status": {
                "description": "Get engine status (play mode, fps, frame count, scene name)",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_engine_status,
            },
            "engine_play": {
                "description": "Start play mode",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_engine_play,
            },
            "engine_stop": {
                "description": "Stop play mode",
                "inputSchema": {"type": "object", "properties": {}},
                "handler": self._tool_engine_stop,
            },
            "engine_execute_code": {
                "description": "Execute arbitrary Python code in the engine context. Use with caution.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                        "context": {"type": "string", "description": "Optional: 'engine', 'scene', or empty for global"},
                    },
                    "required": ["code"],
                },
                "handler": self._tool_engine_execute_code,
            },
        }

    def _build_resources(self):
        self._resources = {
            "scene://entities": {
                "name": "Scene Entities",
                "description": "Full list of all entities with component summaries",
                "mimeType": "application/json",
                "handler": self._res_scene_entities,
            },
            "scene://hierarchy": {
                "name": "Scene Hierarchy",
                "description": "Entity hierarchy tree",
                "mimeType": "application/json",
                "handler": self._res_scene_hierarchy,
            },
            "project://info": {
                "name": "Project Info",
                "description": "Project root, config, and scene list",
                "mimeType": "application/json",
                "handler": self._res_project_info,
            },
            "engine://status": {
                "name": "Engine Status",
                "description": "Engine runtime status",
                "mimeType": "application/json",
                "handler": self._res_engine_status,
            },
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_scene(self):
        eng = self._engine
        if eng is None:
            return None
        return eng.scene

    def _get_entity_by_id_or_name(self, entity_id: str = "", entity_name: str = ""):
        scene = self._get_scene()
        if scene is None:
            return None
        if entity_id:
            return scene.get_entity(entity_id)
        if entity_name:
            return scene.get_entity_by_name(entity_name)
        return None

    def _serialize_component(self, comp) -> dict:
        try:
            data = comp.serialize()
            return data
        except Exception:
            base = {"type": type(comp).__name__, "enabled": getattr(comp, "enabled", True)}
            for attr in dir(comp):
                if attr.startswith("_"):
                    continue
                val = getattr(comp, attr, None)
                if callable(val):
                    continue
                try:
                    json.dumps({attr: val})
                    base[attr] = val
                except (TypeError, OverflowError):
                    base[attr] = str(val)
            return base

    # -------------------------------------------------------------------------
    # Tool handlers
    # -------------------------------------------------------------------------
    def _tool_scene_list_entities(self, include_components: bool = False):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        results = []
        for e in scene.get_all_entities():
            entry = {
                "id": e.id,
                "name": e.name,
                "active": e.active,
                "component_count": len(e.get_all_components()),
                "component_types": [type(c).__name__ for c in e.get_all_components()],
                "child_count": len(e.children),
                "parent_id": e.parent.id if e.parent else None,
            }
            if include_components:
                entry["components"] = [self._serialize_component(c) for c in e.get_all_components()]
            results.append(entry)
        return {"entities": results, "count": len(results)}

    def _tool_scene_get_entity(self, entity_id: str = "", entity_name: str = ""):
        e = self._get_entity_by_id_or_name(entity_id, entity_name)
        if e is None:
            return {"error": "Entity not found"}
        return {
            "id": e.id,
            "name": e.name,
            "active": e.active,
            "parent_id": e.parent.id if e.parent else None,
            "children": [{"id": c.id, "name": c.name} for c in e.children],
            "components": [self._serialize_component(c) for c in e.get_all_components()],
        }

    def _tool_scene_create_entity(self, name: str = "GameObject", parent_id: str = ""):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        from core.ecs import Entity
        from core.components.transform.transform import Transform
        e = scene.create_entity(name)
        e.add_component(Transform())
        if parent_id:
            parent = scene.get_entity(parent_id)
            if parent:
                e.set_parent(parent)
        return {"id": e.id, "name": e.name, "message": f"Created entity '{e.name}' ({e.id})"}

    def _tool_scene_delete_entity(self, entity_id: str):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        e = scene.get_entity(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        name = e.name
        scene.remove_entity(entity_id)
        return {"message": f"Deleted entity '{name}' ({entity_id})"}

    def _tool_scene_rename_entity(self, entity_id: str, new_name: str):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        e = scene.get_entity(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        old = e.name
        e.name = new_name
        return {"message": f"Renamed '{old}' to '{new_name}'"}

    def _tool_scene_create_primitive(self, mesh: str, name: str = ""):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        from core.ecs import Entity
        from core.components.transform.transform import Transform
        from core.components.rendering.mesh_filter import MeshFilter
        from core.components.rendering.mesh_renderer import MeshRenderer
        e = scene.create_entity(name or mesh.capitalize())
        e.add_component(Transform())
        mf = MeshFilter()
        mf.mesh_name = mesh
        e.add_component(mf)
        e.add_component(MeshRenderer())
        return {"id": e.id, "name": e.name, "message": f"Created {mesh} '{e.name}'"}

    def _tool_scene_create_light(self, light_type: str):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        from core.ecs import Entity
        from core.components.transform.transform import Transform
        from core.components.lighting.light import Light, LightType
        name_map = {"directional": "Directional Light", "point": "Point Light", "spot": "Spot Light"}
        type_map = {"directional": LightType.DIRECTIONAL, "point": LightType.POINT, "spot": LightType.SPOT}
        if light_type not in type_map:
            return {"error": f"Unknown light type: {light_type}. Use: directional, point, or spot"}
        e = scene.create_entity(name_map[light_type])
        e.add_component(Transform())
        l = Light()
        l.light_type = type_map[light_type]
        e.add_component(l)
        return {"id": e.id, "name": e.name, "message": f"Created {light_type} light"}

    def _tool_scene_create_camera(self):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        from core.ecs import Entity
        from core.components.transform.transform import Transform
        from core.components.rendering.camera import Camera
        e = scene.create_entity("Camera")
        e.add_component(Transform())
        e.add_component(Camera())
        return {"id": e.id, "name": e.name, "message": "Created Camera"}

    def _tool_scene_save(self):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}
        if not scene.path:
            return {"error": "Scene has no path. Use scene_save with a path or save via editor first."}
        self._engine.save_scene()
        return {"message": f"Scene saved to {scene.path}"}

    def _tool_scene_load(self, path: str = ""):
        if not path:
            scenes = self._tool_project_list_scenes()
            return {"message": "Provide a path. Available scenes:", "scenes": scenes.get("scenes", [])}
        full = os.path.join(self._engine.project_root, path) if not os.path.isabs(path) else path
        scene = self._engine.load_scene(full)
        if scene is None:
            return {"error": f"Failed to load scene: {path}"}
        return {"message": f"Loaded scene '{scene.name}' from {path}"}

    def _tool_scene_new(self, name: str = "NewScene"):
        self._engine.new_scene(name)
        return {"message": f"Created new scene '{name}'"}

    def _tool_scene_hierarchy(self):
        scene = self._get_scene()
        if scene is None:
            return {"error": "No scene loaded"}

        def _build_tree(e):
            children_data = []
            for child in e.children:
                children_data.append(_build_tree(child))
            comps = [type(c).__name__ for c in e.get_all_components()]
            return {"id": e.id, "name": e.name, "active": e.active, "components": comps, "children": children_data}

        roots = []
        for e in scene.get_root_entities():
            roots.append(_build_tree(e))
        return {"hierarchy": roots, "scene_name": scene.name}

    def _tool_component_list_types(self):
        all_comps = ComponentRegistry.all()
        cats = ComponentRegistry.all_categories()
        result = {}
        for name, cls in all_comps.items():
            module = getattr(cls, "__module__", "")
            cat = cats.get(name, ["Other"])
            result[name] = {
                "category": cat[0] if cat else "Other",
                "module": module,
                "allow_multiple": getattr(cls, "_allow_multiple", False),
            }
        return {"component_types": result, "count": len(result)}

    def _tool_component_add(self, entity_id: str, component_type: str):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component type: {component_type}. Use component_list_types to see available types."}
        try:
            inst = cls()
            e.add_component(inst)
            return {"message": f"Added {component_type} to '{e.name}'", "component": self._serialize_component(inst)}
        except Exception as ex:
            return {"error": f"Failed to add component: {ex}"}

    def _tool_component_remove(self, entity_id: str, component_type: str):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component type: {component_type}"}
        if not e.has_component(cls):
            return {"error": f"Entity does not have component {component_type}"}
        if component_type == "Transform":
            return {"error": "Cannot remove Transform component"}
        e.remove_component(cls)
        return {"message": f"Removed {component_type} from '{e.name}'"}

    def _tool_component_get(self, entity_id: str, component_type: str):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component type: {component_type}"}
        comp = e.get_component(cls)
        if comp is None:
            return {"error": f"Entity does not have component {component_type}"}
        return {"component": self._serialize_component(comp)}

    def _tool_component_set_property(self, entity_id: str, component_type: str, property: str, value):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        cls = ComponentRegistry.get(component_type)
        if cls is None:
            return {"error": f"Unknown component type: {component_type}"}
        comp = e.get_component(cls)
        if comp is None:
            return {"error": f"Entity does not have component {component_type}"}
        try:
            setattr(comp, property, value)
            return {"message": f"Set {component_type}.{property} = {value}"}
        except Exception as ex:
            return {"error": f"Failed to set property: {ex}"}

    def _tool_transform_get(self, entity_id: str):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.get_component_by_name("Transform")
        if t is None:
            return {"error": "Entity has no Transform"}
        return {
            "position": [t.position.x, t.position.y, t.position.z],
            "local_position": [t.local_position.x, t.local_position.y, t.local_position.z],
            "local_euler": [t.local_euler_angles.x, t.local_euler_angles.y, t.local_euler_angles.z],
            "local_scale": [t.local_scale.x, t.local_scale.y, t.local_scale.z],
            "forward": [t.forward.x, t.forward.y, t.forward.z],
            "up": [t.up.x, t.up.y, t.up.z],
        }

    def _tool_transform_set_position(self, entity_id: str, position: list):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.get_component_by_name("Transform")
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.math3d import Vec3
        t.position = Vec3(*position)
        return {"message": f"Set position to {position}"}

    def _tool_transform_set_rotation(self, entity_id: str, euler: list):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.get_component_by_name("Transform")
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.math3d import Vec3
        t.local_euler_angles = Vec3(*euler)
        return {"message": f"Set rotation to {euler}"}

    def _tool_transform_set_scale(self, entity_id: str, scale: list):
        e = self._get_entity_by_id_or_name(entity_id)
        if e is None:
            return {"error": "Entity not found"}
        t = e.get_component_by_name("Transform")
        if t is None:
            return {"error": "Entity has no Transform"}
        from core.math3d import Vec3
        t.local_scale = Vec3(*scale)
        return {"message": f"Set scale to {scale}"}

    def _tool_project_info(self):
        eng = self._engine
        if eng is None:
            return {"error": "Engine not available"}
        root = eng.project_root
        return {
            "project_root": root,
            "project_name": os.path.basename(root) if root else "",
        }

    def _tool_project_settings(self):
        from core.config import get_project_config
        cfg = get_project_config(".", lazy=True)
        if cfg is None:
            return {"error": "No project config"}
        return {"settings": cfg._data}

    def _tool_project_set_settings(self, key: str, value):
        from core.config import get_project_config
        cfg = get_project_config(".", lazy=True)
        if cfg is None:
            return {"error": "No project config"}
        cfg.set(key, value)
        cfg.save()
        return {"message": f"Set {key} = {value}"}

    def _tool_project_list_scenes(self):
        eng = self._engine
        if eng is None:
            return {"error": "Engine not available"}
        root = eng.project_root
        scenes = glob.glob(os.path.join(root, "**", "*.scene"), recursive=True)
        rel = [os.path.relpath(s, root).replace("\\", "/") for s in scenes]
        return {"scenes": sorted(rel), "count": len(rel)}

    def _tool_engine_status(self):
        eng = self._engine
        if eng is None:
            return {"error": "Engine not available"}
        scene = eng.scene
        return {
            "play_mode": eng.play_mode,
            "fps": eng.fps,
            "frame_count": eng.frame_count,
            "time_scale": eng.time_scale,
            "scene_name": scene.name if scene else None,
            "scene_path": scene.path if scene else None,
            "entity_count": len(scene.get_all_entities()) if scene else 0,
        }

    def _tool_engine_play(self):
        if self._engine is None:
            return {"error": "Engine not available"}
        self._engine.start_play()
        return {"message": "Play mode started"}

    def _tool_engine_stop(self):
        if self._engine is None:
            return {"error": "Engine not available"}
        self._engine.stop_play()
        return {"message": "Play mode stopped"}

    def _tool_engine_execute_code(self, code: str, context: str = ""):
        try:
            loc = {}
            if context == "engine":
                loc["engine"] = self._engine
            elif context == "scene":
                loc["scene"] = self._engine.scene if self._engine else None
            else:
                loc["engine"] = self._engine
                loc["scene"] = self._engine.scene if self._engine else None
                loc["Entity"] = __import__("core.ecs", fromlist=["Entity"]).Entity
                loc["Component"] = __import__("core.ecs", fromlist=["Component"]).Component
                loc["ComponentRegistry"] = __import__("core.ecs", fromlist=["ComponentRegistry"]).ComponentRegistry
            exec(code, globals(), loc)
            result = loc.get("_result", "Code executed successfully (no _result variable set)")
            return {"result": str(result)}
        except Exception as e:
            return {"error": f"Execution error: {e}\n{traceback.format_exc()}"}

    # -------------------------------------------------------------------------
    # Resource handlers
    # -------------------------------------------------------------------------
    def _res_scene_entities(self):
        result = self._tool_scene_list_entities(include_components=True)
        return result

    def _res_scene_hierarchy(self):
        result = self._tool_scene_hierarchy()
        return result

    def _res_project_info(self):
        return {
            "project": self._tool_project_info(),
            "settings": self._tool_project_settings(),
            "scenes": self._tool_project_list_scenes(),
        }

    def _res_engine_status(self):
        return self._tool_engine_status()


# Required for DLL/SO loading
def get_plugin():
    return ZarinMCPPlugin()
