"""Small, read-only journey projection from campaign metadata and durable facts."""
from copy import deepcopy

from .content import get_campaign, get_exits, get_room


def conversation_recap(state, room):
    """Prefer recorded evidence; legacy flags identify facts, never old dice rolls."""
    recorded = state.flags.get(f"conversation:{room.room_id}")
    if recorded:
        return str(recorded)
    if room.kind != "social":
        return None
    config = room.social_config or {}
    succeeded = bool(state.flags.get(str(config.get("success_flag", ""))))
    if not succeeded and not state.flags.get(str(config.get("done_flag", "social_done"))):
        return None
    # Without a success flag, a legacy done flag cannot establish the outcome.
    outcome = "success" if succeeded else "fail" if config.get("success_flag") else None
    return str(config.get(f"{outcome}_recap") or "This conversation is exhausted; no further details were recorded.")


def location_statuses(state, room_id):
    statuses = ["Current"] if room_id == state.room_id else []
    statuses.append("Visited" if room_id in state.visited or room_id == state.room_id else "Unexplored")
    if room_id in state.flags.get("defeated_rooms", []):
        statuses.append("Cleared")
    if state.flags.get(f"searched:{room_id}") or state.flags.get(f"room_loot_taken_{room_id}"):
        statuses.append("Searched")
    if any(not entry.get("looted") for entry in state.flags.get("corpses", {}).get(room_id, [])):
        statuses.append("Unlooted remains")
    return statuses


def room_description(state):
    room = get_room(state.campaign_id, state.room_id)
    if room.room_id in state.flags.get("defeated_rooms", []) and not state.in_combat:
        remains = " Fallen enemies still carry unclaimed supplies." if "Unlooted remains" in location_statuses(state, room.room_id) else " The fallen have been searched."
        return f"{room.name} is quiet now. The enemies here have been defeated.{remains} The way onward is open."
    return room.description


def exploration_action(state, action):
    room = get_room(state.campaign_id, state.room_id)
    config = room.social_config or {}
    canonical = "search" if action == "inspect" else "loot" if action == "open" else action
    labels = {"talk": f"Talk to {room.npc}" if room.npc else "Talk", "search": f"Search {room.name}", "loot": "Loot remains" if room.kind == "combat" else f"Loot {room.name}"}
    reason = None
    if canonical == "talk":
        if room.kind != "social":
            reason = "There is no one here to question."
        elif state.flags.get(str(config.get("done_flag", "social_done"))) or state.flags.get(str(config.get("success_flag", ""))):
            reason = "This conversation is exhausted; its information is in your journal."
    elif canonical in {"search", "loot"}:
        if room.challenge_config and room.challenge_config.get("completion"):
            if state.flags.get(f"challenge_resolved:{room.room_id}") or state.flags.get("loot_taken"):
                reason = "The seal has already been restored."
            labels[canonical] = "Restore the seal"
        elif canonical == "loot" and room.kind == "combat":
            if not any(not c.get("looted") for c in state.flags.get("corpses", {}).get(room.room_id, [])):
                reason = "There are no unlooted remains here."
        elif state.flags.get(f"room_loot_taken_{room.room_id}"):
            reason = "This area has already been searched."
        elif canonical == "search" and state.flags.get(f"searched:{room.room_id}"):
            reason = "This area has already been searched."
        elif canonical == "loot" and room.kind not in {"loot", "combat"} and not room.room_loot_config:
            reason = "There is nothing here to loot."
        elif room.kind == "loot" and state.flags.get("loot_taken"):
            reason = "The container is already empty."
    result = {"id": action, "label": labels.get(canonical, action.title()), "disabled": reason is not None, "disabled_reason": reason}
    if action == "loot":
        result["requires"] = ["target?"]
    return result


def journey_snapshot(state):
    campaign = get_campaign(state.campaign_id)
    config = campaign.journey_config
    known = set(state.visited) | {state.room_id}
    known.update(get_exits(state.campaign_id, state.room_id).values())
    locations = [{"id": rid, "name": room.name, "statuses": location_statuses(state, rid)} for rid, room in campaign.rooms.items() if rid in known]
    journal = []
    for flag, text in config.get("facts", {}).items():
        if state.flags.get(flag):
            journal.append({"id": flag, "text": text})
    for rid, room in campaign.rooms.items():
        key = f"conversation:{rid}"
        recap = conversation_recap(state, room)
        if recap:
            journal.append({"id": key, "text": recap})
    for key, text in state.flags.items():
        if key.startswith("companion_conversation:"):
            journal.append({"id": key, "text": str(text)})
    if state.flags.get("ending_explanation"):
        journal.append({"id": "ending", "text": state.flags["ending_explanation"]})
    objective = deepcopy(config.get("objectives", {}).get(state.room_id, {"title": "Explore the adventure", "description": "Follow the available exits, speak with the people you meet, and investigate your surroundings."}))
    from .rules.challenges import active_challenge
    challenge = active_challenge(state)
    if state.in_combat:
        objective = {"title": "Survive the encounter", "description": "Defeat the enemies blocking your route before moving on."}
    elif state.game_over:
        objective = {"title": "Adventure complete" if state.player.hp > 0 else "Adventure ended", "description": state.flags.get("ending_explanation", "Your journey here has ended.")}
    elif challenge and challenge["required"]:
        objective = {"title": challenge["title"], "description": f"{challenge['prompt']} Resolve this challenge before moving on."}
    elif get_room(state.campaign_id, state.room_id).kind == "social" and exploration_action(state, "talk")["disabled"]:
        objective["description"] = config.get("onward", {}).get(state.room_id, "You have heard what there is to learn here. Continue through an available exit.")
    elif "Searched" in location_statuses(state, state.room_id):
        objective["description"] = config.get("onward", {}).get(state.room_id, "This area has been searched. Continue through an available exit.")
    return {"objective": objective, "journal": journal, "locations": locations}
