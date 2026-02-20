from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple


def clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, value))


def yes_no(prompt: str) -> bool:
    while True:
        raw = input(f"{prompt} [y/n]: ").strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please enter y or n.")


def prompt_choice(prompt: str, options: List[str]) -> str:
    options_lower = {opt.lower(): opt for opt in options}
    while True:
        raw = input(f"{prompt} ({'/'.join(options)}): ").strip()
        if raw.lower() in options_lower:
            return options_lower[raw.lower()]
        print(f"Please choose one of: {', '.join(options)}")


# AD&D-style ability scores
STAT_NAMES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]


def prompt_stat_allocation(total_points: int = 12, min_value: int = 0, max_value: int = 4) -> Dict[str, int]:
    stats = {name: 0 for name in STAT_NAMES}
    remaining = total_points
    while True:
        print(f"Allocate stats. Remaining points: {remaining}")
        for key in stats:
            current = stats[key]
            prompt = f"{key} (current {current}, {min_value}-{max_value})"
            raw = input(f"{prompt}: ").strip()
            if not raw:
                value = current
            else:
                try:
                    value = int(raw)
                except ValueError:
                    print("Enter a number.")
                    break
            if value < min_value or value > max_value:
                print(f"{key} must be between {min_value} and {max_value}.")
                break
            delta = value - current
            if delta > remaining:
                print("Not enough points remaining.")
                break
            stats[key] = value
            remaining -= delta
        else:
            if remaining == 0:
                return stats
            print("You must spend all points.")
        remaining = total_points - sum(stats.values())


def format_stats(stats: Dict[str, int]) -> str:
    return ", ".join(f"{key}:{value}" for key, value in stats.items())


def inventory_names(items: List[object]) -> List[str]:
    names: List[str] = []
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name", "Unknown Item"))
        else:
            name = str(item)
        names.append(name)
    return names


def format_inventory(items: List[object]) -> str:
    if not items:
        return "Inventory: (empty)"
    counts: Dict[str, int] = {}
    for name in inventory_names(items):
        counts[name] = counts.get(name, 0) + 1
    parts = []
    for name, count in counts.items():
        if count > 1:
            parts.append(f"{name} x{count}")
        else:
            parts.append(name)
    return "Inventory: " + ", ".join(parts)


def format_inventory_detailed(items: List[object]) -> str:
    if not items:
        return "Inventory (detailed): (empty)"
    lines = ["Inventory (detailed):"]
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            name = str(item.get("name", "Unknown Item"))
            kind = str(item.get("kind", "item"))
            slot = str(item.get("slot", "")) if kind == "armor" else ""
            extra = f" [{kind} {slot}]".rstrip()
        else:
            name = str(item)
            extra = ""
        lines.append(f"{idx}. {name}{extra}")
    return "\n".join(lines)


def format_equipment(equipment: Dict[str, object]) -> str:
    lines = ["Equipment:"]
    for slot in ["head", "arms", "hands", "chest", "legs", "feet"]:
        item = equipment.get(slot)
        if isinstance(item, dict):
            name = str(item.get("name", "Unknown Item"))
        else:
            name = "(empty)"
        lines.append(f"- {slot}: {name}")
    return "\n".join(lines)


def format_currency(gold: int) -> str:
    return f"Gold: {gold}"


def summarize_health(name: str, hp: int, max_hp: int) -> str:
    return f"{name} HP {hp}/{max_hp}"


def print_divider() -> None:
    print("-" * 60)


def normalize_action(raw: str) -> str:
    cleaned = raw.strip().lower()
    if not cleaned:
        return cleaned
    tokens = cleaned.split()
    filler = {"to", "the", "a", "an", "towards", "toward"}
    verbs = {"go", "move", "walk", "head", "enter", "travel"}
    if tokens and tokens[0] in verbs:
        tokens = [tokens[0]] + [tok for tok in tokens[1:] if tok not in filler]
    return " ".join(tokens)


def pick_target_by_hp(options: List[Tuple[str, int]]) -> str:
    return min(options, key=lambda item: item[1])[0]


def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"").strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def color_text(text: str, color: str) -> str:
    if not supports_color():
        return text
    codes = {
        "green": "32",
        "yellow": "33",
        "red": "31",
        "cyan": "36",
        "gray": "90",
    }
    code = codes.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"
