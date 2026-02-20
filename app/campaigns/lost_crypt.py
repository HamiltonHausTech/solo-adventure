"""The Lost Crypt - a more involved campaign for testing companions and progression."""

from __future__ import annotations

from typing import Dict

from ..content import Campaign, Room, register_campaign
from ..profiles import CompanionProfile, MobProfile


ROOM_ORDER = [
    "approach",
    "gate",
    "hallway",
    "guard_room",
    "antechamber",
    "crypt",
    "treasure",
]

ROOMS: Dict[str, Room] = {
    "approach": Room(
        room_id="approach",
        name="Overgrown Approach",
        description=(
            "A worn path leads through tangled undergrowth to a sunken stone arch. "
            "Moss and vines cling to weathered carvings. The entrance to the crypt lies ahead."
        ),
        kind="social",
        npc="Keeper Aldric",
        social_config={
            "stat": "WIS",
            "dc": 12,
            "success_flag": "keeper_warned",
            "success_msg": "Aldric shares what he knows (roll {roll} -> {total}). 'The lower levels hold restless dead. Bring light and steel.'",
            "fail_msg": "Aldric shrugs (roll {roll} -> {total}). 'Go if you must. I've said my piece.'",
            "done_flag": "social_done",
        },
    ),
    "gate": Room(
        room_id="gate",
        name="Sealed Gate",
        description=(
            "A heavy iron gate blocks the descent. Rust has weakened the mechanism. "
            "A careful hand might ease it open, or force could break it."
        ),
        kind="social",
        npc=None,
        social_config={
            "stat": "DEX",
            "dc": 11,
            "success_flag": "gate_opened",
            "success_msg": "You work the latch free (roll {roll} -> {total}). The gate swings open silently.",
            "fail_msg": "The mechanism resists (roll {roll} -> {total}). You can try again or force it.",
            "done_flag": "gate_done",
        },
    ),
    "hallway": Room(
        room_id="hallway",
        name="Dusty Hallway",
        description=(
            "Torch sconces line the walls, long cold. Faint scratches mark the floor. "
            "Something has been through here recently."
        ),
        kind="passage",
        npc=None,
    ),
    "guard_room": Room(
        room_id="guard_room",
        name="Guard Chamber",
        description=(
            "Skeletal figures in rusted mail stand watch. At your approach, "
            "their eyes flare with cold light. The dead do not rest easy here."
        ),
        kind="combat",
        enemy_name="Crypt Guardians",
    ),
    "antechamber": Room(
        room_id="antechamber",
        name="Antechamber",
        description=(
            "A small chamber before the main crypt. Faded murals depict a burial procession. "
            "A lone wight stirs from the shadows, drawn by the living."
        ),
        kind="combat",
        enemy_name="Crypt Wight",
    ),
    "crypt": Room(
        room_id="crypt",
        name="Main Crypt",
        description=(
            "Stone sarcophagi line the walls. The air is cold and still. "
            "A wraith coalesces from the darkness—ancient, hungry, and hostile."
        ),
        kind="combat",
        enemy_name="Crypt Wraith",
    ),
    "treasure": Room(
        room_id="treasure",
        name="Treasure Vault",
        description=(
            "The innermost chamber. A stone casket rests on a dais, lid askew. "
            "Within lies the Amulet of Rest—the prize that might quiet the crypt forever."
        ),
        kind="loot",
        loot="amulet_of_rest",
        loot_config={
            "stat": "INT",
            "dc": 14,
            "win_item_id": "amulet_of_rest",
            "game_over": True,
            "success_msg": "You secure the Amulet (roll {roll} -> {total}). Its warmth spreads through you. The crypt falls silent. Victory.",
            "fail_msg": "The wards resist (roll {roll} -> {total}). Steady your mind and try again.",
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
    "chain_shirt": {
        "id": "chain_shirt",
        "name": "Chain Shirt",
        "kind": "armor",
        "slot": "chest",
        "effect": {"type": "ac", "bonus": 2},
        "counts_toward_limit": True,
    },
    "amulet_of_rest": {
        "id": "amulet_of_rest",
        "name": "Amulet of Rest",
        "kind": "quest",
        "effect": None,
        "counts_toward_limit": False,
    },
}

COMPANIONS: Dict[str, CompanionProfile] = {
    "eldrin": CompanionProfile(
        companion_id="eldrin",
        name="Eldrin",
        hp=8,
        max_hp=8,
        ac=12,
        attack_bonus=1,
        damage="1d4+1",
        ai="cautious",
        defend_hp_threshold=3,
        mana=6,
        max_mana=6,
        spells=["Spark", "Magic Missile"],
    ),
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
    "Crypt Guardians": MobProfile(
        name="Crypt Guardians",
        hp=8,
        ac=14,
        attack_bonus=2,
        damage="1d6",
        loot={"gold": "2d4", "items": ["chain_shirt"]},
        ai="focus_weakest",
        xp=30,
    ),
    "Crypt Wight": MobProfile(
        name="Crypt Wight",
        hp=12,
        ac=13,
        attack_bonus=3,
        damage="1d6+1",
        loot={"gold": "1d6+3"},
        ai="focus_player",
        xp=40,
    ),
    "Crypt Wraith": MobProfile(
        name="Crypt Wraith",
        hp=14,
        ac=14,
        attack_bonus=4,
        damage="1d8",
        loot={"gold": "3d6"},
        ai="focus_player",
        xp=75,
    ),
}

LOST_CRYPT = Campaign(
    campaign_id="lost_crypt",
    name="The Lost Crypt",
    description=(
        "A sunken crypt holds restless dead and a fabled amulet. "
        "Choose your companion and descend. Multiple combats, social checks, and a climactic boss."
    ),
    room_order=ROOM_ORDER,
    rooms=ROOMS,
    items=ITEM_CATALOG,
    mobs=MOBS,
    companions=COMPANIONS,
    default_companion_ids=["eldrin", "mara"],
    completion_xp=150,
    exits={
        "approach": {"gate": "gate", "down": "gate"},
        "gate": {"approach": "approach", "hallway": "hallway", "down": "hallway"},
        "hallway": {"gate": "gate", "guard_room": "guard_room", "down": "guard_room"},
        "guard_room": {"hallway": "hallway", "antechamber": "antechamber", "down": "antechamber"},
        "antechamber": {"guard_room": "guard_room", "crypt": "crypt", "down": "crypt"},
        "crypt": {"antechamber": "antechamber", "treasure": "treasure", "down": "treasure"},
        "treasure": {"crypt": "crypt", "up": "crypt"},
    },
)

register_campaign(LOST_CRYPT)
