from __future__ import annotations


def _get_scale() -> float:
    try:
        from core.config import get_global_config
        cfg = get_global_config()
        return cfg.get("editor.ui_scale", 100) / 100.0
    except Exception:
        return 1.0


def scale(val) -> int:
    return int(val * _get_scale())


def scale_xy(w, h) -> tuple[int, int]:
    s = _get_scale()
    return int(w * s), int(h * s)
