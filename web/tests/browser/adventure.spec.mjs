import { test, expect } from '@playwright/test';
import { seedProgression, seedCombatAfterFirstDefeat } from '../progression-fixture.mjs';
import { randomUUID } from 'node:crypto';
const api = 'http://127.0.0.1:18800';
async function create(request, name) {
  const response = await request.post(`${api}/api/games`, { data: { name, class: 'Fighter', race: 'Human', sex: 'Female', companion_id: 'mara' } });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function saved(request, game) {
  const roster = await (await request.get(`${api}/api/adventurers`)).json();
  return roster.adventurers.find(entry => entry.source_game_id === game.game_id);
}

test('real Python API: create, equip, combat, reload and resume exact persisted state', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('Name', { exact: true }).fill('Browser Hero');
  const created = page.waitForResponse(response => response.url() === `${api}/api/games` && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Enter the watchtower', exact: true }).click();
  const payload = await (await created).json();
  await expect(page.getByRole('heading', { name: 'Ruined Courtyard' })).toBeVisible();
  await page.getByRole('button', { name: /Leather Cap/ }).click();
  await expect(page.locator('.player-portrait').locator('..')).toContainText('AC 16');
  await page.getByRole('button', { name: /Move to Crumbling Barracks/ }).click();
  await expect(page.locator('.enemy-strip')).toBeVisible();
  const attack = page.waitForResponse(response => response.url().endsWith('/commands') && response.request().postDataJSON().command === 'attack');
  await page.getByRole('button', { name: /Attack/ }).first().click();
  const outcome = await (await attack).json();
  expect(outcome.accepted).toBe(true);
  expect(outcome.events.length).toBeGreaterThan(0);
  await expect(page.locator('.turn-counter b')).toHaveText(String(outcome.state.turn).padStart(2, '0'));
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: /Browser Hero/ }).click();
  await expect(page.getByRole('heading', { name: 'Crumbling Barracks' })).toBeVisible();
  await expect(page.locator('.turn-counter b')).toHaveText(String(outcome.state.turn).padStart(2, '0'));
  const persisted = await (await request.get(`${api}/api/games/${payload.game_id}`)).json();
  expect(persisted.state.turn).toBe(outcome.state.turn);
  expect(persisted.state.player.hp).toBe(outcome.state.player.hp);
  expect(errors).toEqual([]);
});

for (const action of ['attack', 'special', 'cast']) {
  test(`real Python API: ${action} targets living enemies after enemy 1 dies`, async ({ page, request }) => {
    const { id, name } = seedCombatAfterFirstDefeat();
    const before = await (await request.get(`${api}/api/games/${id}`)).json();
    expect(before.state.phase).toBe('combat');
    expect(before.state.enemies.map(enemy => enemy.id)).toEqual([2]);
    await page.goto('/');
    await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
    const response = page.waitForResponse(response => response.url() === `${api}/api/games/${id}/commands`);
    if (action === 'cast') {
      await page.getByRole('button', { name: 'Open spellbook', exact: false }).click();
      await page.locator('.spell-list article').filter({ has: page.getByRole('heading', { name: 'Spark', exact: true }) }).getByRole('button', { name: /^Cast on / }).click();
    } else {
      await page.locator('.action-grid').getByRole('button', { name: new RegExp(action, 'i') }).click();
    }
    const completed = await response;
    expect(completed.ok()).toBeTruthy();
    expect(completed.request().postDataJSON()).toEqual(action === 'cast'
      ? { command: 'cast', spell: 'Spark', target: '2' }
      : { command: action });
    const result = await completed.json();
    expect(result.accepted).toBe(true);
    expect(result.state.turn).toBe(before.state.turn + 1);
    expect(result.events.length).toBeGreaterThan(0);
    expect(result.state.enemies.map(enemy => enemy.id)).toEqual([2]);
    await expect(page.locator('.turn-counter b')).toHaveText(String(result.state.turn).padStart(2, '0'));
    await expect(page.getByRole('alert')).toHaveCount(0);
    const persisted = await (await request.get(`${api}/api/games/${id}`)).json();
    expect(persisted.state.turn).toBe(result.state.turn);
    expect(persisted.state.enemies).toEqual(result.state.enemies);
  });
}

test('real Python API: progression persists and makes the older session read-only', async ({ page, request }) => {
  const name = seedProgression();
  await page.goto('/');
  await page.getByRole('button', { name: new RegExp(`${name}.*Use character`) }).click();
  await page.locator('.attribute-allocation article').filter({ hasText: 'STR' }).getByRole('button', { name: '+', exact: true }).click();
  await page.locator('.upgrade-allocation button').first().click();
  const update = page.waitForResponse(response => response.url().includes('/adventurers/') && response.url().endsWith('/commands'));
  await page.getByRole('button', { name: 'Confirm permanent changes' }).click();
  const result = await (await update).json();
  expect(result.adventurer.player.stats.STR).toBe(3);
  expect(result.adventurer.progression.unspent_attribute_points).toBe(0);
  expect(result.adventurer.progression.unspent_class_upgrades).toBe(0);
  await page.reload();
  await page.getByRole('button', { name: new RegExp(`${name}.*Use character`) }).click();
  await expect(page.getByText('No upgrade decisions are pending.', { exact: false })).toBeVisible();
  const reread = await (await request.get(`${api}/api/adventurers/${result.adventurer.adventurer_id}`)).json();
  expect(reread.adventurer.player.stats.STR).toBe(3);
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  const stale = page.waitForResponse(response => response.url().endsWith('/commands'));
  await page.getByRole('button', { name: 'Ask advice', exact: true }).click();
  expect((await stale).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('read-only');
  await page.getByRole('button', { name: 'Return to adventurer roster' }).click();
  await expect(page.getByRole('heading', { name: 'Choose your adventurer' })).toBeVisible();
});

for (const failedList of ['games', 'adventurers']) {
  test(`${failedList} 503 preserves the healthy list and retry recovers without creation`, async ({ page, request }) => {
    const name = `Roster ${failedList} ${randomUUID().slice(0, 6)}`;
    await create(request, name);
    let offline = true;
    let creations = 0;
    page.on('request', request => { if (request.url() === `${api}/api/games` && request.method() === 'POST') creations++; });
    await page.route(`**/api/${failedList}`, route => offline && route.request().method() === 'GET'
      ? route.fulfill({ status: 503, json: { error: 'Temporary roster outage' } }) : route.continue());
    await page.goto('/');
    const adventure = page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) });
    const character = page.getByRole('button', { name: new RegExp(`${name}.*Use character`) });
    await expect(failedList === 'games' ? character : adventure).toBeVisible();
    await expect(page.getByRole('alert')).toContainText(failedList === 'games' ? 'saved adventures' : 'saved adventurers');
    offline = false;
    await page.getByRole('button', { name: 'Retry saved lists' }).click();
    await expect(adventure).toBeVisible();
    await expect(character).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    expect(creations).toBe(0);
  });
}

for (const status of [200, 503]) {
  test(`roster retry ignores an obsolete ${status} response`, async ({ page, request }) => {
    const name = `Late ${randomUUID().slice(0, 8)}`;
    await create(request, name);
    let release;
    let firstGames = true;
    let firstAdventurers = true;
    await page.route('**/api/games', async route => {
      if (!firstGames) return route.continue();
      firstGames = false;
      await new Promise(resolve => { release = resolve; });
      await route.fulfill({ status, json: status === 200 ? { games: [] } : { error: 'Obsolete outage' } });
    });
    await page.route('**/api/adventurers', route => {
      if (!firstAdventurers) return route.continue();
      firstAdventurers = false;
      return route.fulfill({ status: 503, json: { error: 'Retry needed' } });
    });
    await page.goto('/');
    await expect.poll(() => Boolean(release)).toBe(true);
    await page.getByRole('button', { name: 'Retry saved lists' }).click();
    const adventure = page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) });
    await expect(adventure).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    const obsolete = page.waitForResponse(`${api}/api/games`);
    release();
    await (await obsolete).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(adventure).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
  });
}

for (const failure of ['network', 'http', 'invalid-json']) {
  test(`catalog ${failure} outage is visible and retry does not create a game`, async ({ page }) => {
    let offline = true;
    let creations = 0;
    page.on('request', request => { if (request.url() === `${api}/api/games` && request.method() === 'POST') creations++; });
    await page.route('**/api/catalog', route => offline ? failure === 'network' ? route.abort() : route.fulfill({ status: failure === 'http' ? 503 : 200, contentType: 'text/html', body: 'Unavailable' }) : route.continue());
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'The engine is quiet' })).toBeVisible();
    offline = false;
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByRole('heading', { name: 'Choose your adventurer' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Enter the watchtower', exact: true })).toBeEnabled();
    expect(creations).toBe(0);
  });
}

test('selection ignores late success, late errors and cleared selection; old controls disappear', async ({ page, request }) => {
  const alphaName = `Race Alpha ${randomUUID()}`;
  const betaName = `Race Beta ${randomUUID()}`;
  const a = await saved(request, await create(request, alphaName));
  await create(request, betaName);
  let release;
  let status = 200;
  const data = await (await request.get(`${api}/api/adventurers/${a.adventurer_id}`)).json();
  await page.route(`**/api/adventurers/${a.adventurer_id}`, async route => {
    await new Promise(resolve => { release = resolve; });
    await route.fulfill({ status, json: status === 200 ? data : { error: 'Obsolete Alpha error' } });
  });
  await page.goto('/');
  const alpha = page.getByRole('button', { name: new RegExp(`${alphaName}.*Use character`) });
  const beta = page.getByRole('button', { name: new RegExp(`${betaName}.*Use character`) });
  await beta.click();
  await expect(page.getByRole('region', { name: `${betaName} character management` })).toBeVisible();
  for (const fail of [false, true]) {
    status = fail ? 500 : 200;
    await alpha.click();
    await expect(page.getByRole('status')).toHaveText('Loading adventurer…');
    await expect(page.locator('.adventurer-hub')).toHaveCount(0);
    await expect(page.locator('.begin-button')).toBeDisabled();
    await beta.click();
    await expect(page.getByRole('region', { name: `${betaName} character management` })).toBeVisible();
    const response = page.waitForResponse(`${api}/api/adventurers/${a.adventurer_id}`);
    release();
    await (await response).finished();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.getByRole('region', { name: `${betaName} character management` })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
  }
  await alpha.click();
  await expect(page.getByRole('status')).toBeVisible();
  await page.getByRole('button', { name: /Create new instead/ }).click();
  const response = page.waitForResponse(`${api}/api/adventurers/${a.adventurer_id}`);
  release();
  await (await response).finished();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.getByLabel('Name', { exact: true })).toHaveValue('Rowan');
  await expect(page.locator('.adventurer-hub')).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('progression confirmation is busy guarded and provisioner traps/restores keyboard focus', async ({ page, request }) => {
  const name = `Progress ${randomUUID().slice(0, 8)}`;
  const entry = await saved(request, await create(request, name));
  const data = await (await request.get(`${api}/api/adventurers/${entry.adventurer_id}`)).json();
  data.adventurer.progression.unspent_attribute_points = 1;
  data.adventurer.progression.unspent_class_upgrades = 1;
  data.adventurer.progression.upgrade_options = [{ id: 'hardy', name: 'Hardy', description: 'Test upgrade' }];
  await page.route(`**/api/adventurers/${entry.adventurer_id}`, route => route.fulfill({ json: data }));
  let release;
  let sent;
  let count = 0;
  await page.route(`**/api/adventurers/${entry.adventurer_id}/commands`, async route => {
    count++;
    sent = route.request().postDataJSON();
    await new Promise(resolve => { release = resolve; });
    data.adventurer.player.stats.STR++;
    data.adventurer.progression.unspent_attribute_points = 0;
    data.adventurer.progression.unspent_class_upgrades = 0;
    await route.fulfill({ json: data });
  });
  await page.goto('/');
  await page.getByRole('button', { name: new RegExp(`${name}.*Use character`) }).click();
  await page.locator('.attribute-allocation article').filter({ hasText: 'STR' }).getByRole('button', { name: '+', exact: true }).click();
  await page.getByRole('button', { name: 'Hardy Test upgrade' }).click();
  await page.getByRole('button', { name: 'Confirm permanent changes' }).click();
  await expect(page.getByRole('button', { name: 'Confirm permanent changes' })).toBeDisabled();
  await expect(page.getByRole('button', { name: /Create new instead/ })).toBeDisabled();
  expect(sent).toEqual({ command: 'apply_progression', allocations: { STR: 1 }, upgrade: 'hardy' });
  release();
  await expect(page.getByText('No upgrade decisions are pending.', { exact: false })).toBeVisible();
  expect(count).toBe(1);
  const opener = page.getByRole('button', { name: 'Open provisioner' });
  await opener.click();
  const close = page.getByRole('button', { name: 'Close provisioner' });
  await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.evaluate(() => document.activeElement.closest('[role="dialog"]') !== null)).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(opener).toBeFocused();
});

test('active-game weapons equip and stale session 409 returns to roster', async ({ page, request }) => {
  const game = await create(request, 'Weapon Hero');
  game.state.inventory.push({ id: 'test_blade', name: 'Test Blade', kind: 'weapon', slot: 'weapon', effect: { type: 'weapon', damage: '1d8' } });
  await page.route(`**/api/games/${game.game_id}`, route => route.fulfill({ json: game }));
  let sent;
  await page.route(`**/api/games/${game.game_id}/commands`, route => {
    sent = route.request().postDataJSON();
    if (sent.command === 'equip') {
      game.state.equipment.weapon = game.state.inventory.pop();
      return route.fulfill({ json: { ...game, accepted: true, events: [] } });
    }
    return route.fulfill({ status: 409, json: { code: 'stale_adventurer', error: 'This adventurer changed. Reload the hub and start a new adventure.' } });
  });
  await page.goto('/');
  await page.locator('.saved-adventures').getByRole('button', { name: /Weapon Hero/ }).click();
  await page.getByRole('button', { name: /Test Blade/ }).click();
  await expect(page.getByRole('button', { name: /Test Blade/ })).toHaveCount(0);
  expect(sent).toEqual({ command: 'equip', item: 'Test Blade' });
  await page.getByRole('button', { name: 'Ask advice', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('This adventurer changed');
  await page.getByRole('button', { name: 'Return to adventurer roster' }).click();
  await expect(page.getByRole('heading', { name: 'Choose your adventurer' })).toBeVisible();
});
