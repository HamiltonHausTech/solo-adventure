"""Experience and leveling."""

from __future__ import annotations

from typing import List

from ..state import GameState

from .player import is_caster


# XP needed for each level (index 0 = level 1, index 1 = level 2, ...)
XP_TABLE: List[int] = [0, 100, 250, 500, 1000, 2000, 3500, 5000, 7000, 10000]


def xp_for_level(level: int) -> int:
    """XP required to reach this level."""
    if level <= 0:
        return 0
    idx = min(level - 1, len(XP_TABLE) - 1)
    return XP_TABLE[idx]


def level_from_xp(xp: int) -> int:
    """Current level based on total XP."""
    for level in range(len(XP_TABLE), 0, -1):
        if xp >= XP_TABLE[level - 1]:
            return level
    return 1


def grant_xp(state: GameState, amount: int) -> List[str]:
    """Grant XP to the player. Returns list of messages (level-up notices)."""
    if amount <= 0:
        return []
    state.player.xp += amount
    messages: List[str] = []
    while _check_level_up(state):
        msg = _apply_level_up(state)
        if msg:
            messages.append(msg)
    return messages


def _check_level_up(state: GameState) -> bool:
    """Return True if player has enough XP to level up."""
    current = state.player.level
    xp_needed = xp_for_level(current + 1)
    return state.player.xp >= xp_needed and current < len(XP_TABLE)


def _apply_level_up(state: GameState) -> str:
    """Apply one level-up. Returns message. Defers spell/ability choices to rest."""
    from ..profiles import get_class_profile

    from .spells import get_spell_choices_for_level

    state.player.level += 1
    profile = get_class_profile(state.player.cls)
    hp_per_level = getattr(profile, "hp_per_level", 1)
    state.player.max_hp += hp_per_level
    state.player.hp += hp_per_level
    if state.player.level % 2 == 0:
        state.player.attack_bonus += 1
    if is_caster(state.player.cls):
        state.player.max_mana += 2
        state.player.mana = state.player.max_mana

    # Defer spell choices until rest
    choices = get_spell_choices_for_level(
        state.player.cls,
        state.player.level,
        state.player.learned_spells,
    )
    if choices:
        state.pending_level_choices.append({
            "type": "spell",
            "choices": choices,
            "level": state.player.level,
        })

    return f"Level up! {state.player.name} is now level {state.player.level}."
