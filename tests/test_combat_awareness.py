import unittest
from unittest.mock import patch

from app.engine import HeadlessEngine
from app.rules.combat import end_combat_if_needed
from app.rules.exploration import start_room
from app.content import get_room


class CombatAwarenessTests(unittest.TestCase):
    def combat(self):
        engine = HeadlessEngine.new(name="Naria", player_class="Wizard", campaign_id="embers_of_greyfen", companion_id="eldrin")
        engine.state.room_id = "high_road"
        start_room(engine.state, get_room(engine.state.campaign_id, "high_road"))
        return engine

    def test_insufficient_spell_cost_is_not_depleted_mana(self):
        engine = self.combat()
        engine.state.player.mana = 1
        result = engine.execute("special")
        self.assertFalse(result.accepted)
        self.assertIn("Requires 2 mana", result.error or "")
        self.assertIn("1 available", result.error or "")
        self.assertEqual(engine.state.player.mana, 1)

    def test_health_event_is_net_round_change_not_gross_damage(self):
        engine = self.combat()
        engine.state.player.hp = 10
        engine.state.player.max_hp = 20
        def damage(state):
            state.player.hp -= 7
            return ["An opaque narrative without damage keywords."]
        with patch("app.rules.inventory.roll_dice", return_value=(4, "4")), patch("app.engine.apply_companion_action", return_value="Waiting."), patch("app.engine.apply_enemy_action", side_effect=damage):
            result = engine.execute("use", item="healing potion", target="me")
        changes = [event for event in result.events if event.type == "health_changed" and event.actor == "player"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].data, {"hp_before": 10, "hp_after": 7, "max_hp": 20, "hp_delta": -3})
        self.assertIn("health fell 3 this turn", changes[0].message)
        self.assertNotIn("health_changed", str(HeadlessEngine.restore(engine.state.to_dict()).snapshot()))

    def test_net_healing_does_not_claim_damage(self):
        engine = self.combat()
        engine.state.player.hp = 5
        def damage(state):
            state.player.hp -= 1
            return ["Hit for 1 damage."]
        with patch("app.rules.inventory.roll_dice", return_value=(4, "4")), patch("app.engine.apply_companion_action", return_value="Waiting."), patch("app.engine.apply_enemy_action", side_effect=damage):
            result = engine.execute("use", item="healing potion", target="me")
        changes = [event for event in result.events if event.type == "health_changed"]
        self.assertEqual(changes[0].data["hp_delta"], 3)
        self.assertNotIn("fell", changes[0].message)

    def test_greyfen_death_is_not_watchtower_and_overrides_enemy_defeat(self):
        for enemies_dead in (False, True):
            with self.subTest(enemies_dead=enemies_dead):
                engine = self.combat()
                engine.state.player.hp = 0
                if enemies_dead:
                    for enemy in engine.state.enemies:
                        enemy.hp = 0
                message = end_combat_if_needed(engine.state)
                self.assertTrue(engine.state.game_over)
                self.assertEqual(engine.snapshot()["phase"], "defeat")
                self.assertIsNotNone(message)
                self.assertNotIn("watchtower", (message or "").lower())
                self.assertNotIn("high_road", engine.state.flags.get("defeated_rooms", []))
