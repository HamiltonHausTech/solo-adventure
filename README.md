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

### Option A: OpenAI (hosted)
Set an API key in your shell:
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
If no key is set and no local model is configured, the game runs with a stub GM and companion.

### Option B: Local model via Ollama
If you run [Ollama](https://ollama.com) locally, you can use a local model instead of OpenAI:

```bash
# Tell the game to use Ollama instead of OpenAI:
export LLM_PROVIDER=ollama

# Optional: choose the Ollama model (defaults to "gpt-oss"):
export OLLAMA_MODEL=gpt-oss

# Optional: change the Ollama host (defaults to http://localhost:11434):
export OLLAMA_HOST=http://localhost:11434

# You can still skip companion calls as with OpenAI:
export OPENAI_SKIP_COMPANION=1
```
or in `.env`:
```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=gpt-oss
OLLAMA_HOST=http://localhost:11434
OPENAI_SKIP_COMPANION=1
```
With `LLM_PROVIDER=ollama`, no `OPENAI_API_KEY` is required.

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

## Headless engine and web API

The terminal UI and web clients can share the same authoritative Python rules
through `HeadlessEngine`. Commands return a client-safe state snapshot plus
structured events suitable for animation, narration, sound, and replay.

Run the development API:

```bash
python3 -m app.web_api --port 8000 --database var/solo_adventure.db
```

Create a game:

```bash
curl -X POST http://127.0.0.1:8000/api/games \
  -H 'Content-Type: application/json' \
  -d '{"name":"Rowan","class":"Fighter","race":"Human","companion_id":"mara"}'
```

Resolve a command using the returned `game_id`:

```bash
curl -X POST http://127.0.0.1:8000/api/games/GAME_ID/commands \
  -H 'Content-Type: application/json' \
  -d '{"command":"move","target":"barracks"}'
```

Supported endpoints:

- `GET /api/health`
- `POST /api/games`
- `GET /api/games/{game_id}`
- `POST /api/games/{game_id}/commands`

Game sessions are stored in SQLite and survive service restarts. The browser
keeps only the opaque `game_id`; authoritative state remains in the database.

### Character ownership and stale saves

Each saved adventurer has an optimistic revision. A successful adventure command,
hub edit, or newly started adventure advances it. Older adventure snapshots stay
readable, but cannot overwrite the newer character: commands return HTTP `409`
with code `stale_adventurer`. Reload the hub and start from the current adventurer
to continue with the latest gear/progression. Existing adventure history is not
rewritten. Concurrent stale writes are rejected inside the SQLite transaction,
including across server processes. Legacy saves may continue only when their
unversioned snapshot matches the current profile. Back up an existing database
before upgrading; the revision column is added automatically on first startup.

### Local-only service

The API defaults to loopback and accepts browser origins only from localhost or
loopback addresses. It has no user authentication and must not be exposed as a
public service. Browser configuration and browser regression tests are documented
in `web/README.md`. Changing the API URL does not add authentication or remote
origin support. Live AI narration is currently a CLI feature, not a web feature.

## Tests
```bash
python3 -m unittest discover -s tests
```

Frontend checks (from `web/`): `npm test`, `npm run typecheck`, and `npm run lint`.

## Save / Resume
The game auto-saves every turn to `game_state.json` in the project root. If a save is found, you will be prompted to resume.

## Character persistence
Characters are saved to the `characters/` directory and can be reused across campaigns. When starting a new game, you can load an existing character (keeping their gold, inventory, and equipment) or create a new one. Progress is synced to your character roster whenever the game saves.

## Adventure flow

- `camp` takes no arguments and batches up to 100 existing recovery ticks, stopping
  when every living party member is recovered. It never revives fallen actors.
  Mana recovers each tick and HP every second consecutive tick, sharing the same
  `rest_streak` as `rest`. The turn counter advances by the actual ticks, with one
  summary/log and at most one relationship reaction. Full recovery, combat, and
  completed games reject camp without changing state. `rest` remains available
  for one tick (and legacy pending spell choices); camp does not prompt for choices.
- Snapshots add `camp: {available, reason, recovery_turns, recovery}` where each
  recovery entry is `{name, hp, mana}` with actual capped gains, and
  `journey: {objective: {title, description}, journal: [{id, text}],
  locations: [{id, name, statuses}]}`. Previews are read-only. Known locations are
  visited rooms plus their adjacent exits, not the full campaign route. Existing
  action IDs, targets, snapshot fields, and save format remain supported.
- NPC conversations keep their first result, including useful fallback directions
  on failure; exhausted Talk/Search/Loot actions explain why they are disabled.
  Journal evidence, searched locations, and per-room relationship rewards persist
  in save flags. Evicting a companion’s short memory does not reset those rewards.
- Greyfen’s final seal offers reliable approaches through Nessa’s information,
  living Eldrin with trust 60, or Wisdom 5 / Battle Resilience. An unaided Wisdom
  check is always possible: failure still restores the seal at a cost of at most
  3 HP, never killing the player. Legacy `search`, `inspect`, `open`, and `loot`
  use the best available approach from the same resolver, with one-time completion
  rewards and a saved ending explanation; they cannot bypass the challenge.

## Controls
- Exploration: `talk`, `search`, `loot`, `move <destination>` (or `up`/`down`), `rest`, `camp`, `use potion [on mara]`, `gear`, `inventory`, `stats`, `help`, `quit`
- Combat: `attack [target]`, `defend`, `special [target]` (Wizard: Spark or Magic Missile), `use potion [on mara]`, `gear`, `inventory`, `help`, `quit`

## Notes
- Stats: STR, DEX, CON, INT, WIS, CHA (AD&D-style). Allocate 12 points (0–4 per stat). CON adds to max HP.
- XP and leveling: Earn XP from defeating enemies and completing campaigns. Level up for more HP, attack bonus, and (casters) mana. Spell choices (Wizard at levels 2, 4, 6…) are deferred until your next rest.
 - Combat is lightweight and turn-based; Mara acts after you.
- Wizards use mana for Spark (cost 2, damage 1d4) and can learn Magic Missile, Shield, Sleep at level-up. Mana scales with INT; it does not regenerate during combat.
- You start with 3 Healing Potions (each heals 1d6+2 to you or your companion).
- Each completed turn is appended to `turn_log` in the save file for quick replay.
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
