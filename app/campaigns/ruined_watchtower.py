from __future__ import annotations

from typing import Dict

from ..content import Campaign, Room, register_campaign
from ..profiles import CompanionProfile, MobProfile


ROOM_ORDER = ["courtyard", "cellar", "barracks", "spire"]

ROOMS: Dict[str, Room] = {
    "courtyard": Room(
        room_id="courtyard",
        name="Ruined Courtyard",
        description=(
            "Broken stone and fallen beams surround a mossy fire pit. A hooded scout "
            "watches you from a collapsed archway, hand near a shortbow."
        ),
        kind="social",
        npc="Eryn the Scout",
        social_config={
            "stat": "INT",
            "dc": 13,
            "success_flag": "scout_helped",
            "success_msg": "You win Eryn's trust (roll {roll} -> {total}). She points out a safe route and warns you about a lone bandit inside.",
            "fail_msg": "Eryn stays guarded (roll {roll} -> {total}). She gives no help, but allows you to pass.",
            "done_flag": "social_done",
        },
    ),
    "barracks": Room(
        room_id="barracks",
        name="Crumbling Barracks",
        description=(
            "Dusty bunks line the walls. A lone bandit in watchman gear steps from the shadows, "
            "blade raised."
        ),
        kind="combat",
        enemy_name="Watchtower Bandit",
    ),
    "cellar": Room(
        room_id="cellar",
        name="Collapsed Cellar",
        description=(
            "A broken stairwell drops into a damp cellar. Two big rats bristle and hiss, "
            "ready to charge."
        ),
        kind="combat",
        enemy_name="Big Rats",
    ),
    "spire": Room(
        room_id="spire",
        name="Top Spire",
        description=(
            "The top chamber is open to the wind. An ironbound chest sits beneath a broken mural, "
            "its lock rusted but stubborn."
        ),
        kind="loot",
        loot="silver_locket",
        loot_config={
            "stat": "DEX",
            "dc": 13,
            "win_item_id": "silver_locket",
            "game_over": True,
            "success_msg": "You work the rusted lock free (roll {roll} -> {total}). Inside rests the Silver Locket of the Watch. Your adventure ends in triumph.",
            "fail_msg": "Your tools slip (roll {roll} -> {total}). The lock resists for now, but you can try again.",
        },
    ),
}

ITEM_CATALOG: Dict[str, Dict[str, object]] = {
    "healing_potion": {
        "id": "healing_potion",
        "name": "Healing Potion",
        "kind": "potion",
        "effect": {"type": "heal", "dice": "1d6+2"},
        "counts_toward_limit": True,
    },
    "leather_cap": {
        "id": "leather_cap",
        "name": "Leather Cap",
        "kind": "armor",
        "slot": "head",
        "effect": {"type": "ac", "bonus": 1},
        "counts_toward_limit": True,
    },
    "padded_arms": {
        "id": "padded_arms",
        "name": "Padded Armguards",
        "kind": "armor",
        "slot": "arms",
        "effect": {"type": "ac", "bonus": 1},
        "counts_toward_limit": True,
    },
    "worn_boots": {
        "id": "worn_boots",
        "name": "Worn Boots",
        "kind": "armor",
        "slot": "feet",
        "effect": {"type": "ac", "bonus": 1},
        "counts_toward_limit": True,
    },
    "silver_locket": {
        "id": "silver_locket",
        "name": "Silver Locket of the Watch",
        "kind": "quest",
        "effect": None,
        "counts_toward_limit": False,
    },
}

COMPANIONS: Dict[str, CompanionProfile] = {
    "mara": CompanionProfile(
        companion_id="mara",
        name="Mara",
        hp=10,
        max_hp=10,
        ac=13,
        attack_bonus=2,
        damage="1d6",
        ai="cautious",
        defend_hp_threshold=3,
    ),
}

MOBS: Dict[str, MobProfile] = {
    "Watchtower Bandit": MobProfile(
        name="Watchtower Bandit",
        hp=12,
        ac=13,
        attack_bonus=3,
        damage="1d6",
        loot={"gold": "1d6+2", "items": ["padded_arms", "worn_boots", "leather_cap"]},
        ai="focus_player",
        xp=25,
    ),
    "Big Rats": MobProfile(
        name="Big Rats",
        hp_expr="1d4-1",
        hp_min=1,
        count=2,
        ac=12,
        attack_bonus=2,
        damage="1d4",
        loot={},
        ai="focus_weakest",
        xp=10,
    ),
}

RUINED_WATCHTOWER = Campaign(
    campaign_id="ruined_watchtower",
    name="The Ruined Watchtower",
    description="A watchtower with a cellar, one social scene, two combats, and a final loot chamber.",
    room_order=ROOM_ORDER,
    rooms=ROOMS,
    items=ITEM_CATALOG,
    mobs=MOBS,
    companions=COMPANIONS,
    default_companion_ids=["mara"],
    completion_xp=100,
    exits={
        "courtyard": {"down": "cellar", "cellar": "cellar", "up": "barracks", "barracks": "barracks"},
        "cellar": {"up": "courtyard", "courtyard": "courtyard"},
        "barracks": {"down": "courtyard", "courtyard": "courtyard", "up": "spire", "spire": "spire"},
        "spire": {"down": "barracks", "barracks": "barracks"},
    },
)

register_campaign(RUINED_WATCHTOWER)
