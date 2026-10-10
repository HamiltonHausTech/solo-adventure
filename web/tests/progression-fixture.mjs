import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join } from 'node:path';

// Test-only, bounded local helper. No production API endpoint or user DB access.
export function seedProgression() {
  const scratch = realpathSync(process.env.SOLO_BROWSER_FIXTURE_DIR || '');
  if (dirname(scratch) !== realpathSync(tmpdir()) || !basename(scratch).startsWith('solo-web-test-')) {
    throw new Error('Refusing to seed outside the disposable browser fixture directory');
  }
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
