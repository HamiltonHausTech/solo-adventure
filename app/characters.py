"""Character persistence across campaigns."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .content import get_campaign_quest_item_ids, item_from_name
from .state import Character, GameState


CHARACTERS_DIR = "characters"


def _sanitize_name(name: str) -> str:
    """Convert character name to safe filename."""
    safe = re.sub(r"[^\w\s-]", "", name.lower())
    safe = re.sub(r"[-\s]+", "_", safe).strip("_")
    return safe or "character"


def _characters_path() -> str:
    path = os.path.join(os.getcwd(), CHARACTERS_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def character_file_path(name: str) -> str:
    """Path to a character's save file."""
    return os.path.join(_characters_path(), f"{_sanitize_name(name)}.json")


def list_characters() -> List[str]:
    """Return sorted list of saved character names."""
    path = _characters_path()
    if not os.path.isdir(path):
        return []
    names = []
    for f in os.listdir(path):
        if f.endswith(".json"):
            try:
                with open(os.path.join(path, f), "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                names.append(data.get("name", f[:-5]))
            except (json.JSONDecodeError, OSError):
                continue
    return sorted(set(names))


def save_character(
    character: Character,
    inventory: List[Dict[str, Any]],
    equipment: Dict[str, Optional[Dict[str, Any]]],
) -> None:
    """Persist character with inventory and equipment for use across campaigns."""
    data = {
        "version": 1,
        **character.to_dict(),
        "inventory": list(inventory),
        "equipment": dict(equipment),
    }
    path = character_file_path(character.name)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except OSError as e:
        raise IOError(f"Failed to save character to {path}: {e}") from e


def load_character(
    name: str, campaign_id: Optional[str] = None
) -> Tuple[Character, List[Dict[str, Any]], Dict[str, Optional[Dict[str, Any]]]]:
    """Load a saved character. Returns (character, inventory, equipment)."""
    path = character_file_path(name)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise FileNotFoundError(f"Character '{name}' not found.") from None
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Failed to load character: {e}") from e

    character = Character.from_dict(data)
    # Restore full HP/mana for new campaign
    character.hp = character.max_hp
    character.mana = character.max_mana

    raw_inventory = data.get("inventory", [])
    inventory: List[Dict[str, Any]] = []
    cid = campaign_id or "ruined_watchtower"
    for item in raw_inventory:
        if isinstance(item, dict):
            inventory.append(item)
        elif isinstance(item, str):
            inventory.append(item_from_name(cid, item))

    equipment = data.get("equipment", {})
    if not isinstance(equipment, dict):
        equipment = {}
    for slot in ["head", "arms", "hands", "chest", "legs", "feet"]:
        equipment.setdefault(slot, None)

    # Restock consumables when starting a new campaign
    potion_count = sum(
        1 for item in inventory
        if isinstance(item, dict) and str(item.get("id", "")).lower() == "healing_potion"
    )
    for _ in range(max(0, 3 - potion_count)):
        inventory.append(item_from_name(cid, "healing_potion"))

    return character, inventory, equipment


def strip_campaign_quest_items(state: GameState) -> None:
    """Remove campaign quest items from inventory and equipment (call on victory)."""
    quest_ids = set(get_campaign_quest_item_ids(state.campaign_id))
    if not quest_ids:
        return
    state.inventory[:] = [
        item for item in state.inventory
        if isinstance(item, dict) and str(item.get("id", "")) not in quest_ids
    ]
    for slot in state.equipment:
        item = state.equipment.get(slot)
        if isinstance(item, dict) and str(item.get("id", "")) in quest_ids:
            state.equipment[slot] = None


def character_summary(name: str) -> str:
    """Brief summary of a saved character for display."""
    try:
        char, inv, _ = load_character(name)
        inv_count = len([i for i in inv if isinstance(i, dict)])
        return f"{char.name} ({char.race} {char.cls}) — {char.gold} gold, {inv_count} items"
    except (FileNotFoundError, ValueError):
        return name
