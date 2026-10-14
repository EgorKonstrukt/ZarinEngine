# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun


from __future__ import annotations
import math
import os
import tempfile
import uuid
import numpy as np
from core.foundation.logger import Logger


def _sanitize_name(name: str) -> str:
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if out and out[0].isdigit():
        out = "_" + out
    return out or "_"


def _euler_to_quat(euler: tuple[float, float, float]) -> tuple[float, float, float, float]:
    ex, ey, ez = euler
    cx, sx = math.cos(ex / 2), math.sin(ex / 2)
    cy, sy = math.cos(ey / 2), math.sin(ey / 2)
    cz, sz = math.cos(ez / 2), math.sin(ez / 2)
    return (
        sx*cy*cz - cx*sy*sz,
        cx*sy*cz + sx*cy*sz,
        cx*cy*sz - sx*sy*cz,
        cx*cy*cz + sx*sy*sz,
    )


def _quat_to_euler(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    qx, qy, qz, qw = q
    sinr_cosp = 2 * (qw * qx + qy * qz)
    cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2 * (qw * qy - qz * qx)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)
    siny_cosp = 2 * (qw * qz + qx * qy)
    cosy_cosp = 1 - 2 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return (roll, pitch, yaw)


def _build_usda(
    gravity: tuple[float, float, float],
    body_specs: list[dict],
    joint_specs: list[dict] | None = None,
) -> str:
    gx, gy, gz = gravity
    lines = [
        chr(35) + "usda 1.0",
        '(',
        '    defaultPrim = "World"',
        '    metersPerUnit = 1',
        '    upAxis = "Y"',
        ')',
        '',
        'def Xform "World"',
        '{',
    ]

    mag = math.sqrt(gx*gx + gy*gy + gz*gz)
    if mag > 1e-10:
        nd = (gx/mag, gy/mag, gz/mag)
    else:
        nd = (0, -1, 0)
        mag = 9.81

    lines.append('    def PhysicsScene "PhysicsScene"')
    lines.append('    {')
    lines.append(f'        vector3f physics:gravityDirection = ({nd[0]:.6f}, {nd[1]:.6f}, {nd[2]:.6f})')
    lines.append(f'        float physics:gravityMagnitude = {mag:.6f}')
    lines.append('    }')
    lines.append('')

    for b in body_specs:
        bid = b["body_id"]
        eid = b.get("entity_id", "")
        prim_name = _sanitize_name(eid) + f"_{bid}" if eid else f"body_{bid}"
        p = b["position"]
        r = b["rotation"]
        mass = b.get("mass", 1.0)
        is_kinematic = b.get("is_kinematic", False)
        is_trigger = b.get("is_trigger", False)
        shape_type = b["shape_type"]
        shape_params = b.get("shape_params", {})

        is_static = (mass <= 0 and not is_kinematic) or is_trigger

        if is_static:
            api = 'prepend apiSchemas = ["PhysicsCollisionAPI"]'
        else:
            api = 'prepend apiSchemas = ["PhysicsRigidBodyAPI", "PhysicsMassAPI"]'

        lines.append(f'    def Xform "{prim_name}" (')
        lines.append(f'        {api}')
        lines.append('    )')
        lines.append('    {')
        lines.append(f'        double3 xformOp:translate = ({p[0]:.6f}, {p[1]:.6f}, {p[2]:.6f})')
        if not is_static:
            qw, qx, qy, qz = _euler_to_quat(r)
            lines.append(f'        quatd xformOp:orient = ({qw:.10f}, {qx:.10f}, {qy:.10f}, {qz:.10f})')
            lines.append('        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]')
        else:
            lines.append('        uniform token[] xformOpOrder = ["xformOp:translate"]')
        lines.append('')

        if not is_static:
            lines.append(f'        float physics:mass = {mass}')
            if is_kinematic:
                lines.append(f'        bool physics:kinematicEnabled = 1')
            lines.append('')

        geom_name = f"{prim_name}_G"
        if shape_type == "box":
            sx, sy, sz = shape_params.get("size", [1, 1, 1])
            cx, cy, cz = shape_params.get("center", [0, 0, 0])
            lines.append(f'        def Cube "{geom_name}" (')
            lines.append('            prepend apiSchemas = ["PhysicsCollisionAPI"]')
            lines.append('        )')
            lines.append('        {')
            lines.append(f'            double size = 2')
            lines.append(f'            double3 xformOp:scale = ({sx/2:.6f}, {sy/2:.6f}, {sz/2:.6f})')
            if cx != 0 or cy != 0 or cz != 0:
                lines.append(f'            double3 xformOp:translate = ({cx:.6f}, {cy:.6f}, {cz:.6f})')
                lines.append(f'            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]')
            else:
                lines.append(f'            uniform token[] xformOpOrder = ["xformOp:scale"]')
            lines.append('        }')

        elif shape_type == "sphere":
            radius = shape_params.get("radius", 0.5)
            center = shape_params.get("center", [0, 0, 0])
            lines.append(f'        def Sphere "{geom_name}" (')
            lines.append('            prepend apiSchemas = ["PhysicsCollisionAPI"]')
            lines.append('        )')
            lines.append('        {')
            lines.append(f'            float3[] extent = [({-radius:.6f}, {-radius:.6f}, {-radius:.6f}), ({radius:.6f}, {radius:.6f}, {radius:.6f})]')
            lines.append(f'            double radius = {radius:.6f}')
            if center[0] != 0 or center[1] != 0 or center[2] != 0:
                lines.append(f'            double3 xformOp:translate = ({center[0]:.6f}, {center[1]:.6f}, {center[2]:.6f})')
                lines.append(f'            uniform token[] xformOpOrder = ["xformOp:translate"]')
            lines.append('        }')

        elif shape_type == "capsule":
            radius = shape_params.get("radius", 0.5)
            height = shape_params.get("height", 2.0)
            center = shape_params.get("center", [0, 0, 0])
            total_h = height + 2 * radius
            lines.append(f'        def Cylinder "{geom_name}" (')
            lines.append('            prepend apiSchemas = ["PhysicsCollisionAPI"]')
            lines.append('        )')
            lines.append('        {')
            lines.append(f'            double height = {total_h:.6f}')
            lines.append(f'            double radius = {radius:.6f}')
            lines.append(f'            float3[] extent = [({-radius:.6f}, {-total_h/2:.6f}, {-radius:.6f}), ({radius:.6f}, {total_h/2:.6f}, {radius:.6f})]')
            if center[0] != 0 or center[1] != 0 or center[2] != 0:
                lines.append(f'            double3 xformOp:translate = ({center[0]:.6f}, {center[1]:.6f}, {center[2]:.6f})')
                lines.append(f'            uniform token[] xformOpOrder = ["xformOp:translate"]')
            lines.append('            uniform token axis = "Y"')
            lines.append('        }')

        elif shape_type == "cylinder":
            radius = shape_params.get("radius", 0.5)
            h = shape_params.get("height", 1.0)
            center = shape_params.get("center", [0, 0, 0])
            lines.append(f'        def Cylinder "{geom_name}" (')
            lines.append('            prepend apiSchemas = ["PhysicsCollisionAPI"]')
            lines.append('        )')
            lines.append('        {')
            lines.append(f'            double height = {h:.6f}')
            lines.append(f'            double radius = {radius:.6f}')
            lines.append(f'            float3[] extent = [({-radius:.6f}, {-h/2:.6f}, {-radius:.6f}), ({radius:.6f}, {h/2:.6f}, {radius:.6f})]')
            if center[0] != 0 or center[1] != 0 or center[2] != 0:
                lines.append(f'            double3 xformOp:translate = ({center[0]:.6f}, {center[1]:.6f}, {center[2]:.6f})')
                lines.append(f'            uniform token[] xformOpOrder = ["xformOp:translate"]')
            lines.append('            uniform token axis = "Y"')
            lines.append('        }')

        elif shape_type == "plane":
            normal = shape_params.get("normal", [0, 1, 0])
            nx, ny, nz = normal
            axis = "Y" if abs(ny) > 0.5 else ("Z" if abs(nz) > 0.5 else "X")
            lines.append(f'        def Plane "{geom_name}" (')
            lines.append('            prepend apiSchemas = ["PhysicsCollisionAPI"]')
            lines.append('        )')
            lines.append('        {')
            lines.append(f'            uniform token axis = "{axis}"')
            lines.append('            uniform token purpose = "guide"')
            lines.append('        }')

        elif shape_type == "mesh":
            verts = shape_params.get("vertices", [])
            if verts:
                pts_str = ", ".join(f"({v[0]:.6f}, {v[1]:.6f}, {v[2]:.6f})" for v in verts)
                lines.append(f'        def Mesh "{geom_name}" (')
                lines.append('            prepend apiSchemas = ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"]')
                lines.append('        )')
                lines.append('        {')
                lines.append('            uniform token physics:approximation = "convexHull"')
                lines.append('            bool physics:collisionEnabled = 1')
                lines.append(f'            point3f[] points = [{pts_str}]')
                n = len(verts)
                if n >= 3:
                    fc = [3] * (n - 2)
                    fi = []
                    for i in range(1, n - 1):
                        fi.extend([0, i, i + 1])
                    fc_str = ", ".join(str(c) for c in fc)
                    fi_str = ", ".join(str(i) for i in fi)
                    lines.append(f'            int[] faceVertexCounts = [{fc_str}]')
                    lines.append(f'            int[] faceVertexIndices = [{fi_str}]')
                lines.append('        }')
            else:
                file_path = shape_params.get("file", "")
                Logger.warning(f"PhysXSolver: mesh '{file_path}' needs pre-loaded vertices")

        elif shape_type == "heightfield":
            verts = shape_params.get("vertices")
            if verts:
                pts_str = ", ".join(f"({v[0]:.6f}, {v[1]:.6f}, {v[2]:.6f})" for v in verts)
                lines.append(f'        def Mesh "{geom_name}" (')
                lines.append('            prepend apiSchemas = ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"]')
                lines.append('        )')
                lines.append('        {')
                lines.append('            uniform token physics:approximation = "triangleMesh"')
                lines.append('            bool physics:collisionEnabled = 1')
                lines.append(f'            point3f[] points = [{pts_str}]')
                n = len(verts)
                if n >= 3:
                    fc = [3] * (n - 2)
                    fi = []
                    for i in range(1, n - 1):
                        fi.extend([0, i, i + 1])
                    fc_str = ", ".join(str(c) for c in fc)
                    fi_str = ", ".join(str(i) for i in fi)
                    lines.append(f'            int[] faceVertexCounts = [{fc_str}]')
                    lines.append(f'            int[] faceVertexIndices = [{fi_str}]')
                lines.append('        }')
            else:
                Logger.warning("PhysXSolver: heightfield needs pre-built vertices")

        lines.append('')
        lines.append('    }')
        lines.append('')

    if joint_specs:
        lines.append('')
        for j in joint_specs:
            jtype = j["joint_type"]
            jprim = j["prim_name"]
            jbody0 = j["body0_path"]
            jbody1 = j.get("body1_path")
            janchor = j["anchor"]
            jaxis = j.get("axis", (0, 0, 1))
            jlow = j.get("limit_low", -3.14159)
            jhigh = j.get("limit_high", 3.14159)
            jstiff = j.get("stiffness", 10.0)
            jdamp = j.get("damping", 1.0)
            jmax_force = j.get("max_force", 0.0)

            schema_map = {
                "fixed": "PhysicsFixedJoint",
                "revolute": "PhysicsRevoluteJoint",
                "prismatic": "PhysicsPrismaticJoint",
                "spherical": "PhysicsSphericalJoint",
                "d6": "PhysicsD6Joint",
            }
            schema = schema_map.get(jtype, "PhysicsFixedJoint")

            lines.append(f'    def {schema} "{jprim}"')
            lines.append('    {')
            lines.append(f'        rel physics:body0 = <{jbody0}>')
            if jbody1:
                lines.append(f'        rel physics:body1 = <{jbody1}>')
            lines.append(f'        point3f physics:localPos0 = ({janchor[0]:.6f}, {janchor[1]:.6f}, {janchor[2]:.6f})')
            lines.append(f'        point3f physics:localPos1 = ({janchor[0]:.6f}, {janchor[1]:.6f}, {janchor[2]:.6f})')
            lines.append(f'        quatf physics:localRot0 = (1, 0, 0, 0)')
            lines.append(f'        quatf physics:localRot1 = (1, 0, 0, 0)')

            if jtype == "revolute":
                lines.append(f'        float physics:lowerLimit = {jlow:.6f}')
                lines.append(f'        float physics:upperLimit = {jhigh:.6f}')
                lines.append(f'        float3 physics:axis = ({jaxis[0]:.6f}, {jaxis[1]:.6f}, {jaxis[2]:.6f})')
            elif jtype == "prismatic":
                lines.append(f'        float physics:lowerLimit = {jlow:.6f}')
                lines.append(f'        float physics:upperLimit = {jhigh:.6f}')
                lines.append(f'        float3 physics:axis = ({jaxis[0]:.6f}, {jaxis[1]:.6f}, {jaxis[2]:.6f})')
            elif jtype == "spherical":
                lines.append(f'        float physics:coneAngleLimit = {min(jhigh, 3.14159):.6f}')
                lines.append(f'        float3 physics:coneAxis = ({jaxis[0]:.6f}, {jaxis[1]:.6f}, {jaxis[2]:.6f})')
            elif jtype == "d6":
                pass

            if jstiff > 0:
                lines.append(f'        float physics:stiffness = {jstiff:.6f}')
            if jdamp > 0:
                lines.append(f'        float physics:damping = {jdamp:.6f}')
            if jmax_force > 0:
                lines.append(f'        float physics:breakForce = {jmax_force:.6f}')
                lines.append(f'        float physics:breakTorque = {jmax_force:.6f}')

            lines.append('    }')
            lines.append('')

    lines.append('}')
    return "\n".join(lines)


def _rotate_vector_by_quat(
    v: tuple[float, float, float],
    q: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    qw, qx, qy, qz = q
    vx, vy, vz = v
    uv_x = qy * vz - qz * vy
    uv_y = qz * vx - qx * vz
    uv_z = qx * vy - qy * vx
    uv2_x = qy * uv_z - qz * uv_y
    uv2_y = qz * uv_x - qx * uv_z
    uv2_z = qx * uv_y - qy * uv_x
    return (
        vx + 2 * (qw * uv_x + uv2_x),
        vy + 2 * (qw * uv_y + uv2_y),
        vz + 2 * (qw * uv_z + uv2_z),
    )


class ScenesMixin:

    def _destroy_tensor_bindings(self):
        for tb in (self._pose_tb, self._vel_tb, self._wrench_tb):
            if tb is not None:
                try:
                    tb.destroy()
                except Exception:
                    pass
        self._pose_tb = None
        self._vel_tb = None
        self._wrench_tb = None
        self._pose_buf = None
        self._vel_buf = None
        self._wrench_buf = None
        self._dynamic_prim_paths.clear()
        self._prim_path_to_idx.clear()
        self._pending_vel.clear()
        self._pending_ang_vel.clear()
        self._pending_wrench.clear()


    def _create_tensor_bindings(self):
        self._destroy_tensor_bindings()
        if self._body_count == 0 or self._ov_physx is None:
            return

        dynamic_paths = sorted(
            prim for body_id, prim in self._body_id_to_prim.items()
            if body_id in self._body_specs
            and self._body_specs[body_id].get("mass", 0) > 0
            and not self._body_specs[body_id].get("is_trigger", False)
        )
        if not dynamic_paths:
            return

        self._dynamic_prim_paths = dynamic_paths
        self._prim_path_to_idx = {p: i for i, p in enumerate(dynamic_paths)}

        try:
            from ovphysx import TensorType
            self._pose_tb = self._ov_physx.create_tensor_binding(
                prim_paths=dynamic_paths,
                tensor_type=TensorType.RIGID_BODY_POSE,
            )
            self._vel_tb = self._ov_physx.create_tensor_binding(
                prim_paths=dynamic_paths,
                tensor_type=TensorType.RIGID_BODY_VELOCITY,
            )
            self._wrench_tb = self._ov_physx.create_tensor_binding(
                prim_paths=dynamic_paths,
                tensor_type=TensorType.RIGID_BODY_WRENCH,
            )
            self._pose_buf = np.zeros(self._pose_tb.shape, dtype=np.float32)
            self._vel_buf = np.zeros(self._vel_tb.shape, dtype=np.float32)
            self._wrench_buf = np.zeros(self._wrench_tb.shape, dtype=np.float32)
        except Exception as e:
            Logger.warning(f"PhysXSolver: could not create tensor bindings ({e})")


    def _destroy_scene(self):
        self._destroy_tensor_bindings()
        if self._usd_handle is not None and self._ov_physx is not None:
            try:
                self._ov_physx.remove_usd(self._usd_handle)
                self._ov_physx.wait_all()
            except Exception:
                pass
            self._usd_handle = None
        try:
            if self._usd_path and os.path.exists(self._usd_path):
                os.unlink(self._usd_path)
        except Exception:
            pass
        self._usd_path = ""


    def _rebuild_scene(self):
        if self._ov_physx is None:
            return
        self._destroy_scene()
        body_list = list(self._body_specs.values())
        joint_list = list(self._joint_specs.values())
        usda = _build_usda(self._gravity, body_list, joint_list)
        new_path = os.path.join(tempfile.gettempdir(), f"zarin_px_{uuid.uuid4().hex}.usda")
        with open(new_path, "w") as f:
            f.write(usda)
        try:
            handle, _ = self._ov_physx.add_usd(new_path)
            self._ov_physx.wait_all()
            self._usd_handle = handle
            self._usd_path = new_path
            self._create_tensor_bindings()
        except Exception as e:
            Logger.error(f"PhysXSolver: scene rebuild failed: {e}")
            try:
                os.unlink(new_path)
            except Exception:
                pass
        self._bodies_dirty = False


    def _ensure_scene(self):
        if self._ov_physx is None:
            return
        if self._usd_handle is None or self._bodies_dirty:
            self._rebuild_scene()
