"""Combat resolution: attacks, companion actions, enemy actions."""

from __future__ import annotations

from typing import List, Optional

from ..content import get_mob_profile
from ..state import Enemy, GameState
from ..util import pick_target_by_hp

from .dice import roll_die, roll_dice
from .flags import get_flag_dict, get_flag_list, next_corpse_id


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


def _select_enemy(state: GameState, query: Optional[str]) -> tuple[Optional[Enemy], Optional[str]]:
    if not state.enemies:
        return None, "There's nothing to attack."
    alive = [enemy for enemy in state.enemies if enemy.hp > 0]
    if not alive:
        return None, "There's nothing to attack."
    if not query:
        return min(alive, key=lambda item: item.hp), None
    token = query.strip().lower()
    if token.isdigit():
        idx = int(token) - 1
        if idx < 0 or idx >= len(alive):
            return None, "That target doesn't exist."
        return alive[idx], None
    matches = [enemy for enemy in alive if token in enemy.name.lower()]
    if not matches:
        return None, "No such target."
    if len(matches) > 1:
        return None, "Be more specific."
    return matches[0], None


def apply_player_action(state: GameState, action: str, target: Optional[str] = None) -> str:
    from .player import is_caster

    action = action.lower()
    state.player_defending = False
    if action == "defend":
        state.player_defending = True
        return f"{state.player.name} takes a defensive stance (+2 AC until next attack)."

    target_enemy, error = _select_enemy(state, target)
    if error:
        return error
    if not target_enemy:
        return "There's nothing to attack."

    special_bonus = 0
    attack_bonus = state.player.attack_bonus
    damage_expr = state.player.damage
    flavor = ""

    if action == "special":
        if state.player.cls == "Wizard":
            from .spells import SPELL_DAMAGE, get_best_damage_spell

            spell_name = get_best_damage_spell(state.player.learned_spells)
            if not spell_name or spell_name not in SPELL_DAMAGE:
                return "You have no damage spells to cast."
            damage_expr, mana_cost = SPELL_DAMAGE[spell_name]
            if state.player.mana < mana_cost:
                return "You are out of mana."
            state.player.mana -= mana_cost
            attack_bonus += state.player.stats.get("INT", 0)
            flavor = f"You channel {spell_name}. "
        elif state.player.cls == "Fighter":
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


def apply_companion_action(state: GameState) -> str:
    from .spells import SPELL_DAMAGE, get_best_damage_spell

    companion = state.companion
    if companion.hp <= 0:
        return f"{companion.name} is down and cannot act."
    state.companion_defending = False
    defend_threshold = getattr(companion, "defend_hp_threshold", 3)
    if companion.hp <= defend_threshold:
        state.companion_defending = True
        return f"{companion.name} keeps their distance and braces (+2 AC)."
    target_enemy, error = _select_enemy(state, None)
    if error or not target_enemy:
        return f"{companion.name} scans the room, weapon lowered."

    # Caster companion: cast damage spell if mana >= cost and has spell
    spell_name = get_best_damage_spell(companion.learned_spells) if companion.learned_spells else None
    if spell_name and spell_name in SPELL_DAMAGE:
        damage_expr, mana_cost = SPELL_DAMAGE[spell_name]
        if companion.mana >= mana_cost and companion.max_mana > 0:
            companion.mana -= mana_cost
            hit, roll, total = _attack_roll(
                attacker_bonus=companion.attack_bonus,
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
        attacker_bonus=companion.attack_bonus,
        target_ac=target_enemy.ac,
        target_defending=False,
    )
    if hit:
        new_hp, detail = _apply_damage(target_enemy.hp, companion.damage)
        target_enemy.hp = new_hp
        return f"{companion.name} strikes {target_enemy.name} (roll {roll} -> {total}) for {detail} damage."
    return f"{companion.name} misses {target_enemy.name} (roll {roll} -> {total})."


def apply_enemy_action(state: GameState) -> List[str]:
    alive = [enemy for enemy in state.enemies if enemy.hp > 0]
    if not alive:
        return ["The foes are down."]

    results: List[str] = []
    companion = state.companion
    for enemy in alive:
        profile = get_mob_profile(state.campaign_id, enemy.name)
        ai = getattr(profile, "ai", "focus_weakest")
        if ai == "focus_player":
            target = "player" if state.player.hp > 0 else "companion"
        elif ai == "focus_companion":
            target = "companion" if companion.hp > 0 else "player"
        else:
            targets = [("player", state.player.hp)]
            if companion.hp > 0:
                targets.append(("companion", companion.hp))
            target = pick_target_by_hp(targets)

        if target == "player":
            hit, roll, total = _attack_roll(
                attacker_bonus=enemy.attack_bonus,
                target_ac=state.player.ac,
                target_defending=state.player_defending,
            )
            if hit:
                new_hp, detail = _apply_damage(state.player.hp, enemy.damage)
                state.player.hp = new_hp
                results.append(
                    f"{enemy.name} strikes {state.player.name} (roll {roll} -> {total}) for {detail} damage."
                )
            else:
                results.append(
                    f"{enemy.name} misses {state.player.name} (roll {roll} -> {total})."
                )
            continue

        hit, roll, total = _attack_roll(
            attacker_bonus=enemy.attack_bonus,
            target_ac=companion.ac,
            target_defending=state.companion_defending,
        )
        if hit:
            new_hp, detail = _apply_damage(companion.hp, enemy.damage)
            companion.hp = new_hp
            results.append(
                f"{enemy.name} lashes at {companion.name} (roll {roll} -> {total}) for {detail} damage."
            )
        else:
            results.append(f"{enemy.name} misses {companion.name} (roll {roll} -> {total}).")
    return results


def end_combat_if_needed(state: GameState) -> Optional[str]:
    from .experience import grant_xp

    if not state.enemies:
        return None
    if all(enemy.hp <= 0 for enemy in state.enemies):
        state.in_combat = False
        defeated_rooms = get_flag_list(state, "defeated_rooms")
        if state.room_id not in defeated_rooms:
            defeated_rooms.append(state.room_id)
        total_xp = sum(
            getattr(get_mob_profile(state.campaign_id, e.name), "xp", 0)
            for e in state.enemies
        )
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
    if state.player.hp <= 0:
        state.game_over = True
        return "You collapse from your wounds. The watchtower claims another victim."
    return None
