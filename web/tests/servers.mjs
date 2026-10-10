import { spawn, execFileSync } from 'node:child_process';
import { rm, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, join } from 'node:path';

// Only Playwright's unique disposable directory may be used for fixtures.
const scratch = await realpath(process.env.SOLO_BROWSER_FIXTURE_DIR || '');
if (dirname(scratch) !== await realpath(tmpdir()) || !basename(scratch).startsWith('solo-web-test-')) throw new Error('Missing disposable browser fixture directory');
const frontendEnv = { ...process.env, NODE_ENV: 'production', NEXT_PUBLIC_API_BASE_URL: 'http://127.0.0.1:18800' };
execFileSync('npm', ['run', 'build'], { stdio: 'inherit', env: frontendEnv, timeout: 60000 });
const children = [];
let stopping = false;
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  await Promise.all(children.map(child => new Promise(resolve => {
    if (child.exitCode !== null) return resolve();
    child.once('exit', resolve);
    child.kill('SIGTERM');
  })));
  await rm(scratch, { recursive: true, force: true });
  process.exit(code);
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => void stop());
children.push(spawn(process.env.PYTHON || 'python3', ['-m', 'app.web_api', '--host', '127.0.0.1', '--port', '18800', '--database', join(scratch, 'games.sqlite')], { cwd: '..', stdio: 'inherit' }));
children.push(spawn('npm', ['run', 'start', '--', '--hostname', '127.0.0.1', '--port', '18765'], { stdio: 'inherit', env: frontendEnv }));
for (const child of children) {
  child.on('error', error => { console.error(error); void stop(1); });
  child.on('exit', code => { if (!stopping) void stop(code || 1); });
}
