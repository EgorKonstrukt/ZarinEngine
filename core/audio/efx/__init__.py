# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
from .efx import EFXError, efx_available, ensure_efx, invalidate_efx_cache
from .efx import create_effect, delete_effect, is_effect, set_effect_type, set_effect_param_i, set_effect_param_f
from .efx import reverb_enabled, occlusion_enabled, spatialization_enabled
from .efx import AL_EFFECT_NULL, AL_EFFECT_REVERB, AL_EFFECT_CHORUS, AL_EFFECT_DISTORTION, AL_EFFECT_ECHO, AL_EFFECT_FLANGER, AL_EFFECT_FREQUENCY_SHIFTER, AL_EFFECT_VOCAL_MORPHER, AL_EFFECT_PITCH_SHIFTER, AL_EFFECT_RING_MODULATOR, AL_EFFECT_AUTOWAH, AL_EFFECT_COMPRESSOR, AL_EFFECT_EQUALIZER, AL_EFFECT_EAXREVERB, AL_EFFECT_TYPE
from .efx import AL_EFFECTSLOT_EFFECT, AL_EFFECTSLOT_GAIN, AL_EFFECTSLOT_AUXILIARY_SEND_AUTO
from .efx import AL_REVERB_DENSITY, AL_REVERB_DIFFUSION, AL_REVERB_GAIN, AL_REVERB_GAINHF, AL_REVERB_DECAY_TIME, AL_REVERB_DECAY_HFRATIO, AL_REVERB_REFLECTIONS_GAIN, AL_REVERB_REFLECTIONS_DELAY, AL_REVERB_LATE_REVERB_GAIN, AL_REVERB_LATE_REVERB_DELAY, AL_REVERB_AIR_ABSORPTION_GAINHF, AL_REVERB_ROOM_ROLLOFF_FACTOR, AL_REVERB_DECAY_HFLIMIT
from .efx import AL_EAXREVERB_DENSITY, AL_EAXREVERB_DIFFUSION, AL_EAXREVERB_GAIN, AL_EAXREVERB_GAINHF, AL_EAXREVERB_GAINLF, AL_EAXREVERB_DECAY_TIME, AL_EAXREVERB_DECAY_HFRATIO, AL_EAXREVERB_DECAY_LFRATIO, AL_EAXREVERB_REFLECTIONS_GAIN, AL_EAXREVERB_REFLECTIONS_DELAY, AL_EAXREVERB_REFLECTIONS_PAN, AL_EAXREVERB_LATE_REVERB_GAIN, AL_EAXREVERB_LATE_REVERB_DELAY, AL_EAXREVERB_LATE_REVERB_PAN, AL_EAXREVERB_ECHO_TIME, AL_EAXREVERB_ECHO_DEPTH, AL_EAXREVERB_MODULATION_TIME, AL_EAXREVERB_MODULATION_DEPTH, AL_EAXREVERB_AIR_ABSORPTION_GAINHF, AL_EAXREVERB_HFREFERENCE, AL_EAXREVERB_LFREFERENCE, AL_EAXREVERB_ROOM_ROLLOFF_FACTOR, AL_EAXREVERB_DECAY_HFLIMIT
from .efx import AL_FILTER_NULL, AL_FILTER_LOWPASS, AL_FILTER_HIGHPASS, AL_FILTER_BANDPASS, AL_FILTER_TYPE, AL_LOWPASS_GAIN, AL_LOWPASS_GAINHF, AL_HIGHPASS_GAIN, AL_HIGHPASS_GAINLF, AL_BANDPASS_GAIN, AL_BANDPASS_GAINLF, AL_BANDPASS_GAINHF, AL_DIRECT_FILTER, AL_AUXILIARY_SEND_FILTER, AL_DIRECT_FILTER_GAINHF_AUTO, AL_AUXILIARY_SEND_FILTER_GAIN_AUTO, AL_MAX_AUXILIARY_SENDS
from .filters import create_filter, delete_filter, is_filter, set_filter_type, set_filter_param_i, set_filter_param_f
from .slots import create_aux_slot, delete_aux_slot, is_aux_slot, set_aux_slot_effect, set_aux_slot_gain
from .slots import apply_reverb_params, apply_eax_preset, get_eax_preset, eax_preset_names, apply_reverb_mb, get_reverb_preset, reverb_preset_names, normalize_preset_name, mb_to_gain, gain_to_mb, get_reverb_preset_as_eax
from .slots import EAX_PRESETS, REVERB_PRESETS_MB, REVERB_PRESET_ORDER
from .slots import get_max_aux_sends, get_aux_send_enum, get_direct_filter_enum, set_source_aux_send, set_source_direct_filter
__all__ = [
    "EFXError", "efx_available", "ensure_efx", "invalidate_efx_cache",
    "create_effect", "delete_effect", "is_effect", "set_effect_type",
    "set_effect_param_i", "set_effect_param_f",
    "create_filter", "delete_filter", "is_filter", "set_filter_type",
    "set_filter_param_i", "set_filter_param_f",
    "create_aux_slot", "delete_aux_slot", "is_aux_slot",
    "set_aux_slot_effect", "set_aux_slot_gain",
    "apply_reverb_params", "apply_eax_preset", "get_eax_preset", "eax_preset_names",
    "apply_reverb_mb", "get_reverb_preset", "reverb_preset_names", "normalize_preset_name",
    "mb_to_gain", "gain_to_mb", "get_reverb_preset_as_eax",
    "REVERB_PRESETS_MB", "EAX_PRESETS", "REVERB_PRESET_ORDER",
    "get_max_aux_sends", "get_aux_send_enum", "get_direct_filter_enum",
    "set_source_aux_send", "set_source_direct_filter",
    "reverb_enabled", "occlusion_enabled", "spatialization_enabled",
    "AL_EFFECT_NULL", "AL_EFFECT_REVERB", "AL_EFFECT_CHORUS", "AL_EFFECT_DISTORTION", "AL_EFFECT_ECHO", "AL_EFFECT_FLANGER", "AL_EFFECT_FREQUENCY_SHIFTER", "AL_EFFECT_VOCAL_MORPHER", "AL_EFFECT_PITCH_SHIFTER", "AL_EFFECT_RING_MODULATOR", "AL_EFFECT_AUTOWAH", "AL_EFFECT_COMPRESSOR", "AL_EFFECT_EQUALIZER", "AL_EFFECT_EAXREVERB", "AL_EFFECT_TYPE",
    "AL_EFFECTSLOT_EFFECT", "AL_EFFECTSLOT_GAIN", "AL_EFFECTSLOT_AUXILIARY_SEND_AUTO",
    "AL_REVERB_DENSITY", "AL_REVERB_DIFFUSION", "AL_REVERB_GAIN", "AL_REVERB_GAINHF", "AL_REVERB_DECAY_TIME", "AL_REVERB_DECAY_HFRATIO", "AL_REVERB_REFLECTIONS_GAIN", "AL_REVERB_REFLECTIONS_DELAY", "AL_REVERB_LATE_REVERB_GAIN", "AL_REVERB_LATE_REVERB_DELAY", "AL_REVERB_AIR_ABSORPTION_GAINHF", "AL_REVERB_ROOM_ROLLOFF_FACTOR", "AL_REVERB_DECAY_HFLIMIT",
    "AL_EAXREVERB_DENSITY", "AL_EAXREVERB_DIFFUSION", "AL_EAXREVERB_GAIN", "AL_EAXREVERB_GAINHF", "AL_EAXREVERB_GAINLF", "AL_EAXREVERB_DECAY_TIME", "AL_EAXREVERB_DECAY_HFRATIO", "AL_EAXREVERB_DECAY_LFRATIO", "AL_EAXREVERB_REFLECTIONS_GAIN", "AL_EAXREVERB_REFLECTIONS_DELAY", "AL_EAXREVERB_REFLECTIONS_PAN", "AL_EAXREVERB_LATE_REVERB_GAIN", "AL_EAXREVERB_LATE_REVERB_DELAY", "AL_EAXREVERB_LATE_REVERB_PAN", "AL_EAXREVERB_ECHO_TIME", "AL_EAXREVERB_ECHO_DEPTH", "AL_EAXREVERB_MODULATION_TIME", "AL_EAXREVERB_MODULATION_DEPTH", "AL_EAXREVERB_AIR_ABSORPTION_GAINHF", "AL_EAXREVERB_HFREFERENCE", "AL_EAXREVERB_LFREFERENCE", "AL_EAXREVERB_ROOM_ROLLOFF_FACTOR", "AL_EAXREVERB_DECAY_HFLIMIT",
    "AL_FILTER_NULL", "AL_FILTER_LOWPASS", "AL_FILTER_HIGHPASS", "AL_FILTER_BANDPASS", "AL_FILTER_TYPE", "AL_LOWPASS_GAIN", "AL_LOWPASS_GAINHF", "AL_HIGHPASS_GAIN", "AL_HIGHPASS_GAINLF", "AL_BANDPASS_GAIN", "AL_BANDPASS_GAINLF", "AL_BANDPASS_GAINHF", "AL_DIRECT_FILTER", "AL_AUXILIARY_SEND_FILTER", "AL_DIRECT_FILTER_GAINHF_AUTO", "AL_AUXILIARY_SEND_FILTER_GAIN_AUTO", "AL_MAX_AUXILIARY_SENDS",
]
