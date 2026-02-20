"""Dice rolling and skill checks."""

from __future__ import annotations

import random
from typing import Tuple


def roll_die(sides: int) -> int:
    return random.randint(1, sides)


def roll_dice(expr: str) -> Tuple[int, str]:
    expr = expr.replace(" ", "")
    if "d" not in expr:
        value = int(expr)
        return value, str(value)
    left, right = expr.split("d", 1)
    count = int(left) if left else 1
    if "+" in right:
        sides_str, bonus_str = right.split("+", 1)
        bonus = int(bonus_str)
    elif "-" in right:
        sides_str, bonus_str = right.split("-", 1)
        bonus = -int(bonus_str)
    else:
        sides_str = right
        bonus = 0
    sides = int(sides_str)
    rolls = [roll_die(sides) for _ in range(count)]
    total = sum(rolls) + bonus
    detail = f"{'+'.join(str(r) for r in rolls)}"
    if bonus:
        detail = f"{detail}{bonus:+d}"
    return total, detail


def check(stat_bonus: int, dc: int) -> Tuple[bool, int, int]:
    roll = roll_die(20)
    total = roll + stat_bonus
    return total >= dc, roll, total
