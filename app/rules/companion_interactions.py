"""Deterministic companion conversation, advice, and relationship rules."""

from __future__ import annotations

from ..content import get_room
from ..state import GameState


MARA_ROOM_LINES = {
    "courtyard": "The stones are too quiet. Someone has been keeping watch from the broken arch.",
    "cellar": "Rats don't worry me. What drives them up from deeper ground does.",
    "barracks": "Old soldiers leave patterns behind. Check the bunks before we trust the silence.",
    "spire": "Places like this remember who climbed them. Let's leave it with a better memory.",
    "crypt": "The dead deserve distance, but not fear. Keep your light ahead of you.",
    "treasure": "Take what we came for. Greed is how a victory learns to bite.",
}


def _remember(state: GameState, key: str, trust_delta: int = 0) -> bool:
    companion = state.companion
    if key in companion.memories:
        return False
    companion.memories.append(key)
    companion.memories[:] = companion.memories[-20:]
    companion.trust = max(0, min(100, companion.trust + trust_delta))
    return True


def talk_to_companion(state: GameState) -> str:
    companion = state.companion
    room = get_room(state.campaign_id, state.room_id)
    first_time = _remember(state, f"talk:{state.campaign_id}:{state.room_id}", 2)
    if companion.name == "Mara":
        line = MARA_ROOM_LINES.get(state.room_id, "I trust the road more when we take time to read it together.")
    elif companion.name == "Torvald":
        line = f"{room.name} has stood this long. Stay close and we'll outlast whatever waits here."
    elif companion.name == "Eldrin":
        line = f"There is a pattern beneath {room.name}. Give me a moment and I may understand it."
    else:
        line = "I'm with you. Let's keep moving carefully."
    if first_time:
        companion.mood = "engaged"
        return f'{companion.name}: “{line}” Trust +2.'
    return f'{companion.name}: “We have already taken the measure of this place. I have nothing to add yet.”'


def companion_advice(state: GameState) -> str:
    companion = state.companion
    if state.in_combat:
        alive = [enemy for enemy in state.enemies if enemy.hp > 0]
        if state.player.hp <= max(3, state.player.max_hp // 3):
            advice = "You're hurt. Guard yourself or use a potion; I'll draw their eye."
        elif len(alive) > 1:
            advice = "Focus the weakest target. Every enemy we drop changes the odds."
        elif alive:
            advice = f"Keep pressure on {alive[0].name}. Don't give it room to choose the fight."
        else:
            advice = "The danger has passed. Check the fallen before we move."
    else:
        room = get_room(state.campaign_id, state.room_id)
        advice = {
            "social": "Talk first. A drawn weapon answers fewer questions than people think.",
            "loot": "Inspect the lock before forcing it. Old mechanisms punish impatience.",
            "combat": "Search after the fighting. People hide useful things where they sleep.",
        }.get(room.kind, "Look for what does not belong. That usually tells us where to go next.")
    return f'{companion.name}: “{advice}”'


def set_companion_tactic(state: GameState, tactic: str) -> str:
    normalized = tactic.strip().lower()
    if normalized not in {"cautious", "balanced", "aggressive"}:
        raise ValueError("Tactic must be cautious, balanced, or aggressive.")
    state.companion.tactic = normalized
    description = {
        "cautious": "I'll cover you and protect whoever is in the most danger.",
        "balanced": "I'll finish exposed targets and keep enough distance to react.",
        "aggressive": "I'll press the strongest threat before it can settle in.",
    }[normalized]
    return f'{state.companion.name}: “{description}” Tactic set to {normalized}.'


def rest_reaction(state: GameState) -> str | None:
    if not _remember(state, f"rest:{state.campaign_id}:{state.room_id}", 1):
        return None
    state.companion.mood = "rested"
    return f'{state.companion.name}: “Good. A quiet minute now may save us an hour of bleeding later.” Trust +1.'


def post_combat_reaction(state: GameState) -> str | None:
    if not _remember(state, f"victory:{state.campaign_id}:{state.room_id}", 2):
        return None
    state.companion.mood = "encouraged"
    line = "That was too close. Next time, let me take more of the risk." if state.player.hp <= max(3, state.player.max_hp // 3) else "Clean enough. We watched each other's openings."
    return f'{state.companion.name}: “{line}” Trust +2.'
