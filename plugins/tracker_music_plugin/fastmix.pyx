# Fast stereo mixing kernel for TrackerSoftwareRenderer.
#
# This module is compiled with Cython into `fastmix.<ext>` inside the
# tracker_music_plugin directory. It replaces the per-tick / per-voice
# NumPy pipeline (`_mix_one` + pan + peak) with a single C loop without
# temporary allocations.
#
# Bit-compatibility notes vs renderer._mix_one:
# - linear interpolation, clip to [0, wlen-1], i1 = min(i0+1, wlen-1)
# - loop_mode == 0 or loop_start >= loop_end (or span <= 1) -> no loop
# - loop_mode == 1 -> forward loop, same wrapping as np.mod version
# - loop_mode == 2 -> "triangular" ping-pong exactly as the old code:
#       rel = mod(p - loop_start, span); idx = loop_start + min(rel, span-rel)
# - past-the-end tail holds the last sample (clip), voice deactivation is
#   still handled by the Python caller (v.pos advance + active flag).
#
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: nonecheck=False
# cython: initializedcheck=False

import numpy as np
cimport numpy as cnp
cimport cython
from libc.math cimport fmod, fabs

# Ensure NumPy C-API is initialized (harmless for memoryview-only code).
cnp.import_array()


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef float mix_add_voice(
    float[::1] wave,
    double pos,
    double step,
    float vol_gain,
    int loop_start,
    int loop_end,
    int loop_mode,
    float lg,
    float rg,
    float[::1] left,
    float[::1] right,
) except -1.0:
    """Mix one voice into stereo buffers, return mono peak (after gain).

    Args:
        wave: mono sample data, float32 contiguous, normalized to ~[-1, 1].
        pos: start read position in sample units.
        step: freq / sample_rate (samples advanced per output frame).
        vol_gain: voice vol * channel gain (0 skips mixing).
        loop_start/loop_end/loop_mode: same semantics as renderer.
        lg/rg: constant-power pan gains for left/right.
        left/right: stereo accumulators, length n (contiguous).

    Returns:
        Peak of abs(mono * vol_gain) over this block (0 if skipped).
    """
    cdef Py_ssize_t n = left.shape[0]
    cdef Py_ssize_t wlen = wave.shape[0]
    cdef Py_ssize_t i
    cdef double p = pos
    cdef double q = pos
    cdef double rel = 0.0
    cdef double idx
    cdef Py_ssize_t i0
    cdef float frac, s, m, a
    cdef float peak = 0.0
    cdef int span = 0
    cdef double tri
    cdef float last

    if n == 0 or wlen == 0 or vol_gain == 0.0 or step <= 0.0:
        return 0.0
    if n != right.shape[0]:
        raise ValueError("left/right length mismatch")

    last = wave[wlen - 1]

    if loop_mode == 0 or loop_end <= loop_start:
        # ---- No loop: clip, hold last sample past the end ----
        for i in range(n):
            if p >= wlen:
                s = last
            elif p < 0.0:
                s = wave[0]
            else:
                i0 = <Py_ssize_t>p
                if i0 >= wlen - 1:
                    s = last
                else:
                    frac = <float>(p - <double>i0)
                    s = wave[i0] * (1.0 - frac) + wave[i0 + 1] * frac
            m = s * vol_gain
            a = m if m >= 0.0 else -m
            if a > peak:
                peak = a
            left[i] += m * lg
            right[i] += m * rg
            p += step
        return peak

    span = loop_end - loop_start
    if span <= 1:
        for i in range(n):
            if p >= wlen:
                s = last
            elif p < 0.0:
                s = wave[0]
            else:
                i0 = <Py_ssize_t>p
                if i0 >= wlen - 1:
                    s = last
                else:
                    frac = <float>(p - <double>i0)
                    s = wave[i0] * (1.0 - frac) + wave[i0 + 1] * frac
            m = s * vol_gain
            a = m if m >= 0.0 else -m
            if a > peak:
                peak = a
            left[i] += m * lg
            right[i] += m * rg
            p += step
        return peak

    if loop_mode == 2:
        # ---- Triangular ping-pong (matches old np.minimum(rel, span-rel)) ----
        if pos >= <double>loop_start:
            rel = fmod(pos - <double>loop_start, <double>span)
            if rel < 0.0:
                rel += <double>span
        else:
            rel = 0.0
        for i in range(n):
            if p < <double>loop_start:
                if p < 0.0:
                    s = wave[0]
                else:
                    i0 = <Py_ssize_t>p
                    if i0 >= wlen - 1:
                        s = last
                    else:
                        frac = <float>(p - <double>i0)
                        s = wave[i0] * (1.0 - frac) + wave[i0 + 1] * frac
            else:
                # Exact head->loop transition: first wrapped sample uses
                # rel = p - loop_start (in [0, step)), not stale 0.
                if pos < <double>loop_start and rel == 0.0 and (p - step) < <double>loop_start:
                    rel = p - <double>loop_start
                    if rel < 0.0:
                        rel = 0.0
                    elif rel >= <double>span:
                        rel = fmod(rel, <double>span)
                tri = rel if rel <= <double>span - rel else <double>span - rel
                idx = <double>loop_start + tri
                i0 = <Py_ssize_t>idx
                if i0 >= wlen - 1:
                    s = last
                elif i0 < 0:
                    s = wave[0]
                else:
                    frac = <float>(idx - <double>i0)
                    s = wave[i0] * (1.0 - frac) + wave[i0 + 1] * frac
                rel += step
                if rel >= <double>span:
                    # step is tiny (freq/sr < 1), so a single subtract
                    # covers the common case; loop for safety.
                    rel = fmod(rel, <double>span)
            m = s * vol_gain
            a = m if m >= 0.0 else -m
            if a > peak:
                peak = a
            left[i] += m * lg
            right[i] += m * rg
            p += step
        return peak

    # ---- Forward loop (mode 1 and any other nonzero mode) ----
    if pos >= <double>loop_start:
        q = <double>loop_start + fmod(pos - <double>loop_start, <double>span)
    else:
        q = pos
    for i in range(n):
        if p < <double>loop_start:
            if p < 0.0:
                s = wave[0]
            else:
                i0 = <Py_ssize_t>p
                if i0 >= wlen - 1:
                    s = last
                else:
                    frac = <float>(p - <double>i0)
                    s = wave[i0] * (1.0 - frac) + wave[i0 + 1] * frac
            # Keep q in lockstep so the head->loop transition is seamless
            # (q == p while in head; first wrapped sample then uses q == p).
            q += step
        else:
            i0 = <Py_ssize_t>q
            if i0 >= wlen - 1:
                s = last
            elif i0 < 0:
                s = wave[0]
            else:
                frac = <float>(q - <double>i0)
                # NOTE: matches old code — interpolation may read one
                # sample past loop_end (no wrap of i1 to loop_start).
                if i0 + 1 >= wlen:
                    s = last
                else:
                    s = wave[i0] * (1.0 - frac) + wave[i0 + 1] * frac
            q += step
            if q >= <double>loop_end:
                q -= <double>span
                while q >= <double>loop_end:
                    q -= <double>span
        m = s * vol_gain
        a = m if m >= 0.0 else -m
        if a > peak:
            peak = a
        left[i] += m * lg
        right[i] += m * rg
        p += step
    return peak


@cython.boundscheck(False)
@cython.wraparound(False)
cpdef void clear_stereo(float[::1] left, float[::1] right) noexcept:
    """Zero two buffers (single C loop, avoids np.zeros per tick)."""
    cdef Py_ssize_t n = left.shape[0]
    cdef Py_ssize_t i
    for i in range(n):
        left[i] = 0.0
    n = right.shape[0]
    for i in range(n):
        right[i] = 0.0


def pan_gains(int pan) -> tuple:
    """Constant-power pan gains, same formula as renderer."""
    cdef float lg, rg
    if pan < 0:
        pan = 0
    elif pan > 255:
        pan = 255
    lg = (<float>((255.0 - pan) / 255.0)) ** 0.5
    rg = (<float>(pan / 255.0)) ** 0.5
    # NOTE: ** on floats follows Python semantics; keep in sync with
    # np.sqrt(max(0.0, ...)) used by the Python fallback.
    return (float(lg), float(rg))
