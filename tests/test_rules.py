import unittest
from unittest.mock import patch

from app.content import item_from_id
from app.characters import strip_campaign_quest_items
from app.rules.experience import grant_xp, level_from_xp, xp_for_level
from app.util import normalize_action
from app.profiles import apply_race_mods
from app.profiles import CompanionProfile
from app.rules import (
    add_item_to_inventory,
    apply_progression_choices,
    apply_companion_action,
    apply_exploration_action,
    apply_enemy_action,
    apply_player_action,
    apply_rest,
    buy_healing_potions,
    buy_shop_item,
    create_companion,
    create_companion_from_profile,
    create_enemy,
    create_enemies,
    create_player,
    drop_item,
    regen_mana,
    end_combat_if_needed,
    equip_item,
    equipped_damage,
    reset_rest_streak,
    scale_companion_for_level,
    sell_item,
    sync_player_ac,
    unequip_item,
    use_item,
)
from app.state import GameState


class RulesTests(unittest.TestCase):
    def make_state(self) -> GameState:
        player = create_player("Hero", "Fighter", {"STR": 2, "DEX": 2, "INT": 2})
        companion = create_companion("ruined_watchtower")
        return GameState(
            campaign_id="ruined_watchtower",
            player=player,
            room_id="courtyard",
            companions=[companion],
            inventory=[],
        )

    def test_attack_hits_and_deals_damage(self) -> None:
        state = self.make_state()
        state.enemies = [create_enemy("ruined_watchtower", "Watchtower Bandit")]
        with patch("app.rules.combat.roll_die", return_value=15), patch(
            "app.rules.dice.roll_die", return_value=4
        ):
            result = apply_player_action(state, "attack")
        self.assertIn("Hit", result)
        self.assertEqual(state.enemies[0].hp, 7)

    def test_big_rats_hp_minimum(self) -> None:
        with patch("app.rules.dice.roll_die", side_effect=[1, 1]):
            enemies = create_enemies("ruined_watchtower", "Big Rats")
        self.assertEqual(len(enemies), 2)
        self.assertEqual(sum(enemy.hp for enemy in enemies), 2)

    def test_loot_adds_item_and_ends_game(self) -> None:
        state = self.make_state()
        state.room_id = "spire"
        with patch("app.rules.dice.roll_die", return_value=20):
            result = apply_exploration_action(state, "search")
        self.assertTrue(state.game_over)
        self.assertTrue(state.flags.get("loot_taken"))
        self.assertIn("Silver Locket", result)
        self.assertEqual(state.inventory[0]["id"], "silver_locket")

    def test_bandit_loot_adds_gold_and_item(self) -> None:
        state = self.make_state()
        state.room_id = "barracks"
        state.flags["defeated_rooms"] = ["barracks"]
        state.flags["corpses"] = {
            "barracks": [{"id": 1, "name": "Watchtower Bandit", "looted": False}]
        }
        with patch("app.rules.dice.roll_die", side_effect=[4, 1]):
            result = apply_exploration_action(state, "loot")
        self.assertIn("gain 6 gold", result.lower())
        self.assertEqual(state.player.gold, 6)
        self.assertTrue(state.inventory)

    def test_bandit_loot_gold_even_if_full(self) -> None:
        state = self.make_state()
        state.room_id = "barracks"
        state.inventory_limit = 0
        state.flags["defeated_rooms"] = ["barracks"]
        state.flags["corpses"] = {
            "barracks": [{"id": 1, "name": "Watchtower Bandit", "looted": False}]
        }
        with patch("app.rules.dice.roll_die", side_effect=[2, 1]):
            result = apply_exploration_action(state, "loot")
        self.assertIn("gain 4 gold", result.lower())
        self.assertEqual(state.player.gold, 4)
        self.assertFalse(state.inventory)

    def test_search_barracks_after_combat(self) -> None:
        state = self.make_state()
        state.room_id = "barracks"
        state.flags["defeated_rooms"] = ["barracks"]
        result = apply_exploration_action(state, "search")
        self.assertIn("search the crumbling barracks", result.lower())

    def test_passage_room_loot_adds_gold(self) -> None:
        from app.content import Room, get_campaign, register_campaign
        from app.rules.exploration import apply_exploration_action

        # Use lost_crypt hallway which has room_loot_config
        state = self.make_state()
        state.campaign_id = "lost_crypt"
        state.room_id = "hallway"
        state.player.gold = 5
        with patch("app.rules.exploration.roll_dice", return_value=(7, "2d6")):
            result = apply_exploration_action(state, "loot")
        self.assertIn("7 gold", result)
        self.assertEqual(state.player.gold, 12)
        # Second loot returns already searched
        result2 = apply_exploration_action(state, "loot")
        self.assertIn("already searched", result2.lower())

    def test_loot_without_corpse(self) -> None:
        state = self.make_state()
        state.room_id = "barracks"
        state.flags["defeated_rooms"] = ["barracks"]
        state.flags.pop("corpses", None)
        result = apply_exploration_action(state, "loot")
        self.assertIn("nothing here to loot", result.lower())

    def test_loot_all_corpses(self) -> None:
        state = self.make_state()
        state.room_id = "cellar"
        state.flags["defeated_rooms"] = ["cellar"]
        state.flags["corpses"] = {
            "cellar": [
                {"id": 1, "name": "Big Rats", "looted": False},
                {"id": 2, "name": "Big Rats", "looted": False},
            ]
        }
        result = apply_exploration_action(state, "loot all")
        self.assertIn("corpse", result.lower())

    def test_use_potion_heals_most_wounded(self) -> None:
        state = self.make_state()
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        state.player.hp = 10
        state.companion.hp = 3
        with patch("app.rules.dice.roll_die", return_value=4):
            used, result = use_item(state, "potion")
        self.assertTrue(used)
        self.assertIn("healing", result.lower())
        self.assertGreater(state.companion.hp, 3)
        self.assertEqual(state.inventory, [])

    def test_use_potion_on_player(self) -> None:
        state = self.make_state()
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        state.player.hp = 6
        state.companion.hp = 9
        with patch("app.rules.dice.roll_die", return_value=3):
            used, result = use_item(state, "potion", "me")
        self.assertTrue(used)
        self.assertIn("healing", result.lower())
        self.assertGreater(state.player.hp, 6)
        self.assertEqual(state.inventory, [])

    def test_use_potion_on_companion(self) -> None:
        state = self.make_state()
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        state.player.hp = 12
        state.companion.hp = 4
        with patch("app.rules.dice.roll_die", return_value=2):
            used, result = use_item(state, "potion", "mara")
        self.assertTrue(used)
        self.assertIn("healing", result.lower())
        self.assertGreater(state.companion.hp, 4)
        self.assertEqual(state.inventory, [])

    def test_potion_revives_downed_companion(self) -> None:
        state = self.make_state()
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        state.companion.hp = 0
        with patch("app.rules.dice.roll_die", return_value=3):
            used, result = use_item(state, "potion", state.companion.name)
        self.assertTrue(used)
        self.assertIn("healing", result.lower())
        self.assertGreater(state.companion.hp, 0)
        self.assertEqual(state.inventory, [])

    def test_untargeted_potion_prioritizes_downed_companion(self) -> None:
        state = self.make_state()
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        state.player.hp = state.player.max_hp - 2
        state.companion.hp = 0
        with patch("app.rules.dice.roll_die", return_value=3):
            used, result = use_item(state, "potion")
        self.assertTrue(used)
        self.assertIn(state.companion.name, result)
        self.assertGreater(state.companion.hp, 0)

    def test_use_one_of_multiple_identical_potions(self) -> None:
        state = self.make_state()
        state.inventory = [
            item_from_id("ruined_watchtower", "healing_potion"),
            item_from_id("ruined_watchtower", "healing_potion"),
            item_from_id("ruined_watchtower", "healing_potion"),
        ]
        state.player.hp = 5
        with patch("app.rules.dice.roll_die", return_value=3):
            used, result = use_item(state, "healing potion", "me")
        self.assertTrue(used)
        self.assertIn("healing", result.lower())
        self.assertEqual(len(state.inventory), 1)
        self.assertEqual(state.inventory[0]["quantity"], 2)

    def test_potion_targets_companion_by_dynamic_name(self) -> None:
        state = self.make_state()
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        state.companion.name = "Torvald"
        state.companion.hp = 3
        with patch("app.rules.dice.roll_die", return_value=3):
            used, result = use_item(state, "healing potion", "torvald")
        self.assertTrue(used)
        self.assertIn("Torvald", result)
        self.assertGreater(state.companion.hp, 3)

    def test_potion_is_not_consumed_at_full_health(self) -> None:
        state = self.make_state()
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        state.player.hp = state.player.max_hp
        used, result = use_item(state, "healing potion", "me")
        self.assertFalse(used)
        self.assertIn("full health", result.lower())
        self.assertEqual(len(state.inventory), 1)

    def test_use_item_missing(self) -> None:
        state = self.make_state()
        used, result = use_item(state, "potion")
        self.assertFalse(used)
        self.assertIn("don't have", result.lower())

    def test_inventory_limit_blocks_general_item(self) -> None:
        state = self.make_state()
        state.inventory_limit = 1
        first = item_from_id("ruined_watchtower", "leather_cap")
        second = item_from_id("ruined_watchtower", "worn_boots")
        added, _ = add_item_to_inventory(state, first)
        self.assertTrue(added)
        added, message = add_item_to_inventory(state, second)
        self.assertFalse(added)
        self.assertIn("full", message.lower())

    def test_inventory_limit_allows_quest_item(self) -> None:
        state = self.make_state()
        state.inventory_limit = 0
        quest = item_from_id("ruined_watchtower", "silver_locket")
        added, _ = add_item_to_inventory(state, quest)
        self.assertTrue(added)

    def test_stackable_item_can_join_stack_when_pack_is_full(self) -> None:
        state = self.make_state()
        state.inventory_limit = 1
        potion = item_from_id("ruined_watchtower", "healing_potion")
        added, _ = add_item_to_inventory(state, potion)
        self.assertTrue(added)
        added, _ = add_item_to_inventory(state, potion)
        self.assertTrue(added)
        self.assertEqual(len(state.inventory), 1)
        self.assertEqual(state.inventory[0]["quantity"], 2)

    def test_consumable_stack_limit_rejects_excess_purchase(self) -> None:
        state = self.make_state()
        potion = item_from_id("ruined_watchtower", "healing_potion")
        potion["quantity"] = 9
        state.inventory = [potion]
        state.player.gold = 100
        accepted, message = buy_healing_potions(state, 3)
        self.assertFalse(accepted)
        self.assertIn("at most 10", message)
        self.assertEqual(state.inventory[0]["quantity"], 9)
        self.assertEqual(state.player.gold, 100)

    def test_buy_potions_adds_to_stack_and_spends_gold(self) -> None:
        state = self.make_state()
        state.player.gold = 30
        state.inventory = [item_from_id("ruined_watchtower", "healing_potion")]
        accepted, message = buy_healing_potions(state, 3)
        self.assertTrue(accepted)
        self.assertIn("24 gold", message)
        self.assertEqual(state.player.gold, 6)
        self.assertEqual(state.inventory[0]["quantity"], 4)

    def test_sell_equipment_adds_gold(self) -> None:
        state = self.make_state()
        armor = item_from_id("ruined_watchtower", "leather_cap")
        state.inventory = [armor]
        accepted, message = sell_item(state, "leather cap")
        self.assertTrue(accepted)
        self.assertIn("8 gold", message)
        self.assertEqual(state.player.gold, 8)
        self.assertEqual(state.inventory, [])

    def test_shop_weapon_can_be_bought_and_equipped(self) -> None:
        state = self.make_state()
        state.player.gold = 40
        accepted, _ = buy_shop_item(state, "duelist_knife")
        self.assertTrue(accepted)
        self.assertEqual(state.player.gold, 12)
        equipped, _ = equip_item(state, "duelist's knife")
        self.assertTrue(equipped)
        self.assertEqual(state.equipment["weapon"]["id"], "duelist_knife")
        self.assertEqual(equipped_damage(state), "1d6+1")

    def test_drop_item_frees_inventory_space(self) -> None:
        state = self.make_state()
        armor = item_from_id("ruined_watchtower", "leather_cap")
        state.inventory = [armor]
        dropped, message = drop_item(state, "leather cap")
        self.assertTrue(dropped)
        self.assertIn("drop", message.lower())
        self.assertEqual(state.inventory, [])

    def test_quest_item_cannot_be_dropped(self) -> None:
        state = self.make_state()
        quest = item_from_id("ruined_watchtower", "silver_locket")
        state.inventory = [quest]
        dropped, message = drop_item(state, "silver locket")
        self.assertFalse(dropped)
        self.assertIn("cannot", message.lower())
        self.assertEqual(state.inventory, [quest])

    def test_greyfen_item_drop_chance_can_yield_only_gold(self) -> None:
        from app.rules.inventory import roll_loot

        with patch("app.rules.inventory.roll_dice", return_value=(5, "5")), patch(
            "app.rules.inventory.roll_die", return_value=100
        ):
            gold, item_id = roll_loot("embers_of_greyfen", "Thornbound Dead")
        self.assertEqual(gold, 5)
        self.assertIsNone(item_id)

    def test_equipment_slots_initialized(self) -> None:
        state = self.make_state()
        for slot in ["head", "arms", "hands", "chest", "legs", "feet"]:
            self.assertIn(slot, state.equipment)
            self.assertIsNone(state.equipment[slot])

    def test_equip_and_unequip_armor(self) -> None:
        state = self.make_state()
        armor = {"id": "iron_helm", "name": "Iron Helm", "kind": "armor", "slot": "head"}
        state.inventory.append(armor)
        equipped, result = equip_item(state, "iron helm")
        self.assertTrue(equipped)
        self.assertIn("equipped", result.lower())
        self.assertIs(state.equipment["head"], armor)
        self.assertNotIn(armor, state.inventory)
        removed, result = unequip_item(state, "head")
        self.assertTrue(removed)
        self.assertIn("removed", result.lower())
        self.assertIn(armor, state.inventory)

    def test_equipping_armor_updates_ac(self) -> None:
        state = self.make_state()
        base_ac = state.player.ac
        armor = {
            "id": "leather_cap",
            "name": "Leather Cap",
            "kind": "armor",
            "slot": "head",
            "effect": {"type": "ac", "bonus": 1},
        }
        state.inventory.append(armor)
        equipped, _ = equip_item(state, "leather cap")
        self.assertTrue(equipped)
        self.assertEqual(state.player.ac, base_ac + 1)
        removed, _ = unequip_item(state, "head")
        self.assertTrue(removed)
        self.assertEqual(state.player.ac, base_ac)

    def test_equip_by_index(self) -> None:
        state = self.make_state()
        first = {"id": "cap_a", "name": "Leather Cap", "kind": "armor", "slot": "head"}
        second = {"id": "cap_b", "name": "Leather Cap", "kind": "armor", "slot": "head"}
        state.inventory.extend([first, second])
        equipped, _ = equip_item(state, "2")
        self.assertTrue(equipped)
        self.assertIs(state.equipment["head"], second)

    def test_defend_prevents_hit(self) -> None:
        state = self.make_state()
        state.enemies = [create_enemy("ruined_watchtower", "Watchtower Bandit")]
        state.player.hp = 5
        state.companion.hp = 10
        state.player_defending = True
        with patch("app.rules.combat.roll_die", return_value=12):
            results = apply_enemy_action(state)
        self.assertTrue(any("misses" in item.lower() for item in results))

    def test_end_combat_enemy_down(self) -> None:
        state = self.make_state()
        state.in_combat = True
        state.room_id = "barracks"
        state.enemies = [create_enemy("ruined_watchtower", "Watchtower Bandit")]
        state.enemies[0].hp = 0
        result = end_combat_if_needed(state)
        self.assertIn("foes fall", result.lower())
        self.assertIn("corpses:", result.lower())
        self.assertFalse(state.in_combat)
        self.assertIn("barracks", state.flags.get("defeated_rooms", []))
        self.assertEqual(state.enemies, [])

    def test_end_combat_player_down(self) -> None:
        state = self.make_state()
        state.in_combat = True
        state.enemies = [create_enemy("ruined_watchtower", "Watchtower Bandit")]
        state.player.hp = 0
        result = end_combat_if_needed(state)
        self.assertIn("collapse", result.lower())
        self.assertTrue(state.game_over)

    def test_caster_companion_casts_spell(self) -> None:
        caster_profile = CompanionProfile(
            companion_id="eldrin",
            name="Eldrin",
            hp=8,
            max_hp=8,
            ac=12,
            attack_bonus=1,
            damage="1d4+1",
            mana=6,
            max_mana=6,
            spells=["Spark", "Magic Missile"],
        )
        companion = create_companion_from_profile(caster_profile)
        state = GameState(
            campaign_id="ruined_watchtower",
            player=create_player("Hero", "Fighter", {"STR": 2, "DEX": 2, "INT": 0}),
            room_id="barracks",
            companions=[companion],
        )
        state.enemies = [create_enemy("ruined_watchtower", "Watchtower Bandit")]
        with patch("app.rules.combat.roll_die", side_effect=[12, 3]):
            result = apply_companion_action(state)
        self.assertIn("Magic Missile", result)
        self.assertEqual(companion.mana, 4)

    def test_wizard_spark_uses_mana(self) -> None:
        wizard = create_player("Mage", "Wizard", {"STR": 0, "DEX": 1, "INT": 2})
        state = GameState(
            campaign_id="ruined_watchtower",
            player=wizard,
            room_id="barracks",
            companions=[create_companion("ruined_watchtower")],
        )
        state.enemies = [create_enemy("ruined_watchtower", "Watchtower Bandit")]
        with patch("app.rules.combat.roll_die", side_effect=[12, 2]):
            result = apply_player_action(state, "special")
        self.assertIn("Spark", result)
        self.assertEqual(state.player.mana, state.player.max_mana - 2)

    def test_apply_race_mods_noop_for_human(self) -> None:
        stats = {"STR": 1, "DEX": 2, "INT": 3}
        result = apply_race_mods(stats, "Human")
        self.assertEqual(result["STR"], 1)
        self.assertEqual(result["DEX"], 2)
        self.assertEqual(result["INT"], 3)
        self.assertEqual(result.get("CON", 0), 0)

    def test_normalize_action_strips_filler(self) -> None:
        self.assertEqual(normalize_action("go to the cellar"), "go cellar")
        self.assertEqual(normalize_action("move to barracks"), "move barracks")

    def test_mana_regen_caps_at_max(self) -> None:
        wizard = create_player("Mage", "Wizard", {"STR": 0, "DEX": 1, "INT": 2})
        wizard.mana = wizard.max_mana - 1
        state = GameState(
            campaign_id="ruined_watchtower",
            player=wizard,
            room_id="barracks",
            companions=[create_companion("ruined_watchtower")],
        )
        gained = regen_mana(state, 2)
        self.assertEqual(gained, 1)
        self.assertEqual(state.player.mana, state.player.max_mana)

    def test_rest_heals_every_two_consecutive(self) -> None:
        wizard = create_player("Mage", "Wizard", {"STR": 0, "DEX": 1, "INT": 2})
        wizard.hp = wizard.max_hp - 1
        state = GameState(
            campaign_id="ruined_watchtower",
            player=wizard,
            room_id="courtyard",
            companions=[create_companion("ruined_watchtower")],
        )
        first = apply_rest(state)
        self.assertIn("rest", first.lower())
        self.assertEqual(state.player.hp, wizard.max_hp - 1)
        self.assertEqual(state.rest_streak, 1)
        second = apply_rest(state)
        self.assertIn("rest", second.lower())
        self.assertEqual(state.player.hp, wizard.max_hp)
        self.assertEqual(state.rest_streak, 0)

    def test_rest_heals_companion_every_two_consecutive(self) -> None:
        player = create_player("Hero", "Fighter", {"STR": 2, "DEX": 2, "INT": 0})
        companion = create_companion("ruined_watchtower")
        companion.hp = companion.max_hp - 1
        state = GameState(
            campaign_id="ruined_watchtower",
            player=player,
            room_id="courtyard",
            companions=[companion],
        )
        apply_rest(state)
        self.assertEqual(companion.hp, companion.max_hp - 1)
        result = apply_rest(state)
        self.assertIn("HP +1", result)
        self.assertEqual(companion.hp, companion.max_hp)

    def test_grant_xp_level_up(self) -> None:
        state = self.make_state()
        state.player.xp = 0
        state.player.level = 1
        msgs = grant_xp(state, 100)
        self.assertEqual(state.player.xp, 100)
        self.assertEqual(state.player.level, 2)
        self.assertIn("Level up", msgs[0])
        self.assertEqual(state.player.unspent_attribute_points, 2)
        self.assertEqual(state.player.unspent_class_upgrades, 1)

    def test_wizard_level_up_moves_choices_to_hub(self) -> None:
        wizard = create_player("Mage", "Wizard", {"STR": 0, "DEX": 1, "INT": 2})
        state = GameState(
            campaign_id="ruined_watchtower",
            player=wizard,
            room_id="courtyard",
            companions=[create_companion("ruined_watchtower")],
        )
        state.player.xp = 0
        state.player.level = 1
        grant_xp(state, 100)
        self.assertEqual(state.player.level, 2)
        self.assertEqual(state.pending_level_choices, [])
        self.assertEqual(state.player.unspent_attribute_points, 2)
        self.assertEqual(state.player.unspent_class_upgrades, 1)

    def test_progression_applies_attributes_and_upgrade_atomically(self) -> None:
        state = self.make_state()
        state.player.unspent_attribute_points = 2
        state.player.unspent_class_upgrades = 1
        old_hp = state.player.max_hp
        old_attack = state.player.attack_bonus
        old_con = state.player.stats["CON"]
        accepted, message = apply_progression_choices(
            state, {"CON": 1, "STR": 1}, "precision"
        )
        self.assertTrue(accepted)
        self.assertIn("confirmed", message.lower())
        self.assertEqual(state.player.stats["CON"], old_con + 1)
        self.assertEqual(state.player.max_hp, old_hp + 1)
        self.assertEqual(state.player.attack_bonus, old_attack + 1)
        self.assertEqual(state.player.unspent_attribute_points, 0)
        self.assertEqual(state.player.unspent_class_upgrades, 0)

    def test_progression_rejects_attribute_above_cap_without_changes(self) -> None:
        state = self.make_state()
        state.player.stats["STR"] = 6
        state.player.unspent_attribute_points = 2
        before = dict(state.player.stats)
        accepted, message = apply_progression_choices(state, {"STR": 1}, "")
        self.assertFalse(accepted)
        self.assertIn("cannot exceed", message.lower())
        self.assertEqual(state.player.stats, before)
        self.assertEqual(state.player.unspent_attribute_points, 2)

    def test_caster_can_learn_spell_as_class_upgrade(self) -> None:
        wizard = create_player("Mage", "Wizard", {"STR": 0, "DEX": 1, "INT": 2})
        wizard.unspent_class_upgrades = 1
        state = GameState(
            campaign_id="ruined_watchtower",
            player=wizard,
            room_id="courtyard",
            companions=[create_companion("ruined_watchtower")],
        )
        accepted, _ = apply_progression_choices(state, {}, "learn:Magic Missile")
        self.assertTrue(accepted)
        self.assertIn("Magic Missile", state.player.learned_spells)

    def test_rest_resolves_pending_spell_choice(self) -> None:
        wizard = create_player("Mage", "Wizard", {"STR": 0, "DEX": 1, "INT": 2})
        wizard.level = 2
        state = GameState(
            campaign_id="ruined_watchtower",
            player=wizard,
            room_id="courtyard",
            companions=[create_companion("ruined_watchtower")],
        )
        state.pending_level_choices = [
            {"type": "spell", "choices": ["Magic Missile", "Shield"], "level": 2}
        ]
        with patch("app.rules.rest.prompt_choice", return_value="Magic Missile"):
            result = apply_rest(state)
        self.assertIn("Magic Missile", state.player.learned_spells)
        self.assertEqual(len(state.pending_level_choices), 0)
        self.assertIn("You learn Magic Missile", result)

    def test_xp_for_level(self) -> None:
        self.assertEqual(xp_for_level(1), 0)
        self.assertEqual(xp_for_level(2), 100)
        self.assertEqual(level_from_xp(99), 1)
        self.assertEqual(level_from_xp(100), 2)

    def test_strip_quest_items_on_victory(self) -> None:
        state = self.make_state()
        state.campaign_id = "ruined_watchtower"
        state.game_over = True
        state.player.hp = 10
        quest_item = item_from_id("ruined_watchtower", "silver_locket")
        state.inventory.append(quest_item)
        strip_campaign_quest_items(state)
        self.assertNotIn(quest_item, state.inventory)
        ids = [i.get("id") for i in state.inventory if isinstance(i, dict)]
        self.assertNotIn("silver_locket", ids)

    def test_rest_streak_resets_on_non_rest(self) -> None:
        wizard = create_player("Mage", "Wizard", {"STR": 0, "DEX": 1, "INT": 2})
        state = GameState(
            campaign_id="ruined_watchtower",
            player=wizard,
            room_id="courtyard",
            companions=[create_companion("ruined_watchtower")],
        )
        apply_rest(state)
        self.assertEqual(state.rest_streak, 1)
        reset_rest_streak(state)
        self.assertEqual(state.rest_streak, 0)

    def test_cautious_companion_covers_wounded_player(self) -> None:
        state = self.make_state()
        state.player.hp = 2
        state.companion.tactic = "cautious"
        state.enemies = [create_enemy("ruined_watchtower", "Watchtower Bandit")]
        result = apply_companion_action(state)
        self.assertIn("covers", result.lower())
        self.assertTrue(state.player_defending)
        self.assertTrue(state.companion_defending)

    def test_companion_scaling_is_modest_and_archetype_aware(self) -> None:
        eldrin = create_companion("embers_of_greyfen", "eldrin")
        scale_companion_for_level(eldrin, 6)
        self.assertEqual(eldrin.max_hp, 14)
        self.assertEqual(eldrin.ac, 13)
        self.assertEqual(eldrin.attack_bonus, 4)
        self.assertEqual(eldrin.max_mana, 12)

    def test_fighter_guard_intercepts_companion_attack(self) -> None:
        state = self.make_state()
        state.campaign_id = "embers_of_greyfen"
        state.room_id = "marsh_path"
        state.enemies = create_enemies("embers_of_greyfen", "Bog Hounds")[:1]
        state.companion.hp = 1
        companion_hp = state.companion.hp
        player_hp = state.player.hp
        apply_player_action(state, "guard_companion")
        with patch("app.rules.combat.roll_die", return_value=20), patch(
            "app.rules.dice.roll_die", return_value=2
        ):
            messages = apply_enemy_action(state)
        self.assertTrue(any("intercepts" in message for message in messages))
        self.assertEqual(state.companion.hp, companion_hp)
        self.assertLess(state.player.hp, player_hp)

    def test_ordinary_enemy_group_spreads_attacks(self) -> None:
        state = self.make_state()
        state.campaign_id = "embers_of_greyfen"
        state.room_id = "marsh_path"
        state.enemies = create_enemies("embers_of_greyfen", "Bog Hounds")
        player_hp = state.player.hp
        companion_hp = state.companion.hp
        with patch("app.rules.combat.roll_die", return_value=20), patch(
            "app.rules.dice.roll_die", return_value=1
        ):
            apply_enemy_action(state)
        self.assertLess(state.player.hp, player_hp)
        self.assertLess(state.companion.hp, companion_hp)

    def test_aggressive_companion_targets_strongest_enemy(self) -> None:
        state = self.make_state()
        state.companion.tactic = "aggressive"
        weak = create_enemy("ruined_watchtower", "Watchtower Bandit")
        strong = create_enemy("ruined_watchtower", "Watchtower Bandit")
        weak.hp = 2
        strong.hp = 10
        state.enemies = [weak, strong]
        with patch("app.rules.combat.roll_die", return_value=20), patch(
            "app.rules.dice.roll_die", return_value=2
        ):
            apply_companion_action(state)
        self.assertEqual(weak.hp, 2)
        self.assertLess(strong.hp, 10)


if __name__ == "__main__":
    unittest.main()
