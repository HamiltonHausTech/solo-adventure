# The Ruined Watchtower (Solo MVP)

A tiny, local, text-based solo adventure with an AI GM and a cautious archer companion. The rules engine owns all game state; the LLM only narrates.

## Requirements
- Python 3.11+
- (Optional) OpenAI API key for live narration

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure the AI (Optional)
Option A: set an API key in your shell:
```bash
export OPENAI_API_KEY=YOUR_KEY_HERE
# Optional (faster models = quicker responses):
export OPENAI_MODEL=gpt-4o-mini
# Skip companion API calls for faster turns (uses stub suggestions):
export OPENAI_SKIP_COMPANION=1
```
Option B: create a `.env` file (you can copy `.env.example`), for example:
```bash
OPENAI_API_KEY=YOUR_KEY_HERE
OPENAI_MODEL=gpt-4o-mini
OPENAI_SKIP_COMPANION=1
```
If no key is set, the game runs with a stub GM and companion.

### Rate limits and debugging
The game makes **2 API calls per turn** (companion suggestion + GM narration). If you hit rate limits:
- You'll see `[Rate limit]` messages; the game falls back to stub responses
- Set `OPENAI_SKIP_COMPANION=1` to cut API calls in half
- Set `OPENAI_DEBUG=1` to log each API call and any errors to stderr
- Check your [OpenAI usage limits](https://platform.openai.com/account/limits)

## Run
```bash
python3 -m app.main
```

## Tests
```bash
python3 -m unittest discover -s tests
```

## Save / Resume
The game auto-saves every turn to `game_state.json` in the project root. If a save is found, you will be prompted to resume.

## Character persistence
Characters are saved to the `characters/` directory and can be reused across campaigns. When starting a new game, you can load an existing character (keeping their gold, inventory, and equipment) or create a new one. Progress is synced to your character roster whenever the game saves.

## Controls
- Exploration: `talk`, `search`, `loot`, `move <destination>` (or `up`/`down`), `rest`, `use potion [on mara]`, `gear`, `inventory`, `stats`, `help`, `quit`
- Combat: `attack [target]`, `defend`, `special [target]` (Wizard: Spark or Magic Missile), `use potion [on mara]`, `gear`, `inventory`, `help`, `quit`

## Notes
- Stats: STR, DEX, CON, INT, WIS, CHA (AD&D-style). Allocate 12 points (0–4 per stat). CON adds to max HP.
- XP and leveling: Earn XP from defeating enemies and completing campaigns. Level up for more HP, attack bonus, and (casters) mana. Spell choices (Wizard at levels 2, 4, 6…) are deferred until your next rest.
 - Combat is lightweight and turn-based; Mara acts after you.
- Wizards use mana for Spark (cost 2, damage 1d4) and can learn Magic Missile, Shield, Sleep at level-up. Mana scales with INT, regen 1 per round.
- You start with 3 Healing Potions (each heals 1d6+2 to you or your companion).
- Each completed turn is appended to a short `turn_log` in the save file for quick replay.
- Inventory has a slot limit (default 10) and armor slots (head, arms, hands, chest, legs, feet).
- Looting enemies is manual (`loot` after a fight) and grants gold plus a possible armor piece.
- Resting regenerates 1 mana and grants +1 HP every 2 consecutive rests (only out of combat).
- Races: Human, Elf, Dwarf, Halfling (with stat mods and ability placeholders).
- Class profiles now include spell lists; see `stats` in-game.
- Companions can be casters: set `mana`, `max_mana`, and `spells` in `CompanionProfile`. Example: Eldrin in Ruined Watchtower.
- Enemy stats and loot are data-driven via mob profiles.

## Campaigns
- **The Ruined Watchtower** – Short regression/flow test: courtyard, cellar, barracks, spire. Mara (archer) companion.
- **The Lost Crypt** – Longer dungeon crawl: approach, gate, hallway, guard room, antechamber, crypt, treasure. Choose Eldrin (caster) or Mara. Multiple combats, social checks, climactic boss.

## Adding campaigns
Campaigns are pluggable modules under `app/campaigns/`.
1) Create a new campaign file (copy `app/campaigns/ruined_watchtower.py` as a template).
2) Define rooms with optional `social_config` and `loot_config` for campaign-specific behavior.
3) Define companions via `CompanionProfile` and add to `campaign.companions`.
4) Register it via `register_campaign(...)`.
5) Import it in `app/campaigns/__init__.py`.
The engine will prompt for a campaign if multiple are available.

## Architecture
- **Rules engine** (`app/rules/`): Modular package with `dice`, `combat`, `exploration`, `inventory`, `companions`, `rest`.
- **Room behavior**: Campaign-driven via `Room.social_config` and `Room.loot_config` (no hardcoded room logic).
- **Companions**: Data-driven via `CompanionProfile`; supports multiple companions in state.
