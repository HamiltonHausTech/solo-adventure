"""Adventure flow contract and persistence regression tests (no live services)."""
import unittest
from copy import deepcopy
from unittest.mock import patch

from app.engine import HeadlessEngine
from app.main import parse_engine_action
from app.rules.companion_interactions import talk_to_companion


class CampTests(unittest.TestCase):
    def game(self):
        return HeadlessEngine.new(campaign_id="embers_of_greyfen", player_class="Wizard")

    def test_preview_pure_and_matches_batch(self):
        e = self.game()
        e.state.player.hp -= 3
        e.state.player.mana = 0
        e.state.companion.hp -= 2
        e.state.rest_streak = 1
        before = deepcopy(e.state.to_dict())
        preview = e.snapshot()["camp"]
        self.assertEqual(e.state.to_dict(), before)
        self.assertTrue(preview["available"])
        result = e.execute("camp")
        self.assertTrue(result.accepted)
        self.assertEqual(e.state.turn, before["turn"] + preview["recovery_turns"])
        for actor, gains in zip([e.state.player, *e.state.companions], preview["recovery"]):
            old = before["player"] if actor is e.state.player else before["companions"][0]
            self.assertEqual(actor.hp - old["hp"], gains["hp"])
            self.assertEqual(actor.mana - old["mana"], gains["mana"])
        self.assertEqual(len(e.state.turn_log), 1)
        self.assertEqual(len(result.events), 1)
        self.assertEqual(e.state.companion.trust, before["companions"][0]["trust"] + 1)
        self.assertEqual(HeadlessEngine.restore(e.state.to_dict()).snapshot()["camp"], e.snapshot()["camp"])

    def test_cap_dead_multiple_and_streak(self):
        e = self.game()
        e.state.player.max_hp = 300
        e.state.player.hp = 1
        dead = deepcopy(e.state.companion)
        dead.name = "Fallen"
        dead.hp = 0
        dead.mana = 0
        e.state.companions.append(dead)
        e.state.rest_streak = 1
        self.assertEqual(e.snapshot()["camp"]["recovery_turns"], 100)
        self.assertTrue(e.execute("camp").accepted)
        self.assertEqual(e.state.player.hp, 51)
        self.assertEqual(e.state.rest_streak, 1)
        self.assertEqual((dead.hp, dead.mana), (0, 0))
        self.assertTrue(e.execute("rest").accepted)
        self.assertEqual(dead.hp, 0)

    def test_camp_keeps_pending_choices_and_does_not_repeat_trust(self):
        e = self.game()
        e.state.pending_level_choices = [{"type": "spell", "choices": ["Magic Missile"], "level": 2}]
        pending = deepcopy(e.state.pending_level_choices)
        e.state.player.hp -= 1
        with patch("app.rules.rest.prompt_choice", side_effect=AssertionError("camp must not prompt")):
            self.assertTrue(e.execute("camp").accepted)
            trust = e.state.companion.trust
            e.state.player.hp -= 1
            self.assertTrue(e.execute("camp").accepted)
        self.assertEqual(e.state.companion.trust, trust)
        self.assertEqual(e.state.pending_level_choices, pending)

    def test_rejects_atomic(self):
        for change, kwargs in [(None, {}), ("combat", {}), ("over", {}), ("hurt", {"target": ""}), ("hurt", {"item": "potion"}), ("hurt", {"spell": "Spark"})]:
            e = self.game()
            if change:
                e.state.player.hp -= 1
            if change == "combat": e.state.in_combat = True
            if change == "over": e.state.game_over = True
            before = deepcopy(e.state.to_dict())
            self.assertFalse(e.execute("camp", **kwargs).accepted)
            self.assertEqual(e.state.to_dict(), before)
        e = self.game()
        self.assertEqual(parse_engine_action("camp", e), ("camp", {}))
        e.state.player.hp -= 1
        command, kwargs = parse_engine_action("camp 3", e)
        before = deepcopy(e.state.to_dict())
        self.assertFalse(e.execute(command, **kwargs).accepted)
        self.assertEqual(e.state.to_dict(), before)


class JourneyTests(unittest.TestCase):
    def test_known_locations_and_isolation(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        before = deepcopy(e.state.to_dict())
        j = e.snapshot()["journey"]
        self.assertEqual({r["id"] for r in j["locations"]}, {"greyfen_road", "crossroads"})
        self.assertNotIn("ember_truth_known", str(j))
        j["journal"].append({"id": "bad", "text": "bad"})
        self.assertEqual(e.state.to_dict(), before)

    def test_only_current_exits_expand_known_locations(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        self.assertTrue(e.execute("move", target="crossroads").accepted)
        self.assertIn("marsh_path", {r["id"] for r in e.snapshot()["journey"]["locations"]})
        self.assertTrue(e.execute("move", target="high_road").accepted)
        expected = {"greyfen_road", "crossroads", "high_road", "signal_tower"}
        for engine in [e, HeadlessEngine.restore(e.state.to_dict())]:
            self.assertEqual({r["id"] for r in engine.snapshot()["journey"]["locations"]}, expected)

    def test_searched_supply_objective_points_onward(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        e.state.room_id = "fallen_bridge"
        self.assertIn("Search the abandoned camp", e.snapshot()["journey"]["objective"]["description"])
        self.assertTrue(e.execute("search").accepted)
        for engine in [e, HeadlessEngine.restore(e.state.to_dict())]:
            objective = engine.snapshot()["journey"]["objective"]
            self.assertEqual(objective["title"], "Approach Blackbriar")
            self.assertNotIn("Search the abandoned camp", objective["description"])
            self.assertIn("gate", objective["description"])

    def test_conversation_persists_and_exhausts(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        e.state.room_id = "refuge"
        with patch("app.rules.exploration.check", return_value=(True, 20, 22)):
            self.assertTrue(e.execute("talk").accepted)
        e = HeadlessEngine.restore(e.state.to_dict())
        self.assertIn("seal", str(e.snapshot()["journey"]["journal"]))
        before = deepcopy(e.state.to_dict())
        with patch("app.rules.exploration.check", side_effect=AssertionError("must not reroll")):
            self.assertFalse(e.execute("talk").accepted)
        self.assertEqual(e.state.to_dict(), before)

    def test_failed_talk_fallback_persists_and_route_stays_open(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        e.state.room_id = "refuge"
        with patch("app.rules.exploration.check", return_value=(False, 1, 3)):
            self.assertTrue(e.execute("talk").accepted)
        self.assertNotIn("ember_truth_known", e.state.flags)
        self.assertIn("dusk", str(e.snapshot()["journey"]["journal"]))
        self.assertIn("old forest", e.snapshot()["journey"]["objective"]["description"])
        self.assertTrue(e.execute("move", target="old_forest").accepted)

    def test_search_exhaustion_and_post_combat_description(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        e.state.room_id = "fallen_bridge"
        self.assertTrue(e.execute("search").accepted)
        before = deepcopy(e.state.to_dict())
        for command in ["search", "inspect", "loot"]:
            self.assertFalse(e.execute(command).accepted)
            self.assertEqual(e.state.to_dict(), before)
        e.state.room_id = "great_hall"
        e.state.flags["defeated_rooms"] = ["great_hall"]
        e.state.flags["corpses"] = {"great_hall": [{"id": 1, "name": "Captain Veyra", "looted": False}]}
        snap = e.snapshot()
        self.assertNotIn("stands before", snap["room"]["description"])
        self.assertIn("Unlooted remains", next(r for r in snap["journey"]["locations"] if r["id"] == "great_hall")["statuses"])

    def test_companion_conversation_journal_and_legacy_memory(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        self.assertTrue(e.execute("companion_talk").accepted)
        self.assertIn("Eldrin", str(e.snapshot()["journey"]["journal"]))
        e.state.companion.memories.append("rest:embers_of_greyfen:greyfen_road")
        e.state.player.hp -= 1
        trust = e.state.companion.trust
        self.assertTrue(e.execute("camp").accepted)
        self.assertEqual(e.state.companion.trust, trust)
        e.state.companion.memories.clear()
        e.state.player.hp -= 1
        self.assertTrue(e.execute("camp").accepted)
        self.assertEqual(e.state.companion.trust, trust)

    def test_trust_cannot_be_farmed_after_memory_eviction(self):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen")
        talk_to_companion(e.state)
        trust = e.state.companion.trust
        e.state.companion.memories = [f"other:{i}" for i in range(20)]
        talk_to_companion(e.state)
        self.assertEqual(e.state.companion.trust, trust)


class SealTests(unittest.TestCase):
    def game(self, companion="eldrin"):
        e = HeadlessEngine.new(campaign_id="embers_of_greyfen", companion_id=companion)
        e.state.room_id = "ember_vault"
        return e

    def options(self, e):
        return {o["id"]: o for o in e.snapshot()["challenge"]["options"]}

    def test_requirements_and_truth(self):
        e = self.game()
        self.assertFalse(self.options(e)["restore_informed"]["available"])
        e.state.flags["ember_truth_known"] = True
        with patch("app.rules.challenges.check", side_effect=AssertionError("automatic")):
            self.assertTrue(e.execute("challenge", target="restore_informed").accepted)
        self.assertTrue(e.state.game_over)
        self.assertEqual(e.state.flags["ending_outcome"], "informed")

    def test_trust_identity_alive_and_development(self):
        for companion, hp, trust, available in [("eldrin", 9, 60, True), ("eldrin", 9, 59, False), ("eldrin", 0, 100, False), ("mara", 9, 100, False)]:
            e = self.game(companion)
            e.state.companion.hp, e.state.companion.trust = hp, trust
            self.assertEqual(self.options(e)["eldrin_aid"]["available"], available)
        e = self.game()
        self.assertFalse(self.options(e)["mastered_seal"]["available"])
        e.state.player.stats["WIS"] = 5
        self.assertTrue(self.options(e)["mastered_seal"]["available"])

    def test_reliable_alternatives_execute_without_roll_and_legacy_failure_recovers(self):
        for option, ending in [("eldrin_aid", "trusted"), ("mastered_seal", "mastered")]:
            e = self.game()
            e.state.companion.trust = 60
            e.state.player.chosen_upgrades.append("resilience")
            e.state.flags["loot_failed"] = True
            with patch("app.rules.challenges.check", side_effect=AssertionError("reliable approach must not roll")):
                self.assertTrue(e.execute("challenge", target=option).accepted)
            self.assertEqual(e.state.flags["ending_outcome"], ending)
            self.assertTrue(e.state.flags["completion_xp_awarded"])
            self.assertEqual(sum(i.get("id") == "ember_heart" for i in e.state.inventory), 1)
            self.assertIn("Greyfen", e.state.flags["ending_explanation"])

    def test_legacy_targets_cannot_bypass_resolver(self):
        e = self.game()
        before = deepcopy(e.state.to_dict())
        for command in ["loot", "search", "inspect", "open"]:
            self.assertFalse(e.execute(command, target="anything").accepted)
            self.assertEqual(e.state.to_dict(), before)

    def test_unavailable_approach_atomic_and_nested_snapshot_detached(self):
        e = self.game()
        before = deepcopy(e.state.to_dict())
        self.assertFalse(e.execute("challenge", target="eldrin_aid").accepted)
        self.assertEqual(e.state.to_dict(), before)
        snap = e.snapshot()
        snap["challenge"]["options"][0]["requires"]["flags"].clear()
        self.assertFalse(self.options(e)["restore_informed"]["available"])

    def test_ability_legacy_and_companion_other_slot(self):
        e = self.game("mara")
        from app.rules import create_companion
        eldrin = create_companion("embers_of_greyfen", "eldrin")
        eldrin.trust = 60
        e.state.companions.append(eldrin)
        self.assertTrue(self.options(e)["eldrin_aid"]["available"])
        e.state.player.chosen_upgrades.append("resilience")
        self.assertTrue(self.options(e)["mastered_seal"]["available"])
        e.state.flags["loot_taken"] = True
        restored = HeadlessEngine.restore(e.state.to_dict())
        self.assertIsNone(restored.snapshot()["challenge"])
        before = deepcopy(restored.state.to_dict())
        self.assertFalse(restored.execute("loot").accepted)
        self.assertEqual(before, restored.state.to_dict())

    def test_legacy_commands_fail_forward_once(self):
        for command in ["search", "open", "loot", "inspect", "challenge"]:
            e = self.game()
            e.state.player.hp = 2
            with patch("app.rules.challenges.check", return_value=(False, 1, 3)):
                result = e.execute(command, **({"target": "attempt_seal"} if command == "challenge" else {}))
            self.assertTrue(result.accepted)
            self.assertTrue(e.state.game_over)
            self.assertGreater(e.state.player.hp, 0)
            self.assertEqual(e.state.flags["ending_outcome"], "costly")
            before = deepcopy(e.state.to_dict())
            self.assertFalse(e.execute(command).accepted)
            self.assertEqual(before, e.state.to_dict())
            self.assertEqual(e.state.player.campaign_completions["embers_of_greyfen"], 1)
