"""Exploration: room entry, movement, and room-type actions."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..content import Room, get_exits, get_room, item_from_id
from ..state import GameState

from .enemies import create_enemies
from .flags import get_flag_dict, get_flag_list, next_corpse_id
from .inventory import add_item_to_inventory, can_add_item, roll_loot
from .dice import check, roll_dice


def _guidance_bonus(state: GameState) -> int:
    if not state.flags.pop("guidance_active", False):
        return 0
    return 2


def start_room(state: GameState, room: Room) -> str:
    if room.room_id not in state.visited:
        state.visited.append(room.room_id)
    defeated_rooms = get_flag_list(state, "defeated_rooms")
    if room.kind == "combat" and room.room_id not in defeated_rooms:
        if not state.enemies:
            state.enemies = create_enemies(state.campaign_id, room.enemy_name or "Watchtower Bandit")
        if state.enemies:
            state.flags["active_enemy_name"] = state.enemies[0].name
        state.in_combat = True
        enemy_name = room.enemy_name or "enemies"
        return f"A fight breaks out with {enemy_name}."
    return room.description


def _handle_social_room(state: GameState, room: Room, action: str) -> Optional[str]:
    """Handle social room actions using room.social_config or defaults."""
    cfg = room.social_config or {}
    stat_key = str(cfg.get("stat", "INT")).upper()
    dc = int(cfg.get("dc", 13))
    success_flag = cfg.get("success_flag")
    success_msg = cfg.get("success_msg")
    fail_msg = cfg.get("fail_msg")
    done_flag = cfg.get("done_flag", "social_done")

    if action in {"talk", "speak", "parley", "approach"}:
        guidance = _guidance_bonus(state)
        stat_bonus = state.player.stats.get(stat_key, 0) + guidance
        success, roll, total = check(stat_bonus, dc)
        state.flags[str(done_flag)] = True
        if success and success_flag:
            state.flags[str(success_flag)] = True
        if success and success_msg:
            return ("Guidance steadies you. " if guidance else "") + str(success_msg).format(
                roll=roll, total=total, stat=stat_key, bonus=stat_bonus, dc=dc
            )
        if not success and fail_msg:
            return ("Guidance steadies you. " if guidance else "") + str(fail_msg).format(
                roll=roll, total=total, stat=stat_key, bonus=stat_bonus, dc=dc
            )
        # Fallback if no config messages
        if success:
            return f"You succeed (roll {roll} -> {total})."
        return f"You fail (roll {roll} -> {total})."
    if action in {"leave", "move", "continue", "go"}:
        return "You prepare to move on."
    return None


def _handle_loot_room(state: GameState, room: Room, action: str) -> Optional[str]:
    """Handle loot room (chest/container) actions using room.loot_config or defaults."""
    cfg = room.loot_config or {}
    stat_key = str(cfg.get("stat", "DEX")).upper()
    dc = int(cfg.get("dc", 13))
    success_msg = cfg.get("success_msg")
    fail_msg = cfg.get("fail_msg")
    win_item_id = cfg.get("win_item_id") or room.loot
    game_over = cfg.get("game_over", True)
    taken_flag = "loot_taken"
    failed_flag = "loot_failed"

    if action in {"search", "open", "loot", "inspect"}:
        if state.flags.get(taken_flag):
            return "The chest is already open and empty."
        guidance = _guidance_bonus(state)
        stat_bonus = state.player.stats.get(stat_key, 0) + guidance
        success, roll, total = check(stat_bonus, dc)
        if success:
            if win_item_id:
                item = item_from_id(state.campaign_id, str(win_item_id))
                added, message = add_item_to_inventory(state, item)
                if not added:
                    return (
                        f"You force the lock (roll {roll} -> {total}) but {message.lower()} "
                        "You can rearrange your gear and try again."
                    )
            state.flags[taken_flag] = True
            if game_over:
                state.game_over = True
            if success_msg:
                return ("Guidance steadies you. " if guidance else "") + str(success_msg).format(roll=roll, total=total)
            return f"You work the lock free (roll {roll} -> {total})."
        state.flags[failed_flag] = True
        if fail_msg:
            return ("Guidance steadies you. " if guidance else "") + str(fail_msg).format(roll=roll, total=total)
        return f"Your tools slip (roll {roll} -> {total}). The lock resists for now."
    if action in {"leave", "move", "continue", "go"}:
        return "There's nowhere left to go but the chest."
    return None


def select_corpse_targets(state: GameState, query: Optional[str]) -> tuple[List[Dict], Optional[str]]:
    """Resolve persistent corpse IDs without mutating state during validation."""
    if query is not None and not isinstance(query, str):
        return [], "A target must be text."
    corpses = state.flags.get("corpses", {})
    entries = corpses.get(state.room_id, []) if isinstance(corpses, dict) else []
    if not isinstance(entries, list) or not entries:
        return [], "Nothing here to loot."
    unlooted = [entry for entry in entries if not entry.get("looted")]
    if not unlooted:
        return [], "You already searched the corpses."
    token = (query or "").strip().lower()
    if token == "all":
        return unlooted, None
    if not token:
        if len(unlooted) > 1:
            return [], "Multiple corpses here. Use 'loot <number>' or 'loot all'."
        return unlooted, None
    if token.isascii() and token.isdecimal():
        matches = [entry for entry in unlooted if str(entry.get("id")) == token.lstrip("0")]
    else:
        matches = [entry for entry in unlooted if token in str(entry.get("name", "")).lower()]
    if not matches:
        return [], "No such unlooted corpse."
    if len(matches) > 1:
        return [], "Be more specific."
    return matches, None


def _handle_combat_room_post_fight(
    state: GameState, room: Room, action: str
) -> Optional[str]:
    """Handle post-combat actions: looting corpses, searching."""
    defeated_rooms = state.flags.get("defeated_rooms", [])
    if room.room_id not in defeated_rooms:
        return None

    if action.startswith("loot"):
        unlooted, error = select_corpse_targets(state, action.removeprefix("loot").strip())
        if error:
            return error

        total_gold = 0
        item_texts: List[str] = []
        for entry in unlooted:
            enemy_name = str(entry.get("name", ""))
            owned_item_ids = {
                str(item.get("id", ""))
                for item in state.inventory
                if isinstance(item, dict)
            }
            owned_item_ids.update(
                str(item.get("id", ""))
                for item in state.equipment.values()
                if isinstance(item, dict)
            )
            owned_item_ids.update(state.player.discovered_unique_items)
            gold, item_id = roll_loot(
                state.campaign_id,
                enemy_name,
                player_class=state.player.cls,
                owned_item_ids=owned_item_ids,
                repeat_run=state.player.campaign_completions.get(state.campaign_id, 0) > 0,
            )
            total_gold += gold
            if item_id:
                item = item_from_id(state.campaign_id, item_id)
                added, message = add_item_to_inventory(state, item)
                if added:
                    item_texts.append(f"You find {item.get('name', 'gear')}.")
                    if bool(item.get("unique", False)) and item_id not in state.player.discovered_unique_items:
                        state.player.discovered_unique_items.append(item_id)
                else:
                    item_texts.append(
                        f"You spot {item.get('name', 'gear')}, but {message.lower()}"
                    )
            entry["looted"] = True
        state.player.gold += total_gold
        if total_gold == 0 and not item_texts:
            return "You search the corpse but find nothing."
        item_text = " " + " ".join(item_texts) if item_texts else ""
        return f"You loot the corpse and gain {total_gold} gold.{item_text}"

    if action in {"search", "inspect"}:
        return f"You search the {room.name.lower()}. Most supplies are rotted or picked clean."
    if action in {"leave", "move", "continue", "go"}:
        return "The room falls silent after the fight."
    return "The room falls silent after the fight."


def apply_exploration_action(state: GameState, action: str) -> str:
    if not isinstance(action, str):
        return "An action must be text."
    room = get_room(state.campaign_id, state.room_id)
    action = action.strip().lower()

    if room.kind == "social":
        result = _handle_social_room(state, room, action)
        if result is not None:
            return result
        npc = room.npc or "Someone"
        return f"{npc} waits, watching for your move."

    if room.kind == "loot":
        result = _handle_loot_room(state, room, action)
        if result is not None:
            return result
        return f"The {room.name.lower()} is quiet. The prize awaits."

    if room.kind == "combat":
        result = _handle_combat_room_post_fight(state, room, action)
        if result is not None:
            return result
        return "The enemy blocks your way, ready to strike."

    if room.kind == "passage":
        cfg = getattr(room, "room_loot_config", None) or {}
        if cfg and action in {"search", "loot", "inspect", "look"}:
            taken_key = f"room_loot_taken_{room.room_id}"
            if state.flags.get(taken_key):
                return "You've already searched this area."
            gold_expr = cfg.get("gold")
            if gold_expr:
                gold_amount, _ = roll_dice(str(gold_expr))
                state.player.gold += gold_amount
                state.flags[taken_key] = True
                return f"You find a discarded pouch with {gold_amount} gold."
        if action in {"search", "inspect", "look"}:
            return room.description
        return "You press onward."

    return "The ruins are quiet."


def move_player(state: GameState, destination: str) -> Tuple[bool, str]:
    exits = get_exits(state.campaign_id, state.room_id)
    target = exits.get(destination)
    if not target:
        for key, value in exits.items():
            if destination == value:
                target = value
                break
    if not target:
        if exits:
            options = ", ".join(sorted(set(exits.values())))
            return False, f"Can't go that way. Options: {options}."
        return False, "There's nowhere to go from here."
    state.room_id = target
    return True, start_room(state, get_room(state.campaign_id, state.room_id))
