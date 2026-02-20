from __future__ import annotations

import os
import re

from .agents import companion_suggest, gm_narrate, gm_narrate_with_source
from .content import get_campaign, get_exits, get_room, item_from_id, list_campaigns
from .profiles import (
    get_class_profile,
    get_race_profile,
    list_class_names,
    list_race_names,
)
from .llm import LLMClient
from .rules import (
    grant_xp,
    apply_companion_action,
    apply_enemy_action,
    apply_exploration_action,
    apply_player_action,
    apply_rest,
    clear_round_buffs,
    create_companion,
    create_player,
    ensure_caster_mana,
    end_combat_if_needed,
    equip_item,
    is_caster,
    move_player,
    regen_companion_mana,
    regen_mana,
    reset_rest_streak,
    sync_player_ac,
    start_room,
    unequip_item,
    use_item,
)
from .state import GameState, load_state, save_state
from .characters import list_characters, load_character, save_character, strip_campaign_quest_items
from .util import (
    color_text,
    format_equipment,
    format_inventory,
    format_inventory_detailed,
    format_stats,
    format_currency,
    load_env_file,
    normalize_action,
    print_divider,
    prompt_choice,
    prompt_stat_allocation,
    summarize_health,
    yes_no,
)

SAVE_PATH = os.path.join(os.getcwd(), "game_state.json")


def _extract_campaign_content(rules_result: str, state: GameState) -> str | None:
    """Extract quoted dialogue/campaign content from rules result for display."""
    quoted = re.findall(r"'([^']+)'", rules_result)
    if not quoted:
        return None
    # Use the longest quote (usually the main dialogue)
    quote = max(quoted, key=len)
    room = get_room(state.campaign_id, state.room_id)
    npc = getattr(room, "npc", None)
    if npc:
        return f'{npc}: "{quote}"'
    return f'"{quote}"'


def _sync_character(state: GameState) -> None:
    """Persist character to roster so they can be reused across campaigns."""
    try:
        save_character(state.player, state.inventory, state.equipment)
    except IOError:
        pass  # Non-fatal; character roster is optional


def save_game(state: GameState) -> None:
    """Save game state and sync character to roster."""
    save_state(state, SAVE_PATH)
    _sync_character(state)


def _choose_or_create_character(campaign_id: str):
    """Return (player, inventory, equipment) for a new game."""
    saved = list_characters()
    if saved:
        options = ["Create new"] + saved
        choice = prompt_choice("Load character or create new?", options)
        if choice != "Create new":
            player, inventory, equipment = load_character(choice, campaign_id)
            return player, inventory, equipment

    # New character
    name = input("Enter your character name: ").strip() or "Adventurer"
    cls = prompt_choice("Choose a class", list_class_names())
    race = choose_race()
    stats = prompt_stat_allocation(total_points=12)
    player = create_player(name=name, cls=cls, stats=stats, race=race)
    inventory = [
        item_from_id(campaign_id, "healing_potion"),
        item_from_id(campaign_id, "healing_potion"),
        item_from_id(campaign_id, "healing_potion"),
        item_from_id(campaign_id, "leather_cap"),
        item_from_id(campaign_id, "worn_boots"),
    ]
    equipment = {s: None for s in ["head", "arms", "hands", "chest", "legs", "feet"]}
    return player, inventory, equipment


def setup_new_game() -> GameState:
    print("Welcome to the Solo Adventure")
    campaign_id = choose_campaign()
    campaign = get_campaign(campaign_id)
    print(f"Campaign selected: {campaign.name}")
    player, inventory, equipment = _choose_or_create_character(campaign_id)
    companion = _choose_companion(campaign_id, campaign)
    start_room_id = campaign.room_order[0] if campaign.room_order else "courtyard"
    state = GameState(
        campaign_id=campaign_id,
        player=player,
        room_id=start_room_id,
        companions=[companion],
        inventory=inventory,
        equipment=equipment,
    )
    sync_player_ac(state)
    intro = start_room(state, get_room(state.campaign_id, state.room_id))
    state.last_event = intro
    return state


def maybe_resume() -> GameState:
    if os.path.exists(SAVE_PATH) and yes_no("Found a saved game. Resume?"):
        state = load_state(SAVE_PATH)
        sync_player_ac(state)
        ensure_caster_mana(state)
        return state
    return setup_new_game()


def _choose_companion(campaign_id: str, campaign) -> "Companion":
    """Pick companion: use default if only one, else prompt."""
    from .rules import create_companion

    ids = campaign.default_companion_ids or list(campaign.companions.keys())
    if len(ids) <= 1:
        return create_companion(campaign_id, ids[0] if ids else None)
    names = [campaign.companions[cid].name for cid in ids if cid in campaign.companions]
    choice = prompt_choice("Choose your companion", names)
    cid = next((i for i in ids if campaign.companions.get(i) and campaign.companions[i].name == choice), ids[0])
    return create_companion(campaign_id, cid)


def choose_campaign() -> str:
    campaigns = list_campaigns()
    if not campaigns:
        raise RuntimeError("No campaigns are registered.")
    if len(campaigns) == 1:
        return campaigns[0].campaign_id
    name_to_id = {campaign.name: campaign.campaign_id for campaign in campaigns}
    choice = prompt_choice("Choose a campaign", list(name_to_id.keys()))
    return name_to_id[choice]


def choose_race() -> str:
    races = list_race_names()
    if not races:
        return "Human"
    if len(races) == 1:
        return races[0]
    return prompt_choice("Choose a race", races)


def print_status(state: GameState) -> None:
    print(
        f"{summarize_health(state.player.name, state.player.hp, state.player.max_hp)} | "
        f"{summarize_health(state.companion.name, state.companion.hp, state.companion.max_hp)}"
    )
    print(f"Level {state.player.level} | XP {state.player.xp}")
    if is_caster(state.player.cls):
        print(f"Mana: {state.player.mana}/{state.player.max_mana}")
    if state.companion.max_mana > 0:
        print(f"{state.companion.name} mana: {state.companion.mana}/{state.companion.max_mana}")
    print(format_currency(state.player.gold))
    if state.enemies:
        enemies = [
            f"{idx}. {enemy.name} {enemy.hp}/{enemy.max_hp}"
            for idx, enemy in enumerate(state.enemies, start=1)
            if enemy.hp > 0
        ]
        if enemies:
            print("Enemies: " + " | ".join(enemies))


def print_exits(state: GameState) -> None:
    exits = get_exits(state.campaign_id, state.room_id)
    if not exits:
        print("Exits: none")
        return
    exit_list = ", ".join(sorted(set(exits.values())))
    print(f"Exits: {exit_list}")


def print_combat_status(state: GameState) -> None:
    round_num = state.turn + 1
    player_note = " (defending)" if state.player_defending else ""
    companion_note = " (defending)" if state.companion_defending else ""
    print(f"Round {round_num}")
    print(
        f"{state.player.name} HP {state.player.hp}/{state.player.max_hp} AC {state.player.ac}{player_note} | "
        f"{state.companion.name} HP {state.companion.hp}/{state.companion.max_hp} "
        f"AC {state.companion.ac}{companion_note}"
    )
    print(f"Level {state.player.level} | XP {state.player.xp}")
    if is_caster(state.player.cls):
        print(f"Mana: {state.player.mana}/{state.player.max_mana}")
    if state.companion.max_mana > 0:
        print(f"{state.companion.name} mana: {state.companion.mana}/{state.companion.max_mana}")
    if state.enemies:
        enemy_lines = [
            f"{idx}. {enemy.name} HP {enemy.hp}/{enemy.max_hp} AC {enemy.ac}"
            for idx, enemy in enumerate(state.enemies, start=1)
            if enemy.hp > 0
        ]
        if enemy_lines:
            print("Enemies: " + " | ".join(enemy_lines))
            print("Targets: " + ", ".join(str(idx) for idx in range(1, len(enemy_lines) + 1)))


def log_turn(state: GameState, player_input: str = "") -> None:
    """Log turn with player input and rules result."""
    if player_input:
        state.last_player_input = player_input
    if state.last_event:
        state.turn_log.append(
            f"Turn {state.turn}: input={player_input!r} | {state.last_event}"
        )


def gear_menu(state: GameState) -> None:
    print()
    print(format_equipment(state.equipment))
    print(format_inventory_detailed(state.inventory))
    print(format_currency(state.player.gold))
    print("Gear commands: show, equip <item>, unequip <slot>, back")
    while True:
        raw = input("Gear> ").strip()
        action = normalize_action(raw)
        if action in {"back", "exit", "quit"}:
            return
        if action in {"show", "list"}:
            print(format_equipment(state.equipment))
            print(format_inventory_detailed(state.inventory))
            print(format_currency(state.player.gold))
            continue
        if action.startswith("equip "):
            item_name = action[len("equip ") :].strip()
            success, message = equip_item(state, item_name)
            print(color_text(message, "green" if success else "yellow"))
            continue
        if action.startswith("unequip "):
            slot = action[len("unequip ") :].strip()
            success, message = unequip_item(state, slot)
            print(color_text(message, "green" if success else "yellow"))
            continue
        print("Try: show, equip <item>, unequip <slot>, back")


def colorize_outcome(text: str, state: GameState) -> str:
    lowered = text.lower()
    if "damage" in lowered and ("strikes" in lowered or "lashes at" in lowered):
        return color_text(text, "red")
    if "game over" in lowered or "collapse" in lowered or "dead" in lowered:
        return color_text(text, "red")
    if "miss" in lowered or "fails" in lowered or "no effect" in lowered or "out of" in lowered:
        return color_text(text, "yellow")
    if "hit" in lowered or "damage" in lowered or "healing" in lowered or "heals" in lowered:
        return color_text(text, "green")
    return text


def print_outcomes(state: GameState, lines: list[str]) -> None:
    if not lines:
        return
    print()
    for line in lines:
        print(colorize_outcome(line, state))
    print()


def parse_use_action(action: str) -> tuple[str, str | None] | None:
    if action.startswith("use "):
        payload = action[4:]
    elif action.startswith("drink "):
        payload = action[6:]
    elif action in {"use", "drink"}:
        payload = ""
    else:
        return None
    if " on " in payload:
        item_part, target_part = payload.split(" on ", 1)
        return item_part.strip(), target_part.strip() or None
    return payload.strip(), None


def handle_exploration(state: GameState, llm: LLMClient, last_input: str) -> str:
    print()
    print_status(state)
    print_exits(state)
    print(color_text(f"{state.companion.name} suggests: {companion_suggest(state, llm)}", "cyan"))
    raw = input("Action (talk/search/loot/move/rest [N]/use/gear/inventory/help/quit): ")
    action = normalize_action(raw)
    move_target = None
    if action in {"up", "down", "north", "south", "east", "west", "back"}:
        move_target = action
    elif action.startswith("go "):
        move_target = action[3:].strip()
    elif action.startswith("move "):
        move_target = action[5:].strip()
    elif action.startswith("walk "):
        move_target = action[5:].strip()
    elif action.startswith("head "):
        move_target = action[5:].strip()
    elif action.startswith("enter "):
        move_target = action[6:].strip()
    elif action.startswith("travel "):
        move_target = action[7:].strip()
    elif action.startswith("leave "):
        move_target = action[6:].strip()

    if action in {"quit", "exit"}:
        save_game(state)
        raise SystemExit
    if action in {"help", "?"}:
        exits = get_exits(state.campaign_id, state.room_id)
        exit_list = ", ".join(sorted(set(exits.values()))) if exits else "none"
        print(
            "Try: talk, search, loot [number|all], move <destination>, rest [N], "
            "use potion [on mara], gear, inventory, stats, quit"
        )
        print(f"Exits: {exit_list}")
        return last_input
    if action in {"gear", "equip", "equipment"}:
        gear_menu(state)
        save_game(state)
        return last_input
    if action in {"inventory", "inv", "i"}:
        print(format_inventory(state.inventory))
        print(format_currency(state.player.gold))
        return last_input
    if action == "stats":
        class_profile = get_class_profile(state.player.cls)
        race_profile = get_race_profile(state.player.race)
        mods = race_profile.stat_mods or {}
        mods_text = ", ".join(f"{k}{v:+d}" for k, v in mods.items()) if mods else "none"
        spells = ", ".join(state.player.learned_spells) if state.player.learned_spells else "none"
        print(f"Race: {state.player.race} (mods: {mods_text})")
        print(f"Class: {state.player.cls} (role: {class_profile.role})")
        print(f"Level: {state.player.level} | XP: {state.player.xp}")
        print(f"Spells: {spells}")
        print(f"Stats: {format_stats(state.player.stats)}")
        return last_input
    use_payload = parse_use_action(action)
    if use_payload:
        item_name, target = use_payload
        used, result = use_item(state, item_name, target)
        if used:
            state.turn += 1
            state.last_event = result
            reset_rest_streak(state)
            save_game(state)
        else:
            print(color_text(result, "yellow"))
        return action

    if action == "rest" or action.startswith("rest "):
        rest_count = 1
        if action.startswith("rest "):
            try:
                rest_count = max(1, min(int(action.split()[1]), 20))
            except (ValueError, IndexError):
                rest_count = 1
        results: list[str] = []
        for _ in range(rest_count):
            result = apply_rest(state)
            state.turn += 1
            state.last_event = result
            results.append(result)
            log_turn(state, raw)
        state.last_event = " | ".join(results)
        save_game(state)
        return action

    if move_target or action in {"move", "go", "leave", "continue"}:
        if not move_target:
            exits = get_exits(state.campaign_id, state.room_id)
            exit_list = ", ".join(sorted(set(exits.values()))) if exits else "none"
            print(f"Where to? Exits: {exit_list}")
            return last_input
        ok, entry = move_player(state, move_target)
        if not ok:
            print(color_text(entry, "yellow"))
            return last_input
        result = entry
    else:
        result = apply_exploration_action(state, action)
    state.turn += 1
    state.last_event = result
    reset_rest_streak(state)
    log_turn(state, raw)
    save_game(state)
    return action


def handle_combat(state: GameState, llm: LLMClient, last_input: str) -> str:
    print()
    print_combat_status(state)
    print(color_text(f"{state.companion.name} suggests: {companion_suggest(state, llm)}", "cyan"))
    raw = input("Combat action (attack/defend/special/cast/use/gear/inventory/help/quit): ")
    action = normalize_action(raw)
    target = None
    spell_name = None
    if action.startswith("attack "):
        target = action[len("attack ") :].strip()
        action = "attack"
    elif action.startswith("cast "):
        rest = action[len("cast ") :].strip()
        action = "special"
        if " " in rest:
            spell_name, target = rest.split(" ", 1)
        else:
            spell_name = rest
            target = None
    elif action.startswith("special "):
        target = action[len("special ") :].strip()
        action = "special"
    elif action == "spark" or action.startswith("spark "):
        target = action[len("spark ") :].strip() if " " in action else None
        spell_name = "spark"
        action = "special"
    elif action == "magic missile" or action.startswith("magic missile "):
        target = action[len("magic missile ") :].strip() if " " in action else None
        spell_name = "magic missile"
        action = "special"
    elif action == "sleep" or action.startswith("sleep "):
        target = action[len("sleep ") :].strip() if " " in action else None
        spell_name = "sleep"
        action = "special"
    elif action == "shield":
        spell_name = "shield"
        action = "special"
    elif action == "cure wounds" or action.startswith("cure wounds "):
        target = action[len("cure wounds ") :].strip() if " " in action else None
        spell_name = "cure wounds"
        action = "special"
    elif action == "bless" or action.startswith("bless "):
        target = action[len("bless ") :].strip() if " " in action else None
        spell_name = "bless"
        action = "special"

    if action in {"quit", "exit"}:
        save_game(state)
        raise SystemExit
    if action in {"help", "?"}:
        print(
            "Try: attack [target], defend, special, cast <spell> [target], "
            "use potion [on mara], gear, inventory, quit"
        )
        if state.player.learned_spells:
            print(f"Spells: {', '.join(state.player.learned_spells)}")
        if state.enemies:
            targets = [
                f"{idx}:{enemy.name}"
                for idx, enemy in enumerate(state.enemies, start=1)
                if enemy.hp > 0
            ]
            if targets:
                print("Targets: " + ", ".join(targets))
        return last_input
    if action in {"gear", "equip", "equipment"}:
        gear_menu(state)
        save_game(state)
        return last_input
    if action in {"inventory", "inv", "i"}:
        print(format_inventory(state.inventory))
        print(format_currency(state.player.gold))
        return last_input

    use_payload = parse_use_action(action)
    if use_payload:
        item_name, target = use_payload
        used, result = use_item(state, item_name, target)
        if used:
            results = [result]
            results.append(apply_companion_action(state))
            results.extend(apply_enemy_action(state))
            clear_round_buffs(state)
            end_result = end_combat_if_needed(state)
            if end_result:
                results.append(end_result)
            regen_mana(state, 1)
            regen_companion_mana(state, 1)
            state.turn += 1
            state.last_event = " ".join(results)
            reset_rest_streak(state)
            log_turn(state, raw)
            save_game(state)
        else:
            print(color_text(result, "yellow"))
        return action

    if action == "cast" and not spell_name:
        print("Cast which spell? (e.g. cast magic missile, cast sleep 1)")
        return last_input
    if action not in {"attack", "defend", "special"}:
        print("Choose attack, defend, special, or cast <spell> [target].")
        return last_input

    results = [apply_player_action(state, action, target, spell_name)]
    results.append(apply_companion_action(state))
    results.extend(apply_enemy_action(state))
    clear_round_buffs(state)
    end_result = end_combat_if_needed(state)
    if end_result:
        results.append(end_result)

    regen_mana(state, 1)
    regen_companion_mana(state, 1)
    state.turn += 1
    state.last_event = " ".join(results)
    reset_rest_streak(state)
    log_turn(state, raw)
    save_game(state)
    return action


def main() -> None:
    load_env_file(os.path.join(os.getcwd(), ".env"))
    llm = LLMClient()
    if llm.stub:
        print("OpenAI API key not found. Running with stub GM/companion.")
    state = maybe_resume()
    last_player_input = ""
    last_narrated_turn = state.turn - 1

    while True:
        if state.game_over:
            if state.last_event and last_narrated_turn != state.turn:
                if state.in_combat:
                    print_outcomes(state, [state.last_event])
                campaign_content = _extract_campaign_content(state.last_event, state)
                if campaign_content:
                    print(color_text(campaign_content, "cyan"))
            print_divider()
            if state.last_event and last_narrated_turn != state.turn:
                gm_text, gm_source = gm_narrate_with_source(
                    state, llm, state.last_player_input, state.last_event
                )
                state.response_log.append({
                    "turn": state.turn,
                    "player_input": state.last_player_input,
                    "rules_result": state.last_event,
                    "gm_response": gm_text,
                    "gm_source": gm_source,
                })
                print(gm_text)
                last_narrated_turn = state.turn
            if state.player.hp > 0:
                campaign = get_campaign(state.campaign_id)
                completion_xp = getattr(campaign, "completion_xp", 0)
                if completion_xp > 0:
                    level_msgs = grant_xp(state, completion_xp)
                    for msg in level_msgs:
                        print(color_text(msg, "green"))
                strip_campaign_quest_items(state)
                sync_player_ac(state)
                save_state(state, SAVE_PATH)
                _sync_character(state)
            print("Game over.")
            break

        if state.last_event and last_narrated_turn != state.turn:
            if state.in_combat:
                print_outcomes(state, [state.last_event])
            campaign_content = _extract_campaign_content(state.last_event, state)
            if campaign_content:
                print(color_text(campaign_content, "cyan"))
            print_divider()
            gm_text, gm_source = gm_narrate_with_source(
                state, llm, state.last_player_input, state.last_event
            )
            state.response_log.append({
                "turn": state.turn,
                "player_input": state.last_player_input,
                "rules_result": state.last_event,
                "gm_response": gm_text,
                "gm_source": gm_source,
            })
            print(gm_text)
            last_narrated_turn = state.turn
            print()
            if not state.in_combat:
                corpses = state.flags.get("corpses", {}) if isinstance(state.flags.get("corpses"), dict) else {}
                corpse_entries = corpses.get(state.room_id, [])
                if isinstance(corpse_entries, list):
                    unlooted = [e for e in corpse_entries if not e.get("looted")]
                    if unlooted:
                        print(color_text("Tip: You can 'loot' the corpse.", "gray"))
                        print()

        if state.in_combat:
            last_player_input = handle_combat(state, llm, last_player_input)
        else:
            last_player_input = handle_exploration(state, llm, last_player_input)


if __name__ == "__main__":
    main()
