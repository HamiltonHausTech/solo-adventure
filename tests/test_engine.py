import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app.engine import HeadlessEngine
from app.content import get_campaign
from app.storage import GameStore
from app.web_api import GameAPIHandler, SESSIONS
import app.web_api as web_api


class HeadlessEngineTests(unittest.TestCase):
    def test_character_sex_survives_save_restore(self) -> None:
        engine = HeadlessEngine.new(name="Astaria", player_class="Rogue", sex="Female")
        self.assertEqual(engine.snapshot()["player"]["sex"], "Female")
        restored = HeadlessEngine.restore(engine.state.to_dict())
        self.assertEqual(restored.state.player.sex, "Female")

    def test_legacy_character_without_sex_remains_loadable(self) -> None:
        payload = HeadlessEngine.new().state.to_dict()
        payload["player"].pop("sex")
        self.assertEqual(HeadlessEngine.restore(payload).state.player.sex, "Unspecified")

    def test_new_game_stores_potions_as_one_stack(self) -> None:
        engine = HeadlessEngine.new()
        potions = [item for item in engine.state.inventory if item.get("id") == "healing_potion"]
        self.assertEqual(len(potions), 1)
        self.assertEqual(potions[0]["quantity"], 3)

    def test_long_campaign_has_two_routes_that_reconverge(self) -> None:
        campaign = get_campaign("embers_of_greyfen")
        self.assertGreaterEqual(len(campaign.rooms), 12)
        self.assertEqual(
            set(campaign.exits["crossroads"].values()),
            {"high_road", "marsh_path"},
        )
        self.assertEqual(campaign.exits["signal_tower"]["refuge"], "refuge")
        self.assertEqual(campaign.exits["sunken_chapel"]["refuge"], "refuge")
        self.assertEqual(campaign.rooms["ember_vault"].loot_config["game_over"], True)

    def test_long_campaign_branch_is_playable(self) -> None:
        engine = HeadlessEngine.new(
            campaign_id="embers_of_greyfen", companion_id="eldrin"
        )
        engine.execute("move", target="crossroads")
        with patch("app.rules.dice.roll_die", return_value=4):
            result = engine.execute("move", target="marsh_path")
        self.assertEqual(result.state["phase"], "combat")
        self.assertEqual(len(result.state["enemies"]), 2)
        self.assertEqual(result.state["room"]["id"], "marsh_path")

    def test_potion_revives_companion_during_combat_turn(self) -> None:
        engine = HeadlessEngine.new(
            campaign_id="embers_of_greyfen", companion_id="eldrin"
        )
        engine.execute("move", target="crossroads")
        engine.execute("move", target="marsh_path")
        engine.state.companion.hp = 0
        with patch("app.rules.dice.roll_die", return_value=4), patch(
            "app.rules.combat.roll_die", return_value=1
        ):
            result = engine.execute(
                "use", item="healing potion", target="Eldrin"
            )
        self.assertTrue(result.accepted)
        self.assertGreater(result.state["companions"][0]["hp"], 0)
        self.assertTrue(
            any(event.type == "healing_applied" for event in result.events)
        )

    def test_new_game_returns_client_safe_snapshot(self) -> None:
        engine = HeadlessEngine.new(name="Rowan", companion_id="mara")
        snapshot = engine.snapshot()
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["player"]["name"], "Rowan")
        self.assertEqual(snapshot["phase"], "exploration")
        self.assertEqual(snapshot["room"]["id"], "courtyard")
        self.assertTrue(snapshot["available_actions"])

    def test_invalid_command_does_not_advance_turn(self) -> None:
        engine = HeadlessEngine.new()
        result = engine.execute("dance")
        self.assertFalse(result.accepted)
        self.assertEqual(result.state["turn"], 0)
        self.assertIn("not available", result.error)

    def test_drop_command_removes_non_quest_item(self) -> None:
        engine = HeadlessEngine.new()
        before = len(engine.state.inventory)
        result = engine.execute("drop", item="leather cap")
        self.assertTrue(result.accepted)
        self.assertEqual(len(result.state["inventory"]), before - 1)

    def test_move_starts_authoritative_combat(self) -> None:
        engine = HeadlessEngine.new()
        with patch("app.rules.dice.roll_die", return_value=2):
            result = engine.execute("move", target="cellar")
        self.assertTrue(result.accepted)
        self.assertEqual(result.state["phase"], "combat")
        self.assertEqual(len(result.state["enemies"]), 2)
        self.assertTrue(any(item.type == "combat_started" for item in result.events))
        self.assertTrue(any(item.type == "room_entered" for item in result.events))

    def test_combat_command_emits_structured_events(self) -> None:
        engine = HeadlessEngine.new()
        with patch("app.rules.dice.roll_die", return_value=2):
            engine.execute("move", target="cellar")
        with patch("app.rules.combat.roll_die", return_value=20), patch(
            "app.rules.dice.roll_die", return_value=4
        ):
            result = engine.execute("attack", target="1")
        self.assertTrue(result.accepted)
        self.assertEqual(result.state["turn"], 2)
        self.assertTrue(
            any(item.type in {"damage_applied", "combat_ended"} for item in result.events)
        )
        self.assertTrue(all(item.event_id for item in result.events))

    def test_restore_round_trip(self) -> None:
        engine = HeadlessEngine.new(name="Save Test")
        engine.execute("talk")
        restored = HeadlessEngine.restore(engine.snapshot()["save"])
        self.assertEqual(restored.snapshot()["player"]["name"], "Save Test")
        self.assertEqual(restored.snapshot()["turn"], 1)

    def test_restore_migrates_legacy_duplicate_potions_to_stack(self) -> None:
        engine = HeadlessEngine.new()
        payload = engine.state.to_dict()
        potion = dict(payload["inventory"][0])
        potion.pop("stackable", None)
        potion.pop("quantity", None)
        payload["inventory"] = [dict(potion), dict(potion), dict(potion)]
        restored = HeadlessEngine.restore(payload)
        self.assertEqual(len(restored.state.inventory), 1)
        self.assertEqual(restored.state.inventory[0]["quantity"], 3)

    def test_restore_grants_legacy_level_rewards(self) -> None:
        engine = HeadlessEngine.new()
        payload = engine.state.to_dict()
        payload["player"]["level"] = 3
        payload["player"].pop("unspent_attribute_points")
        payload["player"].pop("unspent_class_upgrades")
        payload["player"].pop("chosen_upgrades")
        restored = HeadlessEngine.restore(payload)
        self.assertEqual(restored.state.player.unspent_attribute_points, 4)
        self.assertEqual(restored.state.player.unspent_class_upgrades, 2)

    def test_completion_xp_is_idempotent(self) -> None:
        engine = HeadlessEngine.new()
        engine.state.game_over = True
        messages = []
        engine._award_completion_once(messages)
        first_xp = engine.state.player.xp
        engine._award_completion_once(messages)
        self.assertEqual(engine.state.player.xp, first_xp)
        self.assertTrue(engine.state.flags["completion_xp_awarded"])

    def test_companion_conversation_updates_relationship_once(self) -> None:
        engine = HeadlessEngine.new(companion_id="mara")
        first = engine.execute("companion_talk")
        trust = engine.state.companion.trust
        second = engine.execute("companion_talk")
        self.assertTrue(first.accepted)
        self.assertTrue(any(item.type == "companion_interaction" for item in first.events))
        self.assertEqual(trust, 52)
        self.assertEqual(engine.state.companion.trust, trust)
        self.assertIn("already", second.events[0].message.lower())

    def test_companion_tactic_persists_through_save(self) -> None:
        engine = HeadlessEngine.new(companion_id="mara")
        result = engine.execute("set_tactic", target="aggressive")
        restored = HeadlessEngine.restore(result.state["save"])
        self.assertEqual(restored.state.companion.tactic, "aggressive")
        self.assertEqual(restored.state.companion.trust, 50)

    def test_companion_relationship_carries_to_new_campaign(self) -> None:
        source = HeadlessEngine.new(companion_id="mara")
        source.execute("companion_talk")
        fresh = HeadlessEngine.from_adventurer(
            source.state, campaign_id="lost_crypt", companion_id="mara"
        )
        self.assertEqual(fresh.state.companion.trust, 52)
        self.assertTrue(fresh.state.companion.memories)

    def test_level_six_fighter_can_guard_scaled_eldrin(self) -> None:
        source = HeadlessEngine.new(name="Veteran")
        source.state.player.level = 6
        fresh = HeadlessEngine.from_adventurer(
            source.state, campaign_id="embers_of_greyfen", companion_id="eldrin"
        )
        self.assertEqual(fresh.state.companion.max_hp, 14)
        fresh.state.in_combat = True
        actions = {action["id"] for action in fresh.available_actions()}
        self.assertIn("guard_companion", actions)

    def test_non_fighter_guard_is_rejected_without_advancing_turn(self) -> None:
        engine = HeadlessEngine.new(player_class="Rogue")
        engine.state.in_combat = True
        before_hp = engine.state.player.hp
        result = engine.execute("guard_companion")
        self.assertFalse(result.accepted)
        self.assertEqual(engine.state.turn, 0)
        self.assertEqual(engine.state.player.hp, before_hp)
        self.assertIn("fighter", result.error.lower())


class GameStoreTests(unittest.TestCase):
    def test_adventurer_has_stable_record_independent_of_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = GameStore(os.path.join(directory, "games.db"))
            engine = HeadlessEngine.new(name="Stable Hero")
            store.save("first-game", engine)
            adventurer_id = engine.state.adventurer_id
            self.assertIsNotNone(adventurer_id)
            profile = store.get_adventurer(str(adventurer_id))
            self.assertEqual(profile["player"]["name"], "Stable Hero")
            fresh = HeadlessEngine.from_adventurer(
                store.load_adventurer(str(adventurer_id)).state,
                campaign_id="lost_crypt",
                companion_id="mara",
            )
            store.save("second-game", fresh)
            self.assertEqual(fresh.state.adventurer_id, adventurer_id)
            self.assertEqual(len(store.list_adventurers()), 1)

    def test_hub_changes_do_not_rewrite_existing_adventure_saves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = GameStore(os.path.join(directory, "games.db"))
            engine = HeadlessEngine.new(name="Synchronized Hero")
            store.save("existing-game", engine)
            profile = store.load_adventurer(str(engine.state.adventurer_id))
            profile.state.player.unspent_attribute_points = 2
            profile.state.player.stats["CON"] += 1
            profile.state.player.max_hp += 1
            profile.state.player.gold = 99
            store.save_adventurer(profile)
            restored = store.load("existing-game")
            self.assertNotEqual(restored.state.player.stats["CON"], profile.state.player.stats["CON"])
            self.assertNotEqual(restored.state.player.max_hp, profile.state.player.max_hp)
            self.assertEqual(restored.state.player.gold, 0)
            updated_profile = store.load_adventurer(str(engine.state.adventurer_id))
            self.assertEqual(updated_profile.state.player.gold, 99)

    def test_session_survives_a_new_store_instance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "games.db")
            engine = HeadlessEngine.new(name="Durable Hero")
            engine.execute("talk")
            GameStore(path).save("game-1", engine)
            restored = GameStore(path).load("game-1")
            self.assertIsNotNone(restored)
            self.assertEqual(restored.snapshot()["player"]["name"], "Durable Hero")
            self.assertEqual(restored.snapshot()["turn"], 1)

    def test_list_sessions_returns_resume_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = GameStore(os.path.join(directory, "games.db"))
            store.save("game-1", HeadlessEngine.new(name="Listed Hero"))
            sessions = store.list_sessions()
            self.assertEqual(sessions[0]["game_id"], "game-1")
            self.assertEqual(sessions[0]["character_name"], "Listed Hero")
            self.assertEqual(sessions[0]["class"], "Fighter")
            self.assertEqual(sessions[0]["status"], "in_progress")
            self.assertEqual(sessions[0]["level"], 1)

    def test_same_character_traits_create_distinct_adventurers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = GameStore(os.path.join(directory, "games.db"))
            first = HeadlessEngine.new(name="Returning Hero")
            first.state.player.xp = 25
            store.save("old-game", first)
            second = HeadlessEngine.new(name="Returning Hero")
            second.state.player.xp = 75
            store.save("new-game", second)
            adventurers = store.list_adventurers()
            self.assertEqual(len(adventurers), 2)
            self.assertNotEqual(first.state.adventurer_id, second.state.adventurer_id)
            self.assertEqual({item["xp"] for item in adventurers}, {25, 75})

    def test_saved_adventurer_starts_fresh_campaign_with_progression(self) -> None:
        source = HeadlessEngine.new(name="Veteran")
        source.state.player.xp = 80
        source.state.player.gold = 12
        source.state.player.hp = 1
        source.state.flags["old_flag"] = True
        fresh = HeadlessEngine.from_adventurer(
            source.state, campaign_id="lost_crypt", companion_id="mara"
        )
        self.assertEqual(fresh.state.player.xp, 80)
        self.assertEqual(fresh.state.player.gold, 12)
        self.assertEqual(fresh.state.player.hp, fresh.state.player.max_hp)
        self.assertNotIn("old_flag", fresh.state.flags)
        self.assertEqual(fresh.state.campaign_id, "lost_crypt")
        self.assertEqual(fresh.state.turn, 0)


class GameAPITests(unittest.TestCase):
    def test_manage_adventurer_outside_campaign(self) -> None:
        _, created = self.request("/api/games", {"name": "Hub Hero"})
        adventurer_id = created["state"]["save"]["adventurer_id"]
        status, profile = self.request(f"/api/adventurers/{adventurer_id}")
        self.assertEqual(status, 200)
        self.assertEqual(profile["adventurer"]["player"]["name"], "Hub Hero")
        status, updated = self.request(
            f"/api/adventurers/{adventurer_id}/commands",
            {"command": "equip", "item": "Leather Cap"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["adventurer"]["equipment"]["head"]["id"], "leather_cap")

    def test_adventurer_hub_can_buy_potion_stack(self) -> None:
        _, created = self.request("/api/games", {"name": "Prepared Hero"})
        adventurer_id = created["state"]["save"]["adventurer_id"]
        profile = web_api.STORE.load_adventurer(adventurer_id)
        profile.state.player.gold = 30
        web_api.STORE.save_adventurer(profile)
        status, updated = self.request(
            f"/api/adventurers/{adventurer_id}/commands",
            {"command": "buy_potions", "quantity": 3},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["adventurer"]["player"]["gold"], 6)
        potions = next(item for item in updated["adventurer"]["inventory"] if item["id"] == "healing_potion")
        self.assertEqual(potions["quantity"], 6)

    def test_adventurer_hub_lists_and_sells_baseline_equipment(self) -> None:
        _, created = self.request("/api/games", {"name": "Outfitted Hero"})
        adventurer_id = created["state"]["save"]["adventurer_id"]
        profile = web_api.STORE.load_adventurer(adventurer_id)
        profile.state.player.gold = 40
        web_api.STORE.save_adventurer(profile)

        _, hub = self.request(f"/api/adventurers/{adventurer_id}")
        self.assertEqual(hub["adventurer"]["shop"]["stack_limit"], 10)
        self.assertTrue(any(item["id"] == "duelist_knife" for item in hub["adventurer"]["shop"]["items"]))

        status, updated = self.request(
            f"/api/adventurers/{adventurer_id}/commands",
            {"command": "buy_item", "item": "duelist_knife"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["adventurer"]["player"]["gold"], 12)
        self.assertTrue(any(item["id"] == "duelist_knife" for item in updated["adventurer"]["inventory"]))

    def test_confirm_progression_from_adventurer_hub(self) -> None:
        _, created = self.request("/api/games", {"name": "Growing Hero"})
        adventurer_id = created["state"]["save"]["adventurer_id"]
        profile = web_api.STORE.load_adventurer(adventurer_id)
        profile.state.player.unspent_attribute_points = 2
        profile.state.player.unspent_class_upgrades = 1
        web_api.STORE.save_adventurer(profile)
        status, updated = self.request(
            f"/api/adventurers/{adventurer_id}/commands",
            {
                "command": "apply_progression",
                "allocations": {"STR": 1, "CON": 1},
                "upgrade": "vitality",
            },
        )
        self.assertEqual(status, 200)
        player = updated["adventurer"]["player"]
        self.assertEqual(player["unspent_attribute_points"], 0)
        self.assertEqual(player["unspent_class_upgrades"], 0)
        self.assertIn("vitality", player["chosen_upgrades"])
        status, new_game = self.request(
            "/api/games",
            {
                "adventurer_id": adventurer_id,
                "campaign_id": "lost_crypt",
                "companion_id": "mara",
                "stats": {"STR": 0, "DEX": 0, "CON": 0, "INT": 0, "WIS": 0, "CHA": 0},
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(new_game["state"]["player"]["stats"]["STR"], player["stats"]["STR"])
        self.assertEqual(new_game["state"]["player"]["max_hp"], player["max_hp"])

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        web_api.STORE = GameStore(os.path.join(cls.temp_dir.name, "api.db"))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), GameAPIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        web_api.STORE = None
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        SESSIONS.clear()

    def request(self, path: str, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read())
            finally:
                error.close()

    def test_create_fetch_and_command_game(self) -> None:
        status, created = self.request(
            "/api/games", {"name": "API Hero", "companion_id": "mara"}
        )
        self.assertEqual(status, 201)
        game_id = created["game_id"]
        self.assertEqual(created["state"]["player"]["name"], "API Hero")

        status, result = self.request(
            f"/api/games/{game_id}/commands",
            {"command": "move", "target": "barracks"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["state"]["phase"], "combat")

        status, fetched = self.request(f"/api/games/{game_id}")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["state"]["room"]["id"], "barracks")

    def test_rejected_command_uses_422(self) -> None:
        _, created = self.request("/api/games", {"name": "API Hero"})
        status, result = self.request(
            f"/api/games/{created['game_id']}/commands", {"command": "dance"}
        )
        self.assertEqual(status, 422)
        self.assertFalse(result["accepted"])

    def test_catalog_and_persistent_game_list(self) -> None:
        status, catalog = self.request("/api/catalog")
        self.assertEqual(status, 200)
        self.assertTrue(catalog["campaigns"])
        self.assertTrue(catalog["classes"])
        self.assertTrue(catalog["races"])
        eldrin = next(
            companion
            for campaign in catalog["campaigns"]
            for companion in campaign["companions"]
            if companion["id"] == "eldrin"
        )
        self.assertEqual(eldrin["role"], "Arcane Support")
        self.assertTrue(eldrin["description"])
        self.assertIn("Magic Missile", eldrin["spells"])

        _, created = self.request("/api/games", {"name": "Roster Hero"})
        SESSIONS.clear()
        status, fetched = self.request(f"/api/games/{created['game_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["state"]["player"]["name"], "Roster Hero")

        status, games = self.request("/api/games")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["character_name"] == "Roster Hero" for item in games["games"]))

        status, roster = self.request("/api/adventurers")
        self.assertEqual(status, 200)
        self.assertTrue(any(item["name"] == "Roster Hero" for item in roster["adventurers"]))

    def test_new_character_is_rostered_before_adventure_completion(self) -> None:
        status, created = self.request(
            "/api/games",
            {"name": "Astaria", "class": "Rogue", "sex": "Female"},
        )
        self.assertEqual(status, 201)
        self.assertFalse(created["state"]["game_over"])

        status, roster = self.request("/api/adventurers")
        self.assertEqual(status, 200)
        astaria = next(item for item in roster["adventurers"] if item["name"] == "Astaria")
        self.assertEqual(astaria["class"], "Rogue")
        self.assertEqual(astaria["sex"], "Female")

    def test_create_campaign_from_saved_adventurer(self) -> None:
        _, created = self.request("/api/games", {"name": "Veteran", "companion_id": "mara"})
        source = web_api.STORE.load(created["game_id"])
        source.state.player.gold = 19
        web_api.STORE.save(created["game_id"], source)
        SESSIONS.clear()
        status, new_game = self.request(
            "/api/games",
            {
                "adventurer_game_id": created["game_id"],
                "campaign_id": "lost_crypt",
                "companion_id": "mara",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(new_game["state"]["player"]["name"], "Veteran")
        self.assertEqual(new_game["state"]["player"]["gold"], 19)
        self.assertEqual(new_game["state"]["campaign"]["id"], "lost_crypt")
        self.assertEqual(new_game["state"]["turn"], 0)
