import { defineConfig } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
// Inherited by the server and workers (including retries); never use the user's DB.
process.env.SOLO_BROWSER_FIXTURE_DIR ??= mkdtempSync(join(tmpdir(), 'solo-web-test-'));
export default defineConfig({
  testDir: './tests/browser',
  workers: 1,
  timeout: 30000,
  use: { baseURL: 'http://localhost:18765', trace: 'retain-on-failure' },
  webServer: { command: 'node tests/servers.mjs', url: 'http://localhost:18765', reuseExistingServer: false, timeout: 90000 },
});
