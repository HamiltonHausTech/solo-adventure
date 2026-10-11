# Solo Adventure browser client (local only)

This React/vinext interface talks to the authoritative Python game API. It is a
**single-user, local-only application**, not a public hosted service. Keep both
servers on loopback. The API has no user authentication or authorization; CORS
is not authentication. Remote frontend origins are unsupported. The optional
Cloudflare/D1 starter files are not the game's persistence layer and do not make
this application safe to publish.

## Run locally

Prerequisites: Node.js >=22.13, npm, and Python 3.14 (or the Python version
supported by the repository). From the repository root, start the API using a
SQLite path you explicitly choose:

```sh
python3 -m app.web_api --host 127.0.0.1 --port 8000 --database /path/to/games.sqlite
```

In a second terminal:

```sh
cd web
npm ci --include=dev
npm run dev
```

Open the localhost URL printed by vinext. The API permits HTTP/HTTPS origins on
`localhost`, `127.0.0.1`, and `::1` at any port. Do not use a LAN address, tunnel,
or public hostname.

### API configuration

`app/api.ts` owns all game API transport. Its default is
`http://127.0.0.1:8000`. To run another **local** API port:

```sh
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 npm run dev
```

This public setting is embedded in the client build; set it before `npm run
build` as well when using a built bundle. It is not a secret or a deployment/auth
configuration. Requests time out after 15 seconds. Catalog connection failures
show an actionable retry screen; retry reloads the catalog rather than creating
a character. Saved adventures and adventurers load independently; a failed list
shows an alert and **Retry saved lists**, preserving already loaded entries.
Command failures are never automatically replayed.

A hub edit or a newer adventure can make an older session read-only. HTTP 409
errors preserve the server's explanation and offer **Return to adventurer
roster**. Select the current adventurer there and begin a new campaign; do not
retry writes to the old session expecting newer character changes to disappear.

## Combat awareness

**Party readiness**, beside the actions on desktop and mobile, shows exact HP
at or below 25%, fallen companions, and low/depleted caster mana. Potion guidance
requires a usable healing potion; spellbook costs still govern individual spells.
Net HP losses come only from structured `health_changed` command events, never
narrative matching, and disappear on the next command or resume. A cleared-room
recovery summary uses current named party HP/mana and opens the existing Camp
preview; it disappears after living-party recovery, movement to an uncleared
room, a new fight, or death. Camp does not revive fallen companions.

## Verification

The active adventure keeps the server's current objective visible above the
scene. Expand **Journal and known locations** for remembered discoveries and
location statuses; hidden campaign rooms are not listed. Movement buttons use
those same server statuses. Resuming an adventure restores this information
from its saved state, not a browser-only checklist.

**Camp** previews each party member's HP/mana gains and the elapsed turns before
confirmation. Cancel or Escape returns focus to its opener. Confirmation sends
one `camp` command; the Python engine performs the bounded recovery, and the
chronicle shows its summary. The original single-turn rest remains available.
While camp is resolving, confirmation and dismissal are disabled. Commands
are never retried automatically; after a transport error, resume the saved
adventure to check what actually persisted before attempting another command.

Greyfen's finale uses the existing challenge buttons, including visible reasons
for unavailable approaches; completion remains readable in the objective,
journal, and scene when resuming.

```sh
npm ci --include=dev
npx playwright install chromium
npm test
npm run lint
npm run typecheck
npm run test:e2e
```

- `npm test`: builds, runs two current SSR checks, then the Chromium regressions.
- `npm run test:ssr`: build and SSR checks only.
- `npm run test:e2e` / `npm run test:browser`: builds and serves the production
  frontend bundle, then runs Chromium against it and a disposable Python API;
  do not start separate servers for it.
- `npm run test:browser -- --grep progression --repeat-each=2`: repeats both
  progression scenarios with fresh per-test fixtures.
- `npm run test:browser -- tests/browser/adventure-flow.spec.mjs --repeat-each=2`:
  repeats disposable camp, discovery, and finale scenarios. Camp checks exact
  payload, busy/focus handling, gains, elapsed turns, and reload persistence;
  discovery checks mobile layout and server-known locations; finale cases check
  prepared versus fallback options and saved completion. Requires the matching
  Python journey/camp/finale implementation.
- `PYTHON=/path/to/python3.14 npm run test:browser -- tests/browser/combat-awareness.spec.mjs --repeat-each=2`:
  real disposable Python fixtures cover thresholds, healing, empty supplies,
  caster/noncaster mana, net round feedback, death, and victory/Camp/movement
  lifecycle with reloads. No live AI or user database is used.
- `PYTHON=/path/to/python3.14 npm test` selects an interpreter explicitly. This
  is useful on macOS where `python3` can still mean Apple's older interpreter.
- Linux CI may need `npx playwright install --with-deps chromium`.

Tests reserve frontend `localhost:18765` and API `127.0.0.1:18800`; both ports
must be free. The Playwright config allocates a unique directory and
`tests/servers.mjs` starts the API with a SQLite database under the OS
scratch directory (`TMPDIR` when set), never the user's game database, and
removes it on normal shutdown. No LLM is called. Playwright traces on failure
are local ignored files under `test-results/`.

### Coverage and boundaries

Real browser interactions against the real Python API cover character creation,
armor equip, entering combat and attacking, persisted reload/resume, and
attribute/class progression confirmation. The progression test seeds earned
points into a fresh, uniquely named character before every test attempt using
a bounded local Python helper restricted to the disposable database. This also
works on repeats/retries; it tests real confirmation and
persistence, not grinding an entire campaign for XP. It also verifies a genuine
409 after the hub edit and navigation back to the roster.

Controlled browser routes cover each saved-list endpoint returning 503 while
the other succeeds, retry without game creation, obsolete roster responses,
and network/HTTP/invalid-JSON catalog outages,
out-of-order adventurer successes/errors, clearing a pending selection,
management busy guards, active-game weapon equip, and a stale-session error.
The provisioner test checks initial focus, Tab containment, Escape dismissal,
and focus restoration. The same focus hook serves spellbook/new-game dialogs.

The suite is Chromium-only; it does not claim exhaustive campaign completion,
Safari/Firefox coverage, audio playback verification, or a full accessibility
audit. Audio uses one reusable context per mounted game screen and closes it
on unmount. Broader cosmetic component splitting was intentionally avoided:
transport, connection UI, and dialog focus handling are isolated while the
existing game layout is preserved.
