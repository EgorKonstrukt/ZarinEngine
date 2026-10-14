# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Zarrakun

from __future__ import annotations
import ctypes
try:
    import openal
except Exception:
    openal = None


class EFXError(RuntimeError):
    pass


_efx_initialized = False
_efx_available = False
_efx_no_device = False
_max_aux_sends = 0
_enum_cache: dict = {}
_alGenEffects = None
_alDeleteEffects = None
_alIsEffect = None
_alEffecti = None
_alEffectf = None
_alGenFilters = None
_alDeleteFilters = None
_alIsFilter = None
_alFilteri = None
_alFilterf = None
_alGenAuxiliaryEffectSlots = None
_alDeleteAuxiliaryEffectSlots = None
_alIsAuxiliaryEffectSlot = None
_alAuxiliaryEffectSloti = None
_alAuxiliaryEffectSlotf = None
AL_EFFECT_NULL = 0
AL_EFFECT_REVERB = 1
AL_EFFECT_CHORUS = 2
AL_EFFECT_DISTORTION = 3
AL_EFFECT_ECHO = 4
AL_EFFECT_FLANGER = 5
AL_EFFECT_FREQUENCY_SHIFTER = 6
AL_EFFECT_VOCAL_MORPHER = 7
AL_EFFECT_PITCH_SHIFTER = 8
AL_EFFECT_RING_MODULATOR = 9
AL_EFFECT_AUTOWAH = 10
AL_EFFECT_COMPRESSOR = 11
AL_EFFECT_EQUALIZER = 12
AL_EFFECT_EAXREVERB = 32768
AL_EFFECT_TYPE = 32769
AL_EFFECTSLOT_EFFECT = 1
AL_EFFECTSLOT_GAIN = 2
AL_EFFECTSLOT_AUXILIARY_SEND_AUTO = 3
AL_REVERB_DENSITY = 1
AL_REVERB_DIFFUSION = 2
AL_REVERB_GAIN = 3
AL_REVERB_GAINHF = 4
AL_REVERB_DECAY_TIME = 5
AL_REVERB_DECAY_HFRATIO = 6
AL_REVERB_REFLECTIONS_GAIN = 7
AL_REVERB_REFLECTIONS_DELAY = 8
AL_REVERB_LATE_REVERB_GAIN = 9
AL_REVERB_LATE_REVERB_DELAY = 10
AL_REVERB_AIR_ABSORPTION_GAINHF = 11
AL_REVERB_ROOM_ROLLOFF_FACTOR = 12
AL_REVERB_DECAY_HFLIMIT = 13
AL_EAXREVERB_DENSITY = 1
AL_EAXREVERB_DIFFUSION = 2
AL_EAXREVERB_GAIN = 3
AL_EAXREVERB_GAINHF = 4
AL_EAXREVERB_GAINLF = 5
AL_EAXREVERB_DECAY_TIME = 6
AL_EAXREVERB_DECAY_HFRATIO = 7
AL_EAXREVERB_DECAY_LFRATIO = 8
AL_EAXREVERB_REFLECTIONS_GAIN = 9
AL_EAXREVERB_REFLECTIONS_DELAY = 10
AL_EAXREVERB_REFLECTIONS_PAN = 11
AL_EAXREVERB_LATE_REVERB_GAIN = 12
AL_EAXREVERB_LATE_REVERB_DELAY = 13
AL_EAXREVERB_LATE_REVERB_PAN = 14
AL_EAXREVERB_ECHO_TIME = 15
AL_EAXREVERB_ECHO_DEPTH = 16
AL_EAXREVERB_MODULATION_TIME = 17
AL_EAXREVERB_MODULATION_DEPTH = 18
AL_EAXREVERB_AIR_ABSORPTION_GAINHF = 19
AL_EAXREVERB_HFREFERENCE = 20
AL_EAXREVERB_LFREFERENCE = 21
AL_EAXREVERB_ROOM_ROLLOFF_FACTOR = 22
AL_EAXREVERB_DECAY_HFLIMIT = 23
AL_FILTER_NULL = 0
AL_FILTER_LOWPASS = 1
AL_FILTER_HIGHPASS = 2
AL_FILTER_BANDPASS = 3
AL_FILTER_TYPE = 32769
AL_LOWPASS_GAIN = 1
AL_LOWPASS_GAINHF = 2
AL_HIGHPASS_GAIN = 1
AL_HIGHPASS_GAINLF = 2
AL_BANDPASS_GAIN = 1
AL_BANDPASS_GAINLF = 2
AL_BANDPASS_GAINHF = 3
AL_DIRECT_FILTER = 131077
AL_AUXILIARY_SEND_FILTER = 131078
AL_DIRECT_FILTER_GAINHF_AUTO = 131082
AL_AUXILIARY_SEND_FILTER_GAIN_AUTO = 131083
AL_MAX_AUXILIARY_SENDS = 2


def invalidate_efx_cache():
    global _efx_initialized, _efx_available, _efx_no_device, _max_aux_sends
    global _alGenEffects, _alDeleteEffects, _alIsEffect, _alEffecti, _alEffectf
    global _alGenFilters, _alDeleteFilters, _alIsFilter, _alFilteri, _alFilterf
    global _alGenAuxiliaryEffectSlots, _alDeleteAuxiliaryEffectSlots
    global _alIsAuxiliaryEffectSlot, _alAuxiliaryEffectSloti, _alAuxiliaryEffectSlotf
    _efx_initialized = False
    _efx_available = False
    _efx_no_device = False
    _max_aux_sends = 0
    _enum_cache.clear()
    _alGenEffects = None
    _alDeleteEffects = None
    _alIsEffect = None
    _alEffecti = None
    _alEffectf = None
    _alGenFilters = None
    _alDeleteFilters = None
    _alIsFilter = None
    _alFilteri = None
    _alFilterf = None
    _alGenAuxiliaryEffectSlots = None
    _alDeleteAuxiliaryEffectSlots = None
    _alIsAuxiliaryEffectSlot = None
    _alAuxiliaryEffectSloti = None
    _alAuxiliaryEffectSlotf = None


def _resolve_enum(almod, name: bytes, fallback: int) -> int:
    try:
        cached = _enum_cache.get(name)
        if cached is not None:
            return int(cached)
        try:
            value = int(almod.alGetEnumValue(name))
        except Exception:
            value = 0
        if value == 0:
            value = fallback
        _enum_cache[name] = value
        return value
    except Exception:
        return fallback


def _load_proc(almod, alcmod, dev, name: bytes, functype):
    try:
        ptr = almod.alGetProcAddress(name)
    except Exception:
        ptr = 0
    if not ptr and alcmod is not None and dev is not None:
        try:
            ptr = alcmod.alcGetProcAddress(dev, name)
        except Exception:
            ptr = 0
    if not ptr:
        return None
    try:
        return functype(ptr)
    except Exception:
        return None


def ensure_efx() -> bool:
    global _efx_initialized, _efx_available, _efx_no_device, _max_aux_sends
    global _alGenEffects, _alDeleteEffects, _alIsEffect, _alEffecti, _alEffectf
    global _alGenFilters, _alDeleteFilters, _alIsFilter, _alFilteri, _alFilterf
    global _alGenAuxiliaryEffectSlots, _alDeleteAuxiliaryEffectSlots
    global _alIsAuxiliaryEffectSlot, _alAuxiliaryEffectSloti, _alAuxiliaryEffectSlotf
    if _efx_initialized:
        if _efx_available:
            return True
        if _efx_no_device:
            try:
                import openal as _oal_check
                _dev_check = _oal_check.oalGetDevice()
                _init_check = _oal_check.oalGetInit()
            except Exception:
                return False
            if not _init_check or _dev_check is None:
                return False
            _efx_initialized = False
            _efx_no_device = False
        else:
            return False
    if openal is None:
        _efx_initialized = True
        _efx_available = False
        _efx_no_device = False
        return False
    try:
        import openal.al as almod
        from openal import alc as alcmod
        import openal as oalmod
        try:
            dev = oalmod.oalGetDevice()
        except Exception:
            dev = None
        if dev is None:
            try:
                initialized = bool(oalmod.oalGetInit())
            except Exception:
                initialized = False
            if not initialized:
                _efx_initialized = True
                _efx_available = False
                _efx_no_device = True
                return False
            _efx_initialized = True
            _efx_available = False
            _efx_no_device = True
            return False
        try:
            present = bool(alcmod.alcIsExtensionPresent(dev, b"ALC_EXT_EFX"))
        except Exception:
            present = False
        if not present:
            _efx_initialized = True
            _efx_available = False
            _efx_no_device = False
            return False
        funcs = {
            b"alGenEffects": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            b"alDeleteEffects": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            b"alIsEffect": ctypes.CFUNCTYPE(ctypes.c_ubyte, ctypes.c_uint),
            b"alEffecti": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_int, ctypes.c_int),
            b"alEffectf": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_int, ctypes.c_float),
            b"alGenFilters": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            b"alDeleteFilters": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            b"alIsFilter": ctypes.CFUNCTYPE(ctypes.c_ubyte, ctypes.c_uint),
            b"alFilteri": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_int, ctypes.c_int),
            b"alFilterf": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_int, ctypes.c_float),
            b"alGenAuxiliaryEffectSlots": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            b"alDeleteAuxiliaryEffectSlots": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            b"alIsAuxiliaryEffectSlot": ctypes.CFUNCTYPE(ctypes.c_ubyte, ctypes.c_uint),
            b"alAuxiliaryEffectSloti": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_int, ctypes.c_int),
            b"alAuxiliaryEffectSlotf": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_int, ctypes.c_float),
        }
        loaded: dict = {}
        for fname, ftype in funcs.items():
            fn = _load_proc(almod, alcmod, dev, fname, ftype)
            if fn is None:
                _efx_initialized = True
                _efx_available = False
                _efx_no_device = False
                return False
            loaded[fname] = fn
        _alGenEffects = loaded[b"alGenEffects"]
        _alDeleteEffects = loaded[b"alDeleteEffects"]
        _alIsEffect = loaded[b"alIsEffect"]
        _alEffecti = loaded[b"alEffecti"]
        _alEffectf = loaded[b"alEffectf"]
        _alGenFilters = loaded[b"alGenFilters"]
        _alDeleteFilters = loaded[b"alDeleteFilters"]
        _alIsFilter = loaded[b"alIsFilter"]
        _alFilteri = loaded[b"alFilteri"]
        _alFilterf = loaded[b"alFilterf"]
        _alGenAuxiliaryEffectSlots = loaded[b"alGenAuxiliaryEffectSlots"]
        _alDeleteAuxiliaryEffectSlots = loaded[b"alDeleteAuxiliaryEffectSlots"]
        _alIsAuxiliaryEffectSlot = loaded[b"alIsAuxiliaryEffectSlot"]
        _alAuxiliaryEffectSloti = loaded[b"alAuxiliaryEffectSloti"]
        _alAuxiliaryEffectSlotf = loaded[b"alAuxiliaryEffectSlotf"]
        _resolve_enum(almod, b"AL_EFFECT_TYPE", AL_EFFECT_TYPE)
        _resolve_enum(almod, b"AL_EFFECT_REVERB", AL_EFFECT_REVERB)
        _resolve_enum(almod, b"AL_FILTER_TYPE", AL_FILTER_TYPE)
        _resolve_enum(almod, b"AL_FILTER_LOWPASS", AL_FILTER_LOWPASS)
        _resolve_enum(almod, b"AL_AUXILIARY_SEND_FILTER", AL_AUXILIARY_SEND_FILTER)
        _resolve_enum(almod, b"AL_DIRECT_FILTER", AL_DIRECT_FILTER)
        try:
            _max_aux_sends = 1
            try:
                import openal.alc as _alcq
                _val = _alcq.alcGetEnumValue(dev, b"ALC_MAX_AUXILIARY_SENDS")
                if _val:
                    _max_aux_sends = max(1, int(_val))
            except Exception:
                pass
        except Exception:
            _max_aux_sends = 1
        _efx_initialized = True
        _efx_available = True
        _efx_no_device = False
        return True
    except Exception:
        _efx_initialized = True
        _efx_available = False
        _efx_no_device = False
        return False


def efx_available() -> bool:
    if _efx_available:
        return True
    if _efx_initialized and not _efx_no_device:
        return False
    return ensure_efx()


def _effect_type_enum() -> int:
    cached = _enum_cache.get(b"AL_EFFECT_TYPE")
    if cached is not None:
        return int(cached)
    return AL_EFFECT_TYPE


def _reverb_type_enum() -> int:
    cached = _enum_cache.get(b"AL_EFFECT_REVERB")
    if cached is not None:
        return int(cached)
    return AL_EFFECT_REVERB


def create_effect() -> int:
    if not efx_available():
        raise EFXError("EFX not available")
    effect_id = ctypes.c_uint()
    _alGenEffects(1, ctypes.pointer(effect_id))
    if effect_id.value == 0:
        raise EFXError("Failed to create effect")
    return effect_id.value


def delete_effect(effect_id: int):
    if effect_id == 0:
        return
    if not _efx_available or _alDeleteEffects is None:
        return
    try:
        val = ctypes.c_uint(int(effect_id))
        _alDeleteEffects(1, ctypes.pointer(val))
    except Exception:
        pass


def is_effect(effect_id: int) -> bool:
    if effect_id == 0 or not _efx_available or _alIsEffect is None:
        return False
    try:
        return bool(_alIsEffect(int(effect_id)))
    except Exception:
        return False


def set_effect_type(effect_id: int, etype: int):
    if not _efx_available or _alEffecti is None:
        return
    try:
        _alEffecti(int(effect_id), int(_effect_type_enum()), int(etype))
    except Exception:
        pass


def set_effect_param_i(effect_id: int, param: int, value: int):
    if not _efx_available or _alEffecti is None:
        return
    try:
        _alEffecti(int(effect_id), int(param), int(value))
    except Exception:
        pass


def set_effect_param_f(effect_id: int, param: int, value: float):
    if not _efx_available or _alEffectf is None:
        return
    try:
        _alEffectf(int(effect_id), int(param), float(value))
    except Exception:
        pass


def _read_audio_flag(key: str, default: bool) -> bool:
    try:
        from core.engine.eng import Engine
        eng = Engine.instance()
        if eng is not None and getattr(eng, "_project_path", None):
            try:
                from core.config.config import get_project_config
                pcfg = get_project_config(eng._project_path)
                value = pcfg.get(key, None)
                if value is not None:
                    return bool(value)
            except Exception:
                pass
    except Exception:
        pass
    try:
        from core.config.config import get_global_config
        cfg = get_global_config()
        value = cfg.get(key, default)
        return bool(value) if value is not None else bool(default)
    except Exception:
        return bool(default)


def reverb_enabled() -> bool:
    return bool(_read_audio_flag("audio.enable_reverb", True))


def occlusion_enabled() -> bool:
    return bool(_read_audio_flag("audio.enable_occlusion", True))


def spatialization_enabled() -> bool:
    return bool(_read_audio_flag("audio.enable_spatialization", True))
