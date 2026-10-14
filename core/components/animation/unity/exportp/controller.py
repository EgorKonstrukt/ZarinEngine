# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations

from core.components.animation.unity.exportp.clip import _INDENT
from core.components.animation.unity.exportp.clip import _f

_PARAM_TYPE_NUM = {
    "float": 1,
    "int": 2,
    "bool": 4,
    "trigger": 9,
}

_CONDITION_MODE_NUM = {
    "if": 1,
    "if_not": 2,
    "greater": 3,
    "less": 4,
    "not_equal": 5,
    "equals": 6,
}


def _guid_for_path(path: str) -> str:
    import hashlib

    return hashlib.md5(path.encode("utf-8")).hexdigest()


def controller_to_unity_yaml(ctrl) -> str:
    sid = 1102000000
    tid = 1101000000
    doc_store: list = []

    def push(doc_text: str):
        doc_store.append(doc_text)

    param_lines = ""
    for p in ctrl.parameters:
        ptype = p.param_type.value if hasattr(p.param_type, "value") else str(p.param_type)
        pnum = _PARAM_TYPE_NUM.get(str(ptype).lower(), 1)
        param_lines += (
            f"{_INDENT * 2}- m_Name: {p.name}\n"
            f"{_INDENT * 4}m_Type: {pnum}\n"
            f"{_INDENT * 4}m_DefaultFloat: {_f(p.default_float)}\n"
            f"{_INDENT * 4}m_DefaultInt: {p.default_int}\n"
            f"{_INDENT * 4}m_DefaultBool: {1 if p.default_bool else 0}\n"
            f"{_INDENT * 4}m_Controller: {{fileID: 9100000}}\n"
        )
    for li, layer in enumerate(ctrl.layers):
        sm_id = 110700000 + li
        base = (
            "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
            f"--- !u!91 &9100000\nAnimatorController:\n"
            f"{_INDENT}m_ObjectHideFlags: 0\n"
            f"{_INDENT}m_CorrespondingSourceObject: {{fileID: 0}}\n"
            f"{_INDENT}m_PrefabInstance: {{fileID: 0}}\n"
            f"{_INDENT}m_PrefabAsset: {{fileID: 0}}\n"
            f"{_INDENT}m_Name: {ctrl.name}\n"
            f"{_INDENT}serializedVersion: 5\n"
            f"{_INDENT}m_AnimatorParameters:\n{param_lines}"
            f"{_INDENT}m_AnimatorLayers:\n"
        )
        layer_lines = (
            f"{_INDENT * 2}- serializedVersion: 6\n"
            f"{_INDENT * 4}m_Name: {layer.name}\n"
            f"{_INDENT * 4}m_StateMachine: {{fileID: {sm_id}}}\n"
            f"{_INDENT * 4}m_Mask: {{fileID: 0}}\n"
            f"{_INDENT * 4}m_Motions: []\n"
            f"{_INDENT * 4}m_Behaviours: []\n"
            f"{_INDENT * 4}m_BlendingMode: {'1' if str(layer.blending_mode).lower() == 'additive' else '0'}\n"
            f"{_INDENT * 4}m_SyncedLayerIndex: -1\n"
            f"{_INDENT * 4}m_DefaultWeight: {_f(layer.weight)}\n"
            f"{_INDENT * 4}m_IKPass: 0\n"
            f"{_INDENT * 4}m_SyncedLayerAffectsTiming: 0\n"
            f"{_INDENT * 4}m_Controller: {{fileID: 9100000}}\n"
        )
        push(base + layer_lines)
        sm_lines = (
            f"--- !u!1107 &{sm_id}\nAnimatorStateMachine:\n"
            f"{_INDENT}serializedVersion: 6\n"
            f"{_INDENT}m_ObjectHideFlags: 1\n"
            f"{_INDENT}m_CorrespondingSourceObject: {{fileID: 0}}\n"
            f"{_INDENT}m_PrefabInstance: {{fileID: 0}}\n"
            f"{_INDENT}m_PrefabAsset: {{fileID: 0}}\n"
            f"{_INDENT}m_Name: {layer.name}\n"
            f"{_INDENT}m_ChildStates:\n"
        )
        for si in range(len(layer.states)):
            state = layer.states[si]
            sm_lines += (
                f"{_INDENT * 2}- serializedVersion: 1\n"
                f"{_INDENT * 4}m_State: {{fileID: {sid + si}}}\n"
                f"{_INDENT * 4}m_Position: {{x: {_f(state.x)}, y: {_f(state.y)}, z: 0}}\n"
            )
        default_id = 0
        for si, state in enumerate(layer.states):
            if state.name == layer.default_state:
                default_id = sid + si
        sm_lines += (
            f"{_INDENT}m_ChildStateMachines: []\n"
            f"{_INDENT}m_AnyStateTransitions: []\n"
            f"{_INDENT}m_EntryTransitions: []\n"
            f"{_INDENT}m_StateMachineTransitions: {{}}\n"
            f"{_INDENT}m_StateMachineBehaviours: []\n"
            f"{_INDENT}m_AnyStatePosition: {{x: 50, y: 50, z: 0}}\n"
            f"{_INDENT}m_EntryPosition: {{x: 50, y: 50, z: 0}}\n"
            f"{_INDENT}m_ExitPosition: {{x: 800, y: 120, z: 0}}\n"
            f"{_INDENT}m_ParentStateMachinePosition: {{x: 800, y: 20, z: 0}}\n"
            f"{_INDENT}m_DefaultState: {{fileID: {default_id}}}\n"
        )
        push(sm_lines)
        t_counter = 0
        for si, state in enumerate(layer.states):
            base_t = t_counter
            trans_ids = []
            for ti, tr in enumerate(state.transitions):
                trans_ids.append(tid + base_t + ti)
            t_counter += len(state.transitions)
            trans_line = ""
            for t_id in trans_ids:
                trans_line += f"{_INDENT * 2}- {{fileID: {t_id}}}\n"
            motion_guid = "00000000000000000000000000000000"
            if state.clip_path:
                motion_guid = _guid_for_path(state.clip_path)
            elif state.clip is not None:
                path = getattr(state.clip, "_path", "") or state.clip.name
                motion_guid = _guid_for_path(path)
            state_lines = (
                f"--- !u!1102 &{sid + si}\nAnimatorState:\n"
                f"{_INDENT}serializedVersion: 6\n"
                f"{_INDENT}m_ObjectHideFlags: 1\n"
                f"{_INDENT}m_CorrespondingSourceObject: {{fileID: 0}}\n"
                f"{_INDENT}m_PrefabInstance: {{fileID: 0}}\n"
                f"{_INDENT}m_PrefabAsset: {{fileID: 0}}\n"
                f"{_INDENT}m_Name: {state.name}\n"
                f"{_INDENT}m_Speed: {_f(state.speed)}\n"
                f"{_INDENT}m_CycleOffset: 0\n"
                f"{_INDENT}m_Transitions:\n{trans_line}"
                f"{_INDENT}m_StateMachineBehaviours: []\n"
                f"{_INDENT}m_Position: {{x: {_f(state.x)}, y: {_f(state.y)}, z: 0}}\n"
                f"{_INDENT}m_IKOnFeet: 0\n"
                f"{_INDENT}m_WriteDefaultValues: 1\n"
                f"{_INDENT}m_Mirror: 0\n"
                f"{_INDENT}m_SpeedParameterActive: 0\n"
                f"{_INDENT}m_MirrorParameterActive: 0\n"
                f"{_INDENT}m_CycleOffsetParameterActive: 0\n"
                f"{_INDENT}m_TimeParameterActive: 0\n"
                f"{_INDENT}m_Motion: {{fileID: 7400000, guid: {motion_guid}, type: 2}}\n"
            )
            push(state_lines)
            for ti, tr in enumerate(state.transitions):
                t_id = tid + base_t + ti
                cond_lines = ""
                for c in tr.conditions:
                    mode_num = _CONDITION_MODE_NUM.get(
                        c.mode.value if hasattr(c.mode, "value") else str(c.mode), 1
                    )
                    cond_lines += (
                        f"{_INDENT * 2}- m_ConditionMode: {mode_num}\n"
                        f"{_INDENT * 4}m_ConditionEvent: {c.parameter}\n"
                        f"{_INDENT * 4}m_EventTreshold: {_f(c.threshold)}\n"
                    )
                dst_id = 0
                for di, dst in enumerate(layer.states):
                    if dst.name == tr.destination_state:
                        dst_id = sid + di
                if not cond_lines:
                    cond_lines = f"{_INDENT * 2}[]\n"
                trans_lines = (
                    f"--- !u!1101 &{t_id}\nAnimatorStateTransition:\n"
                    f"{_INDENT}m_ObjectHideFlags: 1\n"
                    f"{_INDENT}m_CorrespondingSourceObject: {{fileID: 0}}\n"
                    f"{_INDENT}m_PrefabInstance: {{fileID: 0}}\n"
                    f"{_INDENT}m_PrefabAsset: {{fileID: 0}}\n"
                    f"{_INDENT}m_Name: \n"
                    f"{_INDENT}m_Conditions:\n{cond_lines}"
                    f"{_INDENT}m_DstState: {{fileID: {dst_id}}}\n"
                    f"{_INDENT}m_Solo: {1 if tr.solo else 0}\n"
                    f"{_INDENT}m_Mute: {1 if tr.mute else 0}\n"
                    f"{_INDENT}m_IsExit: 0\n"
                    f"{_INDENT}serializedVersion: 3\n"
                    f"{_INDENT}m_TransitionDuration: {_f(tr.transition_duration)}\n"
                    f"{_INDENT}m_TransitionOffset: {_f(tr.offset)}\n"
                    f"{_INDENT}m_ExitTime: {_f(tr.exit_time)}\n"
                    f"{_INDENT}m_HasExitTime: {1 if tr.has_exit_time else 0}\n"
                    f"{_INDENT}m_HasFixedDuration: {1 if tr.has_fixed_duration else 0}\n"
                    f"{_INDENT}m_InterruptionSource: 0\n"
                    f"{_INDENT}m_OrderedInterruption: 1\n"
                )
                push(trans_lines)
    header = doc_store[0]
    body = doc_store[1:]
    return header + "\n".join(body)
