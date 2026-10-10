"""Real HTTP/CLI parity and connected journey on disposable SQLite saves."""
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import main as cli, web_api
from app.engine import HeadlessEngine
from app.storage import GameStore


class FlowClientTests(unittest.TestCase):
    def test_camp_http_cli_and_persisted_snapshot_agree(self):
        with tempfile.TemporaryDirectory() as directory:
            store = GameStore(os.path.join(directory, "flow.db"))
            e = HeadlessEngine.new(campaign_id="embers_of_greyfen", player_class="Wizard")
            e.state.player.hp -= 3
            e.state.player.mana = 0
            e.state.companion.hp -= 2
            store.save("flow", e)
            direct = HeadlessEngine.restore(store.load("flow").state.to_dict())
            terminal = HeadlessEngine.restore(direct.state.to_dict())
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_api.GameAPIHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            with patch.object(web_api, "STORE", store), patch.object(web_api, "SESSIONS", {}):
                thread.start()
                try:
                    url = f"http://127.0.0.1:{server.server_port}/api/games/flow"
                    before = store.load("flow").state.to_dict()
                    bad = urllib.request.Request(url + "/commands", data=json.dumps({"command": "camp", "count": 3}).encode(), headers={"Content-Type": "application/json"})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(bad)
                    self.assertEqual(error.exception.code, 422)
                    error.exception.close()
                    self.assertEqual(store.load("flow").state.to_dict(), before)
                    req = urllib.request.Request(url + "/commands", data=json.dumps({"command": "camp"}).encode(), headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req) as response:
                        result = json.load(response)
                    self.assertTrue(result["accepted"])
                    self.assertTrue(direct.execute("camp").accepted)
                    with patch("app.main.save_game") as save, redirect_stdout(io.StringIO()):
                        self.assertTrue(cli.execute_cli_action(terminal, "camp"))
                    save.assert_called_once()
                    self.assertEqual(direct.state.to_dict(), terminal.state.to_dict())
                    web_api.SESSIONS.clear()
                    with urllib.request.urlopen(url) as response:
                        fetched = json.load(response)
                    for key in ("camp", "journey", "turn", "player", "companions", "flags"):
                        self.assertEqual(result["state"][key], fetched["state"][key])
                        self.assertEqual(direct.snapshot()[key], fetched["state"][key])
                    before = store.load("flow").state.to_dict()
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(req)
                    self.assertEqual(error.exception.code, 422)
                    error.exception.close()
                    self.assertEqual(store.load("flow").state.to_dict(), before)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

    def test_connected_short_path_and_reload_preserve_consequences(self):
        # Fix attack/check/loot randomness, not commands or combat orchestration.
        attack_calls = []
        def attack(attacker_bonus, target_ac, target_defending):
            attack_calls.append(True)
            roll = 20 if len(attack_calls) == 1 else 1
            return roll + attacker_bonus >= target_ac, roll, roll + attacker_bonus

        with tempfile.TemporaryDirectory() as directory, patch("app.rules.combat._attack_roll", side_effect=attack), patch("app.rules.combat.roll_dice", return_value=(6, "6")), patch("app.rules.exploration.check", return_value=(True, 20, 22)), patch("app.rules.dice.roll_die", return_value=4):
            store = GameStore(os.path.join(directory, "path.db"))
            e = HeadlessEngine.new(campaign_id="embers_of_greyfen", stats={"STR": 4, "DEX": 2, "CON": 2, "INT": 2, "WIS": 1, "CHA": 1})
            self.assertTrue(e.execute("talk").accepted)
            self.assertTrue(e.execute("companion_talk").accepted)
            for destination in ["crossroads", "high_road", "signal_tower", "refuge", "old_forest", "fallen_bridge", "keep_gate", "great_hall", "ember_vault"]:
                self.assertTrue(e.execute("move", target=destination).accepted, destination)
                for _ in range(30):
                    if not e.state.in_combat:
                        break
                    target = str(e.snapshot()["enemies"][0]["id"])
                    attack_calls.clear()
                    self.assertTrue(e.execute("attack", target=target).accepted)
                self.assertFalse(e.state.in_combat)
                self.assertFalse(e.state.game_over)
                if destination in ["signal_tower", "refuge"]:
                    self.assertTrue(e.execute("talk").accepted)
                self.assertTrue(e.execute("companion_talk").accepted)
                if e.snapshot()["camp"]["available"]:
                    self.assertTrue(e.execute("camp").accepted)
                if destination == "fallen_bridge":
                    self.assertTrue(e.execute("search").accepted)
                store.save("path", e)
                journal = e.snapshot()["journey"]
                e = store.load("path")
                self.assertEqual(journal, e.snapshot()["journey"])
            self.assertTrue(e.state.flags["ember_truth_known"])
            options = {o["id"]: o for o in e.snapshot()["challenge"]["options"]}
            self.assertTrue(options["restore_informed"]["available"])
            self.assertTrue(options["eldrin_aid"]["available"])
            self.assertTrue(e.execute("open").accepted)
            self.assertEqual(e.state.flags["ending_outcome"], "informed")
            store.save("path", e)
            restored = store.load("path")
            self.assertTrue(restored.state.game_over)
            self.assertEqual(restored.state.player.campaign_completions["embers_of_greyfen"], 1)
            self.assertEqual(restored.snapshot()["journey"], e.snapshot()["journey"])
            self.assertFalse(restored.execute("open").accepted)
