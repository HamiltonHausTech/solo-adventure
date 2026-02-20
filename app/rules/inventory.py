"""Inventory, equipment, items, and loot."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..content import get_mob_profile, item_from_id
from ..state import GameState

from .dice import roll_die, roll_dice


def item_counts_toward_limit(item: Dict[str, object]) -> bool:
    return bool(item.get("counts_toward_limit", True))


def inventory_used(state: GameState) -> int:
    count = 0
    for item in state.inventory:
        if isinstance(item, dict) and item_counts_toward_limit(item):
            count += 1
        elif not isinstance(item, dict):
            count += 1
    return count


def can_add_item(state: GameState, item: Dict[str, object]) -> bool:
    if not item_counts_toward_limit(item):
        return True
    return inventory_used(state) < state.inventory_limit


def add_item_to_inventory(state: GameState, item: Dict[str, object]) -> Tuple[bool, str]:
    if not can_add_item(state, item):
        return False, "Inventory is full."
    state.inventory.append(item)
    return True, f"Added {item.get('name', 'item')} to your pack."


def roll_loot(campaign_id: str, enemy_name: str) -> Tuple[int, Optional[str]]:
    if not enemy_name:
        return 0, None
    loot = get_mob_profile(campaign_id, enemy_name).loot or {}
    gold_expr = loot.get("gold")
    gold_amount = 0
    if gold_expr:
        gold_amount, _ = roll_dice(str(gold_expr))
    items = list(loot.get("items") or [])
    if not items:
        return gold_amount, None
    idx = roll_die(len(items)) - 1
    return gold_amount, items[idx]


def equipment_ac_bonus(state: GameState) -> int:
    bonus = 0
    for item in state.equipment.values():
        if not isinstance(item, dict):
            continue
        effect = item.get("effect") or {}
        if effect.get("type") == "ac":
            bonus += int(effect.get("bonus", 0))
    return bonus


def sync_player_ac(state: GameState) -> None:
    state.player.ac = state.player.base_ac + equipment_ac_bonus(state)


def find_item(
    state: GameState, query: str, kind_filter: Optional[str] = None
) -> Tuple[Optional[dict], Optional[str]]:
    query = query.strip().lower()
    if not query:
        return None, "Use what?"
    matches = []
    for item in state.inventory:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).lower()
        item_id = str(item.get("id", "")).lower()
        kind = str(item.get("kind", "")).lower()
        if kind_filter and kind != kind_filter:
            continue
        if query in {name, item_id} or query in name:
            matches.append(item)
        elif kind == "potion" and query in {"potion", "healing", "heal"}:
            matches.append(item)
        elif kind == "armor" and query in {"armor", "armour"}:
            matches.append(item)
    if not matches:
        return None, "You don't have that."
    if len(matches) > 1:
        names = ", ".join(str(item.get("name", "Unknown")) for item in matches)
        return None, f"Be more specific or use an item number: {names}"
    return matches[0], None


def use_item(state: GameState, query: str, target: Optional[str] = None) -> Tuple[bool, str]:
    item, error = find_item(state, query, kind_filter="potion")
    if error:
        return False, error
    if not item:
        return False, "You don't have that."
    kind = str(item.get("kind", "")).lower()
    if kind != "potion":
        return False, f"{item.get('name', 'That item')} can't be used right now."
    effect = item.get("effect") or {}
    if effect.get("type") != "heal":
        return False, f"{item.get('name', 'That potion')} has no usable effect yet."

    target_key = (target or "").strip().lower()
    if target_key in {"mara", "companion", "her"}:
        companion = state.companion
        target_label = companion.name
        current_hp = companion.hp
        max_hp = companion.max_hp
        heal_target = "companion"
    elif target_key in {"me", "self", "player", "you"}:
        target_label = state.player.name
        current_hp = state.player.hp
        max_hp = state.player.max_hp
        heal_target = "player"
    else:
        player_ratio = state.player.hp / max(1, state.player.max_hp)
        companion_ratio = (
            state.companion.hp / max(1, state.companion.max_hp)
            if state.companion.hp > 0
            else 1.0
        )
        if state.companion.hp > 0 and companion_ratio < player_ratio:
            target_label = state.companion.name
            current_hp = state.companion.hp
            max_hp = state.companion.max_hp
            heal_target = "companion"
        else:
            target_label = state.player.name
            current_hp = state.player.hp
            max_hp = state.player.max_hp
            heal_target = "player"

    amount, detail = roll_dice(str(effect.get("dice", "1d6")))
    new_hp = min(max_hp, current_hp + amount)
    healed = new_hp - current_hp
    if heal_target == "player":
        state.player.hp = new_hp
    else:
        state.companion.hp = new_hp

    state.inventory.remove(item)
    return True, f"You use {item.get('name', 'a potion')} on {target_label}, healing {healed} ({detail})."


def equip_item(state: GameState, query: str) -> Tuple[bool, str]:
    query = query.strip()
    if query.isdigit():
        idx = int(query) - 1
        if idx < 0 or idx >= len(state.inventory):
            return False, "That item number does not exist."
        item = state.inventory[idx]
        if not isinstance(item, dict) or str(item.get("kind", "")).lower() != "armor":
            return False, "That item is not armor."
        error = None
    else:
        item, error = find_item(state, query, kind_filter="armor")
    if error:
        return False, error
    if not item:
        return False, "You don't have that."
    slot = str(item.get("slot", "")).lower()
    if slot not in state.equipment:
        return False, "That armor can't be equipped."
    current = state.equipment.get(slot)
    if current:
        if not can_add_item(state, current):
            return False, "Inventory is full; unequip something first."
        state.inventory.append(current)
    state.equipment[slot] = item
    state.inventory.remove(item)
    sync_player_ac(state)
    return True, f"Equipped {item.get('name', 'armor')} to {slot}."


def unequip_item(state: GameState, slot: str) -> Tuple[bool, str]:
    slot_key = slot.strip().lower()
    if slot_key not in state.equipment:
        return False, "Unknown equipment slot."
    current = state.equipment.get(slot_key)
    if not current:
        return False, "That slot is already empty."
    if not can_add_item(state, current):
        return False, "Inventory is full."
    state.inventory.append(current)
    state.equipment[slot_key] = None
    sync_player_ac(state)
    return True, f"Removed {current.get('name', 'armor')} from {slot_key}."
