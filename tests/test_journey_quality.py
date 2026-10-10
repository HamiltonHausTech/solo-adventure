"""Legacy journal evidence and required-challenge objective regressions."""
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from app.content import get_room
from app.engine import HeadlessEngine
from app.rules.exploration import apply_exploration_action


class LegacyConversationTests(unittest.TestCase):
    def test_serialized_legacy_recaps_preserve_known_facts_without_rerolls(self):
        cases = [
            ("ruined_watchtower", "courtyard", "scout_helped", "social_done",
             "You win Eryn's trust. She points out a safe route and warns you about a lone bandit inside."),
            ("lost_crypt", "approach", "keeper_warned", "social_done",
             "Aldric shares what he knows. 'The lower levels hold restless dead. Bring light and steel.'"),
            ("embers_of_greyfen", "refuge", None, "nessa_spoken",
             "Nessa withholds the refuge's oldest secret, though she confirms the raiders entered Blackbriar at dusk."),
        ]
        for campaign, room, success, done, expected in cases:
            variants = [{done: True}]
            if success:
                variants = [{success: True}, {done: True, success: True}]
            for flags in variants:
                with self.subTest(campaign=campaign, flags=flags):
                    e = HeadlessEngine.new(campaign_id=campaign)
                    e.state.room_id = room
                    e.state.flags.update(flags)
                    key = f"conversation:{room}"
                    self.assertNotIn(key, e.state.flags)
                    for _ in range(2):
                        e = HeadlessEngine.restore(json.loads(json.dumps(e.state.to_dict())))
                        before = deepcopy(e.state.to_dict())
                        with patch("app.rules.exploration.check", side_effect=AssertionError("must not reroll")):
                            snap = e.snapshot()
                            entries = [x for x in snap["journey"]["journal"] if x["id"] == key]
                            self.assertEqual(entries, [{"id": key, "text": expected}])
                            self.assertTrue(next(x for x in snap["available_actions"] if x["id"] == "talk")["disabled"])
                            self.assertFalse(e.execute("talk").accepted)
                            self.assertEqual(apply_exploration_action(e.state, "talk"), expected)
                        self.assertEqual(e.state.to_dict(), before)
                        if success is None:
                            self.assertNotIn("ember_truth_known", e.state.flags)
                            self.assertNotIn("seal, not a treasure", str(snap["journey"]["journal"]))

    def test_recorded_conversation_takes_precedence_over_legacy_recap(self):
        e = HeadlessEngine.new(campaign_id="ruined_watchtower")
        e.state.flags.update(social_done=True, scout_helped=True)
        text = "You win Eryn's trust (roll 19 -> 21). She points out a safe route."
        e.state.flags["conversation:courtyard"] = text
        e = HeadlessEngine.restore(json.loads(json.dumps(e.state.to_dict())))
        self.assertEqual(e.snapshot()["journey"]["journal"], [{"id": "conversation:courtyard", "text": text}])
        self.assertEqual(apply_exploration_action(e.state, "talk"), text)

    def test_unspoken_legacy_room_has_no_recap(self):
        e = HeadlessEngine.new(campaign_id="ruined_watchtower")
        self.assertEqual(e.snapshot()["journey"]["journal"], [])
        self.assertFalse(next(x for x in e.available_actions() if x["id"] == "talk")["disabled"])


class RequiredChallengeObjectiveTests(unittest.TestCase):
    def test_required_objective_before_after_search_and_resolution(self):
        for campaign, room, option in [
            ("lost_crypt", "gate", "read_sequence"),
            ("ruined_watchtower", "collapsed_passage", "clear_debris"),
        ]:
            for success in (True, False):
                with self.subTest(campaign=campaign, success=success):
                    e = HeadlessEngine.new(campaign_id=campaign)
                    e.state.room_id = room
                    config = get_room(campaign, room).challenge_config
                    assert config is not None
                    for searched in (False, True):
                        if searched:
                            self.assertTrue(e.execute("search").accepted)
                        e = HeadlessEngine.restore(json.loads(json.dumps(e.state.to_dict())))
                        before = deepcopy(e.state.to_dict())
                        snap = e.snapshot()
                        objective = snap["journey"]["objective"]
                        self.assertEqual(objective["title"], config["title"])
                        self.assertIn(config["prompt"], objective["description"])
                        self.assertIn("before moving", objective["description"])
                        self.assertNotIn("Continue through an available exit", objective["description"])
                        moves = [x for x in snap["available_actions"] if x["id"] == "move"]
                        self.assertTrue(moves)
                        self.assertTrue(all(x["disabled"] for x in moves))
                        self.assertFalse(e.execute("move", target=moves[0]["target"]).accepted)
                        self.assertEqual(e.state.to_dict(), before)
                    with patch("app.rules.challenges.check", return_value=(success, 20 if success else 1, 22 if success else 3)):
                        self.assertTrue(e.execute("challenge", target=option).accepted)
                    e = HeadlessEngine.restore(json.loads(json.dumps(e.state.to_dict())))
                    snap = e.snapshot()
                    self.assertIsNone(snap["challenge"])
                    self.assertIn("Continue through an available exit", snap["journey"]["objective"]["description"])
                    moves = [x for x in snap["available_actions"] if x["id"] == "move"]
                    self.assertTrue(all(not x["disabled"] for x in moves))
                    self.assertTrue(e.execute("move", target=moves[0]["target"]).accepted)
