from __future__ import annotations

from .llm import LLMClient
from .prompts import (
    COMPANION_SYSTEM_PROMPT,
    GM_SYSTEM_PROMPT,
    format_state_for_companion,
    format_state_for_gm,
)
from .state import GameState


def gm_narrate(state: GameState, llm: LLMClient, player_input: str, rules_result: str) -> str:
    user_prompt = (
        f"STATE\n{format_state_for_gm(state)}\n\n"
        f"PLAYER INPUT\n{player_input}\n\n"
        f"RULES RESULT\n{rules_result}\n\n"
        "Narrate the rules result and ask the player what they do next."
    )
    return llm.gm_reply(GM_SYSTEM_PROMPT, user_prompt)


def companion_suggest(state: GameState, llm: LLMClient) -> str:
    if state.in_combat:
        actions = "attack, defend, special, use, inventory"
    else:
        actions = "talk, search, loot, move, rest, use, inventory"
    player_full = state.player.hp >= state.player.max_hp
    companions_full = all(c.hp >= c.max_hp for c in state.companions) if state.companions else True
    context_note = ""
    if player_full and companions_full:
        context_note = "\nEveryone at full HP. Suggest movement, exploration, or combat—not healing.\n"
    user_prompt = (
        f"STATE\n{format_state_for_companion(state)}\n"
        f"{context_note}\n"
        f"Available actions: {actions}\n"
        "Give a brief suggestion."
    )
    return llm.companion_reply(COMPANION_SYSTEM_PROMPT, user_prompt)
