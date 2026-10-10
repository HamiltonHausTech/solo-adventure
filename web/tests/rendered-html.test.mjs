import assert from 'node:assert/strict';
import test from 'node:test';
import worker from '../dist/server/index.js';

async function render() {
  return worker.fetch(new Request('http://localhost/', { headers: { accept: 'text/html' } }),
    { ASSETS: { fetch: async () => new Response('Not found', { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} });
}
test('SSR serves the current adventure shell and metadata without an API', async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /^text\/html/);
  const html = await response.text();
  assert.match(html, /<title>Solo Adventure — The Ruined Watchtower<\/title>/);
  assert.match(html, /Waking the watchtower/);
  assert.match(html, /Waiting for the authoritative game engine/);
  assert.match(html, /<main/);
  assert.doesNotMatch(html, /Your site is taking shape|react-loading-skeleton/);
});
test('SSR includes hydration assets, responsive viewport, and no fabricated game state', async () => {
  const html = await (await render()).text();
  assert.match(html, /name="viewport" content="width=device-width, initial-scale=1"/);
  assert.match(html, /rel="modulepreload"/);
  assert.match(html, /rel="stylesheet"/);
  assert.doesNotMatch(html, /Python engine connected|Authoritative events/);
});
