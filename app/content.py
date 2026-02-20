from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .profiles import CompanionProfile, MobProfile


@dataclass(frozen=True)
class Room:
    room_id: str
    name: str
    description: str
    kind: str  # "social", "combat", "loot"
    npc: Optional[str] = None
    enemy_name: Optional[str] = None
    loot: Optional[str] = None  # item id
    # Campaign-driven behavior config (avoids hardcoding in rules)
    social_config: Optional[Dict[str, object]] = None  # stat, dc, success_flag, success_msg, fail_msg
    loot_config: Optional[Dict[str, object]] = None  # stat, dc, success_msg, fail_msg, win_item_id, game_over
    room_loot_config: Optional[Dict[str, object]] = None  # gold: "2d6" etc., no check, one-time pickup


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    name: str
    description: str
    room_order: List[str]
    rooms: Dict[str, Room]
    items: Dict[str, Dict[str, object]]
    mobs: Dict[str, MobProfile]
    exits: Dict[str, Dict[str, str]]
    companions: Dict[str, CompanionProfile] = field(default_factory=dict)
    default_companion_ids: Optional[List[str]] = None
    completion_xp: int = 0  # XP awarded on successful campaign completion


CAMPAIGNS: Dict[str, Campaign] = {}


def register_campaign(campaign: Campaign) -> None:
    CAMPAIGNS[campaign.campaign_id] = campaign


def list_campaigns() -> List[Campaign]:
    return list(CAMPAIGNS.values())


def get_campaign(campaign_id: str) -> Campaign:
    return CAMPAIGNS[campaign_id]


def get_room(campaign_id: str, room_id: str) -> Room:
    return get_campaign(campaign_id).rooms[room_id]


def next_room_id(campaign_id: str, current_room_id: str) -> Optional[str]:
    campaign = get_campaign(campaign_id)
    try:
        idx = campaign.room_order.index(current_room_id)
    except ValueError:
        return None
    if idx + 1 >= len(campaign.room_order):
        return None
    return campaign.room_order[idx + 1]


def item_from_id(campaign_id: str, item_id: str) -> Dict[str, object]:
    campaign = get_campaign(campaign_id)
    item = campaign.items.get(item_id)
    if not item:
        return {"id": "unknown", "name": item_id, "kind": "unknown", "effect": None}
    return dict(item)


def item_from_name(campaign_id: str, name: str) -> Dict[str, object]:
    campaign = get_campaign(campaign_id)
    for item in campaign.items.values():
        if str(item.get("name", "")).lower() == name.lower():
            return dict(item)
    return {"id": "unknown", "name": name, "kind": "unknown", "effect": None}


def get_mob_profile(campaign_id: str, name: str) -> MobProfile:
    campaign = get_campaign(campaign_id)
    return campaign.mobs[name]


def get_exits(campaign_id: str, room_id: str) -> Dict[str, str]:
    campaign = get_campaign(campaign_id)
    return dict(campaign.exits.get(room_id, {}))


def get_campaign_quest_item_ids(campaign_id: str) -> List[str]:
    """Return item IDs with kind 'quest' for the campaign (removed on completion)."""
    campaign = get_campaign(campaign_id)
    return [
        item_id
        for item_id, item in campaign.items.items()
        if str(item.get("kind", "")).lower() == "quest"
    ]


from . import campaigns as _campaigns  # noqa: F401
