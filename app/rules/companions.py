"""Companion creation from campaign profiles."""

from __future__ import annotations

from typing import List, Optional

from ..content import get_campaign
from ..profiles import CompanionProfile
from ..state import Companion


def create_companion_from_profile(profile: CompanionProfile) -> Companion:
    mana = getattr(profile, "mana", 0)
    max_mana = getattr(profile, "max_mana", 0)
    spells = getattr(profile, "spells", []) or []
    defend = getattr(profile, "defend_hp_threshold", 3)
    return Companion(
        name=profile.name,
        hp=profile.hp,
        max_hp=profile.max_hp,
        ac=profile.ac,
        attack_bonus=profile.attack_bonus,
        damage=profile.damage,
        mana=mana,
        max_mana=max_mana,
        learned_spells=list(spells),
        defend_hp_threshold=defend,
    )


def create_companion(campaign_id: str, companion_id: Optional[str] = None) -> Companion:
    """Create a companion from campaign's companion profile. Uses default if companion_id is None."""
    campaign = get_campaign(campaign_id)
    if not campaign.companions:
        # Fallback for campaigns without companion data (legacy)
        return Companion(
            name="Mara",
            hp=10,
            max_hp=10,
            ac=13,
            attack_bonus=2,
            damage="1d6",
            mana=0,
            max_mana=0,
            learned_spells=[],
            defend_hp_threshold=3,
        )
    cid = companion_id or (campaign.default_companion_ids or list(campaign.companions.keys()))[0]
    profile = campaign.companions.get(cid)
    if not profile:
        raise ValueError(f"Unknown companion '{cid}' in campaign '{campaign_id}'")
    return create_companion_from_profile(profile)


def create_campaign_companions(
    campaign_id: str, companion_ids: Optional[List[str]] = None
) -> List[Companion]:
    """Create companions for a campaign. If companion_ids is None, use campaign default."""
    campaign = get_campaign(campaign_id)
    if not campaign.companions:
        return [create_companion(campaign_id)]
    ids = companion_ids or campaign.default_companion_ids or list(campaign.companions.keys())[:1]
    return [create_companion(campaign_id, cid) for cid in ids]
