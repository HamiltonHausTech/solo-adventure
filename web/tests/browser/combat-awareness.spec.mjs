import { test, expect } from '@playwright/test';
import { seedCombatAwareness } from '../progression-fixture.mjs';
const api = 'http://127.0.0.1:18800';
const read = async (request, id) => (await request.get(`${api}/api/games/${id}`)).json();
async function resume(page, name) {
  await page.goto('/');
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
}
const awareness = page => page.getByRole('region', { name: 'Party readiness' });

for (const scenario of ['all', 'some', 'affordable', 'none', 'above']) {
  test(`awareness: offensive affordability ${scenario} before Special in real combat`, async ({ page, request }) => {
    const { id, name } = seedCombatAwareness(`spells-${scenario}`);
    if (scenario === 'all') await page.setViewportSize({ width: 390, height: 844 });
    await resume(page, name);
    const state = (await read(request, id)).state;
    expect(state.phase).toBe('combat');
    expect(state.player.mana).toBeGreaterThan(0);
    const offensive = state.spellbook.filter(s => s.target_type === 'enemy' && s.contexts.includes('combat'));
    const costly = offensive.filter(s => s.mana_cost > state.player.mana);
    expect(costly.length).toBe({ all: 2, some: 1, affordable: 0, none: 0, above: 1 }[scenario]);
    if (scenario === 'none') expect(offensive).toHaveLength(0);
    if (scenario === 'all') expect([state.player.mana, state.player.max_mana]).toEqual([1, 6]);
    if (scenario === 'above') expect(state.player.mana).toBeGreaterThan(state.player.max_mana / 4);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const panel = awareness(page);
    expect(await panel.evaluate(el => el.closest('.action-area') !== null)).toBe(true);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByRole('alert')).toHaveCount(0);
    if (costly.length) {
      await expect(panel).toContainText(costly.length === offensive.length ? 'Cannot afford any learned offensive spells' : 'Some learned offensive spells are unaffordable');
      for (const spell of costly) await expect(panel).toContainText(`${spell.name} requires ${spell.mana_cost} mana`);
      await expect(panel).toContainText(`${state.player.mana}/${state.player.max_mana} mana`);
    } else {
      await expect(panel).not.toContainText('unaffordable');
      await expect(panel).not.toContainText('Cannot afford');
    }
    for (const spell of offensive.filter(s => s.available)) {
      if (costly.length) await expect(panel).toContainText(`Available offensive spells: ${spell.name}`);
    }
    if (scenario === 'some') await expect(panel).toContainText('Other available spells: Shield');
    await expect(page.locator('.action-grid').getByRole('button', { name: /Special/ })).toBeEnabled();
    await page.reload();
    await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
    if (costly.length) await expect(panel).toContainText(costly.length === offensive.length ? 'Cannot afford any learned offensive spells' : 'Some learned offensive spells are unaffordable');
    if (scenario === 'some' || scenario === 'none') {
      const spell = state.spellbook.find(s => s.available && (scenario === 'some' ? s.target_type === 'enemy' : s.target_type === 'self'));
      expect(spell).toBeTruthy();
      await page.locator('.action-grid').getByRole('button', { name: /Open spellbook/ }).click();
      const article = page.getByRole('dialog', { name: 'Spellbook' }).locator('article').filter({ has: page.getByRole('heading', { name: spell.name, exact: true }) });
      const castButton = article.getByRole('button', { name: `Cast on ${spell.targets[0].label}`, exact: true }).first();
      await expect(castButton).toBeEnabled();
      const completed = page.waitForResponse(`${api}/api/games/${id}/commands`);
      await castButton.click();
      const cast = await (await completed).json();
      expect(cast.accepted).toBe(true);
      expect(cast.state.player.mana).toBe(state.player.mana - spell.mana_cost);
      expect((await read(request, id)).state.player.mana).toBe(cast.state.player.mana);
    }
  });
}

async function act(page, id, label) {
  const response = page.waitForResponse(`${api}/api/games/${id}/commands`);
  await page.locator('.action-grid').getByRole('button', { name: label }).click();
  const result = await (await response).json();
  expect(result.accepted).toBe(true);
  return result;
}
for (const width of [1280, 390]) {
  test(`awareness: threshold, heal clear, caster depletion and reload at ${width}px`, async ({ page, request }) => {
    const { id, name } = seedCombatAwareness();
    await page.setViewportSize({ width, height: 844 });
    await resume(page, name);
    const panel = awareness(page);
    await expect(panel).toContainText(`${name}: Low health · 5/20 HP`);
    await expect(panel).toContainText('Eldrin: Low health');
    const before = (await read(request, id)).state;
    await expect(panel).toContainText(`${name}: Mana depleted · 0/${before.player.max_mana}`);
    await expect(panel.getByRole('button', { name: `Use healing potion on ${name}` })).toBeEnabled();
    await expect(page.getByRole('alert')).toHaveCount(0);
    expect(await panel.evaluate(el => el.closest('.action-area') !== null)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const completed = page.waitForResponse(`${api}/api/games/${id}/commands`);
    await panel.getByRole('button', { name: `Use healing potion on ${name}` }).click();
    const result = await (await completed).json();
    expect(result.state.player.hp).toBeGreaterThan(5);
    await expect(panel).not.toContainText(`${name}: Low health`);
    await page.reload();
    await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
    await expect(panel).not.toContainText(`${name}: Low health`);
    expect((await read(request, id)).state.player.hp).toBe(result.state.player.hp);
  });
}
for (const scenario of ['above', 'empty', 'noncaster', 'mana-low', 'fallen']) {
  test(`awareness: ${scenario} is truthful`, async ({ page, request }) => {
    const { id, name } = seedCombatAwareness(scenario);
    await resume(page, name);
    const panel = awareness(page);
    const state = (await read(request, id)).state;
    if (scenario === 'above') await expect(panel).not.toContainText(`${name}: Low health`);
    if (scenario === 'empty') await expect(panel.getByRole('button', { name: /Use healing potion/ })).toHaveCount(0);
    if (scenario === 'noncaster') await expect(panel).not.toContainText(`${name}: Mana`);
    if (scenario === 'mana-low') {
      await expect(panel).toContainText(`${name}: Low mana · 1/${state.player.max_mana}`);
      await expect(panel).not.toContainText(`${name}: Mana depleted`);
      await page.locator('.action-grid').getByRole('button', { name: /Open spellbook/ }).click();
      const dialog = page.getByRole('dialog', { name: 'Spellbook' });
      const costly = state.spellbook.filter(s => s.mana_cost > 1 && s.contexts.includes('exploration'));
      expect(costly.length).toBeGreaterThan(0);
      for (const spell of costly) await expect(dialog).toContainText(`Requires ${spell.mana_cost} mana`);
      const guidance = dialog.locator('article').filter({ has: page.getByRole('heading', { name: 'Guidance', exact: true }) });
      await expect(guidance.getByRole('button', { name: `Cast on ${name}` })).toBeEnabled();
      const completed = page.waitForResponse(`${api}/api/games/${id}/commands`);
      await guidance.getByRole('button', { name: `Cast on ${name}` }).click();
      const cast = await (await completed).json();
      expect(cast.accepted).toBe(true);
      expect(cast.state.player.mana).toBe(0);
      await expect(panel).toContainText(`${name}: Mana depleted`);
    }
    if (scenario === 'fallen') { await expect(panel).toContainText('Eldrin: Fallen · 0/'); await expect(panel).not.toContainText('Eldrin: Low health'); }
    await expect(panel).not.toContainText('Battle won');
  });
}
test('awareness: authoritative net health feedback, no replay after reload', async ({ page, request }) => {
  const { id, name } = seedCombatAwareness('damage');
  await resume(page, name);
  const result = await act(page, id, /Defend/);
  const delta = result.events.find(e => e.type === 'health_changed' && e.actor === 'player');
  expect(delta.data.hp_delta).toBe(-1);
  await expect(awareness(page)).toContainText(`${name}: health fell 1 this turn · 9/20 HP`);
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  await expect(awareness(page)).not.toContainText('health fell');
  expect((await read(request, id)).state.player.hp).toBe(9);
});
test('awareness: healing and damage in one real round is not described as a hit', async ({ page }) => {
  const { id, name } = seedCombatAwareness('healing-damage');
  await resume(page, name);
  const result = await act(page, id, new RegExp(`Heal ${name}`));
  expect(result.state.player.hp).toBeGreaterThanOrEqual(10);
  await expect(awareness(page)).not.toContainText('health fell');
});
test('awareness: actual victory summary persists, camp previews then updates recovery', async ({ page, request }) => {
  const { id, name } = seedCombatAwareness('victory');
  await resume(page, name);
  await expect(page.getByRole('region', { name: 'Post-battle recovery' })).toHaveCount(0);
  const result = await act(page, id, /Attack/);
  expect(result.state.phase).toBe('exploration');
  const summary = page.getByRole('region', { name: 'Post-battle recovery' });
  await expect(summary).toContainText('Battle won');
  for (const actor of [result.state.player, ...result.state.companions]) {
    await expect(summary).toContainText(`${actor.name}: ${actor.hp}/${actor.max_hp} HP`);
    if (actor.max_mana) await expect(summary).toContainText(`${actor.mana}/${actor.max_mana} mana`);
  }
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  await expect(summary).toBeVisible();
  await expect(awareness(page)).not.toContainText('health fell');
  await summary.getByRole('button', { name: 'Review camp recovery' }).click();
  const dialog = page.getByRole('dialog', { name: 'Make camp' });
  await expect(dialog).toBeVisible();
  expect((await read(request, id)).state.turn).toBe(result.state.turn);
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(summary.getByRole('button', { name: 'Review camp recovery' })).toBeFocused();
  await summary.getByRole('button', { name: 'Review camp recovery' }).click();
  const completed = page.waitForResponse(`${api}/api/games/${id}/commands`);
  await dialog.getByRole('button', { name: 'Confirm camp' }).click();
  const recovered = await (await completed).json();
  expect(recovered.accepted).toBe(true);
  await expect(summary).toHaveCount(0);
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  await expect(summary).toHaveCount(0);
});
test('awareness: summary disappears on movement and a new fight', async ({ page, request }) => {
  const { id, name } = seedCombatAwareness('victory');
  await resume(page, name);
  await act(page, id, /Attack/);
  const summary = page.getByRole('region', { name: 'Post-battle recovery' });
  await expect(summary).toBeVisible();
  for (const destination of ['crossroads', 'marsh_path']) {
    const before = (await read(request, id)).state;
    const move = before.available_actions.find(action => action.id === 'move' && action.target === destination);
    expect(move).toBeTruthy();
    const result = await act(page, id, new RegExp(move.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    expect(result.state.room.id).toBe(destination);
    await expect(summary).toHaveCount(0);
    if (destination === 'marsh_path') expect(result.state.phase).toBe('combat');
    await page.reload();
    await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
    await expect(summary).toHaveCount(0);
  }
});

test('awareness: Greyfen death is explicit and never victory', async ({ page }) => {
  const { id, name } = seedCombatAwareness('death');
  await resume(page, name);
  const result = await act(page, id, /Defend/);
  expect(result.state.phase).toBe('defeat');
  await expect(awareness(page)).toContainText(`Adventure ended · ${name} has fallen`);
  await expect(awareness(page)).not.toContainText('Low health');
  await expect(page.getByRole('region', { name: 'Post-battle recovery' })).toHaveCount(0);
  await expect(page.locator('.event-list')).not.toContainText('watchtower');
  await page.reload();
  await page.locator('.saved-adventures').getByRole('button', { name: new RegExp(name) }).click();
  await expect(awareness(page)).toContainText('Adventure ended');
});
