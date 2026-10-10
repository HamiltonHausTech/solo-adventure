"""Campaign-configured noncombat challenges with multiple viable approaches."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from copy import deepcopy

from ..content import get_room
from ..state import GameState
from .dice import check


def _flag(state: GameState) -> str:
    return f"challenge_resolved:{state.room_id}"


def active_challenge(state: GameState) -> Optional[Dict[str, Any]]:
    room = get_room(state.campaign_id, state.room_id)
    config = room.challenge_config
    if not config or state.game_over or state.flags.get(_flag(state)) or (config.get("completion") and state.flags.get("loot_taken")):
        return None
    options = []
    for raw in config.get("options", []):
        option = deepcopy(raw)
        requirement = option.get("requires") or {}
        available = True
        reason = None
        if requirement.get("class") and state.player.cls != requirement["class"]:
            available, reason = False, f"Requires {requirement['class']}"
        companions = [c for c in state.companions if not requirement.get("companion") or c.name == requirement["companion"]]
        if requirement.get("companion_alive"):
            companions = [c for c in companions if c.hp > 0]
        if requirement.get("trust"):
            companions = [c for c in companions if c.trust >= int(requirement["trust"])]
        if any(requirement.get(k) for k in ("companion", "companion_alive", "trust")) and not companions:
            available, reason = False, f"Requires living {requirement.get('companion', 'companion')} with trust {requirement.get('trust', 0)}"
        if requirement.get("flags") and not all(state.flags.get(flag) for flag in requirement["flags"]):
            available, reason = False, str(requirement.get("flags_reason", "Requires prior information."))
        if requirement.get("stat"):
            stat_req = requirement["stat"]
            stat_ok = state.player.stats.get(stat_req["name"], 0) >= int(stat_req["minimum"])
            ability_ok = requirement.get("ability") in state.player.chosen_upgrades if requirement.get("ability") else False
            if not (stat_ok or ability_ok):
                available, reason = False, f"Requires {stat_req['name']} {stat_req['minimum']} or {requirement.get('ability', 'a developed ability')}"
        elif requirement.get("ability") and requirement["ability"] not in state.player.chosen_upgrades:
            available, reason = False, f"Requires {requirement['ability']}"
        if requirement.get("spell_revealed") and not state.flags.get(f"detect_magic:{state.room_id}"):
            available, reason = False, "Cast Detect Magic here to reveal this approach"
        option["available"] = available
        option["reason"] = reason
        options.append(option)
    return {
        "title": config.get("title", "Challenge"),
        "prompt": config.get("prompt", room.description),
        "required": bool(config.get("required", True)),
        "options": options,
    }


def challenge_blocks_movement(state: GameState) -> bool:
    challenge = active_challenge(state)
    return bool(challenge and challenge["required"])


def resolve_challenge(state: GameState, option_id: str) -> Tuple[bool, str]:
    challenge = active_challenge(state)
    if not challenge:
        return False, "There is no unresolved challenge here."
    option = next((item for item in challenge["options"] if item.get("id") == option_id), None)
    if not option:
        return False, "That approach is not available."
    if not option.get("available"):
        return False, str(option.get("reason") or "That approach is unavailable.")

    # Automatic approaches make no check and must preserve the next-roll bonus.
    guidance = 2 if not option.get("automatic") and state.flags.pop("guidance_active", False) else 0
    stat = str(option.get("stat", "INT"))
    bonus = state.player.stats.get(stat, 0) + int(option.get("bonus", 0)) + guidance
    if option.get("automatic"):
        success, roll, total = True, 0, bonus
    else:
        success, roll, total = check(bonus, int(option.get("dc", 12)))

    outcome = option.get("success" if success else "failure", {})
    for key, value in dict(outcome.get("flags", {})).items():
        state.flags[str(key)] = value
    damage = int(outcome.get("damage", 0))
    if damage:
        state.player.hp = max(1, state.player.hp - damage)
    state.flags[_flag(state)] = True

    message = str(outcome.get("message", "You overcome the challenge." if success else "The attempt goes poorly, but another way opens."))
    config = get_room(state.campaign_id, state.room_id).challenge_config or {}
    if config.get("completion"):
        from ..content import item_from_id
        from .inventory import add_item_to_inventory
        room = get_room(state.campaign_id, state.room_id)
        if room.loot:
            add_item_to_inventory(state, item_from_id(state.campaign_id, room.loot))
        state.flags["loot_taken"] = True
        state.flags["ending_outcome"] = str(outcome.get("ending", "restored"))
        state.flags["ending_explanation"] = message
        state.game_over = True
    if option.get("automatic"):
        return True, message
    guidance_text = " Guidance lends you clarity." if guidance else ""
    return True, f"{message} (roll {roll} -> {total} vs DC {option.get('dc', 12)}).{guidance_text}"
