"""CLI parity tests: real engine, fake terminal/narration/persistence."""
import io
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch

from app import main as cli
from app.engine import HeadlessEngine


class CLIEngineTests(unittest.TestCase):
    def setUp(self):
        self.contexts = ExitStack()
        self.addCleanup(self.contexts.close)
        self.enterContext = self.contexts.enter_context
        self.output = io.StringIO()
        self.enterContext(redirect_stdout(self.output))
        self.real_save_game = cli.save_game
        self.save = self.enterContext(patch("app.main.save_game"))
        self.enterContext(patch("app.main.companion_suggest", return_value="Keep going."))
        self.enterContext(patch("app.main.gm_narrate_with_source", return_value=("Narration", "stub")))
        self.enterContext(patch("app.rules.dice.roll_die", return_value=4))
        self.enterContext(patch("app.rules.combat.roll_die", return_value=1))

    def act(self, state, text, last_input="previous"):
        with patch("builtins.input", return_value=text):
            handler = cli.handle_combat if state.in_combat else cli.handle_exploration
            return handler(state, None, last_input)

    def assert_gameplay_equal(self, left, right):
        # UUIDs in engine events are not game state; commands/logs are authoritative.
        self.assertEqual(left.to_dict(), right.to_dict())

    def test_required_challenge_movement_matches_headless(self):
        direct = HeadlessEngine.new()
        direct.execute("move", target="collapsed_passage")
        state = HeadlessEngine.restore(direct.state.to_dict()).state
        before = state.to_dict()
        self.assertFalse(direct.execute("move", target="cellar").accepted)
        self.act(state, "go to the cellar")
        self.assertEqual(state.to_dict(), before)
        self.assert_gameplay_equal(state, direct.state)
        self.save.assert_not_called()
        self.assertIn("challenge before moving", self.output.getvalue())
        self.assertIn("challenge clear_debris", self.output.getvalue())
        self.assertTrue(direct.execute("challenge", target="clear_debris").accepted)
        self.act(state, "challenge clear_debris")
        self.assert_gameplay_equal(state, direct.state)
        direct.execute("move", target="cellar")
        self.act(state, "move cellar")
        self.assert_gameplay_equal(state, direct.state)
        self.assertTrue(state.in_combat)

    def test_poison_ticks_for_combat_actions_and_items(self):
        for text, command, kwargs in [
            ("defend", "defend", {}),
            ("use potion on me", "use", {"item": "potion", "target": "me"}),
        ]:
            with self.subTest(text=text):
                direct = HeadlessEngine.new()
                direct.execute("move", target="barracks")
                direct.state.player.hp -= 4
                direct.state.player.conditions["poisoned"] = 2
                state = HeadlessEngine.restore(direct.state.to_dict()).state
                result = direct.execute(command, **kwargs)
                self.assertTrue(result.accepted)
                self.act(state, text)
                self.assert_gameplay_equal(state, direct.state)
                self.assertEqual(state.player.conditions["poisoned"], 1)
                self.assertIn("poison courses", state.last_event.lower())

    def test_multiword_targeted_cure_wounds_matches_headless(self):
        for combat in (False, True):
            for text in ("cast cure wounds on Torvald", "cast cure wounds Torvald", "cure wounds Torvald"):
                with self.subTest(combat=combat, text=text):
                    direct = HeadlessEngine.new(player_class="Cleric", companion_id="torvald")
                    if combat:
                        direct.execute("move", target="barracks")
                    direct.state.companion.hp -= 6
                    state = HeadlessEngine.restore(direct.state.to_dict()).state
                    before_hp = state.companion.hp
                    result = direct.execute("cast", spell="Cure Wounds", target="torvald")
                    self.assertTrue(result.accepted)
                    self.act(state, text)
                    self.assert_gameplay_equal(state, direct.state)
                    self.assertGreater(state.companion.hp, before_hp)

    def test_exploration_gear_and_rest_match_headless(self):
        direct = HeadlessEngine.new()
        state = HeadlessEngine.restore(direct.state.to_dict()).state
        for text, command, kwargs in [
            ("talk", "talk", {}),
            ("search", "search", {}),
            ("equip leather cap", "equip", {"item": "leather cap"}),
            ("unequip head", "unequip", {"target": "head"}),
            ("drop worn boots", "drop", {"item": "worn boots"}),
            ("rest", "rest", {}),
        ]:
            self.assertTrue(direct.execute(command, **kwargs).accepted)
            self.act(state, text)
            self.assert_gameplay_equal(state, direct.state)
        direct.execute("rest")
        direct.execute("rest")
        self.act(state, "rest 2")
        self.assert_gameplay_equal(state, direct.state)

    def test_gear_menu_uses_engine_and_saves_each_mutation(self):
        direct = HeadlessEngine.new()
        state = HeadlessEngine.restore(direct.state.to_dict()).state
        with patch("builtins.input", side_effect=["equip leather cap", "unequip head", "back"]):
            cli.gear_menu(state)
        direct.execute("equip", item="leather cap")
        direct.execute("unequip", target="head")
        self.assert_gameplay_equal(state, direct.state)
        self.assertEqual(self.save.call_count, 2)

    def test_information_controls_do_not_spend_turn_or_save(self):
        state = HeadlessEngine.new(player_class="Cleric").state
        before = state.to_dict()
        for text in ("inventory", "status", "stats", "help", "spellbook", "challenge"):
            self.assertEqual(self.act(state, text), "previous")
        self.assertEqual(state.to_dict(), before)
        self.save.assert_not_called()
        output = self.output.getvalue()
        self.assertIn("Cure Wounds", output)
        self.assertIn("cast <spell> [on <target>]", output)
        self.assertIn("challenge <option>", output)
        self.assertIn("No valid targets", output)

    def test_rejected_combat_action_is_not_saved_or_advanced(self):
        state = HeadlessEngine.new().state
        HeadlessEngine(state).execute("move", target="barracks")
        before = state.to_dict()
        self.act(state, "dance")
        self.assertEqual(state.to_dict(), before)
        self.save.assert_not_called()

    def test_quit_saves_and_syncs_roster_without_disk_writes(self):
        state = HeadlessEngine.new().state
        with self.assertRaises(SystemExit):
            self.act(state, "quit")
        self.save.assert_called_once_with(state)
        # Test the real wrapper separately; both disk-writing endpoints are mocked.
        with patch("app.main.save_state") as save_state, patch("app.main.save_character") as save_character:
            self.real_save_game(state)
            save_state.assert_called_once_with(state, cli.SAVE_PATH)
            save_character.assert_called_once_with(state.player, state.inventory, state.equipment)
        self.assertEqual(state.turn, 0)

    def test_main_normal_flow_with_optional_narration(self):
        for narration in (True, False):
            with self.subTest(narration=narration):
                state = HeadlessEngine.new().state
                with patch("app.main.maybe_resume", return_value=state), patch("app.main.load_env_file"), patch(
                    "app.main.LLMClient"
                ) as client, patch("builtins.input", side_effect=["talk", "inventory", "quit"]):
                    with self.assertRaises(SystemExit):
                        cli.main(narration=narration)
                self.assertEqual(state.turn, 1)
                self.assertEqual(len(state.turn_log), 1)
                if narration:
                    client.assert_called_once()
                else:
                    client.assert_not_called()

    def test_poison_expires_and_fatal_tick_stops_combat(self):
        for hp in (1, 10):
            with self.subTest(hp=hp):
                direct = HeadlessEngine.new()
                direct.execute("move", target="barracks")
                direct.state.player.hp = hp
                direct.state.player.conditions["poisoned"] = 1
                state = HeadlessEngine.restore(direct.state.to_dict()).state
                direct.execute("defend")
                self.act(state, "defend")
                self.assert_gameplay_equal(state, direct.state)
                self.assertNotIn("poisoned", state.player.conditions)
                self.assertEqual(state.game_over, hp == 1)

    def test_combat_attack_and_target_display_match_engine(self):
        direct = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        direct.execute("move", target="crossroads")
        direct.execute("move", target="marsh_path")
        direct.state.enemies[0].hp = 0
        state = HeadlessEngine.restore(direct.state.to_dict()).state
        target = str(direct.snapshot()["enemies"][0]["id"])
        self.assertTrue(direct.execute("attack", target=target).accepted)
        self.act(state, f"attack {target}")
        self.assert_gameplay_equal(state, direct.state)
        self.assertIn(f"Targets: {target}", self.output.getvalue())

    def test_spell_target_can_have_multiple_words(self):
        direct = HeadlessEngine.new(player_class="Cleric")
        direct.state.companion.name = "Mara the Scout"
        direct.state.companion.hp -= 6
        state = HeadlessEngine.restore(direct.state.to_dict()).state
        self.assertTrue(direct.execute("cast", spell="Cure Wounds", target="mara the scout").accepted)
        self.act(state, "cast Cure Wounds on Mara the Scout")
        self.assert_gameplay_equal(state, direct.state)

    def test_utility_spell_reveals_challenge_control(self):
        direct = HeadlessEngine.new(campaign_id="lost_crypt", player_class="Wizard")
        direct.state.player.learned_spells.append("Detect Magic")
        direct.state.room_id = "gate"
        state = HeadlessEngine.restore(direct.state.to_dict()).state
        direct.execute("cast", spell="Detect Magic", target="me")
        self.act(state, "cast detect magic on me")
        self.assert_gameplay_equal(state, direct.state)
        direct.execute("challenge", target="trace_ward")
        self.act(state, "challenge trace_ward")
        self.assert_gameplay_equal(state, direct.state)
        self.assertIn("challenge trace_ward", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
