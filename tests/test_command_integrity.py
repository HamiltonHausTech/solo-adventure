"""Regressions for authoritative command boundaries and detached snapshots."""
import copy
import unittest
from unittest.mock import patch

from app.engine import HeadlessEngine
from app.rules.combat import apply_player_action, resolve_player_action
from app.rules.exploration import apply_exploration_action
from app.state import Enemy


class CommandIntegrityTests(unittest.TestCase):
    def engine(self, combat=True):
        engine = HeadlessEngine.new(name="Rowan", player_class="Cleric")
        state = engine.state
        state.in_combat = combat
        state.enemies = [Enemy("Dead", 0, 10, 1, 0, "1d1"), Enemy("Living", 10, 10, 1, 0, "1d1")]
        state.player_defending = state.companion_defending = True
        state.player_guarding_companion = state.player_shield_active = True
        state.player_bless_active = state.companion_bless_active = True
        state.flags["prepared_strike"] = 2
        return engine

    def test_enemy_snapshot_id_resolves_original_slot(self):
        engine = self.engine()
        target = str(engine.snapshot()["enemies"][0]["id"])
        with patch("app.rules.combat.roll_die", return_value=20), patch("app.rules.combat.roll_dice", return_value=(1, "1")):
            message = apply_player_action(engine.state, "attack", target)
        self.assertIn("Hit Living", message)
        self.assertEqual(engine.state.enemies[1].hp, 9)

    def test_engine_enemy_id_is_accepted(self):
        engine = self.engine()
        with patch.object(engine, "_resolve_other_combatants", return_value=[]):
            self.assertTrue(engine.execute("attack", target="2").accepted)

    def test_rejected_actions_preserve_entire_state(self):
        cases = [("attack", "1", None), ("attack", "999", None), ("attack", "missing", None),
                 ("cast", "2", "Unknown"), ("cast", "me", "Cure Wounds"),
                 ("cast", "missing", "Bless"), ("special", None, None)]
        for command, target, spell in cases:
            for direct in (False, True):
                with self.subTest(command=command, target=target, spell=spell, direct=direct):
                    engine = self.engine()
                    if command == "special":
                        engine.state.player.mana = 0
                    before = copy.deepcopy(engine.state.to_dict())
                    if direct:
                        apply_player_action(engine.state, "special" if command == "cast" else command, target, spell)
                    else:
                        result = engine.execute(command, target=target, spell=spell)
                        self.assertFalse(result.accepted)
                        self.assertEqual(result.events, [])
                    self.assertEqual(engine.state.to_dict(), before)

    def test_malformed_targets_reject_without_exception_or_mutation(self):
        for target in ([], {}, 2, True, "²", "9" * 5000):
            for direct in (True, False):
                with self.subTest(target=str(target)[:30], direct=direct):
                    engine = self.engine()
                    before = copy.deepcopy(engine.state.to_dict())
                    if direct:
                        apply_player_action(engine.state, "attack", target)
                    else:
                        self.assertFalse(engine.execute("attack", target=target).accepted)
                    self.assertEqual(engine.state.to_dict(), before)

    def test_healing_targets_shared_in_both_phases(self):
        for combat in (False, True):
            for target in (None, "companion", "her", "him", "Mira", "mir"):
                with self.subTest(combat=combat, target=target):
                    engine = self.engine(combat)
                    engine.state.companion.name = "Mira"
                    engine.state.companion.hp = 1
                    with patch.object(engine, "_resolve_other_combatants", return_value=[]), patch("app.rules.combat.roll_dice", return_value=(3, "3")):
                        result = engine.execute("cast", spell="Cure Wounds", target=target)
                    self.assertTrue(result.accepted, result.error)
                    self.assertEqual(engine.state.companion.hp, 4)

    def test_heal_player_name_and_default_most_wounded(self):
        for target in (None, "Rowan", "row", "self", "me", "player", "you", "myself"):
            engine = self.engine(False)
            engine.state.player.hp = 1
            with patch("app.rules.combat.roll_dice", return_value=(3, "3")):
                apply_player_action(engine.state, "special", target, "Cure Wounds")
            self.assertEqual(engine.state.player.hp, 4, target)

    def test_healing_never_revives_or_spends_on_invalid_target(self):
        for target, hp in (("companion", 0), ("me", 0), ("missing", 1), ("companion", 999)):
            for direct in (False, True):
                engine = self.engine(False)
                actor = engine.state.player if target == "me" else engine.state.companion
                actor.hp = hp if hp != 999 else actor.max_hp
                before = copy.deepcopy(engine.state.to_dict())
                if direct:
                    apply_player_action(engine.state, "special", target, "Cure Wounds")
                else:
                    self.assertFalse(engine.execute("cast", target=target, spell="Cure Wounds").accepted)
                self.assertEqual(engine.state.to_dict(), before)

    def test_corpse_ids_are_persistent_not_filtered_positions(self):
        for direct in (False, True):
            engine = self.engine(False)
            state = engine.state
            state.room_id = "barracks"
            state.flags["defeated_rooms"] = ["barracks"]
            entries = [{"id": 4, "name": "Watchtower Bandit", "looted": True},
                       {"id": 7, "name": "Watchtower Bandit", "looted": False}]
            state.flags["corpses"] = {"barracks": entries}
            with patch("app.rules.exploration.roll_loot", return_value=(1, None)):
                if direct:
                    apply_exploration_action(state, "loot 7")
                else:
                    self.assertTrue(engine.execute("loot", target="7").accepted)
            self.assertTrue(entries[1]["looted"])

    def test_snapshot_and_serialization_are_detached(self):
        engine = self.engine(False)
        state = engine.state
        state.flags["nested"] = {"values": [1]}
        state.response_log = [{"data": [1]}]
        state.pending_level_choices = [{"type": "attribute", "options": ["STR"]}]
        before = copy.deepcopy(state.to_dict())
        snapshot = engine.snapshot()
        snapshot["player"]["stats"]["STR"] = 99
        snapshot["inventory"][0]["quantity"] = 99
        snapshot["flags"]["nested"]["values"].append(2)
        snapshot["save"]["response_log"][0]["data"].append(2)
        snapshot["save"]["pending_level_choices"][0]["options"].append("DEX")
        self.assertEqual(state.to_dict(), before)
        saved = state.to_dict()
        state.flags["nested"]["values"].append(3)
        self.assertEqual(saved["flags"]["nested"]["values"], [1])

    def test_typed_rejections_do_not_roll_or_mutate(self):
        for action, target, spell in (("special", "missing", "Bless"),
                                     ("special", "companion", "Shield"),
                                     ("special", "1", "Sleep"),
                                     ("special", "1", "Sacred Flame"),
                                     ("special", None, "Detect Magic"),
                                     ("unknown", None, None)):
            engine = self.engine()
            engine.state.player.learned_spells.extend(["Bless", "Shield", "Sleep", "Detect Magic"])
            before = copy.deepcopy(engine.state.to_dict())
            with patch("app.rules.combat.roll_die") as die, patch("app.rules.combat.roll_dice") as dice:
                result = resolve_player_action(engine.state, action, target, spell)
                self.assertFalse(result.accepted, (action, target, spell))
                die.assert_not_called()
                dice.assert_not_called()
            self.assertEqual(engine.state.to_dict(), before)

    def test_heal_default_skips_fallen_ally(self):
        engine = self.engine(False)
        engine.state.player.hp -= 5
        engine.state.companion.hp = 0
        before_hp = engine.state.player.hp
        with patch("app.rules.combat.roll_dice", return_value=(3, "3")):
            result = engine.execute("cast", spell="Cure Wounds")
        self.assertTrue(result.accepted)
        self.assertEqual(engine.state.player.hp, before_hp + 3)
        self.assertEqual(engine.state.companion.hp, 0)

    def test_invalid_corpse_ids_preserve_state(self):
        for target in ("1", "4", "²", "9" * 5000):
            engine = self.engine(False)
            engine.state.room_id = "barracks"
            engine.state.flags["defeated_rooms"] = ["barracks"]
            engine.state.flags["corpses"] = {"barracks": [
                {"id": 4, "name": "Bandit", "looted": True},
                {"id": 7, "name": "Bandit", "looted": False}]}
            before = copy.deepcopy(engine.state.to_dict())
            result = engine.execute("loot", target=target)
            self.assertFalse(result.accepted)
            apply_exploration_action(engine.state, f"loot {target}")
            self.assertEqual(engine.state.to_dict(), before)

    def test_restore_and_revision_metadata_are_detached(self):
        engine = self.engine(False)
        engine.state.adventurer_id = "test-adventurer"
        engine.state.adventurer_revision = 3
        engine.state.flags["nested"] = {"values": [1]}
        payload = engine.state.to_dict()
        restored = HeadlessEngine.restore(payload)
        self.assertEqual(restored.state.adventurer_revision, 3)
        self.assertEqual(restored.snapshot()["save"]["adventurer_revision"], 3)
        restored.state.flags["nested"]["values"].append(2)
        restored.state.player.learned_spells.append("Shield")
        self.assertEqual(payload["flags"]["nested"]["values"], [1])
        self.assertNotIn("Shield", payload["player"]["learned_spells"])
        fresh = HeadlessEngine.from_adventurer(engine.state, campaign_id=engine.state.campaign_id)
        self.assertEqual(fresh.state.adventurer_revision, 3)
        self.assertEqual(fresh.state.adventurer_id, "test-adventurer")
        payload.pop("adventurer_revision")
        self.assertIsNone(HeadlessEngine.restore(payload).state.adventurer_revision)

    def test_command_result_serialization_does_not_mutate_history(self):
        engine = self.engine(False)
        result = engine.execute("inspect")
        before = copy.deepcopy(result.state)
        payload = result.to_dict()
        payload["state"]["player"]["hp"] = 0
        self.assertEqual(result.state, before)


if __name__ == "__main__":
    unittest.main()
