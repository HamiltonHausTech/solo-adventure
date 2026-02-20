"""Modular rules engine: dice, combat, exploration, inventory, companions."""

from __future__ import annotations

from .combat import (
    apply_companion_action,
    apply_enemy_action,
    apply_player_action,
    end_combat_if_needed,
)
from .companions import create_companion, create_campaign_companions, create_companion_from_profile
from .dice import check, roll_die, roll_dice
from .enemies import create_enemy, create_enemies
from .exploration import apply_exploration_action, move_player, start_room
from .inventory import (
    add_item_to_inventory,
    can_add_item,
    equip_item,
    equipment_ac_bonus,
    find_item,
    inventory_used,
    item_counts_toward_limit,
    roll_loot,
    sync_player_ac,
    unequip_item,
    use_item,
)
from .player import (
    create_player,
    ensure_caster_mana,
    ensure_wizard_mana,
    is_caster,
    is_melee,
)
from .rest import apply_rest, regen_companion_mana, regen_mana, reset_rest_streak
from .experience import grant_xp

__all__ = [
    "add_item_to_inventory",
    "apply_companion_action",
    "apply_enemy_action",
    "apply_exploration_action",
    "apply_player_action",
    "apply_rest",
    "can_add_item",
    "check",
    "create_campaign_companions",
    "create_companion",
    "create_companion_from_profile",
    "create_enemies",
    "create_enemy",
    "create_player",
    "end_combat_if_needed",
    "ensure_caster_mana",
    "ensure_wizard_mana",
    "equip_item",
    "equipment_ac_bonus",
    "grant_xp",
    "find_item",
    "inventory_used",
    "is_caster",
    "is_melee",
    "item_counts_toward_limit",
    "move_player",
    "regen_companion_mana",
    "regen_mana",
    "reset_rest_streak",
    "roll_die",
    "roll_dice",
    "roll_loot",
    "start_room",
    "sync_player_ac",
    "unequip_item",
    "use_item",
]
