"""Headless game engine boundary for web and other non-terminal clients."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .content import get_campaign, get_exits, get_room, item_from_id
from .rules import (
    apply_companion_action,
    apply_enemy_action,
    apply_exploration_action,
    apply_rest,
    active_challenge,
    award_campaign_completion,
    clear_round_buffs,
    challenge_blocks_movement,
    create_companion,
    create_player,
    drop_item,
    end_combat_if_needed,
    equip_item,
    move_player,
    normalize_inventory,
    reset_rest_streak,
    resolve_challenge,
    scale_companion_for_level,
    start_room,
    sync_player_ac,
    unequip_item,
    use_item,
)
from .state import GameState
from .rules.combat import resolve_player_action
from .rules.exploration import select_corpse_targets
from .rules.spells import (
    get_spell_definition,
    get_spell_mana_cost,
    is_healing_spell,
    resolve_spell_name,
)


@dataclass(frozen=True)
class EngineEvent:
    """One authoritative result emitted by a resolved command."""

    event_id: str
    turn: int
    type: str
    phase: str
    message: str
    actor: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "turn": self.turn,
            "type": self.type,
            "phase": self.phase,
            "message": self.message,
            "actor": self.actor,
            "data": deepcopy(self.data),
        }


@dataclass(frozen=True)
class CommandResult:
    accepted: bool
    command: str
    events: List[EngineEvent]
    state: Dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "command": self.command,
            "events": [item.to_dict() for item in self.events],
            "state": deepcopy(self.state),
            "error": self.error,
        }


def create_game(
    campaign_id: str = "ruined_watchtower",
    *,
    name: str = "Adventurer",
    player_class: str = "Fighter",
    race: str = "Human",
    sex: str = "Unspecified",
    stats: Optional[Dict[str, int]] = None,
    companion_id: Optional[str] = None,
) -> GameState:
    """Create a fully initialized game without reading from stdin."""

    campaign = get_campaign(campaign_id)
    allocated = stats or {"STR": 2, "DEX": 2, "CON": 2, "INT": 2, "WIS": 2, "CHA": 2}
    if set(allocated) != {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
        raise ValueError("Stats must include STR, DEX, CON, INT, WIS, and CHA.")
    if any(not isinstance(value, int) or value < 0 or value > 4 for value in allocated.values()):
        raise ValueError("Each stat must be an integer from 0 to 4.")
    if sum(allocated.values()) != 12:
        raise ValueError("Stat allocation must total 12 points.")
    if sex not in {"Male", "Female", "Unspecified"}:
        raise ValueError("Sex must be Male or Female.")
    player = create_player(name=name, cls=player_class, stats=allocated, race=race, sex=sex)
    companion = create_companion(campaign_id, companion_id)
    potion_stack = item_from_id(campaign_id, "healing_potion")
    potion_stack["quantity"] = 3
    inventory = [
        potion_stack,
        item_from_id(campaign_id, "leather_cap"),
        item_from_id(campaign_id, "worn_boots"),
    ]
    start_room_id = campaign.room_order[0]
    state = GameState(
        campaign_id=campaign_id,
        player=player,
        room_id=start_room_id,
        companions=[companion],
        inventory=inventory,
    )
    normalize_inventory(state)
    sync_player_ac(state)
    state.last_event = start_room(state, get_room(campaign_id, start_room_id))
    return state


class HeadlessEngine:
    """Resolve commands against a GameState and return client-safe snapshots."""

    def __init__(self, state: GameState):
        self.state = state
        # Keep existing saved Clerics aligned with the revised level-one class kit.
        if state.player.cls == "Cleric" and "Sacred Flame" not in state.player.learned_spells:
            state.player.learned_spells.append("Sacred Flame")

    @classmethod
    def new(cls, **kwargs: Any) -> "HeadlessEngine":
        return cls(create_game(**kwargs))

    @classmethod
    def from_adventurer(
        cls,
        source: GameState,
        *,
        campaign_id: str,
        companion_id: Optional[str] = None,
    ) -> "HeadlessEngine":
        """Start a fresh campaign while preserving a character's progression and gear."""
        from .characters import strip_campaign_quest_items
        from .state import Character, Companion

        carried = GameState.from_dict(source.to_dict())
        strip_campaign_quest_items(carried)
        player = Character.from_dict(carried.player.to_dict())
        player.hp = player.max_hp
        player.mana = player.max_mana
        player.conditions.clear()
        inventory = list(carried.inventory)
        potion_count = sum(
            max(1, int(item.get("quantity", 1))) for item in inventory
            if isinstance(item, dict) and str(item.get("id", "")).lower() == "healing_potion"
        )
        if potion_count < 3:
            restock = item_from_id(campaign_id, "healing_potion")
            restock["quantity"] = 3 - potion_count
            inventory.append(restock)

        campaign = get_campaign(campaign_id)
        start_room_id = campaign.room_order[0]
        selected_companion = create_companion(campaign_id, companion_id)
        scale_companion_for_level(selected_companion, player.level)
        prior_companion = next(
            (item for item in carried.companions if item.name == selected_companion.name),
            None,
        )
        if prior_companion is not None:
            relationship = Companion.from_dict(prior_companion.to_dict())
            selected_companion.trust = relationship.trust
            selected_companion.mood = relationship.mood
            selected_companion.tactic = relationship.tactic
            selected_companion.memories = list(relationship.memories)
        state = GameState(
            campaign_id=campaign_id,
            player=player,
            room_id=start_room_id,
            companions=[selected_companion],
            inventory=inventory,
            equipment=dict(carried.equipment),
            adventurer_id=carried.adventurer_id,
            adventurer_revision=carried.adventurer_revision,
        )
        normalize_inventory(state)
        sync_player_ac(state)
        state.last_event = start_room(state, get_room(campaign_id, start_room_id))
        return cls(state)

    @classmethod
    def restore(cls, payload: Dict[str, Any]) -> "HeadlessEngine":
        return cls(GameState.from_dict(payload))

    def snapshot(self) -> Dict[str, Any]:
        state = self.state
        room = get_room(state.campaign_id, state.room_id)
        campaign = get_campaign(state.campaign_id)
        phase = self._phase()
        return deepcopy({
            "schema_version": 1,
            "campaign": {
                "id": campaign.campaign_id,
                "name": campaign.name,
                "description": campaign.description,
                "room_order": list(campaign.room_order),
            },
            "phase": phase,
            "turn": state.turn,
            "room": {
                "id": room.room_id,
                "name": room.name,
                "description": room.description,
                "kind": room.kind,
                "exits": get_exits(state.campaign_id, state.room_id),
            },
            "player": state.player.to_dict(),
            "companions": [companion.to_dict() for companion in state.companions],
            "enemies": [
                {"id": index + 1, **enemy.to_dict()}
                for index, enemy in enumerate(state.enemies)
                if enemy.hp > 0
            ],
            "inventory": list(state.inventory),
            "equipment": dict(state.equipment),
            "flags": dict(state.flags),
            "available_actions": self.available_actions(),
            "spellbook": self.spellbook(),
            "challenge": active_challenge(state),
            "game_over": state.game_over,
            "save": state.to_dict(),
        })

    def available_actions(self) -> List[Dict[str, Any]]:
        state = self.state
        if state.game_over:
            return []
        common = [
            {"id": "use", "label": "Use item", "requires": ["item"]},
            {"id": "inventory", "label": "View inventory", "informational": True},
            {"id": "companion_advice", "label": "Ask companion"},
        ]
        if state.in_combat:
            actions = [
                {"id": "attack", "label": "Attack", "requires": ["target?"]},
                {"id": "defend", "label": "Defend"},
                {"id": "special", "label": "Special", "requires": ["target?"]},
            ]
            if state.player.cls == "Fighter":
                actions.append({"id": "guard_companion", "label": f"Guard {state.companion.name}"})
            if state.player.learned_spells:
                actions.append({"id": "spellbook", "label": "Open spellbook"})
            return actions + common
        actions = [
            {"id": "talk", "label": "Talk"},
            {"id": "search", "label": "Search"},
            {"id": "loot", "label": "Loot", "requires": ["target?"]},
            {"id": "rest", "label": "Rest"},
        ]
        if state.player.learned_spells:
            actions.append({"id": "spellbook", "label": "Open spellbook"})
        challenge = active_challenge(state)
        if challenge:
            for option in challenge["options"]:
                actions.append(
                    {
                        "id": "challenge",
                        "label": option["label"],
                        "target": option["id"],
                        "description": option.get("description", "Challenge approach"),
                        "disabled": not option["available"],
                        "disabled_reason": option.get("reason"),
                    }
                )
        for alias, destination in get_exits(state.campaign_id, state.room_id).items():
            if alias == destination:
                actions.append(
                    {
                        "id": "move",
                        "label": f"Move to {get_room(state.campaign_id, destination).name}",
                        "target": destination,
                        "disabled": bool(challenge and challenge["required"]),
                        "disabled_reason": "Resolve the required challenge before moving." if challenge and challenge["required"] else None,
                    }
                )
        return actions + common

    def spellbook(self) -> List[Dict[str, Any]]:
        """Return known spells with context-sensitive availability and targets."""
        state = self.state
        context = "combat" if state.in_combat else "exploration"
        entries: List[Dict[str, Any]] = []
        for spell_name in state.player.learned_spells:
            definition = get_spell_definition(spell_name)
            if not definition:
                continue
            targets: List[Dict[str, str]] = []
            if definition.target_type == "enemy":
                targets = [{"id": str(enemy_id + 1), "label": enemy.name} for enemy_id, enemy in enumerate(state.enemies) if enemy.hp > 0]
            elif definition.target_type == "self":
                targets = [{"id": "me", "label": state.player.name}]
            elif definition.target_type == "ally":
                targets = [{"id": "me", "label": state.player.name}]
                if state.companion.hp > 0:
                    targets.append({"id": state.companion.name, "label": state.companion.name})
            elif definition.target_type == "wounded_ally":
                if 0 < state.player.hp < state.player.max_hp:
                    targets.append({"id": "me", "label": state.player.name})
                if 0 < state.companion.hp < state.companion.max_hp:
                    targets.append({"id": state.companion.name, "label": state.companion.name})

            reason: Optional[str] = None
            if context not in definition.contexts:
                reason = "Combat only" if definition.contexts == ("combat",) else "Exploration only"
            elif state.player.mana < definition.mana_cost:
                reason = f"Requires {definition.mana_cost} mana"
            elif not targets:
                reason = "No valid targets"
            elif spell_name == "Detect Magic" and state.flags.get(f"detect_magic:{state.room_id}"):
                reason = "Already examined this location"
            elif spell_name == "Guidance" and state.flags.get("guidance_active"):
                reason = "Guidance is already active"

            entries.append({**definition.to_dict(), "targets": targets, "available": reason is None, "reason": reason})
        return entries

    def execute(
        self,
        command: str,
        *,
        target: Optional[str] = None,
        spell: Optional[str] = None,
        item: Optional[str] = None,
    ) -> CommandResult:
        if not isinstance(command, str):
            return self._rejected("", "A command must be text.")
        for label, value in (("target", target), ("spell", spell), ("item", item)):
            if value is not None and not isinstance(value, str):
                return self._rejected(command, f"A {label} must be text.")
        normalized = command.strip().lower()
        if self.state.game_over:
            return self._rejected(normalized, "The campaign is already over.")

        before = self._metrics()
        messages: List[str] = []
        accepted = True

        if normalized == "move":
            if self.state.in_combat:
                return self._rejected(normalized, "You cannot leave during combat.")
            if not target:
                return self._rejected(normalized, "A destination is required.")
            if challenge_blocks_movement(self.state):
                return self._rejected(normalized, "You must resolve the challenge before moving on.")
            ok, message = move_player(self.state, target.lower())
            if not ok:
                return self._rejected(normalized, message)
            messages.append(message)
        elif normalized == "rest":
            if self.state.in_combat:
                return self._rejected(normalized, "You cannot rest during combat.")
            messages.append(apply_rest(self.state))
            from .rules.companion_interactions import rest_reaction
            reaction = rest_reaction(self.state)
            if reaction:
                messages.append(reaction)
        elif normalized == "challenge":
            if self.state.in_combat:
                return self._rejected(normalized, "There is no time for that during combat.")
            if not target:
                return self._rejected(normalized, "Choose an approach to the challenge.")
            resolved, message = resolve_challenge(self.state, target)
            if not resolved:
                return self._rejected(normalized, message)
            messages.append(message)
        elif normalized == "companion_talk":
            if self.state.in_combat:
                return self._rejected(normalized, "There is no time for a conversation during combat.")
            from .rules.companion_interactions import talk_to_companion
            messages.append(talk_to_companion(self.state))
        elif normalized == "companion_advice":
            from .rules.companion_interactions import companion_advice
            messages.append(companion_advice(self.state))
        elif normalized == "set_tactic":
            if not target:
                return self._rejected(normalized, "A tactic is required.")
            from .rules.companion_interactions import set_companion_tactic
            try:
                messages.append(set_companion_tactic(self.state, target))
            except ValueError as error:
                return self._rejected(normalized, str(error))
        elif normalized == "use":
            query = (item or "healing potion").strip()
            used, message = use_item(self.state, query, target)
            if not used:
                return self._rejected(normalized, message)
            messages.append(message)
            if self.state.in_combat:
                messages.extend(self._resolve_other_combatants())
        elif normalized == "drop":
            if self.state.in_combat:
                return self._rejected(normalized, "You cannot rearrange your pack during combat.")
            if not item:
                return self._rejected(normalized, "An item is required.")
            dropped, message = drop_item(self.state, item)
            if not dropped:
                return self._rejected(normalized, message)
            messages.append(message)
        elif normalized == "equip":
            if not item:
                return self._rejected(normalized, "An item is required.")
            equipped, message = equip_item(self.state, item)
            if not equipped:
                return self._rejected(normalized, message)
            messages.append(message)
        elif normalized == "unequip":
            if not target:
                return self._rejected(normalized, "An equipment slot is required.")
            removed, message = unequip_item(self.state, target)
            if not removed:
                return self._rejected(normalized, message)
            messages.append(message)
        elif normalized == "cast" and not self.state.in_combat:
            resolved, error = resolve_spell_name(self.state.player.learned_spells, spell or "")
            if error:
                return self._rejected(normalized, error)
            definition = get_spell_definition(resolved or "")
            if not definition or "exploration" not in definition.contexts:
                return self._rejected(normalized, "That spell cannot be cast outside combat.")
            if self.state.player.mana < get_spell_mana_cost(resolved):
                return self._rejected(normalized, "You are out of mana.")
            if is_healing_spell(resolved):
                outcome = resolve_player_action(self.state, "special", target, resolved)
                if not outcome.accepted:
                    return self._rejected(normalized, outcome.message)
                messages.append(outcome.message)
            elif resolved == "Detect Magic":
                flag = f"detect_magic:{self.state.room_id}"
                if self.state.flags.get(flag):
                    return self._rejected(normalized, "You have already examined this location for magic.")
                self.state.player.mana -= definition.mana_cost
                self.state.flags[flag] = True
                room = get_room(self.state.campaign_id, self.state.room_id)
                messages.append(f"Arcane traces sharpen into view around {room.name}. Nothing magical here can surprise you now.")
            elif resolved == "Guidance":
                if self.state.flags.get("guidance_active"):
                    return self._rejected(normalized, "Guidance is already active.")
                self.state.player.mana -= definition.mana_cost
                self.state.flags["guidance_active"] = True
                messages.append("A quiet certainty settles over you. Your next social, search, or lock check gains +2.")
            else:
                return self._rejected(normalized, "That utility spell has no effect here.")
        elif self.state.in_combat:
            if normalized == "cast":
                resolved, error = resolve_spell_name(self.state.player.learned_spells, spell or "")
                if error:
                    return self._rejected(normalized, error)
                definition = get_spell_definition(resolved or "")
                if not definition or "combat" not in definition.contexts:
                    return self._rejected(normalized, "That spell cannot be cast during combat.")
                spell = resolved
                normalized = "special"
            if normalized not in {"attack", "defend", "special", "guard_companion"}:
                return self._rejected(command, "That action is not available during combat.")
            if normalized == "guard_companion" and self.state.player.cls != "Fighter":
                return self._rejected(command, "Only a fighter can guard a companion.")
            outcome = resolve_player_action(self.state, normalized, target, spell)
            if not outcome.accepted:
                return self._rejected(command, outcome.message)
            messages.append(outcome.message)
            messages.extend(self._resolve_other_combatants())
        else:
            if normalized not in {"talk", "search", "loot", "inspect", "open"}:
                return self._rejected(normalized, "That action is not available here.")
            if normalized == "loot" and get_room(self.state.campaign_id, self.state.room_id).kind == "combat":
                _, error = select_corpse_targets(self.state, target)
                if error:
                    return self._rejected(command, error)
            action = normalized
            if target and normalized == "loot":
                action = f"loot {target}"
            messages.append(apply_exploration_action(self.state, action))

        self.state.turn += 1
        self.state.last_player_input = command
        self.state.last_event = " ".join(messages)
        if normalized != "rest":
            reset_rest_streak(self.state)
        self._award_completion_once(messages)
        after = self._metrics()
        events = self._events(messages, before, after)
        self.state.turn_log.append(
            f"Turn {self.state.turn}: input={command!r} | {self.state.last_event}"
        )
        return CommandResult(
            accepted=accepted,
            command=command,
            events=events,
            state=self.snapshot(),
        )

    def _resolve_other_combatants(self) -> List[str]:
        from .rules.conditions import resolve_condition_ticks

        messages = resolve_condition_ticks(self.state)
        if self.state.player.hp <= 0:
            self.state.game_over = True
            messages.append("You collapse as the poison takes its final toll.")
            return messages
        messages.append(apply_companion_action(self.state))
        messages.extend(apply_enemy_action(self.state))
        if 0 < self.state.companion.hp <= max(3, self.state.companion.max_hp // 4):
            messages.append(
                f"Warning: {self.state.companion.name} is critically wounded at "
                f"{self.state.companion.hp}/{self.state.companion.max_hp} HP."
            )
        clear_round_buffs(self.state)
        ended = end_combat_if_needed(self.state)
        if ended:
            messages.append(ended)
            if not self.state.in_combat and not self.state.game_over:
                from .rules.companion_interactions import post_combat_reaction
                reaction = post_combat_reaction(self.state)
                if reaction:
                    messages.append(reaction)
        return messages

    def _award_completion_once(self, messages: List[str]) -> None:
        messages.extend(award_campaign_completion(self.state))

    def _phase(self) -> str:
        if self.state.game_over:
            return "defeat" if self.state.player.hp <= 0 else "victory"
        return "combat" if self.state.in_combat else "exploration"

    def _metrics(self) -> Dict[str, Any]:
        state = self.state
        return {
            "room_id": state.room_id,
            "player_hp": state.player.hp,
            "player_mana": state.player.mana,
            "companion_hp": state.companion.hp,
            "xp": state.player.xp,
            "gold": state.player.gold,
            "enemy_hp": [enemy.hp for enemy in state.enemies],
            "in_combat": state.in_combat,
            "game_over": state.game_over,
        }

    def _events(
        self, messages: List[str], before: Dict[str, Any], after: Dict[str, Any]
    ) -> List[EngineEvent]:
        phase = self._phase()
        deltas = {
            key: after[key] - before[key]
            for key in ("player_hp", "player_mana", "companion_hp", "xp", "gold")
            if after[key] != before[key]
        }
        events: List[EngineEvent] = []
        for index, message in enumerate(messages):
            lowered = message.lower()
            event_type = "narrative"
            actor: Optional[str] = None
            if "roll " in lowered or "->" in message:
                event_type = "roll_resolved"
            if "damage" in lowered or "strikes" in lowered or "lashes at" in lowered:
                event_type = "damage_applied"
            if "heal" in lowered:
                event_type = "healing_applied"
            if "is poisoned" in lowered or "resists the venom" in lowered:
                event_type = "condition_applied" if "is poisoned" in lowered else "condition_resisted"
            if "poison courses" in lowered:
                event_type = "condition_tick"
            if "xp +" in lowered or "campaign complete" in lowered:
                event_type = "progression_awarded"
            if "loot" in lowered or "gold" in lowered or "find " in lowered:
                event_type = "loot_resolved"
            if before["room_id"] != after["room_id"]:
                event_type = "room_entered"
            if self.state.player.name.lower() in lowered or lowered.startswith("you "):
                actor = "player"
            elif self.state.companion.name.lower() in lowered:
                actor = "companion"
                if event_type == "narrative":
                    event_type = "companion_interaction"
            data = deltas if index == len(messages) - 1 else {}
            events.append(
                EngineEvent(
                    event_id=str(uuid4()),
                    turn=self.state.turn,
                    type=event_type,
                    phase=phase,
                    message=message,
                    actor=actor,
                    data=data,
                )
            )
        if before["in_combat"] != after["in_combat"]:
            events.append(
                EngineEvent(
                    event_id=str(uuid4()),
                    turn=self.state.turn,
                    type="combat_started" if after["in_combat"] else "combat_ended",
                    phase=phase,
                    message="Combat begins." if after["in_combat"] else "Combat ends.",
                )
            )
        if not before["game_over"] and after["game_over"]:
            events.append(
                EngineEvent(
                    event_id=str(uuid4()),
                    turn=self.state.turn,
                    type="campaign_completed" if self.state.player.hp > 0 else "game_over",
                    phase=phase,
                    message="The campaign is complete." if self.state.player.hp > 0 else "The adventure ends here.",
                )
            )
        return events

    def _rejected(self, command: str, message: str) -> CommandResult:
        return CommandResult(
            accepted=False,
            command=command,
            events=[],
            state=self.snapshot(),
            error=message,
        )
