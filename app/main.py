from __future__ import annotations

import os
import re

from .agents import companion_suggest, gm_narrate_with_source
from .content import get_campaign, get_exits, get_room, item_from_id, list_campaigns
from .profiles import (
    get_class_profile,
    get_race_profile,
    list_class_names,
    list_race_names,
)
from .llm import LLMClient
from .engine import HeadlessEngine
from .rules import (
    create_player,
    ensure_caster_mana,
    is_caster,
    sync_player_ac,
    start_room,
)
from .state import Companion, GameState, load_state, save_state
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
    enemies = HeadlessEngine(state).snapshot()["enemies"]
    if enemies:
        print("Enemies: " + " | ".join(
            f"{enemy['id']}. {enemy['name']} {enemy['hp']}/{enemy['max_hp']}"
            for enemy in enemies
        ))


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
    enemies = HeadlessEngine(state).snapshot()["enemies"]
    if enemies:
        print("Enemies: " + " | ".join(
            f"{enemy['id']}. {enemy['name']} HP {enemy['hp']}/{enemy['max_hp']} AC {enemy['ac']}"
            for enemy in enemies
        ))
        print("Targets: " + ", ".join(str(enemy["id"]) for enemy in enemies))


def gear_menu(state: GameState) -> None:
    engine = HeadlessEngine(state)
    print()
    print(format_equipment(state.equipment))
    print(format_inventory_detailed(state.inventory))
    print(format_currency(state.player.gold))
    print("Gear commands: show, equip <item>, unequip <slot>, drop <item>, back")
    while not state.game_over:
        action = normalize_action(input("Gear> "))
        if action in {"back", "exit", "quit"}:
            return
        if action in {"show", "list"}:
            print(format_equipment(state.equipment))
            print(format_inventory_detailed(state.inventory))
            print(format_currency(state.player.gold))
        elif action.partition(" ")[0] in {"equip", "unequip", "drop"}:
            execute_cli_action(engine, action)
        else:
            print("Try: show, equip <item>, unequip <slot>, drop <item>, back")


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


def parse_engine_action(action: str, engine: HeadlessEngine) -> tuple[str, dict]:
    """Translate terminal shorthand, leaving all validation to the engine."""
    verb, _, payload = action.partition(" ")
    if action in {"up", "down", "north", "south", "east", "west", "back"}:
        return "move", {"target": action}
    if verb in {"go", "move", "walk", "head", "enter", "travel", "leave", "continue"}:
        return "move", {"target": payload or None}
    use_payload = parse_use_action(action)
    if use_payload is not None:
        item, target = use_payload
        return "use", {"item": item or None, "target": target}
    if verb in {"equip", "drop"}:
        return verb, {"item": payload or None}
    if verb in {"unequip", "challenge", "attack", "special", "loot", "set_tactic"}:
        return verb, {"target": payload or None}

    # Longest known name first: "cure wounds Torvald" is not spell="cure".
    spell_payload = payload if verb == "cast" else action
    for name in sorted(engine.state.player.learned_spells, key=len, reverse=True):
        lowered = name.lower()
        if spell_payload == lowered or spell_payload.startswith(lowered + " "):
            target = spell_payload[len(name):].strip()
            if target.startswith("on "):
                target = target[3:].strip()
            return "cast", {"spell": name, "target": target or None}
    if verb == "cast":
        spell, _, target = payload.partition(" on ")
        return "cast", {"spell": spell, "target": target or None}
    return action, {}


def execute_cli_action(engine: HeadlessEngine, action: str) -> bool:
    """One gameplay boundary for both prompts and the gear submenu."""
    command, kwargs = parse_engine_action(action, engine)
    result = engine.execute(command, **kwargs)
    if not result.accepted:
        print(color_text(result.error or "That action is not available.", "yellow"))
        return False
    print_outcomes(engine.state, [event.message for event in result.events])
    save_game(engine.state)
    return True


def print_challenge(engine: HeadlessEngine) -> None:
    challenge = engine.snapshot()["challenge"]
    if not challenge:
        print("There is no unresolved challenge here.")
        return
    requirement = "required" if challenge["required"] else "optional"
    print(f"Challenge: {challenge['title']} ({requirement})")
    print(challenge["prompt"])
    for option in challenge["options"]:
        reason = f" — unavailable: {option['reason']}" if not option["available"] else ""
        print(f"  challenge {option['id']}: {option['label']} — {option.get('description', '')}{reason}")


def print_spellbook(engine: HeadlessEngine) -> None:
    spells = engine.spellbook()
    if not spells:
        print("You do not know any spells.")
        return
    print("Cast with: cast <spell> [on <target>]")
    for spell in spells:
        reason = f" — unavailable: {spell['reason']}" if not spell["available"] else ""
        targets = ", ".join(f"{target['id']} ({target['label']})" for target in spell["targets"]) or "none"
        print(f"  {spell['name']} ({spell['mana_cost']} mana){reason}; targets: {targets}")


def print_stats(state: GameState) -> None:
    class_profile = get_class_profile(state.player.cls)
    race_profile = get_race_profile(state.player.race)
    mods = race_profile.stat_mods or {}
    mods_text = ", ".join(f"{key}{value:+d}" for key, value in mods.items()) or "none"
    print(f"Race: {state.player.race} (mods: {mods_text})")
    print(f"Class: {state.player.cls} (role: {class_profile.role})")
    print(f"Level: {state.player.level} | XP: {state.player.xp}")
    print(f"Spells: {', '.join(state.player.learned_spells) or 'none'}")
    print(f"Stats: {format_stats(state.player.stats)}")


def handle_action(state: GameState, llm: LLMClient | None, last_input: str) -> str:
    engine = HeadlessEngine(state)
    print()
    if state.in_combat:
        print_combat_status(state)
    else:
        print_status(state)
        print_exits(state)
        if engine.snapshot()["challenge"]:
            print_challenge(engine)
    if llm is not None:
        print(color_text(f"{state.companion.name} suggests: {companion_suggest(state, llm)}", "cyan"))
    prompt = "Combat" if state.in_combat else "Action"
    action = normalize_action(input(f"{prompt} (help for commands): "))
    if action in {"quit", "exit"}:
        save_game(state)
        raise SystemExit
    if action in {"help", "?"}:
        print(
            "Try: talk, search, loot [number|all], move <destination>, rest [N], "
            "challenge <option>, attack [target], defend, special [target], guard_companion, "
            "cast <spell> [on <target>], spellbook, use potion [on <target>], "
            "gear, equip <item>, unequip <slot>, drop <item>, inventory, status, stats, "
            "companion_talk, companion_advice, set_tactic <tactic>, quit"
        )
        print_exits(state)
        print_spellbook(engine)
        if not state.in_combat:
            print_challenge(engine)
        return last_input
    if action in {"gear", "equip", "equipment"}:
        gear_menu(state)
        return last_input
    if action in {"inventory", "inv", "i"}:
        print(format_inventory(state.inventory))
        print(format_currency(state.player.gold))
        return last_input
    if action == "stats":
        print_stats(state)
        return last_input
    if action == "status":
        print_status(state)
        return last_input
    if action in {"spells", "spellbook", "cast"}:
        print_spellbook(engine)
        return last_input
    if action in {"challenge", "challenges"}:
        print_challenge(engine)
        return last_input

    # Repetition is terminal convenience, not a second rest implementation.
    count = 1
    command = action
    if action.startswith("rest "):
        try:
            count = max(1, min(int(action[5:]), 20))
        except ValueError:
            print("Try: rest [N], where N is a number from 1 to 20.")
            return last_input
        command = "rest"
    accepted = False
    for _ in range(count):
        if not execute_cli_action(engine, command):
            break
        accepted = True
        if state.game_over:
            break
    return action if accepted else last_input


def handle_exploration(state: GameState, llm: LLMClient | None, last_input: str) -> str:
    return handle_action(state, llm, last_input)


def handle_combat(state: GameState, llm: LLMClient | None, last_input: str) -> str:
    return handle_action(state, llm, last_input)


def main(*, narration: bool = True) -> None:
    load_env_file(os.path.join(os.getcwd(), ".env"))
    llm = LLMClient() if narration else None
    if llm is not None and llm.stub:
        print("OpenAI API key not found. Running with stub GM/companion.")
    state = maybe_resume()
    last_player_input = ""
    last_narrated_turn = state.turn - 1
    if llm is None and state.last_event:
        print(state.last_event)

    while True:
        if state.last_event and last_narrated_turn != state.turn:
            campaign_content = _extract_campaign_content(state.last_event, state)
            if campaign_content:
                print(color_text(campaign_content, "cyan"))
            if llm is not None:
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
            if not state.in_combat:
                corpses = state.flags.get("corpses", {})
                entries = corpses.get(state.room_id, []) if isinstance(corpses, dict) else []
                if isinstance(entries, list) and any(not entry.get("looted") for entry in entries):
                    print(color_text("Tip: You can 'loot' the corpse.", "gray"))

        if state.game_over:
            # Completion rewards are already resolved by the engine. Roster cleanup
            # is a persistence concern, not another gameplay/combat resolution.
            if state.player.hp > 0:
                strip_campaign_quest_items(state)
                sync_player_ac(state)
            save_game(state)
            print("Game over.")
            break

        if state.in_combat:
            last_player_input = handle_combat(state, llm, last_player_input)
        else:
            last_player_input = handle_exploration(state, llm, last_player_input)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Play Solo Adventure in the terminal.")
    parser.add_argument("--no-narration", action="store_true", help="Use rules output only; do not call an LLM.")
    main(narration=not parser.parse_args().no_narration)
