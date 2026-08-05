"""Inventory, equipment, items, and loot."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..content import get_campaign, get_mob_profile, item_from_id
from ..state import GameState

from .dice import roll_die, roll_dice


STACK_LIMIT = 10

SHOP_ITEMS: Dict[str, Dict[str, object]] = {
    "traveler_blade": {
        "id": "traveler_blade", "name": "Traveler's Blade", "kind": "weapon",
        "slot": "weapon", "tier": 1, "buy_value": 24, "sell_value": 12,
        "description": "A reliable balanced blade.",
        "effect": {"type": "weapon", "damage": "1d8", "attack_bonus": 0},
    },
    "duelist_knife": {
        "id": "duelist_knife", "name": "Duelist's Knife", "kind": "weapon",
        "slot": "weapon", "tier": 1, "buy_value": 28, "sell_value": 14,
        "description": "A quick weapon made for precise strikes.",
        "effect": {"type": "weapon", "damage": "1d6+1", "attack_bonus": 1},
    },
    "reinforced_cap": {
        "id": "reinforced_cap", "name": "Reinforced Cap", "kind": "armor",
        "slot": "head", "tier": 1, "buy_value": 20, "sell_value": 10,
        "description": "Layered leather and iron protect the head.",
        "effect": {"type": "ac", "bonus": 1},
    },
    "roadwarden_vest": {
        "id": "roadwarden_vest", "name": "Roadwarden Vest", "kind": "armor",
        "slot": "chest", "tier": 1, "buy_value": 36, "sell_value": 18,
        "description": "A sturdy vest suited to long expeditions.",
        "effect": {"type": "ac", "bonus": 2},
    },
    "scout_gloves": {
        "id": "scout_gloves", "name": "Scout Gloves", "kind": "armor",
        "slot": "hands", "tier": 1, "buy_value": 22, "sell_value": 11,
        "description": "Supple gloves that preserve a quick grip.",
        "effect": {"type": "ac", "bonus": 0, "attack_bonus": 1},
    },
    "reinforced_gauntlets": {
        "id": "reinforced_gauntlets", "name": "Reinforced Gauntlets", "kind": "armor",
        "slot": "hands", "tier": 1, "buy_value": 24, "sell_value": 12,
        "description": "Heavy protection at the cost of finesse.",
        "effect": {"type": "ac", "bonus": 1, "attack_bonus": 0},
    },
    "trail_leggings": {
        "id": "trail_leggings", "name": "Trail Leggings", "kind": "armor",
        "slot": "legs", "tier": 1, "buy_value": 24, "sell_value": 12,
        "description": "Layered road leathers offering reliable protection.",
        "effect": {"type": "ac", "bonus": 1, "attack_bonus": 0},
    },
    "duelist_leggings": {
        "id": "duelist_leggings", "name": "Duelist Leggings", "kind": "armor",
        "slot": "legs", "tier": 1, "buy_value": 26, "sell_value": 13,
        "description": "Flexible tailoring designed for aggressive footwork.",
        "effect": {"type": "ac", "bonus": 0, "attack_bonus": 1},
    },
}


def item_counts_toward_limit(item: Dict[str, object]) -> bool:
    return bool(item.get("counts_toward_limit", True))


def item_quantity(item: Dict[str, object]) -> int:
    return max(1, int(item.get("quantity", 1)))


def normalize_inventory(state: GameState) -> None:
    """Merge legacy duplicate stackable entries into quantity-based stacks."""
    normalized: List[Dict[str, object]] = []
    stack_by_id: Dict[str, Dict[str, object]] = {}
    for raw in state.inventory:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id", "")).lower()
        if bool(raw.get("stackable", False)) and item_id:
            item = dict(raw)
            quantity = item_quantity(item)
            item["quantity"] = quantity
            existing = stack_by_id.get(item_id)
            if existing is not None:
                existing["quantity"] = item_quantity(existing) + quantity
                continue
            stack_by_id[item_id] = item
            normalized.append(item)
        else:
            normalized.append(raw)
    state.inventory = normalized


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
    normalize_inventory(state)
    if bool(item.get("stackable", False)):
        item_id = str(item.get("id", "")).lower()
        existing = next(
            (entry for entry in state.inventory if str(entry.get("id", "")).lower() == item_id),
            None,
        )
        if existing is not None:
            combined = item_quantity(existing) + item_quantity(item)
            stack_limit = max(1, int(item.get("stack_limit", STACK_LIMIT)))
            if combined > stack_limit:
                return False, f"That stack can hold at most {stack_limit}."
            existing["quantity"] = combined
            return True, f"Added {item.get('name', 'item')} to its stack."
    if not can_add_item(state, item):
        return False, "Inventory is full."
    added = dict(item)
    added["quantity"] = item_quantity(added)
    state.inventory.append(added)
    return True, f"Added {item.get('name', 'item')} to your pack."


def roll_loot(
    campaign_id: str,
    enemy_name: str,
    player_class: str = "",
    owned_item_ids: Optional[set[str]] = None,
    repeat_run: bool = False,
) -> Tuple[int, Optional[str]]:
    if not enemy_name:
        return 0, None
    loot = get_mob_profile(campaign_id, enemy_name).loot or {}
    gold_expr = loot.get("gold")
    gold_amount = 0
    if gold_expr:
        gold_amount, _ = roll_dice(str(gold_expr))
    campaign = get_campaign(campaign_id)
    owned = owned_item_ids or set()
    items = []
    for item_id in list(loot.get("items") or []):
        item = campaign.items.get(str(item_id), {})
        if int(item.get("tier", 1)) > campaign.max_item_tier:
            continue
        if bool(item.get("unique", False)) and str(item_id) in owned:
            continue
        items.append(str(item_id))
        affinities = {str(value) for value in item.get("class_affinity", [])}
        if player_class and player_class in affinities:
            items.extend([str(item_id), str(item_id)])
    if repeat_run:
        gold_amount = int(gold_amount * campaign.repeat_reward_multiplier)
    if not items:
        return gold_amount, None
    item_chance = int(loot.get("item_chance", 100))
    if repeat_run:
        item_chance = int(item_chance * campaign.repeat_reward_multiplier)
    item_chance = max(0, min(100, item_chance))
    if item_chance < 100 and roll_die(100) > item_chance:
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
    normalize_inventory(state)
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
        # A stack of identical consumables is one unambiguous choice.
        match_ids = {str(item.get("id", "")).lower() for item in matches}
        if len(match_ids) == 1:
            return matches[0], None
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
    companion_tokens = {
        "companion",
        "her",
        "him",
        state.companion.name.lower(),
    }
    if target_key in companion_tokens:
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
        companion_ratio = state.companion.hp / max(1, state.companion.max_hp)
        if companion_ratio < player_ratio:
            target_label = state.companion.name
            current_hp = state.companion.hp
            max_hp = state.companion.max_hp
            heal_target = "companion"
        else:
            target_label = state.player.name
            current_hp = state.player.hp
            max_hp = state.player.max_hp
            heal_target = "player"

    if current_hp >= max_hp:
        return False, f"{target_label} is already at full health."

    amount, detail = roll_dice(str(effect.get("dice", "1d6")))
    new_hp = min(max_hp, current_hp + amount)
    healed = new_hp - current_hp
    if heal_target == "player":
        state.player.hp = new_hp
    else:
        state.companion.hp = new_hp

    quantity = item_quantity(item)
    if quantity > 1:
        item["quantity"] = quantity - 1
    else:
        state.inventory.remove(item)
    return True, f"You use {item.get('name', 'a potion')} on {target_label}, healing {healed} ({detail})."


def drop_item(state: GameState, query: str) -> Tuple[bool, str]:
    """Discard one carried item. Quest items are protected from accidental loss."""
    item, error = find_item(state, query)
    if error:
        return False, error
    if not item:
        return False, "You don't have that."
    if str(item.get("kind", "")).lower() == "quest":
        return False, "Quest items cannot be dropped."
    quantity = item_quantity(item)
    if quantity > 1:
        item["quantity"] = quantity - 1
        return True, f"You drop one {item.get('name', 'item')}. {quantity - 1} remain."
    state.inventory.remove(item)
    return True, f"You drop {item.get('name', 'the item')}."


def item_sell_value(item: Dict[str, object]) -> int:
    explicit = int(item.get("sell_value", 0))
    if explicit > 0:
        return explicit
    if str(item.get("kind", "")).lower() not in {"armor", "weapon"}:
        return 0
    effect = item.get("effect") if isinstance(item.get("effect"), dict) else {}
    return 4 + max(0, int(effect.get("bonus", 0))) * 4


def buy_healing_potions(state: GameState, quantity: int) -> Tuple[bool, str]:
    quantity = int(quantity)
    if quantity not in {1, 3}:
        return False, "Potions may be purchased one or three at a time."
    unit_price = 8
    total = unit_price * quantity
    if state.player.gold < total:
        return False, f"You need {total} gold for that purchase."
    item = item_from_id(state.campaign_id, "healing_potion")
    item["quantity"] = quantity
    added, message = add_item_to_inventory(state, item)
    if not added:
        return False, message
    state.player.gold -= total
    return True, f"You buy {quantity} healing potion{'s' if quantity != 1 else ''} for {total} gold."


def shop_catalog() -> List[Dict[str, object]]:
    return [dict(item) for item in SHOP_ITEMS.values()]


def buy_shop_item(state: GameState, item_id: str) -> Tuple[bool, str]:
    item = SHOP_ITEMS.get(item_id.strip().lower())
    if not item:
        return False, "That item is not sold here."
    price = int(item.get("buy_value", 0))
    if state.player.gold < price:
        return False, f"You need {price} gold for that purchase."
    added, message = add_item_to_inventory(state, dict(item))
    if not added:
        return False, message
    state.player.gold -= price
    return True, f"You buy {item.get('name', 'the item')} for {price} gold."


def sell_item(state: GameState, query: str) -> Tuple[bool, str]:
    item, error = find_item(state, query)
    if error:
        return False, error
    if not item:
        return False, "You don't have that."
    value = item_sell_value(item)
    if value <= 0:
        return False, "That item cannot be sold here."
    quantity = item_quantity(item)
    if quantity > 1:
        item["quantity"] = quantity - 1
    else:
        state.inventory.remove(item)
    state.player.gold += value
    return True, f"You sell {item.get('name', 'the item')} for {value} gold."


def equip_item(state: GameState, query: str) -> Tuple[bool, str]:
    query = query.strip()
    if query.isdigit():
        idx = int(query) - 1
        if idx < 0 or idx >= len(state.inventory):
            return False, "That item number does not exist."
        item = state.inventory[idx]
        if not isinstance(item, dict) or str(item.get("kind", "")).lower() not in {"armor", "weapon"}:
            return False, "That item cannot be equipped."
        error = None
    else:
        item, error = find_item(state, query)
    if error:
        return False, error
    if not item:
        return False, "You don't have that."
    if str(item.get("kind", "")).lower() not in {"armor", "weapon"}:
        return False, "That item cannot be equipped."
    slot = str(item.get("slot", "")).lower()
    if slot not in state.equipment:
        return False, "That item can't be equipped."
    current = state.equipment.get(slot)
    state.inventory.remove(item)
    if current:
        state.inventory.append(current)
    state.equipment[slot] = item
    sync_player_ac(state)
    return True, f"Equipped {item.get('name', 'item')} to {slot}."


def equipment_attack_bonus(state: GameState) -> int:
    bonus = 0
    for item in state.equipment.values():
        raw_effect = item.get("effect") if isinstance(item, dict) else None
        effect = raw_effect if isinstance(raw_effect, dict) else {}
        bonus += int(effect.get("attack_bonus", 0))
    return bonus


def equipped_damage(state: GameState) -> str:
    weapon = state.equipment.get("weapon")
    raw_effect = weapon.get("effect") if isinstance(weapon, dict) else None
    effect = raw_effect if isinstance(raw_effect, dict) else {}
    if effect.get("type") == "weapon" and effect.get("damage"):
        return str(effect["damage"])
    return state.player.damage


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
