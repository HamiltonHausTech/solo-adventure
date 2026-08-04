"""Minimal JSON API for the headless solo-adventure engine."""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, RLock
from typing import Any, Dict
from uuid import uuid4

from .content import list_campaigns
from .engine import HeadlessEngine
from .profiles import CLASS_PROFILES, RACE_PROFILES, get_companion_archetype
from .rules import apply_progression_choices, buy_healing_potions, buy_shop_item, drop_item, equip_item, sell_item, unequip_item
from .storage import GameStore


SESSIONS: Dict[str, HeadlessEngine] = {}
STORE: GameStore | None = None
RESOURCE_LOCKS: Dict[str, RLock] = {}
RESOURCE_LOCKS_GUARD = Lock()


def _resource_lock(resource_id: str) -> RLock:
    with RESOURCE_LOCKS_GUARD:
        return RESOURCE_LOCKS.setdefault(resource_id, RLock())


def _load_session(game_id: str) -> HeadlessEngine | None:
    engine = SESSIONS.get(game_id)
    if engine is not None:
        return engine
    if STORE is not None:
        engine = STORE.load(game_id)
        if engine is not None:
            SESSIONS[game_id] = engine
    return engine


def _save_session(game_id: str, engine: HeadlessEngine) -> None:
    SESSIONS[game_id] = engine
    if STORE is not None:
        STORE.save(game_id, engine)


class GameAPIHandler(BaseHTTPRequestHandler):
    server_version = "SoloAdventure/0.1"

    def _send(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object.")
        return data

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            self._send(
                HTTPStatus.OK,
                {"ok": True, "schema_version": 1, "persistent": STORE is not None},
            )
            return
        if self.path == "/api/catalog":
            campaigns = []
            for campaign in list_campaigns():
                campaigns.append(
                    {
                        "id": campaign.campaign_id,
                        "name": campaign.name,
                        "description": campaign.description,
                        "companions": [
                            {
                                "id": profile.companion_id,
                                "name": profile.name,
                                "hp": profile.max_hp,
                                "ac": profile.ac,
                                "attack_bonus": profile.attack_bonus,
                                "damage": profile.damage,
                                "mana": profile.max_mana,
                                "spells": list(profile.spells),
                                "personality": profile.personality,
                                "default_tactic": profile.ai,
                                **get_companion_archetype(profile.companion_id),
                            }
                            for profile in campaign.companions.values()
                        ],
                    }
                )
            self._send(
                HTTPStatus.OK,
                {
                    "campaigns": campaigns,
                    "classes": [
                        {
                            "name": profile.name,
                            "role": profile.role,
                            "description": profile.description,
                            "base_hp": profile.base_hp,
                            "base_ac": profile.base_ac,
                            "spells": list(profile.spells),
                        }
                        for profile in CLASS_PROFILES.values()
                    ],
                    "races": [
                        {
                            "name": profile.name,
                            "description": profile.description,
                            "stat_mods": dict(profile.stat_mods),
                            "abilities": list(profile.abilities),
                        }
                        for profile in RACE_PROFILES.values()
                    ],
                },
            )
            return
        if self.path == "/api/games":
            sessions = STORE.list_sessions() if STORE is not None else []
            self._send(HTTPStatus.OK, {"games": sessions})
            return
        if self.path == "/api/adventurers":
            adventurers = STORE.list_adventurers() if STORE is not None else []
            self._send(HTTPStatus.OK, {"adventurers": adventurers})
            return
        if self.path.startswith("/api/adventurers/"):
            adventurer_id = self.path.removeprefix("/api/adventurers/").split("/", 1)[0]
            adventurer = STORE.get_adventurer(adventurer_id) if STORE is not None else None
            if adventurer is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Adventurer not found."})
                return
            self._send(HTTPStatus.OK, {"adventurer": adventurer})
            return
        if self.path.startswith("/api/games/"):
            session_id = self.path.removeprefix("/api/games/").split("/", 1)[0]
            engine = _load_session(session_id)
            if not engine:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Game not found."})
                return
            self._send(HTTPStatus.OK, {"game_id": session_id, "state": engine.snapshot()})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "Route not found."})

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._body()
        except (json.JSONDecodeError, ValueError) as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return

        if self.path == "/api/games":
            try:
                adventurer_id = str(payload.get("adventurer_id", "")).strip()
                source_game_id = str(payload.get("adventurer_game_id", "")).strip()
                if adventurer_id:
                    source = STORE.load_adventurer(adventurer_id) if STORE is not None else None
                    if source is None:
                        raise ValueError("Saved adventurer not found.")
                    engine = HeadlessEngine.from_adventurer(
                        source.state,
                        campaign_id=str(payload.get("campaign_id", "ruined_watchtower")),
                        companion_id=payload.get("companion_id"),
                    )
                elif source_game_id:
                    source = _load_session(source_game_id)
                    if source is None:
                        raise ValueError("Saved adventurer not found.")
                    engine = HeadlessEngine.from_adventurer(
                        source.state,
                        campaign_id=str(payload.get("campaign_id", "ruined_watchtower")),
                        companion_id=payload.get("companion_id"),
                    )
                else:
                    engine = HeadlessEngine.new(
                        campaign_id=str(payload.get("campaign_id", "ruined_watchtower")),
                        name=str(payload.get("name", "Adventurer")),
                        player_class=str(payload.get("class", "Fighter")),
                        race=str(payload.get("race", "Human")),
                        sex=str(payload.get("sex", "Unspecified")),
                        stats=payload.get("stats"),
                        companion_id=payload.get("companion_id"),
                    )
            except (KeyError, TypeError, ValueError) as error:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            session_id = str(uuid4())
            _save_session(session_id, engine)
            self._send(
                HTTPStatus.CREATED,
                {"game_id": session_id, "state": engine.snapshot()},
            )
            return

        if self.path.endswith("/commands") and self.path.startswith("/api/adventurers/"):
            adventurer_id = self.path.removeprefix("/api/adventurers/").split("/", 1)[0]
            engine = STORE.load_adventurer(adventurer_id) if STORE is not None else None
            if engine is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Adventurer not found."})
                return
            command = str(payload.get("command", "")).strip().lower()
            item = str(payload.get("item", "")).strip()
            target = str(payload.get("target", "")).strip()
            if command == "equip":
                accepted, message = equip_item(engine.state, item)
            elif command == "unequip":
                accepted, message = unequip_item(engine.state, target)
            elif command == "drop":
                accepted, message = drop_item(engine.state, item)
            elif command == "apply_progression":
                raw_allocations = payload.get("allocations", {})
                if not isinstance(raw_allocations, dict):
                    self._send(HTTPStatus.BAD_REQUEST, {"error": "Allocations must be an object."})
                    return
                try:
                    accepted, message = apply_progression_choices(
                        engine.state,
                        raw_allocations,
                        str(payload.get("upgrade", "")),
                    )
                except (TypeError, ValueError):
                    self._send(HTTPStatus.BAD_REQUEST, {"error": "Invalid progression allocation."})
                    return
            elif command == "buy_potions":
                try:
                    accepted, message = buy_healing_potions(
                        engine.state, int(payload.get("quantity", 1))
                    )
                except (TypeError, ValueError):
                    self._send(HTTPStatus.BAD_REQUEST, {"error": "Invalid purchase quantity."})
                    return
            elif command == "buy_item":
                accepted, message = buy_shop_item(engine.state, item)
            elif command == "sell":
                accepted, message = sell_item(engine.state, item)
            else:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "Unknown adventurer command."})
                return
            if not accepted:
                self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": message})
                return
            STORE.save_adventurer(engine)
            self._send(
                HTTPStatus.OK,
                {"message": message, "adventurer": STORE.get_adventurer(adventurer_id)},
            )
            return

        if self.path.endswith("/commands") and self.path.startswith("/api/games/"):
            session_id = self.path.removeprefix("/api/games/").split("/", 1)[0]
            with _resource_lock(f"game:{session_id}"):
                engine = _load_session(session_id)
                if not engine:
                    self._send(HTTPStatus.NOT_FOUND, {"error": "Game not found."})
                    return
                command = str(payload.get("command", "")).strip()
                if not command:
                    self._send(HTTPStatus.BAD_REQUEST, {"error": "Command is required."})
                    return
                result = engine.execute(
                    command,
                    target=payload.get("target"),
                    spell=payload.get("spell"),
                    item=payload.get("item"),
                )
                if result.accepted:
                    _save_session(session_id, engine)
            status = HTTPStatus.OK if result.accepted else HTTPStatus.UNPROCESSABLE_ENTITY
            self._send(status, {"game_id": session_id, **result.to_dict()})
            return

        self._send(HTTPStatus.NOT_FOUND, {"error": "Route not found."})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    global STORE
    parser = argparse.ArgumentParser(description="Run the Solo Adventure game API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--database",
        default=os.path.join("var", "solo_adventure.db"),
        help="SQLite database path for durable game sessions.",
    )
    args = parser.parse_args()
    STORE = GameStore(args.database)
    server = ThreadingHTTPServer((args.host, args.port), GameAPIHandler)
    print(f"Solo Adventure API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
