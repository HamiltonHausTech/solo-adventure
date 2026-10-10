"""Regression coverage for stale character writes and the HTTP trust boundary."""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer

from app.engine import HeadlessEngine
from app.storage import GameStore, StaleAdventurerError
from app import web_api


class StorageIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "games.db")
        self.store = GameStore(self.path)
        self.engine = HeadlessEngine.new()
        self.store.save("original", self.engine)
        self.aid = self.engine.state.adventurer_id

    def test_hub_edit_makes_old_session_read_only_without_losing_either_save(self):
        before = self.store.load("original").state.to_dict()
        hub = self.store.load_adventurer(self.aid)
        hub.state.player.gold = 73
        self.store.save_adventurer(hub)
        old = self.store.load("original")
        old.execute("rest")
        with self.assertRaises(StaleAdventurerError):
            self.store.save("original", old)
        self.assertEqual(self.store.load_adventurer(self.aid).state.player.gold, 73)
        self.assertEqual(self.store.load("original").state.to_dict(), before)

    def test_second_adventure_invalidates_older_branch(self):
        current = self.store.load_adventurer(self.aid)
        fresh = HeadlessEngine.from_adventurer(current.state, campaign_id="lost_crypt")
        self.store.save("second", fresh)
        old = self.store.load("original")
        with self.assertRaises(StaleAdventurerError):
            self.store.save("original", old)
        fresh.execute("rest")
        self.store.save("second", fresh)
        self.assertEqual(self.store.load("second").state.turn, 1)

    def test_concurrent_hub_writes_have_one_winner_across_store_instances(self):
        left = self.store.load_adventurer(self.aid)
        right = self.store.load_adventurer(self.aid)
        left.state.player.gold, right.state.player.gold = 11, 22
        barrier = threading.Barrier(2)
        def save(engine):
            other = GameStore(self.path)
            barrier.wait()
            try:
                other.save_adventurer(engine)
                return "saved"
            except StaleAdventurerError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(save, (left, right)), ["saved", "conflict"])
        self.assertIn(self.store.load_adventurer(self.aid).state.player.gold, (11, 22))

    def test_repeated_session_saves_and_restarts_retain_revision(self):
        self.engine.execute("rest")
        self.store.save("original", self.engine)
        store = GameStore(self.path)
        loaded = store.load("original")
        loaded.execute("rest")
        store.save("original", loaded)
        self.assertEqual(store.load("original").state.turn, 2)

    def test_legacy_session_is_rejected_if_hub_already_differs(self):
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT state_json FROM game_sessions WHERE game_id='original'").fetchone()
            state = json.loads(row[0]); state.pop("adventurer_revision", None)
            db.execute("UPDATE game_sessions SET state_json=?", (json.dumps(state),))
            profile = dict(state); profile["player"] = dict(state["player"], gold=99)
            db.execute("UPDATE adventurers SET profile_json=?", (json.dumps(profile),))
        restarted = GameStore(self.path)
        old = restarted.load("original")
        with self.assertRaises(StaleAdventurerError):
            restarted.save("original", old)
        self.assertEqual(restarted.load_adventurer(self.aid).state.player.gold, 99)

    def test_mid_transaction_failure_rolls_back_session_and_profile(self):
        before = self.store.load("original").state.to_dict()
        revision = self.engine.state.adventurer_revision
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TRIGGER fail_profile BEFORE UPDATE ON adventurers
                          BEGIN SELECT RAISE(ABORT, 'injected write failure'); END""")
        self.engine.execute("rest")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save("original", self.engine)
        self.assertEqual(self.engine.state.adventurer_revision, revision)
        self.assertEqual(self.store.load("original").state.to_dict(), before)
        self.assertEqual(self.store.load_adventurer(self.aid).state.to_dict(), before)

    def test_sessions_only_pre_id_migration_survives_restarts(self):
        path = os.path.join(self.temp.name, "legacy.db")
        latest = HeadlessEngine.new(name="Legacy Hero").state.to_dict()
        latest.pop("adventurer_id", None)
        latest.pop("adventurer_revision", None)
        older = json.loads(json.dumps(latest))
        latest["player"]["gold"] = 9
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE game_sessions (
                game_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL,
                character_name TEXT NOT NULL, state_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            for game_id, state, stamp in (("old", older, "2026-01-01"), ("latest", latest, "2026-01-02")):
                db.execute("INSERT INTO game_sessions VALUES (?, ?, ?, ?, ?, ?)",
                           (game_id, state["campaign_id"], "Legacy Hero", json.dumps(state), stamp, stamp))
        ids = set()
        for _ in range(3):
            store = GameStore(path)
            self.assertEqual(len(store.list_adventurers()), 1)
            current = store.load("latest")
            ids.add(current.state.adventurer_id)
            current.execute("rest")
            store.save("latest", current)
            with self.assertRaises(StaleAdventurerError):
                store.save("old", store.load("old"))
            self.assertEqual(store.load_adventurer(current.state.adventurer_id).state.player.gold, 9)
        self.assertEqual(len(ids), 1)

    def test_legacy_matching_save_can_continue(self):
        with sqlite3.connect(self.path) as db:
            db.execute("ALTER TABLE adventurers DROP COLUMN revision")
            for table, column in (("game_sessions", "state_json"), ("adventurers", "profile_json")):
                state = json.loads(db.execute(f"SELECT {column} FROM {table}").fetchone()[0])
                state.pop("adventurer_revision", None)
                db.execute(f"UPDATE {table} SET {column}=?", (json.dumps(state),))
        store = GameStore(self.path)
        loaded = store.load("original")
        loaded.execute("rest")
        store.save("original", loaded)
        self.assertEqual(store.load("original").state.turn, 1)


class HTTPIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_store = web_api.STORE
        web_api.STORE = GameStore(os.path.join(self.temp.name, "api.db"))
        web_api.SESSIONS.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web_api.GameAPIHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        web_api.STORE = self.previous_store
        web_api.SESSIONS.clear()
        self.temp.cleanup()

    def request(self, path, payload=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if origin: headers["Origin"] = origin
        req = urllib.request.Request(self.base + path,
            data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, json.load(response), response.headers
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error), error.headers

    def test_stale_command_returns_conflict_and_preserves_session(self):
        _, created, _ = self.request("/api/games", {"name": "Hero"})
        gid = created["game_id"]; aid = created["state"]["save"]["adventurer_id"]
        status, _, _ = self.request(f"/api/adventurers/{aid}/commands", {"command":"equip", "item":"Leather Cap"})
        self.assertEqual(status, 200)
        status, body, _ = self.request(f"/api/games/{gid}/commands", {"command":"rest"})
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], "stale_adventurer")
        _, fetched, _ = self.request(f"/api/games/{gid}")
        self.assertEqual(fetched["state"]["turn"], 0)
        _, profile, _ = self.request(f"/api/adventurers/{aid}")
        self.assertEqual(profile["adventurer"]["equipment"]["head"]["id"], "leather_cap")
        status, _, _ = self.request("/api/games", {"adventurer_id": aid, "campaign_id":"lost_crypt"})
        self.assertEqual(status, 201)

    def test_hub_write_between_execution_and_save_returns_conflict(self):
        _, created, _ = self.request("/api/games", {})
        gid = created["game_id"]
        aid = created["state"]["save"]["adventurer_id"]
        original_save = web_api._save_session
        def racing_save(game_id, engine):
            profile = web_api.STORE.load_adventurer(aid)
            profile.state.player.gold = 77
            web_api.STORE.save_adventurer(profile)
            original_save(game_id, engine)
        with patch.object(web_api, "_save_session", side_effect=racing_save):
            status, body, _ = self.request(f"/api/games/{gid}/commands", {"command": "rest"})
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], "stale_adventurer")
        self.assertEqual(web_api.STORE.load(gid).state.turn, 0)
        self.assertEqual(web_api.STORE.load_adventurer(aid).state.player.gold, 77)
        self.assertEqual(self.request(f"/api/games/{gid}/commands", {"command": "rest"})[0], 409)
        self.assertEqual(self.request(f"/api/games/{gid}")[1]["state"]["turn"], 0)

    def test_invalid_command_field_types_return_bad_request(self):
        _, created, _ = self.request("/api/games", {})
        path = f"/api/games/{created['game_id']}/commands"
        for payload in ({"command":"move","target":42}, {"command":[]}, {"command":"use","item":{}}, {"command":"cast","spell":False}):
            with self.subTest(payload=payload):
                self.assertEqual(self.request(path, payload)[0], 400)
        self.assertEqual(self.request(f"/api/games/{created['game_id']}")[1]["state"]["turn"], 0)

    def test_untrusted_browser_origin_is_denied(self):
        status, _, headers = self.request("/api/games", {}, "https://untrusted.example")
        self.assertEqual(status, 403)
        self.assertNotEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_local_browser_origin_is_allowed(self):
        status, _, headers = self.request("/api/catalog", origin="http://localhost:3000")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "http://localhost:3000")

    def test_bad_creation_stats_returns_bad_request(self):
        self.assertEqual(self.request("/api/games", {"stats": ["STR"]})[0], 400)


if __name__ == "__main__":
    unittest.main()
