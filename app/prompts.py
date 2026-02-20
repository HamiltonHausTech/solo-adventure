from __future__ import annotations

from typing import List

from .content import get_room
from .state import GameState
from .util import inventory_names


GM_SYSTEM_PROMPT = (
    "You are the GM for a tiny solo fantasy adventure. Narrate outcomes that the rules engine "
    "already resolved. Do NOT invent new outcomes, rolls, damage, or state changes. Ask the player "
    "what they do next with a short question. Keep responses under 120 words."
)

COMPANION_SYSTEM_PROMPT = (
    "You are Mara, a cautious archer companion. Give a short, practical suggestion (1 sentence) "
    "based on the current situation. Do NOT narrate outcomes or change the game state. "
    "Only suggest actions that are actually available. "
    "Vary your suggestions: movement, exploration (talk/search), combat actions, or rest—whatever fits best. "
    "Only suggest healing or potions when someone is wounded (HP below max) and it would help. "
    "When everyone is at full HP, never suggest healing."
)


def format_state_for_gm(state: GameState) -> str:
    room = get_room(state.campaign_id, state.room_id)
    parts: List[str] = [
        f"Room: {room.name}",
        f"Room kind: {room.kind}",
        f"Player: {state.player.name} ({state.player.race} {state.player.cls}) "
        f"Level {state.player.level} HP {state.player.hp}/{state.player.max_hp}",
        f"Stats: STR {state.player.stats.get('STR', 0)} DEX {state.player.stats.get('DEX', 0)} CON {state.player.stats.get('CON', 0)} INT {state.player.stats.get('INT', 0)} WIS {state.player.stats.get('WIS', 0)} CHA {state.player.stats.get('CHA', 0)}",
        f"Mana: {state.player.mana}/{state.player.max_mana}",
        f"Gold: {state.player.gold}",
        f"Companion: {state.companion.name} HP {state.companion.hp}/{state.companion.max_hp}",
        f"Inventory: {', '.join(inventory_names(state.inventory)) if state.inventory else '(empty)'}",
        f"In combat: {state.in_combat}",
    ]
    if state.enemies:
        enemy_lines = [
            f"{enemy.name} HP {enemy.hp}/{enemy.max_hp}" for enemy in state.enemies
        ]
        parts.append("Enemies: " + " | ".join(enemy_lines))
    if state.last_event:
        parts.append(f"Last event: {state.last_event}")
    if state.flags:
        parts.append("Flags: " + ", ".join(f"{k}={v}" for k, v in state.flags.items()))
    return "\n".join(parts)


def format_state_for_companion(state: GameState) -> str:
    room = get_room(state.campaign_id, state.room_id)
    parts = [
        f"Room: {room.name} ({room.kind})",
        f"Player Level {state.player.level} HP {state.player.hp}/{state.player.max_hp}",
        f"Mara HP {state.companion.hp}/{state.companion.max_hp}",
        f"Mana: {state.player.mana}/{state.player.max_mana}",
        f"Gold: {state.player.gold}",
        f"Inventory: {', '.join(inventory_names(state.inventory)) if state.inventory else '(empty)'}",
        f"In combat: {state.in_combat}",
    ]
    if state.enemies:
        enemy_lines = [
            f"{enemy.name} HP {enemy.hp}/{enemy.max_hp}" for enemy in state.enemies
        ]
        parts.append("Enemies: " + " | ".join(enemy_lines))
    if state.last_event:
        parts.append(f"Last event: {state.last_event}")
    return "\n".join(parts)
