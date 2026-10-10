"""Campaign-boundary regressions verified from PR review findings."""
import json
import unittest
from unittest.mock import mock_open, patch

from app.characters import load_character
from app.engine import HeadlessEngine


class CampaignBoundaryTests(unittest.TestCase):
    def test_fresh_campaign_clears_conditions_without_altering_saved_source(self):
        source = HeadlessEngine.new()
        source.state.player.conditions = {"poisoned": 2}
        source.state.companion.conditions = {"poisoned": 1}
        saved = source.state.to_dict()
        fresh = HeadlessEngine.from_adventurer(source.state, campaign_id="lost_crypt")
        self.assertEqual(fresh.state.player.conditions, {})
        self.assertEqual(fresh.state.companion.conditions, {})
        self.assertEqual(source.state.to_dict(), saved)
        self.assertEqual(HeadlessEngine.restore(saved).state.player.conditions, {"poisoned": 2})

    def test_cli_roster_starts_clean_but_does_not_rewrite_source(self):
        state = HeadlessEngine.new().state
        state.player.conditions = {"poisoned": 2}
        data = {**state.player.to_dict(), "inventory": state.inventory, "equipment": state.equipment}
        with patch("app.characters.character_file_path", return_value="unused.json"), patch("builtins.open", mock_open(read_data=json.dumps(data))) as opened:
            player, _, _ = load_character("Adventurer")
        self.assertEqual(player.conditions, {})
        opened.assert_called_once_with("unused.json", "r", encoding="utf-8")

    def test_automatic_challenge_preserves_guidance(self):
        engine = HeadlessEngine.new()
        engine.state.room_id = "collapsed_passage"
        engine.state.flags.update({"guidance_active": True, "detect_magic:collapsed_passage": True})
        with patch("app.rules.challenges.check") as check:
            self.assertTrue(engine.execute("challenge", target="arcane_support").accepted)
        check.assert_not_called()
        self.assertTrue(engine.state.flags.get("guidance_active"))

    def test_rolled_challenge_consumes_guidance_and_reports_bonus(self):
        engine = HeadlessEngine.new()
        engine.state.room_id = "collapsed_passage"
        engine.state.flags["guidance_active"] = True
        with patch("app.rules.challenges.check", return_value=(True, 20, 24)) as check:
            result = engine.execute("challenge", target="clear_debris")
        self.assertTrue(result.accepted)
        check.assert_called_once_with(engine.state.player.stats["STR"] + 2, 11)
        self.assertFalse(engine.state.flags.get("guidance_active"))
        self.assertIn("Guidance", engine.state.last_event)

    def test_required_challenge_disables_movement_until_resolved(self):
        engine = HeadlessEngine.new()
        engine.state.room_id = "collapsed_passage"
        moves = [action for action in engine.available_actions() if action["id"] == "move"]
        self.assertTrue(moves)
        self.assertTrue(all(action.get("disabled") and action.get("disabled_reason") for action in moves))
        engine.state.flags["challenge_resolved:collapsed_passage"] = True
        moves = [action for action in engine.available_actions() if action["id"] == "move"]
        self.assertTrue(moves)
        self.assertTrue(all(not action.get("disabled") for action in moves))

    def test_optional_challenge_does_not_disable_movement(self):
        engine = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        engine.state.room_id = "refuge"
        moves = [action for action in engine.available_actions() if action["id"] == "move"]
        self.assertTrue(moves)
        self.assertTrue(all(not action.get("disabled") for action in moves))


if __name__ == "__main__":
    unittest.main()
