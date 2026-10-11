"""Combat resolution: attacks, companion actions, enemy actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..content import get_campaign, get_mob_profile
from ..state import Enemy, GameState

from .dice import roll_die, roll_dice
from .conditions import attempt_poison
from .flags import get_flag_dict, get_flag_list, next_corpse_id
from .spells import (
    SPELL_DAMAGE,
    SPELL_HEAL,
    get_best_damage_spell,
    get_spell_mana_cost,
    is_damage_spell,
    is_healing_spell,
    resolve_spell_name,
)


def _attack_roll(attacker_bonus: int, target_ac: int, target_defending: bool) -> tuple[bool, int, int]:
    roll = roll_die(20)
    total = roll + attacker_bonus
    effective_ac = target_ac + (2 if target_defending else 0)
    return total >= effective_ac, roll, total


def _apply_damage(target_hp: int, damage_expr: str, bonus: int = 0) -> tuple[int, str]:
    damage, detail = roll_dice(damage_expr)
    if bonus:
        detail = f"{detail}{bonus:+d}"
    damage += bonus
    return max(0, target_hp - damage), f"{damage} ({detail})"


def _select_heal_target(
    state: GameState, query: Optional[str], *, wounded: bool = True
) -> tuple[Optional[str], Optional[str]]:
    """Resolve ally aliases/names once, excluding fallen and (for healing) full allies.

    Untargeted healing chooses the lowest HP fraction, with player winning ties.
    An explicit invalid target never falls back to another actor.
    """
    if query is not None and not isinstance(query, str):
        return None, "A target must be text."
    token = (query or "").strip().lower()
    actors = {"player": state.player, "companion": state.companion}
    if not token:
        eligible = [key for key, actor in actors.items()
                    if actor.hp > 0 and (not wounded or actor.hp < actor.max_hp)]
        if not eligible:
            return None, "There are no valid wounded allies." if wounded else "There are no living allies."
        key = min(eligible, key=lambda key: actors[key].hp / max(1, actors[key].max_hp))
    elif token in {"me", "self", "player", "you", "myself"}:
        key = "player"
    elif token in {"companion", "her", "him", "them"}:
        key = "companion"
    else:
        matches = [key for key, actor in actors.items() if token == actor.name.lower()]
        if not matches:
            matches = [key for key, actor in actors.items() if token in actor.name.lower()]
        if len(matches) != 1:
            return None, "Be more specific." if matches else "No such ally."
        key = matches[0]
    actor = actors[key]
    if actor.hp <= 0:
        return None, "Cure Wounds cannot revive a fallen ally." if wounded else "That ally has fallen."
    if wounded and actor.hp >= actor.max_hp:
        return None, f"{actor.name} is already at full health."
    return key, None


def _select_enemy(state: GameState, query: Optional[str]) -> tuple[Optional[Enemy], Optional[str]]:
    if not state.enemies:
        return None, "There's nothing to attack."
    alive = [enemy for enemy in state.enemies if enemy.hp > 0]
    if not alive:
        return None, "There's nothing to attack."
    if query is not None and not isinstance(query, str):
        return None, "A target must be text."
    token = (query or "").strip().lower()
    if not token:
        return min(alive, key=lambda item: item.hp), None
    if token.isascii() and token.isdecimal():
        # Compare textual IDs rather than parsing arbitrary-sized user integers.
        target = next((enemy for index, enemy in enumerate(state.enemies, 1)
                       if str(index) == token.lstrip("0") and enemy.hp > 0), None)
        return (target, None) if target else (None, "That target doesn't exist.")
    matches = [enemy for enemy in alive if token in enemy.name.lower()]
    if not matches:
        return None, "No such target."
    if len(matches) > 1:
        return None, "Be more specific."
    return matches[0], None


@dataclass(frozen=True)
class ActionResult:
    accepted: bool
    message: str


class _ActionRejected(Exception):
    """Internal validation failure, raised before any state mutation."""


def resolve_player_action(
    state: GameState, action: str, target: Optional[str] = None, spell_name: Optional[str] = None
) -> ActionResult:
    """Typed boundary: rejected actions leave all state untouched."""
    try:
        message = _apply_player_action(state, action, target, spell_name)
    except _ActionRejected as error:
        return ActionResult(False, str(error))
    if action.strip().lower() not in {"defend", "guard_companion"}:
        state.player_defending = False
    return ActionResult(True, message)


def apply_player_action(
    state: GameState, action: str, target: Optional[str] = None, spell_name: Optional[str] = None
) -> str:
    """Compatibility string API; use resolve_player_action for acceptance status."""
    return resolve_player_action(state, action, target, spell_name).message


def _apply_player_action(
    state: GameState, action: str, target: Optional[str] = None, spell_name: Optional[str] = None
) -> str:
    from .player import is_caster

    if not isinstance(action, str):
        raise _ActionRejected("An action must be text.")
    if target is not None and not isinstance(target, str):
        raise _ActionRejected("A target must be text.")
    if spell_name is not None and not isinstance(spell_name, str):
        raise _ActionRejected("A spell must be text.")
    action = action.strip().lower()
    if action not in {"attack", "special", "defend", "guard_companion"}:
        raise _ActionRejected("That combat action is not available.")
    if action == "defend":
        state.player_defending = True
        return f"{state.player.name} takes a defensive stance (+2 AC until next attack)."
    if action == "guard_companion":
        if state.player.cls != "Fighter":
            raise _ActionRejected("Only a fighter can reliably intercept an attack this way.")
        state.player_guarding_companion = True
        state.player_defending = True
        return (
            f"{state.player.name} moves to guard {state.companion.name}, ready to intercept "
            "the next attack against them (+2 AC)."
        )

    # Spell casting: explicit spell or "special" (auto best damage for casters)
    if spell_name or (action == "special" and is_caster(state.player.cls)):
        if spell_name:
            resolved, err = resolve_spell_name(state.player.learned_spells, spell_name)
            if err:
                raise _ActionRejected(err)
            spell_name = resolved
        else:
            spell_name = get_best_damage_spell(state.player.learned_spells)
            if not spell_name or not is_damage_spell(spell_name):
                raise _ActionRejected("You have no damage spells to cast.")

        mana_cost = get_spell_mana_cost(spell_name)
        if mana_cost <= 0:
            raise _ActionRejected(f"You don't know how to cast {spell_name}.")
        if state.player.mana < mana_cost:
            raise _ActionRejected(f"Requires {mana_cost} mana; {state.player.mana} available.")

        # Cure Wounds: healing spell, target player or companion
        if spell_name == "Cure Wounds":
            heal_target, err = _select_heal_target(state, target)
            if err:
                raise _ActionRejected(err)
            state.player.mana -= mana_cost
            heal_dice, _ = SPELL_HEAL[spell_name]
            amount, detail = roll_dice(heal_dice)
            if heal_target == "player":
                old_hp = state.player.hp
                state.player.hp = min(state.player.max_hp, old_hp + amount)
                healed = state.player.hp - old_hp
                return f"You cast Cure Wounds on yourself, healing {healed} ({detail})."
            companion = state.companion
            old_hp = companion.hp
            companion.hp = min(companion.max_hp, old_hp + amount)
            healed = companion.hp - old_hp
            return f"You cast Cure Wounds on {companion.name}, healing {healed} ({detail})."

        # Bless: +1 AC and +1 attack until next turn for one ally
        if spell_name == "Bless":
            bless_target, err = _select_heal_target(state, target, wounded=False)
            if err:
                raise _ActionRejected(err)
            state.player.mana -= mana_cost
            if bless_target == "player":
                state.player_bless_active = True
                return "You bless yourself. +1 AC and +1 attack until your next turn."
            state.companion_bless_active = True
            return f"You bless {state.companion.name}. +1 AC and +1 attack until your next turn."

        # Shield: self-buff, no target
        if spell_name == "Shield":
            if target and target.strip():
                shield_target, error = _select_heal_target(state, target, wounded=False)
                if error or shield_target != "player":
                    raise _ActionRejected(error or "Shield can only target yourself.")
            state.player.mana -= mana_cost
            state.player_shield_active = True
            return f"You weave a shimmering barrier. +2 AC until your next turn."

        # Sleep: control spell, needs target
        if spell_name == "Sleep":
            target_enemy, error = _select_enemy(state, target)
            if error:
                raise _ActionRejected(error)
            if not target_enemy:
                raise _ActionRejected("There's nothing to cast Sleep on.")
            state.player.mana -= mana_cost  # Pay before save
            dc = 12 + state.player.stats.get("INT", 0)
            save_roll = roll_die(20)
            if save_roll >= dc:
                return f"You cast Sleep at {target_enemy.name}. They resist (roll {save_roll} vs DC {dc})."
            target_enemy.asleep = True
            return f"You cast Sleep. {target_enemy.name} slumps, unconscious (roll {save_roll} vs DC {dc})."

        # Damage spell
        if is_damage_spell(spell_name) and spell_name in SPELL_DAMAGE:
            target_enemy, error = _select_enemy(state, target)
            if error:
                raise _ActionRejected(error)
            if not target_enemy:
                raise _ActionRejected("There's nothing to attack.")
            damage_expr, _ = SPELL_DAMAGE[spell_name]
            state.player.mana -= mana_cost
            spell_mod = state.player.stats.get("WIS", 0) if state.player.cls == "Cleric" else state.player.stats.get("INT", 0)
            prepared_bonus = int(state.flags.pop("prepared_strike", 0))
            attack_bonus = state.player.attack_bonus + spell_mod + (1 if state.player_bless_active else 0) + prepared_bonus
            hit, roll, total = _attack_roll(
                attacker_bonus=attack_bonus,
                target_ac=target_enemy.ac,
                target_defending=False,
            )
            if hit:
                new_hp, detail = _apply_damage(target_enemy.hp, damage_expr)
                target_enemy.hp = new_hp
                return f"You channel {spell_name}. Hit {target_enemy.name} (roll {roll} -> {total}) for {detail} damage."
            return f"You channel {spell_name}. Miss {target_enemy.name} (roll {roll} -> {total})."

        raise _ActionRejected("That spell cannot be resolved as a combat action.")

    # Melee: attack, Fighter/Rogue special
    target_enemy, error = _select_enemy(state, target)
    if error:
        raise _ActionRejected(error)
    if not target_enemy:
        raise _ActionRejected("There's nothing to attack.")

    special_bonus = 0
    from .inventory import equipment_attack_bonus, equipped_damage

    prepared_bonus = int(state.flags.pop("prepared_strike", 0))
    attack_bonus = state.player.attack_bonus + equipment_attack_bonus(state) + (1 if state.player_bless_active else 0) + prepared_bonus
    damage_expr = equipped_damage(state)
    flavor = ""

    if action == "special":
        if state.player.cls == "Fighter":
            special_bonus = 2
            flavor = "You drive a heavy power strike. "
        elif state.player.cls == "Rogue":
            attack_bonus += 2
            flavor = "You line up a precise shot. "

    hit, roll, total = _attack_roll(
        attacker_bonus=attack_bonus,
        target_ac=target_enemy.ac,
        target_defending=False,
    )
    if hit:
        new_hp, detail = _apply_damage(target_enemy.hp, damage_expr, bonus=special_bonus)
        target_enemy.hp = new_hp
        return f"{flavor}Hit {target_enemy.name} (roll {roll} -> {total}) for {detail} damage."
    return f"{flavor}Miss {target_enemy.name} (roll {roll} -> {total})."


def clear_round_buffs(state: GameState) -> None:
    """Clear temporary buffs at end of combat round."""
    state.player_shield_active = False
    state.player_bless_active = False
    state.companion_bless_active = False
    state.player_guarding_companion = False


def apply_companion_action(state: GameState) -> str:
    from .spells import SPELL_DAMAGE, get_best_damage_spell

    companion = state.companion
    if companion.hp <= 0:
        return f"{companion.name} is down and cannot act."
    state.companion_defending = False
    tactic = getattr(companion, "tactic", "balanced")
    alive = [enemy for enemy in state.enemies if enemy.hp > 0]
    defend_threshold = getattr(companion, "defend_hp_threshold", 3) + (2 if tactic == "cautious" else 0)
    if tactic == "cautious" and len(alive) > 1:
        defend_threshold += 2
    if companion.hp <= defend_threshold:
        state.companion_defending = True
        return f"{companion.name} keeps their distance and braces (+2 AC)."
    if tactic == "cautious" and state.player.hp <= max(3, state.player.max_hp // 3):
        state.player_defending = True
        state.companion_defending = True
        return f"{companion.name} covers {state.player.name}, granting +2 AC to both until the enemies act."
    target_enemy = (
        max(alive, key=lambda enemy: enemy.hp)
        if alive and tactic == "aggressive"
        else min(alive, key=lambda enemy: enemy.hp)
        if alive
        else None
    )
    error = None if target_enemy else "There's nothing to attack."
    if error or not target_enemy:
        return f"{companion.name} scans the room, weapon lowered."

    # Caster companion: cast damage spell if mana >= cost and has spell
    spell_name = get_best_damage_spell(companion.learned_spells) if companion.learned_spells else None
    comp_attack_bonus = companion.attack_bonus + (1 if state.companion_bless_active else 0) + (1 if tactic == "aggressive" else 0)
    if spell_name and spell_name in SPELL_DAMAGE:
        damage_expr, mana_cost = SPELL_DAMAGE[spell_name]
        if companion.mana >= mana_cost and companion.max_mana > 0:
            companion.mana -= mana_cost
            hit, roll, total = _attack_roll(
                attacker_bonus=comp_attack_bonus,
                target_ac=target_enemy.ac,
                target_defending=False,
            )
            if hit:
                new_hp, detail = _apply_damage(target_enemy.hp, damage_expr)
                target_enemy.hp = new_hp
                return f"{companion.name} channels {spell_name}. Hit {target_enemy.name} (roll {roll} -> {total}) for {detail} damage."
            return f"{companion.name} channels {spell_name}. Miss {target_enemy.name} (roll {roll} -> {total})."

    # Melee attack
    hit, roll, total = _attack_roll(
        attacker_bonus=comp_attack_bonus,
        target_ac=target_enemy.ac,
        target_defending=False,
    )
    if hit:
        new_hp, detail = _apply_damage(
            target_enemy.hp,
            companion.damage,
            bonus=1 if tactic == "aggressive" else 0,
        )
        target_enemy.hp = new_hp
        return f"{companion.name} strikes {target_enemy.name} (roll {roll} -> {total}) for {detail} damage."
    return f"{companion.name} misses {target_enemy.name} (roll {roll} -> {total})."


def apply_enemy_action(state: GameState) -> List[str]:
    alive = [enemy for enemy in state.enemies if enemy.hp > 0]
    if not alive:
        return ["The foes are down."]

    results: List[str] = []
    companion = state.companion
    target_counts = {"player": 0, "companion": 0}
    for enemy in alive:
        if getattr(enemy, "asleep", False):
            enemy.asleep = False
            results.append(f"{enemy.name} stirs and wakes.")
            continue
        profile = get_mob_profile(state.campaign_id, enemy.name)
        ai = getattr(profile, "ai", "focus_weakest")
        if ai == "focus_player":
            target = "player" if state.player.hp > 0 else "companion"
        elif ai == "focus_companion":
            target = "companion" if companion.hp > 0 else "player"
        else:
            if companion.hp <= 0:
                target = "player"
            else:
                player_score = state.player.hp / max(1, state.player.max_hp) + target_counts["player"] * 0.75
                companion_score = companion.hp / max(1, companion.max_hp) + target_counts["companion"] * 0.75
                target = "companion" if companion_score < player_score else "player"

        if target == "companion" and state.player_guarding_companion and state.player.hp > 0:
            state.player_guarding_companion = False
            target = "player"
            results.append(
                f"{state.player.name} intercepts an attack meant for {companion.name}."
            )
        target_counts[target] += 1

        if target == "player":
            ac = state.player.ac + (2 if state.player_shield_active else 0) + (1 if state.player_bless_active else 0)
            hit, roll, total = _attack_roll(
                attacker_bonus=enemy.attack_bonus,
                target_ac=ac,
                target_defending=state.player_defending,
            )
            if hit:
                new_hp, detail = _apply_damage(state.player.hp, enemy.damage)
                state.player.hp = new_hp
                results.append(
                    f"{enemy.name} strikes {state.player.name} (roll {roll} -> {total}) for {detail} damage."
                )
                condition = getattr(profile, "on_hit_condition", {})
                if condition.get("id") == "poisoned":
                    result = attempt_poison(
                        state.player,
                        dc=int(condition.get("dc", 12)),
                        duration=int(condition.get("duration", 2)),
                    )
                    if result:
                        results.append(result)
            else:
                results.append(
                    f"{enemy.name} misses {state.player.name} (roll {roll} -> {total})."
                )
            continue

        comp_ac = companion.ac + (1 if state.companion_bless_active else 0)
        hit, roll, total = _attack_roll(
            attacker_bonus=enemy.attack_bonus,
            target_ac=comp_ac,
            target_defending=state.companion_defending,
        )
        if hit:
            new_hp, detail = _apply_damage(companion.hp, enemy.damage)
            companion.hp = new_hp
            results.append(
                f"{enemy.name} lashes at {companion.name} (roll {roll} -> {total}) for {detail} damage."
            )
            condition = getattr(profile, "on_hit_condition", {})
            if condition.get("id") == "poisoned":
                result = attempt_poison(
                    companion,
                    dc=int(condition.get("dc", 12)),
                    duration=int(condition.get("duration", 2)),
                )
                if result:
                    results.append(result)
        else:
            results.append(f"{enemy.name} misses {companion.name} (roll {roll} -> {total}).")
    return results


def end_combat_if_needed(state: GameState) -> Optional[str]:
    from .experience import grant_xp

    if state.player.hp <= 0:
        state.game_over = True
        return "You collapse from your wounds. Your adventure ends here."
    if not state.enemies:
        return None
    if all(enemy.hp <= 0 for enemy in state.enemies):
        state.in_combat = False
        state.player.conditions.pop("poisoned", None)
        state.companion.conditions.pop("poisoned", None)
        defeated_rooms = get_flag_list(state, "defeated_rooms")
        if state.room_id not in defeated_rooms:
            defeated_rooms.append(state.room_id)
        total_xp = sum(
            getattr(get_mob_profile(state.campaign_id, e.name), "xp", 0)
            for e in state.enemies
        )
        campaign = get_campaign(state.campaign_id)
        if state.player.campaign_completions.get(state.campaign_id, 0) > 0:
            total_xp = int(total_xp * campaign.repeat_reward_multiplier)
        if state.player.level >= campaign.recommended_level + 2:
            total_xp = int(total_xp * 0.5)
        level_messages = grant_xp(state, total_xp) if total_xp > 0 else []
        corpses = get_flag_dict(state, "corpses")
        entries = []
        for enemy in state.enemies:
            entries.append({"id": next_corpse_id(state), "name": enemy.name, "looted": False})
        corpses[state.room_id] = entries
        state.enemies = []
        corpse_list = ", ".join(f"{entry['id']}. {entry['name']}" for entry in entries)
        hint = ""
        if any(not entry.get("looted") for entry in entries):
            hint = " You can 'loot <number>' or 'loot all'."
        parts = [f"The foes fall. Corpses: {corpse_list}.{hint} The way forward is clear."]
        if total_xp > 0:
            parts.append(f"XP +{total_xp}.")
        parts.extend(level_messages)
        return " ".join(parts)
    return None
