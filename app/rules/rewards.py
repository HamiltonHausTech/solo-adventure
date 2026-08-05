"""Campaign completion rewards shared by every game interface."""

from __future__ import annotations

from typing import List

from ..content import get_campaign
from ..state import GameState
from .experience import grant_xp


def award_campaign_completion(state: GameState) -> List[str]:
    """Award one victory exactly once and return player-facing messages."""
    if not state.game_over or state.player.hp <= 0:
        return []
    if state.flags.get("completion_xp_awarded"):
        return []

    campaign = get_campaign(state.campaign_id)
    prior_completions = state.player.campaign_completions.get(state.campaign_id, 0)
    overlevel_cutoff = state.player.level >= campaign.recommended_level + 10
    amount = campaign.completion_xp
    if prior_completions:
        amount = int(amount * campaign.repeat_reward_multiplier)
    if overlevel_cutoff:
        amount = 0
    elif prior_completions and state.player.level >= campaign.recommended_level + 2:
        amount = int(amount * 0.5)

    reward_label = "Repeat clear" if prior_completions else "First clear"
    if amount > 0:
        messages = [f"Campaign complete · {reward_label}. XP +{amount}."]
        messages.extend(grant_xp(state, amount))
    elif overlevel_cutoff:
        messages = [
            f"Campaign complete · {reward_label}. Completion XP +0 because your level "
            "exceeds this campaign's recommended level by 10 or more."
        ]
    elif campaign.completion_xp <= 0:
        messages = [f"Campaign complete · {reward_label}. This campaign has no completion XP reward."]
    else:
        messages = [f"Campaign complete · {reward_label}. The adjusted completion XP rounds to 0."]

    state.player.campaign_completions[state.campaign_id] = prior_completions + 1
    state.flags["completion_xp_awarded"] = True
    return messages
