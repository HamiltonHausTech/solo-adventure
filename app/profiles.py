from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ClassProfile:
    name: str
    role: str  # "caster" or "melee"
    base_hp: int
    base_ac: int
    attack_bonus: int
    damage: str
    spells: List[str] = field(default_factory=list)
    description: str = ""
    hp_per_level: int = 1  # HP gained per level


@dataclass(frozen=True)
class RaceProfile:
    """Extensible race definition for character creation and future abilities."""

    name: str
    description: str = ""
    stat_mods: Dict[str, int] = field(default_factory=dict)
    abilities: List[str] = field(default_factory=list)  # e.g. "darkvision", "resist_poison"
    proficiencies: List[str] = field(default_factory=list)  # e.g. "bows", "stealth"


@dataclass(frozen=True)
class MobProfile:
    name: str
    hp: int = 1
    hp_expr: str = ""
    hp_min: int = 1
    count: int = 1
    ac: int = 10
    attack_bonus: int = 0
    damage: str = "1d4"
    loot: Dict[str, object] = field(default_factory=dict)
    ai: str = "focus_weakest"
    xp: int = 0


@dataclass(frozen=True)
class CompanionProfile:
    """Data-driven companion definition for campaigns."""

    companion_id: str
    name: str
    hp: int
    max_hp: int
    ac: int
    attack_bonus: int
    damage: str
    ai: str = "cautious"  # cautious, aggressive, focus_weakest
    defend_hp_threshold: int = 3  # defend when HP at or below this
    mana: int = 0
    max_mana: int = 0
    spells: List[str] = field(default_factory=list)  # for caster companions


CLASS_PROFILES: Dict[str, ClassProfile] = {
    "Fighter": ClassProfile(
        name="Fighter",
        role="melee",
        base_hp=14,
        base_ac=15,
        attack_bonus=3,
        damage="1d8+1",
        spells=[],
        description="Hardy frontline combatant.",
        hp_per_level=2,
    ),
    "Rogue": ClassProfile(
        name="Rogue",
        role="melee",
        base_hp=10,
        base_ac=14,
        attack_bonus=2,
        damage="1d6+1",
        spells=[],
        description="Agile skirmisher with precision strikes.",
    ),
    "Wizard": ClassProfile(
        name="Wizard",
        role="caster",
        base_hp=8,
        base_ac=12,
        attack_bonus=1,
        damage="1d4+1",
        spells=["Spark"],
        description="Arcane caster with limited stamina.",
    ),
    "Cleric": ClassProfile(
        name="Cleric",
        role="caster",
        base_hp=12,
        base_ac=14,
        attack_bonus=2,
        damage="1d6+1",
        spells=["Cure Wounds"],
        description="Divine healer and support caster.",
        hp_per_level=1,
    ),
}

RACE_PROFILES: Dict[str, RaceProfile] = {
    "Human": RaceProfile(
        name="Human",
        description="Versatile and adaptable.",
        stat_mods={},
        abilities=[],
        proficiencies=[],
    ),
    "Elf": RaceProfile(
        name="Elf",
        description="Graceful and perceptive, with keen senses.",
        stat_mods={"DEX": 1, "INT": 1},
        abilities=["darkvision", "keen_senses"],
        proficiencies=["bows"],
    ),
    "Dwarf": RaceProfile(
        name="Dwarf",
        description="Sturdy and resilient, at home underground.",
        stat_mods={"STR": 1, "CON": 1, "CHA": -1},
        abilities=["darkvision", "stonecunning"],
        proficiencies=["axes"],
    ),
    "Halfling": RaceProfile(
        name="Halfling",
        description="Small and nimble, quick to avoid danger.",
        stat_mods={"DEX": 1, "STR": -1},
        abilities=["lucky", "nimble"],
        proficiencies=["stealth"],
    ),
}


def list_class_names() -> List[str]:
    return list(CLASS_PROFILES.keys())


def get_class_profile(name: str) -> ClassProfile:
    return CLASS_PROFILES[name]


def is_caster_class(name: str) -> bool:
    profile = CLASS_PROFILES.get(name)
    return bool(profile and profile.role == "caster")


def is_melee_class(name: str) -> bool:
    profile = CLASS_PROFILES.get(name)
    return bool(profile and profile.role == "melee")


def get_class_spells(name: str) -> List[str]:
    profile = CLASS_PROFILES.get(name)
    if not profile:
        return []
    return list(profile.spells)


def list_race_names() -> List[str]:
    return list(RACE_PROFILES.keys())


def get_race_profile(name: str) -> RaceProfile:
    return RACE_PROFILES[name]


def list_mob_names(mobs: Dict[str, MobProfile]) -> List[str]:
    return list(mobs.keys())


def apply_race_mods(stats: Dict[str, int], race: str) -> Dict[str, int]:
    from .util import STAT_NAMES

    profile = RACE_PROFILES.get(race)
    result = {k: int(stats.get(k, 0)) for k in STAT_NAMES}
    if not profile:
        return result
    for key, value in profile.stat_mods.items():
        if key in result:
            new_value = result[key] + int(value)
            result[key] = max(0, min(4, new_value))
    return result
