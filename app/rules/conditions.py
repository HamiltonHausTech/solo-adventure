"""Shared combat-condition application and turn processing."""

from __future__ import annotations

from typing import List

from ..state import Character, Companion, GameState
from .dice import roll_die


def attempt_poison(target: Character | Companion, *, dc: int = 12, duration: int = 2) -> str:
    """Attempt to poison a living target; returns a narrated save result."""
    if target.hp <= 0:
        return ""
    con_bonus = target.stats.get("CON", 0) if isinstance(target, Character) else 1
    roll = roll_die(20)
    total = roll + con_bonus
    if total >= dc:
        return f"{target.name} resists the venom (roll {roll} -> {total} vs DC {dc})."
    target.conditions["poisoned"] = max(duration, target.conditions.get("poisoned", 0))
    return f"{target.name} is poisoned for {duration} rounds (roll {roll} -> {total} vs DC {dc})."


def resolve_condition_ticks(state: GameState) -> List[str]:
    """Resolve recurring party conditions once per completed player turn."""
    messages: List[str] = []
    for actor in [state.player, state.companion]:
        remaining = actor.conditions.get("poisoned", 0)
        if remaining <= 0 or actor.hp <= 0:
            continue
        actor.hp = max(0, actor.hp - 1)
        remaining -= 1
        if remaining:
            actor.conditions["poisoned"] = remaining
            messages.append(f"Poison courses through {actor.name} for 1 damage ({remaining} round{'s' if remaining != 1 else ''} remaining).")
        else:
            actor.conditions.pop("poisoned", None)
            messages.append(f"Poison courses through {actor.name} for 1 damage, then fades.")
    return messages
