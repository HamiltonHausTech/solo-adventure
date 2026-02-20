"""Player creation and mana management."""

from __future__ import annotations

from typing import Dict

from ..profiles import apply_race_mods, get_class_profile, is_caster_class, is_melee_class
from ..state import Character, GameState

from .dice import roll_dice


def _caster_mana(stats: Dict[str, int], cls: str = "Wizard") -> int:
    if cls == "Cleric":
        mod = max(0, int(stats.get("WIS", 0)))
    else:
        mod = max(0, int(stats.get("INT", 0)))
    return 2 + mod * 2


def is_caster(cls: str) -> bool:
    return is_caster_class(cls)


def is_melee(cls: str) -> bool:
    return is_melee_class(cls)


def create_player(name: str, cls: str, stats: Dict[str, int], race: str = "Human") -> Character:
    profile = get_class_profile(cls)
    final_stats = apply_race_mods(stats, race)
    con_bonus = max(0, final_stats.get("CON", 0))
    base_hp = profile.base_hp + con_bonus
    spark_uses = 2 if is_caster(cls) else 0
    mana = _caster_mana(final_stats, cls) if is_caster(cls) else 0
    learned_spells = list(profile.spells) if profile.spells else []
    return Character(
        name=name,
        race=race,
        cls=cls,
        stats=final_stats,
        hp=base_hp,
        max_hp=base_hp,
        ac=profile.base_ac,
        base_ac=profile.base_ac,
        mana=mana,
        max_mana=mana,
        attack_bonus=profile.attack_bonus,
        damage=profile.damage,
        spark_uses=spark_uses,
        gold=0,
        learned_spells=learned_spells,
    )


def ensure_wizard_mana(state: GameState) -> None:
    if not is_caster(state.player.cls):
        return
    if state.player.max_mana <= 0:
        max_mana = _caster_mana(state.player.stats, state.player.cls)
        state.player.max_mana = max_mana
        state.player.mana = max_mana
    else:
        state.player.mana = min(state.player.mana, state.player.max_mana)


def ensure_caster_mana(state: GameState) -> None:
    ensure_wizard_mana(state)
