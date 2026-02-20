"""Enemy creation from campaign mob profiles."""

from __future__ import annotations

from typing import List

from ..content import get_mob_profile
from ..state import Enemy

from .dice import roll_dice


def _roll_mob_hp(expr: str, minimum: int, count: int) -> int:
    total = 0
    for _ in range(max(1, count)):
        roll, _detail = roll_dice(expr)
        total += max(minimum, roll)
    return total


def create_enemy(campaign_id: str, name: str) -> Enemy:
    template = get_mob_profile(campaign_id, name)
    if template.hp_expr:
        hp = _roll_mob_hp(template.hp_expr, template.hp_min, 1)
    else:
        hp = template.hp
    return Enemy(
        name=name,
        hp=hp,
        max_hp=hp,
        ac=template.ac,
        attack_bonus=template.attack_bonus,
        damage=template.damage,
    )


def create_enemies(campaign_id: str, name: str) -> List[Enemy]:
    template = get_mob_profile(campaign_id, name)
    count = max(1, int(template.count))
    enemies: List[Enemy] = []
    for _ in range(count):
        if template.hp_expr:
            hp = _roll_mob_hp(template.hp_expr, template.hp_min, 1)
        else:
            hp = template.hp
        enemies.append(
            Enemy(
                name=name,
                hp=hp,
                max_hp=hp,
                ac=template.ac,
                attack_bonus=template.attack_bonus,
                damage=template.damage,
            )
        )
    return enemies
