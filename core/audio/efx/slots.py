# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import ctypes
from . import efx as _core
EAX_PRESETS: dict = {
    "Generic": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.83, "reflections_gain": 0.05, "reflections_delay": 0.007, "late_gain": 1.26, "late_delay": 0.011, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "PaddedCell": {"density": 0.1715, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.1, "decay_time": 0.17, "decay_hf_ratio": 0.1, "reflections_gain": 0.25, "reflections_delay": 0.001, "late_gain": 1.26, "late_delay": 0.002, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "Room": {"density": 0.4287, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.592, "decay_time": 0.4, "decay_hf_ratio": 0.83, "reflections_gain": 0.121, "reflections_delay": 0.002, "late_gain": 1.26, "late_delay": 0.003, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "Bathroom": {"density": 0.1715, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.1, "decay_time": 1.49, "decay_hf_ratio": 0.54, "reflections_gain": 0.653, "reflections_delay": 0.007, "late_gain": 3.27, "late_delay": 0.011, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "LivingRoom": {"density": 0.9767, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.1, "decay_time": 0.5, "decay_hf_ratio": 0.1, "reflections_gain": 0.205, "reflections_delay": 0.003, "late_gain": 0.28, "late_delay": 0.004, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "StoneRoom": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 2.31, "decay_hf_ratio": 0.64, "reflections_gain": 0.441, "reflections_delay": 0.012, "late_gain": 1.1, "late_delay": 0.017, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Auditorium": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 4.32, "decay_hf_ratio": 0.59, "reflections_gain": 0.464, "reflections_delay": 0.02, "late_gain": 1.1, "late_delay": 0.03, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "ConcertHall": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 3.92, "decay_hf_ratio": 0.7, "reflections_gain": 0.242, "reflections_delay": 0.02, "late_gain": 0.994, "late_delay": 0.029, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "Cave": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 2.91, "decay_hf_ratio": 1.3, "reflections_gain": 0.5, "reflections_delay": 0.015, "late_gain": 0.706, "late_delay": 0.022, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Arena": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 7.24, "decay_hf_ratio": 0.33, "reflections_gain": 0.261, "reflections_delay": 0.02, "late_gain": 1.018, "late_delay": 0.03, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "Hangar": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 10.05, "decay_hf_ratio": 0.23, "reflections_gain": 0.5, "reflections_delay": 0.02, "late_gain": 1.256, "late_delay": 0.03, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "CarpetedHallway": {"density": 0.4287, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.1, "decay_time": 0.3, "decay_hf_ratio": 0.1, "reflections_gain": 0.121, "reflections_delay": 0.002, "late_gain": 0.153, "late_delay": 0.03, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Hallway": {"density": 0.3643, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.59, "reflections_gain": 0.245, "reflections_delay": 0.007, "late_gain": 1.661, "late_delay": 0.011, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "StoneCorridor": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 2.7, "decay_hf_ratio": 0.79, "reflections_gain": 0.639, "reflections_delay": 0.012, "late_gain": 1.04, "late_delay": 0.017, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Alley": {"density": 1.0, "diffusion": 0.3, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.86, "reflections_gain": 0.25, "reflections_delay": 0.007, "late_gain": 0.995, "late_delay": 0.011, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Forest": {"density": 1.0, "diffusion": 0.3, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.54, "reflections_gain": 0.052, "reflections_delay": 0.162, "late_gain": 0.768, "late_delay": 0.088, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "City": {"density": 1.0, "diffusion": 0.5, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.67, "reflections_gain": 0.073, "reflections_delay": 0.007, "late_gain": 0.142, "late_delay": 0.011, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Mountains": {"density": 1.0, "diffusion": 0.27, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.21, "reflections_gain": 0.107, "reflections_delay": 0.3, "late_gain": 0.3, "late_delay": 0.1, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Quarry": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.83, "reflections_gain": 0.0, "reflections_delay": 0.061, "late_gain": 1.778, "late_delay": 0.025, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 1},
    "Plain": {"density": 1.0, "diffusion": 0.21, "gain": 0.32, "gain_hf": 0.89, "decay_time": 1.49, "decay_hf_ratio": 0.5, "reflections_gain": 0.058, "reflections_delay": 0.179, "late_gain": 0.108, "late_delay": 0.1, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "ParkingLot": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 1.0, "decay_time": 1.65, "decay_hf_ratio": 1.5, "reflections_gain": 0.208, "reflections_delay": 0.008, "late_gain": 0.265, "late_delay": 0.012, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "SewerPipe": {"density": 0.3071, "diffusion": 0.8, "gain": 0.32, "gain_hf": 0.89, "decay_time": 2.81, "decay_hf_ratio": 0.14, "reflections_gain": 0.625, "reflections_delay": 0.012, "late_gain": 1.0, "late_delay": 0.017, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Underwater": {"density": 1.0, "diffusion": 1.0, "gain": 0.32, "gain_hf": 0.1, "decay_time": 1.49, "decay_hf_ratio": 0.1, "reflections_gain": 0.596, "reflections_delay": 0.007, "late_gain": 7.079, "late_delay": 0.011, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Drugged": {"density": 0.4287, "diffusion": 0.5, "gain": 0.32, "gain_hf": 1.0, "decay_time": 8.39, "decay_hf_ratio": 1.39, "reflections_gain": 0.875, "reflections_delay": 0.002, "late_gain": 3.108, "late_delay": 0.03, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Dizzy": {"density": 0.3643, "diffusion": 0.6, "gain": 0.32, "gain_hf": 0.59, "decay_time": 17.23, "decay_hf_ratio": 0.56, "reflections_gain": 0.139, "reflections_delay": 0.02, "late_gain": 0.493, "late_delay": 0.03, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
    "Psychotic": {"density": 0.0625, "diffusion": 0.5, "gain": 0.32, "gain_hf": 1.0, "decay_time": 7.56, "decay_hf_ratio": 0.91, "reflections_gain": 0.486, "reflections_delay": 0.02, "late_gain": 2.0, "late_delay": 0.03, "air_gain_hf": 0.994, "room_rolloff": 0.0, "decay_hf_limit": 0},
}
REVERB_PRESETS_MB: dict = {
    "Off": {"room": -10000, "room_hf": -10000, "room_lf": 0, "decay_time": 1.0, "decay_hf_ratio": 1.0, "reflections": -10000, "reflections_delay": 0.02, "reverb": -10000, "reverb_delay": 0.04, "diffusion": 0.0, "density": 0.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Generic": {"room": -1000, "room_hf": -100, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.83, "reflections": -2602, "reflections_delay": 0.007, "reverb": 200, "reverb_delay": 0.011, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Padded Cell": {"room": -1400, "room_hf": -6000, "room_lf": 0, "decay_time": 0.17, "decay_hf_ratio": 0.10, "reflections": -1204, "reflections_delay": 0.001, "reverb": 207, "reverb_delay": 0.002, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Room": {"room": -1000, "room_hf": -454, "room_lf": 0, "decay_time": 0.40, "decay_hf_ratio": 0.83, "reflections": -1646, "reflections_delay": 0.002, "reverb": 53, "reverb_delay": 0.003, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Bathroom": {"room": -1000, "room_hf": -1200, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.54, "reflections": -370, "reflections_delay": 0.007, "reverb": 1030, "reverb_delay": 0.011, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Living Room": {"room": -1000, "room_hf": -6000, "room_lf": 0, "decay_time": 0.50, "decay_hf_ratio": 0.10, "reflections": -1376, "reflections_delay": 0.003, "reverb": -1104, "reverb_delay": 0.004, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Stone Room": {"room": -1000, "room_hf": -300, "room_lf": 0, "decay_time": 2.31, "decay_hf_ratio": 0.64, "reflections": -711, "reflections_delay": 0.012, "reverb": 83, "reverb_delay": 0.017, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Auditorium": {"room": -1000, "room_hf": -476, "room_lf": 0, "decay_time": 4.32, "decay_hf_ratio": 0.59, "reflections": -789, "reflections_delay": 0.020, "reverb": -289, "reverb_delay": 0.030, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Concert Hall": {"room": -1000, "room_hf": -500, "room_lf": 0, "decay_time": 3.92, "decay_hf_ratio": 0.70, "reflections": -1230, "reflections_delay": 0.020, "reverb": -2, "reverb_delay": 0.029, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Cave": {"room": -1000, "room_hf": 0, "room_lf": 0, "decay_time": 2.91, "decay_hf_ratio": 1.30, "reflections": -602, "reflections_delay": 0.015, "reverb": -302, "reverb_delay": 0.022, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Arena": {"room": -1000, "room_hf": -698, "room_lf": 0, "decay_time": 7.24, "decay_hf_ratio": 0.33, "reflections": -1166, "reflections_delay": 0.020, "reverb": 16, "reverb_delay": 0.030, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Hangar": {"room": -1000, "room_hf": -1000, "room_lf": 0, "decay_time": 10.05, "decay_hf_ratio": 0.23, "reflections": -602, "reflections_delay": 0.020, "reverb": 198, "reverb_delay": 0.030, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Carpeted Hallway": {"room": -1000, "room_hf": -4000, "room_lf": 0, "decay_time": 0.30, "decay_hf_ratio": 0.10, "reflections": -1831, "reflections_delay": 0.002, "reverb": -1630, "reverb_delay": 0.030, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Hallway": {"room": -1000, "room_hf": -300, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.59, "reflections": -1219, "reflections_delay": 0.007, "reverb": 441, "reverb_delay": 0.011, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Stone Corridor": {"room": -1000, "room_hf": -237, "room_lf": 0, "decay_time": 2.70, "decay_hf_ratio": 0.79, "reflections": -383, "reflections_delay": 0.012, "reverb": 33, "reverb_delay": 0.017, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Alley": {"room": -1000, "room_hf": -270, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.86, "reflections": -1204, "reflections_delay": 0.007, "reverb": -4, "reverb_delay": 0.011, "diffusion": 70.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Forest": {"room": -1000, "room_hf": -3300, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.54, "reflections": -2560, "reflections_delay": 0.162, "reverb": -229, "reverb_delay": 0.088, "diffusion": 70.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "City": {"room": -1000, "room_hf": -800, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.67, "reflections": -2273, "reflections_delay": 0.007, "reverb": -1691, "reverb_delay": 0.011, "diffusion": 50.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Mountains": {"room": -1000, "room_hf": -2500, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.21, "reflections": -2780, "reflections_delay": 0.300, "reverb": -1434, "reverb_delay": 0.100, "diffusion": 27.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Quarry": {"room": -1000, "room_hf": -1000, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.83, "reflections": -10000, "reflections_delay": 0.061, "reverb": 500, "reverb_delay": 0.025, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Plain": {"room": -1000, "room_hf": -2000, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.50, "reflections": -2466, "reflections_delay": 0.179, "reverb": -1926, "reverb_delay": 0.100, "diffusion": 21.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Parking Lot": {"room": -1000, "room_hf": 0, "room_lf": 0, "decay_time": 1.65, "decay_hf_ratio": 1.50, "reflections": -1363, "reflections_delay": 0.008, "reverb": -1153, "reverb_delay": 0.012, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Sewer Pipe": {"room": -1000, "room_hf": -1000, "room_lf": 0, "decay_time": 2.81, "decay_hf_ratio": 0.14, "reflections": -429, "reflections_delay": 0.014, "reverb": 648, "reverb_delay": 0.021, "diffusion": 80.0, "density": 60.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Underwater": {"room": -1000, "room_hf": -4000, "room_lf": 0, "decay_time": 1.49, "decay_hf_ratio": 0.10, "reflections": -449, "reflections_delay": 0.007, "reverb": 1700, "reverb_delay": 0.011, "diffusion": 100.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Drugged": {"room": -1000, "room_hf": 0, "room_lf": 0, "decay_time": 8.39, "decay_hf_ratio": 1.39, "reflections": -115, "reflections_delay": 0.002, "reverb": 985, "reverb_delay": 0.030, "diffusion": 50.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Dizzy": {"room": -1000, "room_hf": -613, "room_lf": 0, "decay_time": 17.23, "decay_hf_ratio": 0.56, "reflections": -1818, "reflections_delay": 0.020, "reverb": -613, "reverb_delay": 0.030, "diffusion": 60.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
    "Psychotic": {"room": -1000, "room_hf": 0, "room_lf": 0, "decay_time": 7.56, "decay_hf_ratio": 0.91, "reflections": -626, "reflections_delay": 0.020, "reverb": 774, "reverb_delay": 0.030, "diffusion": 50.0, "density": 100.0, "hf_reference": 5000.0, "lf_reference": 250.0, "room_rolloff": 0.0},
}
REVERB_PRESET_ORDER: list = [
    "Off", "Generic", "Padded Cell", "Room", "Bathroom", "Living Room",
    "Stone Room", "Auditorium", "Concert Hall", "Cave", "Arena", "Hangar",
    "Carpeted Hallway", "Hallway", "Stone Corridor", "Alley", "Forest",
    "City", "Mountains", "Quarry", "Plain", "Parking Lot", "Sewer Pipe",
    "Underwater", "Drugged", "Dizzy", "Psychotic", "User",
]


def create_aux_slot() -> int:
    if not _core.efx_available():
        raise _core.EFXError("EFX not available")
    slot_id = ctypes.c_uint()
    _core._alGenAuxiliaryEffectSlots(1, ctypes.pointer(slot_id))
    if slot_id.value == 0:
        raise _core.EFXError("Failed to create auxiliary effect slot")
    return slot_id.value


def delete_aux_slot(slot_id: int):
    if slot_id == 0:
        return
    if not _core._efx_available or _core._alDeleteAuxiliaryEffectSlots is None:
        return
    try:
        val = ctypes.c_uint(int(slot_id))
        _core._alDeleteAuxiliaryEffectSlots(1, ctypes.pointer(val))
    except Exception:
        pass


def is_aux_slot(slot_id: int) -> bool:
    if slot_id == 0 or not _core._efx_available or _core._alIsAuxiliaryEffectSlot is None:
        return False
    try:
        return bool(_core._alIsAuxiliaryEffectSlot(int(slot_id)))
    except Exception:
        return False


def set_aux_slot_effect(slot_id: int, effect_id: int):
    if not _core._efx_available or _core._alAuxiliaryEffectSloti is None:
        return
    try:
        _core._alAuxiliaryEffectSloti(int(slot_id), int(_core.AL_EFFECTSLOT_EFFECT), int(effect_id))
    except Exception:
        pass


def set_aux_slot_gain(slot_id: int, gain: float):
    if not _core._efx_available or _core._alAuxiliaryEffectSlotf is None:
        return
    try:
        v = max(0.0, min(1.0, float(gain)))
        _core._alAuxiliaryEffectSlotf(int(slot_id), int(_core.AL_EFFECTSLOT_GAIN), v)
    except Exception:
        pass


def apply_reverb_params(effect_id: int, density: float, diffusion: float, gain: float, gain_hf: float, decay_time: float, decay_hf_ratio: float, reflections_gain: float, reflections_delay: float, late_gain: float, late_delay: float, air_gain_hf: float, room_rolloff: float, decay_hf_limit: int) -> bool:
    if not _core._efx_available or int(effect_id) == 0:
        return False
    try:
        _core.set_effect_type(int(effect_id), int(_core._reverb_type_enum()))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_DENSITY, max(0.0, min(1.0, float(density))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_DIFFUSION, max(0.0, min(1.0, float(diffusion))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_GAIN, max(0.0, min(1.0, float(gain))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_GAINHF, max(0.0, min(1.0, float(gain_hf))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_DECAY_TIME, max(0.1, min(20.0, float(decay_time))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_DECAY_HFRATIO, max(0.1, min(2.0, float(decay_hf_ratio))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_REFLECTIONS_GAIN, max(0.0, min(3.16, float(reflections_gain))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_REFLECTIONS_DELAY, max(0.0, min(0.3, float(reflections_delay))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_LATE_REVERB_GAIN, max(0.0, min(10.0, float(late_gain))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_LATE_REVERB_DELAY, max(0.0, min(0.1, float(late_delay))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_AIR_ABSORPTION_GAINHF, max(0.892, min(1.0, float(air_gain_hf))))
        _core.set_effect_param_f(int(effect_id), _core.AL_REVERB_ROOM_ROLLOFF_FACTOR, max(0.0, min(10.0, float(room_rolloff))))
        _core.set_effect_param_i(int(effect_id), _core.AL_REVERB_DECAY_HFLIMIT, 1 if int(decay_hf_limit) else 0)
        return True
    except Exception:
        return False


def get_eax_preset(name: str):
    if not name:
        return None
    return EAX_PRESETS.get(str(name))


def eax_preset_names() -> list:
    return sorted(EAX_PRESETS.keys())


def apply_eax_preset(effect_id: int, preset_name: str) -> bool:
    preset = EAX_PRESETS.get(str(preset_name))
    if preset is None:
        preset = get_reverb_preset_as_eax(str(preset_name))
    if preset is None or int(effect_id) == 0:
        return False
    return bool(apply_reverb_params(int(effect_id), preset["density"], preset["diffusion"], preset["gain"], preset["gain_hf"], preset["decay_time"], preset["decay_hf_ratio"], preset["reflections_gain"], preset["reflections_delay"], preset["late_gain"], preset["late_delay"], preset["air_gain_hf"], preset["room_rolloff"], preset["decay_hf_limit"]))


def mb_to_gain(mb: float) -> float:
    try:
        v = float(mb)
    except Exception:
        return 0.0
    if v <= -10000.0:
        return 0.0
    if v >= 2000.0:
        return 10.0
    return float(10.0 ** (v / 2000.0))


def gain_to_mb(gain: float) -> float:
    try:
        g = float(gain)
    except Exception:
        return -10000.0
    if g <= 0.00001:
        return -10000.0
    if g >= 10.0:
        return 2000.0
    import math as _math
    return float(2000.0 * _math.log10(g))


def normalize_preset_name(name: str) -> str:
    try:
        raw = str(name or "").strip()
    except Exception:
        return "User"
    if not raw:
        return "User"
    low = raw.lower().replace("_", " ").replace("-", " ")
    compact = "".join(low.split())
    mapping = {
        "off": "Off",
        "generic": "Generic",
        "paddedcell": "Padded Cell",
        "padded": "Padded Cell",
        "room": "Room",
        "bathroom": "Bathroom",
        "livingroom": "Living Room",
        "stoneroom": "Stone Room",
        "auditorium": "Auditorium",
        "concerthall": "Concert Hall",
        "cave": "Cave",
        "arena": "Arena",
        "hangar": "Hangar",
        "carpetedhallway": "Carpeted Hallway",
        "hallway": "Hallway",
        "stonecorridor": "Stone Corridor",
        "alley": "Alley",
        "forest": "Forest",
        "city": "City",
        "mountains": "Mountains",
        "quarry": "Quarry",
        "plain": "Plain",
        "parkinglot": "Parking Lot",
        "sewerpipe": "Sewer Pipe",
        "underwater": "Underwater",
        "drugged": "Drugged",
        "dizzy": "Dizzy",
        "psychotic": "Psychotic",
        "user": "User",
        "custom": "User",
    }
    if compact in mapping:
        return mapping[compact]
    for ordered in REVERB_PRESET_ORDER:
        if ordered.lower().replace(" ", "") == compact:
            return ordered
    return "User"


def get_reverb_preset(name: str):
    if not name:
        return None
    normalized = normalize_preset_name(name)
    preset = REVERB_PRESETS_MB.get(normalized)
    if preset is not None:
        return dict(preset)
    return None


def reverb_preset_names() -> list:
    return list(REVERB_PRESET_ORDER)


def get_reverb_preset_as_eax(name: str):
    preset = get_reverb_preset(name)
    if preset is None:
        return None
    try:
        return {
            "density": max(0.0, min(1.0, float(preset["density"]) / 100.0)),
            "diffusion": max(0.0, min(1.0, float(preset["diffusion"]) / 100.0)),
            "gain": float(mb_to_gain(preset["room"])),
            "gain_hf": float(mb_to_gain(preset["room_hf"])),
            "decay_time": float(preset["decay_time"]),
            "decay_hf_ratio": float(preset["decay_hf_ratio"]),
            "reflections_gain": float(mb_to_gain(preset["reflections"])),
            "reflections_delay": float(preset["reflections_delay"]),
            "late_gain": float(mb_to_gain(preset["reverb"])),
            "late_delay": float(preset["reverb_delay"]),
            "air_gain_hf": 0.994,
            "room_rolloff": float(preset.get("room_rolloff", 0.0)),
            "decay_hf_limit": 1,
        }
    except Exception:
        return None


def apply_reverb_mb(effect_id: int, room: float, room_hf: float, room_lf: float, decay_time: float, decay_hf_ratio: float, reflections: float, reflections_delay: float, reverb: float, reverb_delay: float, diffusion: float, density: float, hf_reference: float, lf_reference: float, room_rolloff: float) -> bool:
    if not _core._efx_available or int(effect_id) == 0:
        return False
    try:
        eax_type = 32768
        try:
            cached = _core._enum_cache.get(b"AL_EFFECT_EAXREVERB")
            if cached is not None:
                eax_type = int(cached)
            else:
                import openal.al as _almod
                eax_type = int(_core._resolve_enum(_almod, b"AL_EFFECT_EAXREVERB", 32768))
        except Exception:
            eax_type = 32768
        _core.set_effect_type(int(effect_id), int(eax_type))
        gain = float(mb_to_gain(room))
        gain_hf = float(mb_to_gain(room_hf))
        gain_lf = float(mb_to_gain(room_lf))
        refl_gain = float(mb_to_gain(reflections))
        late_gain = float(mb_to_gain(reverb))
        dens = max(0.0, min(1.0, float(density) / 100.0))
        diff = max(0.0, min(1.0, float(diffusion) / 100.0))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_DENSITY), float(dens))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_DIFFUSION), float(diff))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_GAIN), max(0.0, min(1.0, float(gain))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_GAINHF), max(0.0, min(1.0, float(gain_hf))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_GAINLF), max(0.0, min(1.0, float(gain_lf))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_DECAY_TIME), max(0.1, min(20.0, float(decay_time))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_DECAY_HFRATIO), max(0.1, min(2.0, float(decay_hf_ratio))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_DECAY_LFRATIO), 1.0)
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_REFLECTIONS_GAIN), max(0.0, min(3.16, float(refl_gain))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_REFLECTIONS_DELAY), max(0.0, min(0.3, float(reflections_delay))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_LATE_REVERB_GAIN), max(0.0, min(10.0, float(late_gain))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_LATE_REVERB_DELAY), max(0.0, min(0.1, float(reverb_delay))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_ECHO_TIME), 0.25)
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_ECHO_DEPTH), 0.0)
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_MODULATION_TIME), 0.25)
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_MODULATION_DEPTH), 0.0)
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_AIR_ABSORPTION_GAINHF), 0.994)
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_HFREFERENCE), max(1000.0, min(20000.0, float(hf_reference))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_LFREFERENCE), max(20.0, min(1000.0, float(lf_reference))))
        _core.set_effect_param_f(int(effect_id), int(_core.AL_EAXREVERB_ROOM_ROLLOFF_FACTOR), max(0.0, min(10.0, float(room_rolloff))))
        _core.set_effect_param_i(int(effect_id), int(_core.AL_EAXREVERB_DECAY_HFLIMIT), 1)
        return True
    except Exception:
        pass
    try:
        return bool(apply_reverb_params(int(effect_id), max(0.0, min(1.0, float(density) / 100.0)), max(0.0, min(1.0, float(diffusion) / 100.0)), float(mb_to_gain(room)), float(mb_to_gain(room_hf)), float(decay_time), float(decay_hf_ratio), float(mb_to_gain(reflections)), float(reflections_delay), float(mb_to_gain(reverb)), float(reverb_delay), 0.994, float(room_rolloff), 1))
    except Exception:
        return False


def get_max_aux_sends() -> int:
    if not _core._efx_available:
        return 1
    try:
        return max(1, int(_core._max_aux_sends) if int(_core._max_aux_sends) > 0 else 1)
    except Exception:
        return 1


def get_aux_send_enum() -> int:
    cached = _core._enum_cache.get(b"AL_AUXILIARY_SEND_FILTER")
    if cached is not None:
        try:
            return int(cached)
        except Exception:
            pass
    if _core._efx_available:
        try:
            import openal.al as almod
            return int(_core._resolve_enum(almod, b"AL_AUXILIARY_SEND_FILTER", _core.AL_AUXILIARY_SEND_FILTER))
        except Exception:
            pass
    return int(_core.AL_AUXILIARY_SEND_FILTER)


def get_direct_filter_enum() -> int:
    cached = _core._enum_cache.get(b"AL_DIRECT_FILTER")
    if cached is not None:
        try:
            return int(cached)
        except Exception:
            pass
    if _core._efx_available:
        try:
            import openal.al as almod
            return int(_core._resolve_enum(almod, b"AL_DIRECT_FILTER", _core.AL_DIRECT_FILTER))
        except Exception:
            pass
    return int(_core.AL_DIRECT_FILTER)


def set_source_aux_send(source_id: int, slot_id: int, filter_id: int = 0, send_index: int = 0) -> bool:
    if int(source_id) == 0:
        return False
    if not _core._efx_available:
        return False
    try:
        import openal.al as almod
        send_enum = int(get_aux_send_enum())
        sends = int(get_max_aux_sends())
        idx = max(0, min(int(send_index), max(0, sends - 1)))
        try:
            almod.alSource3i(int(source_id), int(send_enum), int(slot_id), int(idx), int(filter_id))
        except Exception:
            return False
        try:
            err = int(almod.alGetError())
            return err == 0
        except Exception:
            return True
    except Exception:
        return False


def set_source_direct_filter(source_id: int, filter_id: int = 0) -> bool:
    if int(source_id) == 0:
        return False
    if not _core._efx_available:
        return False
    try:
        import openal.al as almod
        direct_enum = int(get_direct_filter_enum())
        try:
            almod.alSourcei(int(source_id), int(direct_enum), int(filter_id))
        except Exception:
            return False
        try:
            err = int(almod.alGetError())
            return err == 0
        except Exception:
            return True
    except Exception:
        return False
