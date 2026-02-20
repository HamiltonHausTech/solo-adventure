"""Rest and mana regeneration."""

from __future__ import annotations

from ..state import GameState
from ..util import prompt_choice

from .player import is_caster


def _resolve_pending_choices(state: GameState) -> list[str]:
    """Resolve any pending level-up choices (spells, etc.). Returns messages."""
    messages: list[str] = []
    while state.pending_level_choices:
        choice_data = state.pending_level_choices.pop(0)
        if choice_data.get("type") == "spell":
            options = choice_data.get("choices", [])
            if not options:
                continue
            spell = prompt_choice(
                f"Choose a new spell (level {choice_data.get('level', '?')})",
                options,
            )
            state.player.learned_spells.append(spell)
            messages.append(f"You learn {spell}.")
    return messages


def regen_mana(state: GameState, amount: int = 1) -> int:
    if not is_caster(state.player.cls):
        return 0
    if state.player.max_mana <= 0:
        return 0
    before = state.player.mana
    state.player.mana = min(state.player.max_mana, state.player.mana + amount)
    return state.player.mana - before


def regen_companion_mana(state: GameState, amount: int = 1) -> int:
    """Regen mana for all caster companions. Returns total gained."""
    total = 0
    for companion in state.companions:
        if companion.max_mana <= 0:
            continue
        before = companion.mana
        companion.mana = min(companion.max_mana, companion.mana + amount)
        total += companion.mana - before
    return total


def reset_rest_streak(state: GameState) -> None:
    state.rest_streak = 0


def apply_rest(state: GameState) -> str:
    parts: list[str] = []
    choice_msgs = _resolve_pending_choices(state)
    parts.extend(choice_msgs)

    mana_gained = regen_mana(state, 1)
    companion_mana = regen_companion_mana(state, 1)
    mana_gained += companion_mana
    hp_gained = 0
    state.rest_streak += 1
    if state.rest_streak >= 2:
        if state.player.hp < state.player.max_hp:
            state.player.hp += 1
            hp_gained += 1
        for companion in state.companions:
            if companion.hp < companion.max_hp:
                companion.hp += 1
                hp_gained += 1
        state.rest_streak = 0
    parts.append("You rest and regain your focus.")
    if mana_gained:
        parts.append(f"Mana +{mana_gained}.")
    if hp_gained:
        parts.append(f"HP +{hp_gained}.")
    return " ".join(parts)
