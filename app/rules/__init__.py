"""Modular rules engine: dice, combat, exploration, inventory, companions."""

from __future__ import annotations

from .combat import (
    apply_companion_action,
    apply_enemy_action,
    apply_player_action,
    clear_round_buffs,
    end_combat_if_needed,
)
from .companions import create_companion, create_campaign_companions, create_companion_from_profile, scale_companion_for_level
from .dice import check, roll_die, roll_dice
from .enemies import create_enemy, create_enemies
from .exploration import apply_exploration_action, move_player, start_room
from .inventory import (
    add_item_to_inventory,
    buy_healing_potions,
    buy_shop_item,
    can_add_item,
    drop_item,
    equip_item,
    equipment_ac_bonus,
    equipment_attack_bonus,
    equipped_damage,
    find_item,
    inventory_used,
    item_quantity,
    item_sell_value,
    item_counts_toward_limit,
    normalize_inventory,
    roll_loot,
    sell_item,
    shop_catalog,
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
from .progression import apply_progression_choices, class_upgrade_options

__all__ = [
    "add_item_to_inventory",
    "buy_healing_potions",
    "buy_shop_item",
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
    "scale_companion_for_level",
    "clear_round_buffs",
    "create_enemies",
    "create_enemy",
    "create_player",
    "drop_item",
    "end_combat_if_needed",
    "ensure_caster_mana",
    "ensure_wizard_mana",
    "equip_item",
    "equipment_ac_bonus",
    "equipment_attack_bonus",
    "equipped_damage",
    "grant_xp",
    "apply_progression_choices",
    "class_upgrade_options",
    "find_item",
    "inventory_used",
    "item_quantity",
    "item_sell_value",
    "is_caster",
    "is_melee",
    "item_counts_toward_limit",
    "normalize_inventory",
    "move_player",
    "regen_companion_mana",
    "regen_mana",
    "reset_rest_streak",
    "roll_die",
    "roll_dice",
    "roll_loot",
    "sell_item",
    "shop_catalog",
    "start_room",
    "sync_player_ac",
    "unequip_item",
    "use_item",
]
