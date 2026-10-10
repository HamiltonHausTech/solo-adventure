from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .content import item_from_name


@dataclass
class Character:
    name: str
    race: str
    cls: str
    stats: Dict[str, int]
    hp: int
    max_hp: int
    ac: int
    base_ac: int
    mana: int
    max_mana: int
    attack_bonus: int
    damage: str
    sex: str = "Unspecified"
    spark_uses: int = 0
    gold: int = 0
    xp: int = 0
    level: int = 1
    learned_spells: List[str] = field(default_factory=list)
    unspent_attribute_points: int = 0
    unspent_class_upgrades: int = 0
    chosen_upgrades: List[str] = field(default_factory=list)
    campaign_completions: Dict[str, int] = field(default_factory=dict)
    discovered_unique_items: List[str] = field(default_factory=list)
    conditions: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "race": self.race,
            "cls": self.cls,
            "stats": dict(self.stats),
            "hp": self.hp,
            "max_hp": self.max_hp,
            "ac": self.ac,
            "base_ac": self.base_ac,
            "mana": self.mana,
            "max_mana": self.max_mana,
            "attack_bonus": self.attack_bonus,
            "damage": self.damage,
            "sex": self.sex,
            "spark_uses": self.spark_uses,
            "gold": self.gold,
            "xp": self.xp,
            "level": self.level,
            "learned_spells": list(self.learned_spells),
            "unspent_attribute_points": self.unspent_attribute_points,
            "unspent_class_upgrades": self.unspent_class_upgrades,
            "chosen_upgrades": list(self.chosen_upgrades),
            "campaign_completions": dict(self.campaign_completions),
            "discovered_unique_items": list(self.discovered_unique_items),
            "conditions": dict(self.conditions),
        }

    @staticmethod
    def from_dict(data: Dict) -> "Character":
        from .profiles import get_class_profile
        from .util import STAT_NAMES

        raw_stats = dict(data.get("stats", {}))
        stats = {k: int(raw_stats.get(k, 0)) for k in STAT_NAMES}
        cls = data["cls"]
        learned = data.get("learned_spells")
        if learned is None:
            profile = get_class_profile(cls)
            learned = list(profile.spells) if profile.spells else []
        elif not isinstance(learned, list):
            learned = []
        level = int(data.get("level", 1))
        legacy_rewards = "unspent_attribute_points" not in data
        return Character(
            name=data["name"],
            race=data.get("race", "Human"),
            cls=cls,
            stats=stats,
            hp=int(data["hp"]),
            max_hp=int(data["max_hp"]),
            ac=int(data["ac"]),
            base_ac=int(data.get("base_ac", data.get("ac", 0))),
            mana=int(data.get("mana", 0)),
            max_mana=int(data.get("max_mana", 0)),
            attack_bonus=int(data["attack_bonus"]),
            damage=data["damage"],
            sex=str(data.get("sex", "Unspecified")),
            spark_uses=int(data.get("spark_uses", 0)),
            gold=int(data.get("gold", 0)),
            xp=int(data.get("xp", 0)),
            level=level,
            learned_spells=list(learned),
            unspent_attribute_points=max(
                0,
                int(data.get("unspent_attribute_points", (level - 1) * 2 if legacy_rewards else 0)),
            ),
            unspent_class_upgrades=max(
                0,
                int(data.get("unspent_class_upgrades", level - 1 if legacy_rewards else 0)),
            ),
            chosen_upgrades=list(data.get("chosen_upgrades", [])),
            campaign_completions={
                str(key): max(0, int(value))
                for key, value in dict(data.get("campaign_completions", {})).items()
            },
            discovered_unique_items=[str(item) for item in data.get("discovered_unique_items", [])],
            conditions={str(key): max(0, int(value)) for key, value in dict(data.get("conditions", {})).items()},
        )


@dataclass
class Mob:
    name: str
    hp: int
    max_hp: int
    ac: int
    attack_bonus: int
    damage: str
    conditions: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "ac": self.ac,
            "attack_bonus": self.attack_bonus,
            "damage": self.damage,
            "conditions": dict(self.conditions),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Mob":
        return cls(
            name=data["name"],
            hp=int(data["hp"]),
            max_hp=int(data["max_hp"]),
            ac=int(data["ac"]),
            attack_bonus=int(data["attack_bonus"]),
            damage=data["damage"],
            conditions={str(key): max(0, int(value)) for key, value in dict(data.get("conditions", {})).items()},
        )


@dataclass
class Companion(Mob):
    mana: int = 0
    max_mana: int = 0
    learned_spells: List[str] = field(default_factory=list)
    defend_hp_threshold: int = 3
    trust: int = 50
    mood: str = "steady"
    tactic: str = "balanced"
    memories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        base = super().to_dict()
        base["mana"] = self.mana
        base["max_mana"] = self.max_mana
        base["learned_spells"] = list(self.learned_spells)
        base["defend_hp_threshold"] = self.defend_hp_threshold
        base["trust"] = self.trust
        base["mood"] = self.mood
        base["tactic"] = self.tactic
        base["memories"] = list(self.memories)
        return base

    @classmethod
    def from_dict(cls, data: Dict) -> "Companion":
        return cls(
            name=data["name"],
            hp=int(data["hp"]),
            max_hp=int(data["max_hp"]),
            ac=int(data["ac"]),
            attack_bonus=int(data["attack_bonus"]),
            damage=data["damage"],
            mana=int(data.get("mana", 0)),
            max_mana=int(data.get("max_mana", 0)),
            learned_spells=list(data.get("learned_spells", [])),
            defend_hp_threshold=int(data.get("defend_hp_threshold", 3)),
            trust=max(0, min(100, int(data.get("trust", 50)))),
            mood=str(data.get("mood", "steady")),
            tactic=str(data.get("tactic", "balanced")),
            memories=list(data.get("memories", []))[-20:],
            conditions={str(key): max(0, int(value)) for key, value in dict(data.get("conditions", {})).items()},
        )


@dataclass
class Enemy(Mob):
    asleep: bool = False

    def to_dict(self) -> Dict:
        base = super().to_dict()
        base["asleep"] = self.asleep
        return base

    @classmethod
    def from_dict(cls, data: Dict) -> "Enemy":
        mob = super().from_dict(data)
        return cls(
            name=mob.name,
            hp=mob.hp,
            max_hp=mob.max_hp,
            ac=mob.ac,
            attack_bonus=mob.attack_bonus,
            damage=mob.damage,
            conditions=dict(mob.conditions),
            asleep=bool(data.get("asleep", False)),
        )


@dataclass
class GameState:
    campaign_id: str
    player: Character
    room_id: str
    companions: List[Companion] = field(default_factory=list)
    visited: List[str] = field(default_factory=list)
    flags: Dict[str, Any] = field(default_factory=dict)
    inventory: List[Dict[str, Any]] = field(default_factory=list)
    equipment: Dict[str, Optional[Dict[str, Any]]] = field(default_factory=lambda: {
        "weapon": None,
        "head": None,
        "arms": None,
        "hands": None,
        "chest": None,
        "legs": None,
        "feet": None,
    })
    inventory_limit: int = 10
    in_combat: bool = False
    enemies: List[Enemy] = field(default_factory=list)
    turn: int = 0
    turn_log: List[str] = field(default_factory=list)
    last_event: str = ""
    last_player_input: str = ""
    response_log: List[Dict[str, Any]] = field(default_factory=list)
    player_defending: bool = False
    companion_defending: bool = False
    player_guarding_companion: bool = False
    player_shield_active: bool = False
    player_bless_active: bool = False
    companion_bless_active: bool = False
    game_over: bool = False
    rest_streak: int = 0
    pending_level_choices: List[Dict[str, Any]] = field(default_factory=list)
    adventurer_id: Optional[str] = None
    adventurer_revision: Optional[int] = None

    @property
    def companion(self) -> Companion:
        """Primary companion (first in list). For multiple companions, use companions directly."""
        return self.companions[0]

    def to_dict(self) -> Dict:
        return deepcopy({
            "version": 1,
            "campaign_id": self.campaign_id,
            "player": self.player.to_dict(),
            "companion": self.companion.to_dict(),  # backward compat
            "companions": [c.to_dict() for c in self.companions],
            "room_id": self.room_id,
            "visited": list(self.visited),
            "flags": dict(self.flags),
            "inventory": list(self.inventory),
            "equipment": dict(self.equipment),
            "inventory_limit": self.inventory_limit,
            "in_combat": self.in_combat,
            "enemies": [enemy.to_dict() for enemy in self.enemies],
            "turn": self.turn,
            "turn_log": list(self.turn_log),
            "last_event": self.last_event,
            "last_player_input": self.last_player_input,
            "response_log": list(self.response_log[-50:]),
            "player_defending": self.player_defending,
            "companion_defending": self.companion_defending,
            "player_guarding_companion": self.player_guarding_companion,
            "player_shield_active": self.player_shield_active,
            "player_bless_active": self.player_bless_active,
            "companion_bless_active": self.companion_bless_active,
            "game_over": self.game_over,
            "rest_streak": self.rest_streak,
            "pending_level_choices": list(self.pending_level_choices),
            "adventurer_id": self.adventurer_id,
            "adventurer_revision": self.adventurer_revision,
        })

    @staticmethod
    def from_dict(data: Dict) -> "GameState":
        data = deepcopy(data)
        campaign_id = data.get("campaign_id", "ruined_watchtower")
        raw_inventory = data.get("inventory", [])
        inventory: List[Dict[str, Any]] = []
        for item in raw_inventory:
            if isinstance(item, dict):
                item_id = str(item.get("id", ""))
                current = item_from_name(campaign_id, str(item.get("name", item_id)))
                if item_id:
                    from .content import item_from_id

                    current = item_from_id(campaign_id, item_id)
                current.update(item)
                inventory.append(current)
            elif isinstance(item, str):
                inventory.append(item_from_name(campaign_id, item))
        if not inventory and raw_inventory:
            inventory = [item_from_name(campaign_id, str(item)) for item in raw_inventory]
        equipment = data.get("equipment")
        if not isinstance(equipment, dict):
            equipment = {}
        for slot in ["weapon", "head", "arms", "hands", "chest", "legs", "feet"]:
            equipment.setdefault(slot, None)
        enemies = [Enemy.from_dict(item) for item in data.get("enemies", [])]
        if not enemies and data.get("enemy"):
            enemies = [Enemy.from_dict(data["enemy"])]
        raw_companions = data.get("companions", [])
        if raw_companions:
            companions = [Companion.from_dict(c) for c in raw_companions]
        else:
            companions = [Companion.from_dict(data["companion"])]
        state = GameState(
            campaign_id=campaign_id,
            player=Character.from_dict(data["player"]),
            room_id=data["room_id"],
            companions=companions,
            visited=list(data.get("visited", [])),
            flags=dict(data.get("flags", {})),
            inventory=inventory,
            equipment=equipment,
            inventory_limit=int(data.get("inventory_limit", 10)),
            in_combat=bool(data.get("in_combat", False)),
            enemies=enemies,
            turn=int(data.get("turn", 0)),
            turn_log=list(data.get("turn_log", [])),
            last_event=data.get("last_event", ""),
            last_player_input=str(data.get("last_player_input", "")),
            response_log=list(data.get("response_log", [])[-50:]),
            player_defending=bool(data.get("player_defending", False)),
            companion_defending=bool(data.get("companion_defending", False)),
            player_guarding_companion=bool(data.get("player_guarding_companion", False)),
            player_shield_active=bool(data.get("player_shield_active", False)),
            player_bless_active=bool(data.get("player_bless_active", False)),
            companion_bless_active=bool(data.get("companion_bless_active", False)),
            game_over=bool(data.get("game_over", False)),
            rest_streak=int(data.get("rest_streak", 0)),
            pending_level_choices=[
                choice for choice in data.get("pending_level_choices", [])
                if isinstance(choice, dict) and choice.get("type") != "spell"
            ],
            adventurer_id=data.get("adventurer_id"),
            adventurer_revision=(int(data["adventurer_revision"]) if data.get("adventurer_revision") is not None else None),
        )
        from .rules.inventory import normalize_inventory

        normalize_inventory(state)
        return state


SAVE_VERSION = 1


def save_state(state: GameState, path: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, indent=2)
    except OSError as e:
        raise IOError(f"Failed to save game to {path}: {e}") from e
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to serialize game state: {e}") from e


def load_state(path: str) -> GameState:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise FileNotFoundError(f"Save file not found: {path}") from None
    except OSError as e:
        raise IOError(f"Failed to read save file {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Save file is corrupt or invalid JSON: {e}") from e
    try:
        state = GameState.from_dict(data)
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Save file has invalid or incompatible format: {e}") from e
    _migrate_legacy_flags(state)
    # Restock consumables if inventory is empty (safety net for corrupted/cleared state)
    if not state.inventory:
        cid = state.campaign_id or "ruined_watchtower"
        for _ in range(3):
            state.inventory.append(item_from_name(cid, "healing_potion"))
    return state


def _migrate_legacy_flags(state: GameState) -> None:
    flags = state.flags
    if not isinstance(flags, dict):
        state.flags = {}
        flags = state.flags
    if any(key in flags for key in ("bandit_defeated", "bandit_looted", "enemy_name")):
        defeated_rooms = flags.get("defeated_rooms", [])
        looted_corpses = flags.get("looted_corpses", [])
        corpses = flags.get("corpses", {})
        if not isinstance(defeated_rooms, list):
            defeated_rooms = []
        if not isinstance(looted_corpses, list):
            looted_corpses = []
        if not isinstance(corpses, dict):
            corpses = {}
        if state.campaign_id == "ruined_watchtower":
            room_id = "barracks"
        else:
            room_id = state.room_id
        if flags.get("bandit_defeated") and room_id not in defeated_rooms:
            defeated_rooms.append(room_id)
        enemy_name = flags.get("enemy_name")
        if enemy_name and room_id not in corpses:
            corpses[room_id] = [{"id": 1, "name": enemy_name, "looted": False}]
        if flags.get("bandit_looted") and room_id not in looted_corpses:
            looted_corpses.append(room_id)
        flags["defeated_rooms"] = defeated_rooms
        flags["looted_corpses"] = looted_corpses
        flags["corpses"] = corpses
        for key in ("bandit_defeated", "bandit_looted", "enemy_name"):
            flags.pop(key, None)

    corpses = flags.get("corpses")
    if isinstance(corpses, dict):
        for room_id, value in list(corpses.items()):
            if isinstance(value, list):
                if value and isinstance(value[0], str):
                    corpses[room_id] = [
                        {"id": idx + 1, "name": name, "looted": False}
                        for idx, name in enumerate(value)
                    ]
                continue
            if value:
                corpses[room_id] = [{"id": 1, "name": str(value), "looted": False}]
