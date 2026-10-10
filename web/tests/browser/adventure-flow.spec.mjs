import { test, expect } from '@playwright/test';
import { seedAdventureFlow } from '../progression-fixture.mjs';
const api = 'http://127.0.0.1:18800';
const read = async (request, id) => (await request.get(`${api}/api/games/${id}`)).json();
async function resume(page, name) {
  await page.goto('/');
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
}
async function assertJourney(page, state) {
  await expect(page.getByRole('region', { name: 'Current objective' })).toContainText(state.journey.objective.title);
  await expect(page.getByRole('region', { name: 'Current objective' })).toContainText(state.journey.objective.description);
  const details = page.getByText('Journal and known locations', { exact: true });
  if (await details.locator('..').getAttribute('open') === null) await details.click();
  const locations = page.getByRole('list', { name: 'Known locations' });
  await expect(locations.locator('li')).toHaveCount(state.journey.locations.length);
  for (const location of state.journey.locations) {
    const row = locations.locator('li').filter({ hasText: location.name });
    await expect(row).toContainText(location.statuses.join(' · '));
  }
  for (const entry of state.journey.journal) await expect(page.getByRole('list', { name: 'Journal' })).toContainText(entry.text);
}

test('adventure flow: camp preview, cancel, focus, one busy-guarded command and persisted recovery', async ({ page, request }) => {
  const { id, name } = seedAdventureFlow();
  const before = (await read(request, id)).state;
  expect(before.camp.available).toBe(true);
  await resume(page, name);
  const opener = page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: /^Camp/ }) });
  await opener.click();
  const dialog = page.getByRole('dialog', { name: 'Make camp' });
  await expect(dialog).toContainText(`${before.camp.recovery_turns} turns`);
  for (const actor of before.camp.recovery) await expect(dialog.getByRole('listitem').filter({ hasText: actor.name })).toContainText(`+${actor.hp} HP · +${actor.mana} mana`);
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: 'Confirm camp' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect((await read(request, id)).state.turn).toBe(before.turn);
  await opener.click();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(opener).toBeFocused();
  let release;
  const sent = [];
  await page.route(`**/api/games/${id}/commands`, async route => {
    sent.push(route.request().postDataJSON());
    await new Promise(resolve => { release = resolve; });
    await route.continue();
  });
  await opener.click();
  const completed = page.waitForResponse(`${api}/api/games/${id}/commands`);
  await dialog.getByRole('button', { name: 'Confirm camp' }).evaluate(button => { button.click(); button.click(); });
  await expect(dialog.getByRole('button', { name: 'Making camp…' })).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement.closest('[role="dialog"]') !== null)).toBe(true);
  await expect.poll(() => Boolean(release)).toBe(true);
  release();
  const result = await (await completed).json();
  expect(sent).toEqual([{ command: 'camp' }]);
  expect(result.accepted).toBe(true);
  expect(result.state.turn).toBe(before.turn + before.camp.recovery_turns);
  for (const actor of before.camp.recovery) {
    const oldActor = [before.player, ...before.companions].find(entry => entry.name === actor.name);
    const newActor = [result.state.player, ...result.state.companions].find(entry => entry.name === actor.name);
    expect(newActor.hp).toBe(oldActor.hp + actor.hp);
    expect(newActor.mana).toBe(oldActor.mana + actor.mana);
  }
  await expect(dialog).toHaveCount(0);
  for (const event of result.events) await expect(page.locator('.event-list')).toContainText(event.message);
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  const persisted = (await read(request, id)).state;
  expect(persisted.turn).toBe(result.state.turn);
  expect(persisted.player).toEqual(result.state.player);
  expect(persisted.companions).toEqual(result.state.companions);
  await expect(page.locator('.turn-counter b')).toHaveText(String(persisted.turn).padStart(2, '0'));
  await assertJourney(page, persisted);
});

test('adventure flow: objective, cleared description and discovered locations survive reload on mobile', async ({ page, request }) => {
  const { id, name } = seedAdventureFlow('discovery');
  await page.setViewportSize({ width: 390, height: 844 });
  const before = (await read(request, id)).state;
  expect(before.journey.locations.find(location => location.id === 'high_road').statuses.map(status => status.toLowerCase())).toContain('cleared');
  expect(before.room.description).not.toContain('lower hooked spears');
  await resume(page, name);
  await assertJourney(page, before);
  await expect(page.locator('.scene-caption')).toContainText(before.room.description);
  // No campaign room_order disclosure: only server-known locations appear.
  await expect(page.getByRole('list', { name: 'Known locations' })).not.toContainText('The Ember Vault');
  for (const action of before.available_actions.filter(action => action.id === 'move')) {
    const location = before.journey.locations.find(location => location.id === action.target);
    if (location) await expect(page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: action.label }) })).toContainText(location.statuses.join(' · '));
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  await assertJourney(page, before);
  await expect(page.locator('.scene-caption')).toContainText(before.room.description);
  const move = before.available_actions.find(action => action.id === 'move' && action.target === 'signal_tower');
  expect(move).toBeTruthy();
  const moved = page.waitForResponse(`${api}/api/games/${id}/commands`);
  await page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: move.label }) }).click();
  const result = await (await moved).json();
  expect(result.accepted).toBe(true);
  expect(result.state.room.id).toBe('signal_tower');
  expect(result.state.journey.locations.find(location => location.id === 'signal_tower').statuses.map(status => status.toLowerCase())).toContain('visited');
  await assertJourney(page, result.state);
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  expect((await read(request, id)).state.journey).toEqual(result.state.journey);
  await assertJourney(page, result.state);
});

test('adventure flow: failed camp request is not automatically retried', async ({ page, request }) => {
  const { id, name } = seedAdventureFlow();
  const before = (await read(request, id)).state;
  await resume(page, name);
  const sent = [];
  await page.route(`**/api/games/${id}/commands`, route => {
    sent.push(route.request().postDataJSON());
    return route.abort('failed');
  });
  await page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: /^Camp/ }) }).click();
  await page.getByRole('button', { name: 'Confirm camp' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(sent).toEqual([{ command: 'camp' }]);
  expect((await read(request, id)).state.turn).toBe(before.turn);
  await page.getByRole('button', { name: 'Return to adventurer roster' }).click();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  expect(sent).toEqual([{ command: 'camp' }]);
});

test('adventure flow: searching supplies exhausts authoritative actions and persists after reload', async ({ page, request }) => {
  const { id, name } = seedAdventureFlow('search');
  const before = (await read(request, id)).state;
  expect(before.room.id).toBe('fallen_bridge');
  expect(before.journey.locations.find(location => location.id === before.room.id).statuses).not.toContain('Searched');
  const search = before.available_actions.find(action => action.id === 'search');
  expect(search.disabled).toBe(false);
  await resume(page, name);
  await assertJourney(page, before);
  const completed = page.waitForResponse(`${api}/api/games/${id}/commands`);
  await page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: search.label }) }).click();
  const response = await completed;
  expect(response.request().postDataJSON()).toEqual({ command: 'search' });
  const result = await response.json();
  expect(result.accepted).toBe(true);
  expect(result.state.journey.locations.find(location => location.id === before.room.id).statuses).toContain('Searched');
  expect(result.state.journey.objective.description).not.toBe(before.journey.objective.description);
  expect(result.state.journey.objective.description).not.toContain('Search the abandoned camp');
  const exhausted = result.state.available_actions.filter(action => ['search', 'loot'].includes(action.id));
  expect(exhausted.map(action => action.id).sort()).toEqual(['loot', 'search']);
  async function assertExhausted(state) {
    await assertJourney(page, state);
    for (const action of exhausted) {
      expect(action.disabled).toBe(true);
      expect(action.disabled_reason).toBeTruthy();
      const button = page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: action.label }) });
      await expect(button).toBeDisabled();
      await expect(button).toContainText(action.disabled_reason);
    }
  }
  await assertExhausted(result.state);
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  const persisted = (await read(request, id)).state;
  expect(persisted.journey).toEqual(result.state.journey);
  expect(persisted.available_actions).toEqual(result.state.available_actions);
  expect(persisted.inventory).toEqual(result.state.inventory);
  expect(persisted.turn).toBe(result.state.turn);
  await assertExhausted(persisted);
});

for (const scenario of ['finale', 'finale-prepared']) {
  test(`adventure flow: ${scenario} choices explain eligibility and persist completion`, async ({ page, request }) => {
    const { id, name } = seedAdventureFlow(scenario);
    const before = (await read(request, id)).state;
    expect(before.challenge).toBeTruthy();
    expect(before.challenge.options.length).toBeGreaterThan(1);
    if (scenario === 'finale') expect(before.challenge.options.some(option => !option.available)).toBe(true);
    else expect(before.challenge.options.every(option => option.available)).toBe(true);
    await resume(page, name);
    await expect(page.getByRole('heading', { name: before.challenge.title })).toBeVisible();
    await expect(page.getByRole('button', { name: /Open the chest|Restore the seal/ })).toHaveCount(0);
    await expect(page.locator('.action-grid button b').filter({ hasText: /^(Search|Inspect|Loot|Open)$/ })).toHaveCount(0);
    for (const option of before.challenge.options) {
      const button = page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: option.label }) });
      await expect(button).toHaveCount(1);
      if (option.available) await expect(button).toBeEnabled();
      else { await expect(button).toBeDisabled(); await expect(button).toContainText(option.reason); }
    }
    let choice = before.challenge.options.find(option => option.available);
    if (scenario === 'finale-prepared') {
      const unprepared = seedAdventureFlow('finale');
      const baseline = (await read(request, unprepared.id)).state;
      const gatedIds = baseline.challenge.options.filter(option => !option.available).map(option => option.id);
      choice = before.challenge.options.find(option => option.available && gatedIds.includes(option.id));
      expect(choice).toBeTruthy();
    }
    const completed = page.waitForResponse(`${api}/api/games/${id}/commands`);
    await page.locator('.action-grid button').filter({ has: page.locator('b', { hasText: choice.label }) }).click();
    const response = await completed;
    expect(response.request().postDataJSON()).toEqual({ command: 'challenge', target: choice.id });
    const result = await response.json();
    expect(result.accepted).toBe(true);
    expect(result.state.game_over).toBe(true);
    await expect(page.getByText('Campaign resolved', { exact: true })).toBeVisible();
    await assertJourney(page, result.state);
    await expect(page.locator('.scene-caption')).toContainText(result.state.room.description);
    await page.reload();
    await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
    const persisted = (await read(request, id)).state;
    expect(persisted.game_over).toBe(true);
    expect(persisted.journey).toEqual(result.state.journey);
    await assertJourney(page, persisted);
    await expect(page.locator('.scene-caption')).toContainText(result.state.room.description);
  });
}
