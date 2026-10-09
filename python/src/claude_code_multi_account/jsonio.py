"""Strict JSON reading: valid UTF-8 only, no NaN or Infinity literals, optional depth limit."""

from __future__ import annotations

import json
from typing import Any

MAX_DEPTH = 100


def _reject_constant(name: str) -> Any:
    raise ValueError(f"invalid JSON constant {name}")


def depth(value: Any) -> int:
    """Nesting level of `value`: 1 for a flat object or array, 0 for a scalar."""
    best = 0
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        v, level = stack.pop()
        if isinstance(v, dict):
            best = max(best, level)
            stack.extend((c, level + 1) for c in v.values())
        elif isinstance(v, list):
            best = max(best, level)
            stack.extend((c, level + 1) for c in v)
    return best


def parse_json(data: bytes, max_depth: int | None = None) -> Any:
    """Parse strictly. Raises `ValueError` for invalid UTF-8, bad JSON or excessive nesting."""
    try:
        value = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except (RecursionError, OverflowError) as e:
        raise ValueError("JSON too deeply nested or out of range") from e
    if max_depth is not None and depth(value) > max_depth:
        raise ValueError("JSON nested too deeply")
    return value
