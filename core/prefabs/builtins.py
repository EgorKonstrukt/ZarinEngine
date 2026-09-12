# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import os


def _make_spec(entity_name: str, comp_specs: list, builder_name: str = ""):
    def build(scene):
        from core.ecs.ecs import ComponentRegistry
        entity = scene.create_entity(entity_name)
        for spec in comp_specs:
            cls = ComponentRegistry.get(spec.get("type", ""))
            if cls is None:
                continue
            comp = cls()
            for key, value in (spec.get("props") or {}).items():
                try:
                    setattr(comp, key, value)
                except Exception:
                    continue
            entity.add_component(comp)
        return entity
    build.__name__ = builder_name or ("build_" + entity_name)
    return build


def _make_probuilder(primitive_name: str):
    def build(scene):
        from core.components import Transform, MeshFilter, MeshRenderer
        from core.components.mesh_editor import ProBuilderMesh, create_primitive
        entity = scene.create_entity(primitive_name)
        entity.add_component(Transform())
        entity.add_component(MeshFilter())
        entity.add_component(MeshRenderer())
        mesh = ProBuilderMesh()
        entity.add_component(mesh)
        positions, indices = create_primitive(primitive_name)
        mesh.set_mesh_data(positions, indices)
        mesh_filter = entity.get_component(MeshFilter)
        if mesh_filter is not None:
            mesh_filter.mesh_name = f"ProBuilder_{entity.id[:6]}"
        return entity
    build.__name__ = "build_probuilder_" + primitive_name
    return build


def _load_specs() -> list:
    import yaml
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system_prefabs.yaml")
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or []


def register_all() -> None:
    from core.prefabs.registry import register_system_prefab
    for entry in _load_specs():
        menu_path = entry.get("menu", "")
        entity_name = entry.get("name", "")
        order = int(entry.get("order", 100))
        description = entry.get("description", "") or ""
        probuilder = entry.get("probuilder")
        if probuilder:
            register_system_prefab(menu_path, _make_probuilder(str(probuilder)),
                                   name=entity_name, order=order,
                                   description=description, overwrite=True,
                                   icon="ProBuilderMesh")
            continue
        comp_specs = entry.get("components") or [{"type": "Transform"}]
        builder_name = ""
        non_transform = [s for s in comp_specs if s.get("type") != "Transform"]
        if len(non_transform) == 1 and len(comp_specs) == 2:
            builder_name = "build_" + str(non_transform[0].get("type"))
        icon = str(entry.get("icon") or "")
        if not icon and non_transform:
            icon = str(non_transform[0].get("type") or "")
        if not icon and comp_specs:
            icon = str(comp_specs[0].get("type") or "")
        register_system_prefab(menu_path, _make_spec(entity_name, comp_specs, builder_name),
                               name=entity_name, order=order,
                               description=description, overwrite=True, icon=icon)
