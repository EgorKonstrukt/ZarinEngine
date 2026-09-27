from __future__ import annotations
import time

MAX_TARGET_FPS = 10000
MIN_TIMER_INTERVAL_MS = 1
MS_PER_SEC = 1000.0
SUB_MS_BUDGET_SEC = MIN_TIMER_INTERVAL_MS / MS_PER_SEC


def normalize_target_fps(value) -> int:
    try:
        tgt = int(value)
    except (TypeError, ValueError):
        return 60
    if tgt <= 0:
        return 0
    return max(1, min(MAX_TARGET_FPS, tgt))


def frame_budget_sec(value) -> float:
    tgt = normalize_target_fps(value)
    if tgt <= 0:
        return 0.0
    return 1.0 / float(tgt)


def timer_interval_ms(value) -> int:
    budget = frame_budget_sec(value)
    if budget <= 0.0:
        return 0
    interval = int(MS_PER_SEC * budget)
    if interval < MIN_TIMER_INTERVAL_MS:
        return 0
    return interval


def needs_software_pacing(value) -> bool:
    budget = frame_budget_sec(value)
    return 0.0 < budget < SUB_MS_BUDGET_SEC


class FramePacer:
    def __init__(self, target_fps=0):
        self._budget = 0.0
        self._last = 0.0
        self.set_target(target_fps)

    @property
    def budget(self) -> float:
        return self._budget

    @property
    def active(self) -> bool:
        return self._budget > 0.0

    def set_target(self, value) -> float:
        self._budget = frame_budget_sec(value)
        self._last = 0.0
        return self._budget

    def reset(self, now=None) -> None:
        if now is None:
            now = time.perf_counter()
        self._last = now

    def should_run(self, now=None) -> bool:
        if self._budget <= 0.0:
            return True
        if now is None:
            now = time.perf_counter()
        if self._last <= 0.0:
            self._last = now
            return True
        if now - self._last >= self._budget:
            self._last = now
            return True
        return False
