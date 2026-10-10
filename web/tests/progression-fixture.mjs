import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join } from 'node:path';

// Test-only, bounded local helper. No production API endpoint or user DB access.
function fixtureDirectory() {
  const scratch = realpathSync(process.env.SOLO_BROWSER_FIXTURE_DIR || '');
  if (dirname(scratch) !== realpathSync(tmpdir()) || !basename(scratch).startsWith('solo-web-test-')) {
    throw new Error('Refusing to seed outside the disposable browser fixture directory');
  }
  return scratch;
}

export function seedAdventureFlow(scenario = 'camp') {
  if (!['camp', 'discovery', 'search', 'finale', 'finale-prepared'].includes(scenario)) throw new Error('Unknown adventure fixture');
  const scratch = fixtureDirectory();
  const id = randomUUID();
  const name = `Flow ${id.slice(0, 8)}`;
  execFileSync(process.env.PYTHON || 'python3', ['-c', `
import sys
from app.engine import HeadlessEngine
from app.storage import GameStore
engine = HeadlessEngine.new(name=sys.argv[3], player_class="Wizard", campaign_id="embers_of_greyfen", companion_id="eldrin")
scenario = sys.argv[4]
if scenario == "camp":
    engine.state.player.hp = 2
    engine.state.player.mana = 0
    engine.state.companion.hp = 1
    engine.state.companion.mana = 0
elif scenario == "search":
    engine.state.room_id = "fallen_bridge"
    engine.state.visited = ["greyfen_road", "fallen_bridge"]
elif scenario == "discovery":
    engine.state.room_id = "high_road"
    engine.state.visited = ["greyfen_road", "crossroads", "high_road"]
    engine.state.flags["defeated_rooms"] = ["high_road"]
else:
    engine.state.room_id = "ember_vault"
    engine.state.visited = ["greyfen_road", "great_hall", "ember_vault"]
    engine.state.flags["defeated_rooms"] = ["great_hall"]
    if scenario == "finale-prepared":
        engine.state.flags["ember_truth_known"] = True
        engine.state.flags["keep_route_known"] = True
        engine.state.flags["sella_trusted"] = True
        engine.state.companion.trust = 100
        engine.state.player.level = 5
        engine.state.player.stats["WIS"] = 5
        engine.state.player.stats["INT"] = 5
        from app.rules.progression import apply_progression_choices
        engine.state.player.unspent_class_upgrades = 1
        assert apply_progression_choices(engine.state, {}, "mana_reserve")[0]
GameStore(sys.argv[1]).save(sys.argv[2], engine)
`, join(scratch, 'games.sqlite'), id, name, scenario], { cwd: '..', stdio: 'inherit', timeout: 10000 });
  return { id, name };
}

export function seedProgression() {
  const scratch = fixtureDirectory();
  const id = randomUUID();
  const name = `Earned ${id.slice(0, 8)}`;
  execFileSync(process.env.PYTHON || 'python3', ['-c', `
import sys
from app.engine import HeadlessEngine
from app.storage import GameStore
engine = HeadlessEngine.new(name=sys.argv[3], player_class="Fighter")
engine.state.player.level = 2
engine.state.player.xp = 100
engine.state.player.unspent_attribute_points = 1
engine.state.player.unspent_class_upgrades = 1
GameStore(sys.argv[1]).save(sys.argv[2], engine)
`, join(scratch, 'games.sqlite'), id, name], { cwd: '..', stdio: 'inherit', timeout: 10000 });
  return name;
}

export function seedCombatAfterFirstDefeat() {
  const scratch = fixtureDirectory();
  const id = randomUUID();
  const name = `Combat ${id.slice(0, 8)}`;
  execFileSync(process.env.PYTHON || 'python3', ['-c', `
import sys
from app.engine import HeadlessEngine
from app.storage import GameStore
engine = HeadlessEngine.new(name=sys.argv[3], player_class="Wizard")
assert engine.execute("move", target="barracks").accepted
# The opening encounter has one enemy; retain a defeated original slot
# ahead of a living copy to exercise stable IDs through real serialization.
from copy import deepcopy
assert len(engine.state.enemies) == 1
engine.state.enemies.append(deepcopy(engine.state.enemies[0]))
engine.state.enemies[0].hp = 0
# Keep the encounter active through a full round regardless of damage rolls.
for enemy in engine.state.enemies[1:]:
    enemy.hp = enemy.max_hp = 100
GameStore(sys.argv[1]).save(sys.argv[2], engine)
`, join(scratch, 'games.sqlite'), id, name], { cwd: '..', stdio: 'inherit', timeout: 10000 });
  return { id, name };
}
