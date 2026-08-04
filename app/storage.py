"""SQLite persistence for headless game sessions."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from .engine import HeadlessEngine


class GameStore:
    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS game_sessions (
                        game_id TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL,
                        character_name TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_game_sessions_updated "
                    "ON game_sessions(updated_at DESC)"
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS adventurers (
                        adventurer_id TEXT PRIMARY KEY,
                        identity_key TEXT NOT NULL UNIQUE,
                        character_name TEXT NOT NULL,
                        profile_json TEXT NOT NULL,
                        source_game_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_adventurers_updated "
                    "ON adventurers(updated_at DESC)"
                )
                self._backfill_adventurers(connection)
                connection.execute("PRAGMA optimize")

    @staticmethod
    def _identity_key(state: Dict[str, Any]) -> str:
        adventurer_id = str(state.get("adventurer_id", "")).strip()
        if adventurer_id:
            return f"id:{adventurer_id}"
        player = state.get("player") if isinstance(state.get("player"), dict) else {}
        # Name-based identity is retained only for migrating legacy sessions
        # that predate stable adventurer IDs.
        return "|".join(
            str(player.get(key, "")).strip().casefold()
            for key in ("name", "race", "cls")
        )

    def _backfill_adventurers(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT game_id, state_json, created_at, updated_at "
            "FROM game_sessions ORDER BY updated_at DESC"
        ).fetchall()
        identities: Dict[str, str] = {}
        for row in rows:
            state = json.loads(str(row["state_json"]))
            identity = self._identity_key(state)
            if not identity:
                continue
            existing = connection.execute(
                "SELECT adventurer_id FROM adventurers WHERE identity_key = ?",
                (identity,),
            ).fetchone()
            adventurer_id = (
                identities.get(identity)
                or str(existing["adventurer_id"] if existing else state.get("adventurer_id") or uuid4())
            )
            identities[identity] = adventurer_id
            if state.get("adventurer_id") != adventurer_id:
                state["adventurer_id"] = adventurer_id
                connection.execute(
                    "UPDATE game_sessions SET state_json = ? WHERE game_id = ?",
                    (json.dumps(state, separators=(",", ":")), row["game_id"]),
                )
            player = state.get("player") if isinstance(state.get("player"), dict) else {}
            connection.execute(
                """
                INSERT OR IGNORE INTO adventurers (
                    adventurer_id, identity_key, character_name, profile_json,
                    source_game_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adventurer_id,
                    identity,
                    player.get("name", "Adventurer"),
                    json.dumps(state, separators=(",", ":")),
                    row["game_id"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )

    def save(self, game_id: str, engine: HeadlessEngine) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection:
            with connection:
                if not engine.state.adventurer_id:
                    engine.state.adventurer_id = str(uuid4())
                state = engine.state.to_dict()
                identity = self._identity_key(state)
                serialized = json.dumps(state, separators=(",", ":"))
                connection.execute(
                    """
                    INSERT INTO game_sessions (
                        game_id, campaign_id, character_name, state_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(game_id) DO UPDATE SET
                        campaign_id = excluded.campaign_id,
                        character_name = excluded.character_name,
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        game_id,
                        engine.state.campaign_id,
                        engine.state.player.name,
                        serialized,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO adventurers (
                        adventurer_id, identity_key, character_name, profile_json,
                        source_game_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(adventurer_id) DO UPDATE SET
                        character_name = excluded.character_name,
                        profile_json = excluded.profile_json,
                        source_game_id = excluded.source_game_id,
                        updated_at = excluded.updated_at
                    """,
                    (
                        engine.state.adventurer_id,
                        identity,
                        engine.state.player.name,
                        serialized,
                        game_id,
                        now,
                        now,
                    ),
                )

    def load_adventurer(self, adventurer_id: str) -> Optional[HeadlessEngine]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT profile_json FROM adventurers WHERE adventurer_id = ?",
                (adventurer_id,),
            ).fetchone()
        if row is None:
            return None
        return HeadlessEngine.restore(json.loads(str(row["profile_json"])))

    def save_adventurer(self, engine: HeadlessEngine) -> None:
        if not engine.state.adventurer_id:
            raise ValueError("Adventurer ID is required.")
        now = datetime.now(timezone.utc).isoformat()
        state = engine.state.to_dict()
        serialized = json.dumps(state, separators=(",", ":"))
        identity = self._identity_key(state)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE adventurers SET identity_key = ?, character_name = ?,
                        profile_json = ?, updated_at = ?
                    WHERE adventurer_id = ?
                    """,
                    (identity, engine.state.player.name, serialized, now, engine.state.adventurer_id),
                )

    def load(self, game_id: str) -> Optional[HeadlessEngine]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT state_json FROM game_sessions WHERE game_id = ?",
                (game_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["state_json"]))
        return HeadlessEngine.restore(payload)

    def list_sessions(self, limit: int = 20) -> list[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT game_id, campaign_id, character_name, state_json, updated_at
                FROM game_sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        sessions = []
        for row in rows:
            state = json.loads(str(row["state_json"]))
            player = state.get("player") if isinstance(state.get("player"), dict) else {}
            companions = state.get("companions") if isinstance(state.get("companions"), list) else []
            companion = companions[0] if companions and isinstance(companions[0], dict) else {}
            sessions.append(
                {
                    "game_id": row["game_id"],
                    "campaign_id": row["campaign_id"],
                    "character_name": row["character_name"],
                    "room_id": state.get("room_id"),
                    "turn": int(state.get("turn", 0)),
                    "game_over": bool(state.get("game_over", False)),
                    "status": (
                        "defeat"
                        if state.get("game_over") and int(player.get("hp", 0)) <= 0
                        else "complete"
                        if state.get("game_over")
                        else "in_progress"
                    ),
                    "race": player.get("race", "Human"),
                    "sex": player.get("sex", "Unspecified"),
                    "class": player.get("cls", "Fighter"),
                    "level": int(player.get("level", 1)),
                    "xp": int(player.get("xp", 0)),
                    "hp": int(player.get("hp", 0)),
                    "max_hp": int(player.get("max_hp", 0)),
                    "companion_name": companion.get("name"),
                    "updated_at": row["updated_at"],
                }
            )
        return sessions

    def list_adventurers(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Return stable reusable characters independent of adventure sessions."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT adventurer_id, profile_json, source_game_id, updated_at
                FROM adventurers ORDER BY updated_at DESC LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        adventurers: list[Dict[str, Any]] = []
        for row in rows:
            engine = HeadlessEngine.restore(json.loads(str(row["profile_json"])))
            player = engine.state.player
            adventurers.append(
                {
                    "adventurer_id": row["adventurer_id"],
                    "source_game_id": row["source_game_id"],
                    "name": player.name,
                    "race": player.race,
                    "sex": player.sex,
                    "class": player.cls,
                    "level": player.level,
                    "xp": player.xp,
                    "gold": player.gold,
                    "stats": dict(player.stats),
                    "inventory_count": sum(
                        max(1, int(item.get("quantity", 1)))
                        for item in engine.state.inventory if isinstance(item, dict)
                    ),
                    "inventory_slots": len(engine.state.inventory),
                    "equipment_count": sum(
                        1 for item in engine.state.equipment.values() if item is not None
                    ),
                    "last_campaign_id": engine.state.campaign_id,
                    "updated_at": row["updated_at"],
                }
            )
        return adventurers

    def get_adventurer(self, adventurer_id: str) -> Optional[Dict[str, Any]]:
        engine = self.load_adventurer(adventurer_id)
        if engine is None:
            return None
        state = engine.state
        from .rules.experience import XP_TABLE, xp_for_level
        from .rules.progression import ATTRIBUTE_CAP, class_upgrade_options
        from .rules.inventory import STACK_LIMIT, item_sell_value, shop_catalog

        next_level_xp = (
            xp_for_level(state.player.level + 1)
            if state.player.level < len(XP_TABLE)
            else None
        )
        return {
            "adventurer_id": adventurer_id,
            "player": state.player.to_dict(),
            "inventory": [
                {**item, "sell_value": item_sell_value(item)}
                for item in state.inventory
            ],
            "equipment": dict(state.equipment),
            "companions": [companion.to_dict() for companion in state.companions],
            "inventory_limit": state.inventory_limit,
            "inventory_slots": len(state.inventory),
            "progression": {
                "attribute_cap": ATTRIBUTE_CAP,
                "unspent_attribute_points": state.player.unspent_attribute_points,
                "unspent_class_upgrades": state.player.unspent_class_upgrades,
                "current_level_xp": xp_for_level(state.player.level),
                "next_level_xp": next_level_xp,
                "upgrade_options": class_upgrade_options(state),
                "chosen_upgrades": list(state.player.chosen_upgrades),
            },
            "shop": {
                "healing_potion_price": 8,
                "bundle_quantity": 3,
                "stack_limit": STACK_LIMIT,
                "items": shop_catalog(),
            },
        }
