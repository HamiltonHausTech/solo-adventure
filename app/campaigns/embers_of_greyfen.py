"""Embers of Greyfen - a longer branching campaign for sustained playtests."""

from __future__ import annotations

from typing import Dict

from ..content import Campaign, Room, register_campaign
from ..profiles import CompanionProfile, MobProfile


ROOM_ORDER = [
    "greyfen_road",
    "crossroads",
    "high_road",
    "signal_tower",
    "marsh_path",
    "sunken_chapel",
    "refuge",
    "old_forest",
    "fallen_bridge",
    "keep_gate",
    "great_hall",
    "ember_vault",
]

ROOMS: Dict[str, Room] = {
    "greyfen_road": Room(
        room_id="greyfen_road",
        name="Greyfen Road",
        description=(
            "Cold rain sweeps across an abandoned wagon outside Greyfen. Its driver, "
            "Sella Vane, guards a lantern whose flame burns an unnatural blue."
        ),
        kind="social",
        npc="Sella Vane",
        social_config={
            "stat": "CHA", "dc": 12, "success_flag": "sella_trusted",
            "done_flag": "sella_spoken",
            "success_recap": "Sella accepts your promise to help. She explains that raiders carried the Ember Heart toward Blackbriar Keep.",
            "fail_recap": "Sella doubts your intentions, but points you toward the crossroads before driving into the rain.",
            "success_msg": "Sella accepts your promise to help (roll {roll} -> {total}). She explains that raiders carried the Ember Heart toward Blackbriar Keep.",
            "fail_msg": "Sella doubts your intentions (roll {roll} -> {total}), but points you toward the crossroads before driving into the rain.",
        },
    ),
    "crossroads": Room(
        room_id="crossroads",
        name="The Split Stones",
        description=(
            "Two weathered stones divide the way. The exposed high road is direct but watched; "
            "the marsh path is slower, half drowned, and hidden by reeds."
        ),
        kind="passage",
    ),
    "high_road": Room(
        room_id="high_road",
        name="Windcut High Road",
        description=(
            "The road climbs above the fog. Three Blackbriar outriders wheel their mounts "
            "across the narrow shelf and lower hooked spears."
        ),
        kind="combat",
        enemy_name="Blackbriar Outriders",
    ),
    "signal_tower": Room(
        room_id="signal_tower",
        name="Abandoned Signal Tower",
        description=(
            "A cracked beacon crowns the ridge. An old signal keeper shelters inside, "
            "terrified that the raiders will return."
        ),
        kind="social",
        npc="Keeper Orin",
        social_config={
            "stat": "WIS", "dc": 13, "success_flag": "keep_route_known",
            "done_flag": "orin_spoken",
            "success_recap": "Orin steadies under your questions and sketches the keep's ruined western approach.",
            "fail_recap": "Orin's frightened account circles back on itself. You learn only that Blackbriar lies beyond the forest.",
            "success_msg": "Orin steadies under your questions (roll {roll} -> {total}) and sketches the keep's ruined western approach.",
            "fail_msg": "Orin's frightened account circles back on itself (roll {roll} -> {total}). You learn only that Blackbriar lies beyond the forest.",
        },
    ),
    "marsh_path": Room(
        room_id="marsh_path",
        name="Drowned Causeway",
        description=(
            "Black water closes over the old paving stones. Bog hounds rise silently from "
            "the reeds, their eyes reflecting the same blue fire as Sella's lantern."
        ),
        kind="combat",
        enemy_name="Bog Hounds",
    ),
    "sunken_chapel": Room(
        room_id="sunken_chapel",
        name="Sunken Chapel",
        description=(
            "A chapel leans into the mire, its altar barely above the waterline. Faded mosaics "
            "show the Ember Heart being used to seal something beneath Blackbriar Keep."
        ),
        kind="passage",
        room_loot_config={"gold": "2d6+2"},
    ),
    "refuge": Room(
        room_id="refuge",
        name="Greyfen Refuge",
        description=(
            "Survivors have barricaded an old charcoal-burner's lodge. Their leader, Nessa, "
            "asks whether you came to recover the relic or merely hunt its thieves."
        ),
        kind="social",
        npc="Nessa Grey",
        social_config={
            "stat": "INT", "dc": 14, "success_flag": "ember_truth_known",
            "done_flag": "nessa_spoken",
            "success_recap": "You piece together Nessa's guarded history. The Ember Heart is a seal, not a treasure, and its removal is waking the keep.",
            "fail_recap": "Nessa withholds the refuge's oldest secret, though she confirms the raiders entered Blackbriar at dusk.",
            "success_msg": "You piece together Nessa's guarded history (d20 {roll} + {stat} {bonus:+d} = {total} vs DC {dc}). The Ember Heart is a seal, not a treasure, and its removal is waking the keep.",
            "fail_msg": "Nessa withholds the refuge's oldest secret (d20 {roll} + {stat} {bonus:+d} = {total} vs DC {dc}), though she confirms the raiders entered Blackbriar at dusk.",
        },
        challenge_config={
            "title": "Prepare for Blackbriar",
            "prompt": "Before leaving the refuge, you may seek one advantage for the fighting ahead. This opportunity is optional.",
            "required": False,
            "options": [
                {"id": "survey_tracks", "label": "Survey the raider tracks", "description": "Universal · Wisdom check", "stat": "WIS", "dc": 12,
                 "success": {"message": "You identify the raiders' favored ambush pattern. Your next attack gains +2", "flags": {"prepared_strike": 2}},
                 "failure": {"message": "Rain has spoiled the trail. You lose time but suffer no lasting setback."}},
                {"id": "persuade_nessa", "label": "Press Nessa for a weakness", "description": "Charisma check", "stat": "CHA", "dc": 13,
                 "success": {"message": "Nessa reveals the keep guard's blind approach. Your next attack gains +2", "flags": {"prepared_strike": 2}},
                 "failure": {"message": "Nessa refuses to gamble more lives on an unproven plan."}},
                {"id": "eldrin_runes", "label": "Study the route with Eldrin", "description": "Eldrin · automatic", "automatic": True, "requires": {"companion": "Eldrin", "companion_alive": True},
                 "success": {"message": "Eldrin recognizes old boundary marks and plots a precise opening strike", "flags": {"prepared_strike": 2}}},
            ],
        },
    ),
    "old_forest": Room(
        room_id="old_forest",
        name="Old Greyfen Forest",
        description=(
            "The trees knit together above a trail of scorched footprints. Thornbound dead "
            "pull themselves from the roots as you pass."
        ),
        kind="combat",
        enemy_name="Thornbound Dead",
    ),
    "fallen_bridge": Room(
        room_id="fallen_bridge",
        name="Fallen Bridge Camp",
        description=(
            "A collapsed bridge spans a stony ravine. The raiders left bedrolls and a supply "
            "cache beside a precarious crossing toward the keep."
        ),
        kind="passage",
        room_loot_config={"gold": "3d6"},
    ),
    "keep_gate": Room(
        room_id="keep_gate",
        name="Blackbriar Gate",
        description=(
            "Briars writhe through the shattered gatehouse. Raider sentries fight beside a "
            "hulking vine-grown guardian awakened by the stolen relic."
        ),
        kind="combat",
        enemy_name="Gate Marauders",
    ),
    "great_hall": Room(
        room_id="great_hall",
        name="Blackbriar Great Hall",
        description=(
            "Blue fire races through cracks in the floor. Captain Veyra stands before the open "
            "vault stair, the Ember Heart blazing in an iron cradle at her side."
        ),
        kind="combat",
        enemy_name="Captain Veyra",
    ),
    "ember_vault": Room(
        room_id="ember_vault",
        name="The Ember Vault",
        description=(
            "Below the keep, roots strain against a broken stone seal. The Ember Heart answers "
            "your approach with a steady pulse, waiting to be returned to its socket."
        ),
        kind="loot",
        loot="ember_heart",
        challenge_config={
            "title": "Restore the Ember Seal",
            "prompt": "The Heart belongs in the broken seal. What you learned, the trust you built with Eldrin, or your own development can guide a safe restoration. You can always attempt it unaided; even a misstep will end the danger, at a cost.",
            "required": False,
            "completion": True,
            "options": [
                {"id": "restore_informed", "label": "Restore the Heart using Nessa's truth", "description": "Known purpose · reliable restoration", "automatic": True,
                 "requires": {"flags": ["ember_truth_known"], "flags_reason": "Learn the Ember Heart’s purpose from Nessa."},
                 "success": {"ending": "informed", "message": "Remembering Nessa's truth that the Heart is a seal, not treasure, you align its pulse with the socket. The roots fall still. Greyfen is saved without sacrifice."}},
                {"id": "eldrin_aid", "label": "Entrust the restoration to Eldrin", "description": "Living Eldrin · trust 60 · reliable restoration", "automatic": True,
                 "requires": {"companion": "Eldrin", "companion_alive": True, "trust": 60},
                 "success": {"ending": "trusted", "message": "The trust built on your journey lets Eldrin guide your hands through the dangerous counter-runes. Together you restore the seal safely, and Greyfen sees dawn."}},
                {"id": "mastered_seal", "label": "Steady the seal through your own training", "description": "Wisdom 5 or Battle Resilience · reliable restoration", "automatic": True,
                 "requires": {"stat": {"name": "WIS", "minimum": 5}, "ability": "resilience"},
                 "success": {"ending": "mastered", "message": "Your developed discipline holds against the Heart's violent pulse. You steady the broken seal until it accepts the relic. Greyfen is safe because of the strength you cultivated."}},
                {"id": "attempt_seal", "label": "Attempt the restoration unaided", "description": "Always available · Wisdom DC 14 · a failed roll costs at most 3 HP, never your life", "stat": "WIS", "dc": 14,
                 "success": {"ending": "instinctive", "message": "Trusting your instincts, you settle the Heart into its socket. Blue fire turns gold and the seal holds. Greyfen is saved."},
                 "failure": {"ending": "costly", "damage": 3, "message": "The Heart lashes out, costing up to 3 HP but never your last breath. You hold it in place despite the pain; the seal closes and Greyfen is saved. Better preparation could have spared this cost."}},
            ],
        },
        loot_config={
            "stat": "WIS", "dc": 14, "win_item_id": "ember_heart", "game_over": True,
            "success_msg": "You set the Ember Heart into the seal (roll {roll} -> {total}). Blue fire becomes warm gold, the roots fall still, and Greyfen sees dawn again.",
            "fail_msg": "The relic bucks against your grasp (roll {roll} -> {total}). The seal rejects your first attempt, but there is still time to steady yourself.",
        },
    ),
}

ITEM_CATALOG: Dict[str, Dict[str, object]] = {
    "healing_potion": {"id": "healing_potion", "name": "Healing Potion", "kind": "potion", "effect": {"type": "heal", "dice": "1d6+2"}, "stackable": True, "counts_toward_limit": True},
    "leather_cap": {"id": "leather_cap", "name": "Leather Cap", "kind": "armor", "slot": "head", "effect": {"type": "ac", "bonus": 1}, "counts_toward_limit": True},
    "worn_boots": {"id": "worn_boots", "name": "Worn Boots", "kind": "armor", "slot": "feet", "effect": {"type": "ac", "bonus": 1}, "counts_toward_limit": True},
    "briar_guard": {"id": "briar_guard", "name": "Briar Guard", "kind": "armor", "slot": "arms", "effect": {"type": "ac", "bonus": 1}, "counts_toward_limit": True},
    "greyfen_mail": {"id": "greyfen_mail", "name": "Greyfen Mail", "kind": "armor", "slot": "chest", "tier": 2, "unique": True, "class_affinity": ["Fighter", "Cleric"], "effect": {"type": "ac", "bonus": 2}, "counts_toward_limit": True},
    "briar_gloves": {"id": "briar_gloves", "name": "Briar Gloves", "kind": "armor", "slot": "hands", "tier": 2, "sell_value": 14, "description": "Thorn-stitched gloves that reward a decisive grip.", "class_affinity": ["Rogue", "Wizard"], "effect": {"type": "ac", "bonus": 0, "attack_bonus": 1}, "counts_toward_limit": True},
    "greyfen_greaves": {"id": "greyfen_greaves", "name": "Greyfen Greaves", "kind": "armor", "slot": "legs", "tier": 2, "sell_value": 16, "description": "Rain-darkened greaves built for the fen roads.", "effect": {"type": "ac", "bonus": 1, "attack_bonus": 0}, "counts_toward_limit": True},
    "ember_heart": {"id": "ember_heart", "name": "The Ember Heart", "kind": "quest", "effect": None, "counts_toward_limit": False},
}

COMPANIONS: Dict[str, CompanionProfile] = {
    "eldrin": CompanionProfile(companion_id="eldrin", name="Eldrin", hp=9, max_hp=9, ac=12, attack_bonus=2, damage="1d4+1", mana=7, max_mana=7, spells=["Spark", "Magic Missile"], personality="curious"),
    "mara": CompanionProfile(companion_id="mara", name="Mara", hp=11, max_hp=11, ac=14, attack_bonus=3, damage="1d6", personality="guarded"),
    "torvald": CompanionProfile(companion_id="torvald", name="Torvald", hp=15, max_hp=15, ac=15, attack_bonus=3, damage="1d8+1", defend_hp_threshold=4, personality="steadfast"),
}

MOBS: Dict[str, MobProfile] = {
    "Blackbriar Outriders": MobProfile(name="Blackbriar Outriders", hp=7, count=3, ac=12, attack_bonus=2, damage="1d4+1", loot={"gold": "2d6", "items": ["briar_guard", "briar_gloves"], "item_chance": 25}, xp=35),
    "Bog Hounds": MobProfile(name="Bog Hounds", hp=8, count=2, ac=13, attack_bonus=3, damage="1d6", loot={"gold": "1d4"}, xp=35, on_hit_condition={"id": "poisoned", "dc": 12, "duration": 2}),
    "Thornbound Dead": MobProfile(name="Thornbound Dead", hp=9, count=2, ac=13, attack_bonus=3, damage="1d6", loot={"gold": "2d4", "items": ["greyfen_mail", "greyfen_greaves"], "item_chance": 30}, xp=45),
    "Gate Marauders": MobProfile(name="Gate Marauders", hp=11, count=2, ac=14, attack_bonus=3, damage="1d6+1", loot={"gold": "3d6", "items": ["briar_guard"], "item_chance": 30}, ai="focus_player", xp=55),
    "Captain Veyra": MobProfile(name="Captain Veyra", hp=22, ac=15, attack_bonus=4, damage="1d8+1", loot={"gold": "4d6", "items": ["greyfen_mail"]}, ai="focus_player", xp=100),
}

EMBERS_OF_GREYFEN = Campaign(
    campaign_id="embers_of_greyfen",
    name="Embers of Greyfen",
    description=(
        "A longer journey through a rainbound frontier: choose the high road or the drowned "
        "marsh, uncover the truth of a stolen relic, and assault Blackbriar Keep."
    ),
    room_order=ROOM_ORDER,
    rooms=ROOMS,
    items=ITEM_CATALOG,
    mobs=MOBS,
    companions=COMPANIONS,
    default_companion_ids=["eldrin", "mara", "torvald"],
    journey_config={'facts': {'ember_truth_known': 'Nessa revealed that the Ember Heart is a seal, not a treasure. Return it to '
                                'its socket to still the keep.',
           'keep_route_known': 'Orin described the keep’s ruined western approach.',
           'sella_trusted': 'Sella says the raiders carried the Ember Heart toward Blackbriar Keep.'},
 'objectives': {'crossroads': {'description': 'Take the watched high road or the hidden marsh path; both '
                                              'lead onward.',
                               'title': 'Choose your route'},
                'ember_vault': {'description': 'Choose a restoration approach. Knowledge, a trusted living '
                                               'Eldrin, or developed discipline can prevent a painful '
                                               'mistake.',
                                'title': 'Restore the seal'},
                'fallen_bridge': {'description': 'Search the abandoned camp if you need supplies, then '
                                                 'continue to the gate.',
                                  'title': 'Approach Blackbriar'},
                'great_hall': {'description': 'With the hall cleared, descend to the adjacent vault.',
                               'title': 'Recover the Heart'},
                'greyfen_road': {'description': 'Speak with Sella, then take the road to the Split Stones.',
                                 'title': 'Find the raiders’ trail'},
                'high_road': {'description': 'Continue toward the adjacent signal tower after clearing the '
                                             'road.',
                              'title': 'Follow the high road'},
                'keep_gate': {'description': 'Once the gate is clear, continue into the great hall.',
                              'title': 'Enter Blackbriar'},
                'marsh_path': {'description': 'Continue toward the chapel after clearing the causeway.',
                               'title': 'Cross the marsh'},
                'old_forest': {'description': 'Continue toward the fallen bridge once the forest is clear.',
                               'title': 'Reach the keep'},
                'refuge': {'description': 'Speak with Nessa before following the raiders into the old '
                                          'forest. Preparation here is optional.',
                           'title': 'Learn why the Heart matters'},
                'signal_tower': {'description': 'Speak with Orin, then continue to the refuge.',
                                 'title': 'Ask the keeper'},
                'sunken_chapel': {'description': 'Investigate the chapel, then continue to the refuge.',
                                  'title': 'Read the old traces'}},
 'onward': {'fallen_bridge': 'The abandoned camp has been searched. Continue to the gate.',
            'greyfen_road': 'Follow the road to the Split Stones.',
            'refuge': 'Follow the raiders into the old forest. You may prepare here first.',
            'signal_tower': 'Continue from the tower to the refuge.'}},
    completion_xp=250,
    recommended_level=3,
    max_item_tier=2,
    exits={
        "greyfen_road": {"crossroads": "crossroads", "forward": "crossroads"},
        "crossroads": {"high_road": "high_road", "marsh_path": "marsh_path"},
        "high_road": {"crossroads": "crossroads", "signal_tower": "signal_tower"},
        "signal_tower": {"high_road": "high_road", "refuge": "refuge"},
        "marsh_path": {"crossroads": "crossroads", "sunken_chapel": "sunken_chapel"},
        "sunken_chapel": {"marsh_path": "marsh_path", "refuge": "refuge"},
        "refuge": {"signal_tower": "signal_tower", "sunken_chapel": "sunken_chapel", "old_forest": "old_forest"},
        "old_forest": {"refuge": "refuge", "fallen_bridge": "fallen_bridge"},
        "fallen_bridge": {"old_forest": "old_forest", "keep_gate": "keep_gate"},
        "keep_gate": {"fallen_bridge": "fallen_bridge", "great_hall": "great_hall"},
        "great_hall": {"keep_gate": "keep_gate", "ember_vault": "ember_vault"},
        "ember_vault": {"great_hall": "great_hall"},
    },
)

register_campaign(EMBERS_OF_GREYFEN)
