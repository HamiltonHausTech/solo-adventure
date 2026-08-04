"""Permanent between-adventure attribute and class upgrade choices."""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..state import GameState
from ..util import STAT_NAMES
from .spells import get_learnable_spells_for_class


ATTRIBUTE_CAP = 6

BASE_UPGRADES = [
    {"id": "vitality", "name": "Hardened Vitality", "description": "+3 maximum HP."},
    {"id": "precision", "name": "Combat Precision", "description": "+1 attack bonus."},
    {"id": "resilience", "name": "Battle Resilience", "description": "+1 base AC."},
]


def class_upgrade_options(state: GameState) -> List[Dict[str, str]]:
    options = [dict(item) for item in BASE_UPGRADES]
    if state.player.cls in {"Wizard", "Cleric"}:
        options.append(
            {"id": "mana_reserve", "name": "Deepened Reserve", "description": "+3 maximum mana."}
        )
        for spell in get_learnable_spells_for_class(state.player.cls):
            if spell not in state.player.learned_spells:
                options.append(
                    {"id": f"learn:{spell}", "name": f"Learn {spell}", "description": "Add this spell permanently."}
                )
    return options


def apply_progression_choices(
    state: GameState,
    allocations: Dict[str, int],
    upgrade_id: str = "",
) -> Tuple[bool, str]:
    normalized = {str(key).upper(): int(value) for key, value in allocations.items() if int(value)}
    if any(key not in STAT_NAMES for key in normalized):
        return False, "Unknown attribute."
    if any(value != 1 for value in normalized.values()):
        return False, "You may assign at most one point to an attribute per level-up decision."
    points = sum(normalized.values())
    if points > state.player.unspent_attribute_points:
        return False, "Not enough attribute points."
    if any(state.player.stats.get(key, 0) + value > ATTRIBUTE_CAP for key, value in normalized.items()):
        return False, f"Attributes cannot exceed {ATTRIBUTE_CAP}."

    chosen = upgrade_id.strip()
    option = next((item for item in class_upgrade_options(state) if item["id"] == chosen), None)
    if chosen and state.player.unspent_class_upgrades <= 0:
        return False, "No class upgrades are available."
    if chosen and option is None:
        return False, "That class upgrade is not available."
    if points == 0 and not chosen:
        return False, "Choose at least one attribute or class upgrade."

    for stat, value in normalized.items():
        state.player.stats[stat] = state.player.stats.get(stat, 0) + value
        if stat == "CON":
            state.player.max_hp += value
            state.player.hp += value
        if state.player.cls == "Wizard" and stat == "INT":
            state.player.max_mana += value * 2
            state.player.mana += value * 2
        if state.player.cls == "Cleric" and stat == "WIS":
            state.player.max_mana += value * 2
            state.player.mana += value * 2
    state.player.unspent_attribute_points -= points

    if chosen:
        if chosen == "vitality":
            state.player.max_hp += 3
            state.player.hp += 3
        elif chosen == "precision":
            state.player.attack_bonus += 1
        elif chosen == "resilience":
            state.player.base_ac += 1
            state.player.ac += 1
        elif chosen == "mana_reserve":
            state.player.max_mana += 3
            state.player.mana += 3
        elif chosen.startswith("learn:"):
            state.player.learned_spells.append(chosen.removeprefix("learn:"))
        state.player.unspent_class_upgrades -= 1
        state.player.chosen_upgrades.append(chosen)

    parts = []
    if normalized:
        parts.append("Attributes: " + ", ".join(f"{key} +{value}" for key, value in normalized.items()))
    if option:
        parts.append(f"Upgrade: {option['name']}")
    return True, "Progression confirmed. " + ". ".join(parts) + "."
