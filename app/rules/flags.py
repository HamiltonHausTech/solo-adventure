"""Flag helpers for game state."""

from __future__ import annotations

from typing import Any, Dict, List

from ..state import GameState


def get_flag_list(state: GameState, key: str) -> list:
    value = state.flags.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        value = []
    else:
        value = list(value)
    state.flags[key] = value
    return value


def get_flag_dict(state: GameState, key: str) -> Dict[str, Any]:
    value = state.flags.get(key)
    if isinstance(value, dict):
        return value
    state.flags[key] = {}
    return state.flags[key]


def next_corpse_id(state: GameState) -> int:
    value = state.flags.get("next_corpse_id")
    if not isinstance(value, int):
        value = 1
    state.flags["next_corpse_id"] = value + 1
    return value
