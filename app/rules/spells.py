"""Spell definitions and level-up choices for casters."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Spells Wizards can learn (beyond starting spell)
WIZARD_LEARNABLE_SPELLS: List[str] = ["Magic Missile", "Shield", "Sleep"]

# Spells Clerics can learn (beyond starting spell)
CLERIC_LEARNABLE_SPELLS: List[str] = ["Sacred Flame", "Shield", "Bless"]

# Damage spells: name -> (damage_expr, mana_cost). Used in combat.
SPELL_DAMAGE: Dict[str, tuple[str, int]] = {
    "Spark": ("1d4", 2),
    "Magic Missile": ("1d6", 2),
    "Sacred Flame": ("1d6", 2),
}

# Healing spells: name -> (heal_dice, mana_cost)
SPELL_HEAL: Dict[str, tuple[str, int]] = {
    "Cure Wounds": ("1d8+2", 2),
}

# All combat spells: name -> mana_cost
SPELL_MANA: Dict[str, int] = {
    "Spark": 2,
    "Magic Missile": 2,
    "Shield": 2,
    "Sleep": 3,
    "Cure Wounds": 2,
    "Sacred Flame": 2,
    "Bless": 2,
}


def resolve_spell_name(learned_spells: List[str], query: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a player query (e.g. 'magic missile', 'sleep') to a learned spell.
    Returns (spell_name, error). If spell_name is not None, error is None and vice versa.
    """
    q = query.strip().lower().replace(" ", "").replace("-", "")
    if not q:
        return None, "Cast which spell?"
    matches = []
    for name in learned_spells:
        canonical = name.lower().replace(" ", "").replace("-", "")
        if q in canonical or canonical in q:
            matches.append(name)
    if not matches:
        return None, f"You don't know a spell matching '{query}'."
    if len(matches) > 1:
        return None, f"Be more specific: {', '.join(matches)}"
    return matches[0], None


def get_spell_mana_cost(spell_name: str) -> int:
    """Mana cost for a spell. Returns 0 if unknown."""
    return SPELL_MANA.get(spell_name, 0)


def is_damage_spell(spell_name: str) -> bool:
    """True if the spell deals damage (uses attack roll)."""
    return spell_name in SPELL_DAMAGE


def is_healing_spell(spell_name: str) -> bool:
    """True if the spell heals a target."""
    return spell_name in SPELL_HEAL


def get_learnable_spells_for_class(cls: str) -> List[str]:
    """Spells this class can learn (beyond starting spells)."""
    if cls == "Wizard":
        return list(WIZARD_LEARNABLE_SPELLS)
    if cls == "Cleric":
        return list(CLERIC_LEARNABLE_SPELLS)
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
    for name in ["Magic Missile", "Sacred Flame", "Spark"]:
        if name in learned_spells and name in SPELL_DAMAGE:
            return name
    return None
