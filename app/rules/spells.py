"""Spell definitions and level-up choices for casters."""

from __future__ import annotations

from typing import Dict, List

# Spells Wizards can learn (beyond starting spell). Format: name -> {damage, mana}
WIZARD_LEARNABLE_SPELLS: List[str] = ["Magic Missile", "Shield", "Sleep"]

# Damage spells: name -> (damage_expr, mana_cost). Used in combat.
SPELL_DAMAGE: Dict[str, tuple[str, int]] = {
    "Spark": ("1d4", 2),
    "Magic Missile": ("1d6", 2),
}


def get_learnable_spells_for_class(cls: str) -> List[str]:
    """Spells this class can learn (beyond starting spells)."""
    if cls == "Wizard":
        return list(WIZARD_LEARNABLE_SPELLS)
    return []


def get_spell_choices_for_level(cls: str, level: int, learned_spells: List[str]) -> List[str]:
    """Spells available to pick at this level (not yet learned)."""
    learnable = get_learnable_spells_for_class(cls)
    if not learnable:
        return []
    # Casters get a spell choice at levels 2, 4, 6, ...
    if level < 2 or level % 2 != 0:
        return []
    return [s for s in learnable if s not in learned_spells]


def get_best_damage_spell(learned_spells: List[str]) -> str | None:
    """Best damage spell the caster knows (for combat 'special')."""
    for name in ["Magic Missile", "Spark"]:
        if name in learned_spells and name in SPELL_DAMAGE:
            return name
    return None
