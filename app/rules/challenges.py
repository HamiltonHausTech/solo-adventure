"""Campaign-configured noncombat challenges with multiple viable approaches."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..content import get_room
from ..state import GameState
from .dice import check


def _flag(state: GameState) -> str:
    return f"challenge_resolved:{state.room_id}"


def active_challenge(state: GameState) -> Optional[Dict[str, Any]]:
    room = get_room(state.campaign_id, state.room_id)
    config = room.challenge_config
    if not config or state.flags.get(_flag(state)):
        return None
    options = []
    for raw in config.get("options", []):
        option = dict(raw)
        requirement = option.get("requires") or {}
        available = True
        reason = None
        if requirement.get("class") and state.player.cls != requirement["class"]:
            available, reason = False, f"Requires {requirement['class']}"
        if requirement.get("companion") and state.companion.name != requirement["companion"]:
            available, reason = False, f"Requires {requirement['companion']}"
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

    guidance = 2 if state.flags.pop("guidance_active", False) else 0
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
    if option.get("automatic"):
        return True, message
    guidance_text = " Guidance lends you clarity." if guidance else ""
    return True, f"{message} (roll {roll} -> {total} vs DC {option.get('dc', 12)}).{guidance_text}"
