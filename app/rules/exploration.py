"""Exploration: room entry, movement, and room-type actions."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ..content import Room, get_exits, get_room, item_from_id
from ..state import GameState

from .enemies import create_enemies
from .flags import get_flag_dict, get_flag_list, next_corpse_id
from .inventory import add_item_to_inventory, can_add_item, roll_loot
from .dice import check


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
        stat_bonus = state.player.stats.get(stat_key, 0)
        success, roll, total = check(stat_bonus, dc)
        state.flags[str(done_flag)] = True
        if success and success_flag:
            state.flags[str(success_flag)] = True
        if success and success_msg:
            return str(success_msg).format(roll=roll, total=total)
        if not success and fail_msg:
            return str(fail_msg).format(roll=roll, total=total)
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
        stat_bonus = state.player.stats.get(stat_key, 0)
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
                return str(success_msg).format(roll=roll, total=total)
            return f"You work the lock free (roll {roll} -> {total})."
        state.flags[failed_flag] = True
        if fail_msg:
            return str(fail_msg).format(roll=roll, total=total)
        return f"Your tools slip (roll {roll} -> {total}). The lock resists for now."
    if action in {"leave", "move", "continue", "go"}:
        return "There's nowhere left to go but the chest."
    return None


def _handle_combat_room_post_fight(
    state: GameState, room: Room, action: str
) -> Optional[str]:
    """Handle post-combat actions: looting corpses, searching."""
    defeated_rooms = get_flag_list(state, "defeated_rooms")
    if room.room_id not in defeated_rooms:
        return None

    if action.startswith("loot"):
        corpses = get_flag_dict(state, "corpses")
        enemy_entries = corpses.get(room.room_id)
        if not enemy_entries or not isinstance(enemy_entries, list):
            return "Nothing here to loot."
        unlooted = [entry for entry in enemy_entries if not entry.get("looted")]
        if not unlooted:
            return "You already searched the corpses."
        target = action.replace("loot", "", 1).strip()
        if target and target != "all" and not target.isdigit():
            matches = [
                entry
                for entry in unlooted
                if target in str(entry.get("name", "")).lower()
            ]
            if not matches:
                return "No such corpse."
            if len(matches) > 1:
                return "Be more specific."
            unlooted = matches
        elif target.isdigit():
            idx = int(target) - 1
            if idx < 0 or idx >= len(unlooted):
                return "That corpse does not exist."
            unlooted = [unlooted[idx]]
        elif not target and len(unlooted) > 1:
            return "Multiple corpses here. Use 'loot <number>' or 'loot all'."

        total_gold = 0
        item_texts: List[str] = []
        for entry in unlooted:
            enemy_name = str(entry.get("name", ""))
            gold, item_id = roll_loot(state.campaign_id, enemy_name)
            total_gold += gold
            if item_id:
                item = item_from_id(state.campaign_id, item_id)
                added, message = add_item_to_inventory(state, item)
                if added:
                    item_texts.append(f"You find {item.get('name', 'gear')}.")
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
    room = get_room(state.campaign_id, state.room_id)
    action = action.lower()

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
        return "Wind whistles through the spire. The chest waits."

    if room.kind == "combat":
        result = _handle_combat_room_post_fight(state, room, action)
        if result is not None:
            return result
        return "The enemy blocks your way, ready to strike."

    if room.kind == "passage":
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
