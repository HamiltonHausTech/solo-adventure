# Adventure Flow Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make short full-loop playtests smoother and demonstrate that established knowledge, companion trust, and character abilities can affect Greyfen's resolution.

**Architecture:** Keep Python authoritative and frontend a snapshot/command adapter. Add data-driven journey presentation and challenge requirements/outcomes, preserve legacy saves and commands, and batch existing recovery rules without introducing random camp events yet. Work in this isolated worktree; never use the user's database in tests.

**Tech Stack:** Python stdlib/unittest/SQLite; React/TypeScript/vinext; Playwright.

## Boundaries
- No difficulty/level scaling, combat action rebalance, AI integration, audio changes, dependency upgrades, public hosting, or original-checkout/save changes.
- No merge. Focused commits and one PR; independently review Bugbot results with autofix off.
- Original repo `/Users/andrewhamilton/Projects/hamiltonhaus/solo-adventure`; implementation worktree is this directory, branch `feat/adventure-flow`, base `c3ab810`.

## Snapshot contract shared by backend and frontend
Existing fields retained. New fields optional on TypeScript side for compatibility with existing fixtures:
```
journey: {
  objective: {title: string, description: string},
  journal: [{id: string, text: string}],
  locations: [{id: string, name: string, statuses: string[]}]
}
camp: {
  available: boolean, reason: string | null,
  recovery_turns: number,
  recovery: [{name: string, hp: number, mana: number}]
}
```
Journey locations include visited rooms and current adjacent exits only; no future hidden-room list. Statuses are facts such as `Unexplored`, `Visited`, `Cleared`, `Searched`, `Unlooted remains`, `Current`. Labels are derived from authoritative state. Objective copy follows known campaign progress, does not expose hidden secrets, and has a graceful generic fallback for other campaigns. Current `room.description` becomes state-aware. `available_actions` retains IDs/targets and provides contextual labels and disabled reasons.

Camp is a new `camp` command with no arguments: simulate up to 100 existing recovery ticks, stopping when living party members are recovered. Preserve single `rest`. Preview is pure, per-actor actual capped gains, uses the same rules as execution; no resurrection. Reject in combat, on completed games, and if no recovery is needed without mutation. Count elapsed recovery ticks in state.turn; create one summary log/event result with actual time and named gains. No browser looping/retries. Apply at most one rest relationship reaction per batch; no unlimited trust rewards via repeated camp in the same location. Reject malformed/extraneous camp params. No live narration/network in tests.

## Task 1 — Bounded camping (backend owner)
Modify `app/rules/rest.py`, `app/engine.py`, `app/main.py`; create `tests/test_adventure_flow.py` or split focused files.
1. Write failing tests for pure preview, partial/full recovery, existing rest streak, bounded ticks, multiple living actors, dead actor no revival, camp rejection immutability, restore/persistence and CLI parity.
2. Run focused unittest to demonstrate failure.
3. Implement shared recovery simulation/preview and camp execution/CLI adapter; preserve existing single rest semantics except do not revive dead actors accidentally.
4. Run focused tests then full suite.
5. Parent commits after integrated review.

## Task 2 — Journey and contextual actions (same backend owner)
Modify `app/content.py`, `app/campaigns/*.py` as needed, `app/engine.py`, `app/rules/exploration.py`; prefer a small `app/journey.py` module.
1. Test objective transitions, route-back guidance, known-only journal and location list, persistent states across restore, cleared combat descriptions, searched labels, no secret disclosure.
2. Implement minimum campaign-configured milestones and shared presentation; no route solver or elaborate quest framework.
3. NPC conversations retain successful knowledge and acknowledge prior discussion instead of rerolling/contradicting success. Provide useful fallback information after failed dialogue rather than mandatory reroll gates. Contextual Talk/Search/Loot descriptions and exhausted states.
4. Verify old campaigns remain completable and all existing tests pass (update old behavior expectations only when intentionally changed and documented).

## Task 3 — Connected Greyfen resolution (same backend owner)
Modify `app/rules/challenges.py`, `app/campaigns/embers_of_greyfen.py`, `app/rules/companion_interactions.py` and engine/exploration integration as needed.
1. Extend challenge requirements minimally for known flags, companion identity/alive/trust and character stat or learned ability. Availability and execution use identical checks. Test unavailable-choice atomic rejection.
2. Configure Greyfen's final seal as distinct approaches: learned truth provides a reliable informed approach; trusted living Eldrin provides assistance with an explicit trust explanation; a developed character has an ability/stat-based alternative; an always-available attempt has bounded fail-forward consequences, never a mandatory grind or hard lockout.
3. Preserve legacy Search/Open/Loot finale commands through the same resolver (cannot bypass prerequisites or duplicate rewards). Legacy completed saves remain completed; old mid-campaign saves still have fallback. Completing any approach uses existing one-time completion/reward semantics and a visible ending/outcome flag, with explanatory prose.
4. Record quest-relevant evidence in the journal. Make trust-relevant benefits legible; don't unlock them by unlimited repeats of the same conversation. If bounded companion memories can forget reward keys, use durable session flags for reward idempotency with legacy fallback.
5. Test low/high trust, wrong/dead companion, knowledge/no knowledge, developed/undeveloped character, failed rolls, completion idempotency, full deterministic short path and serialization. No need to redesign all NPCs or campaigns.

## Task 4 — Browser flow (separate frontend owner)
Modify only `web/` files; consume contract above. Keep design compact and consistent, mobile-friendly and accessible.
1. Add current-objective/journal and discovered-location presentation without replacing main UI.
2. Display status with movement choices and honor server descriptions/reasons. Avoid duplicate action controls for challenges.
3. Camp action opens accessible preview confirmation with named recovery and elapsed recovery turns, cancel/Escape/focus return. Confirm sends exactly one `{command: 'camp'}` and shows summary. Keep single rest available. No automatic retry, busy duplicate requests, or frontend simulation.
4. Existing challenge UI displays reasons and choices, including new finale choices; completed outcome remains readable.
5. Add real-Python browser fixtures/tests in disposable scratch only for camp, objective/location persistence after reload, contextual cleared/search states and knowledge/trust affecting choices. Supplement with focused mocked transport tests if needed. Verify new stateful fixtures with repeat-each=2.
6. Run npm test, typecheck, lint. Use `npm ci --include=dev` (environment may omit dev deps by default).

## Task 5 — Review, verification, publication (parent)
1. Inspect implementation against scope; separate spec review then independent quality review after spec passes. Resolve findings and re-review.
2. Full Python 3.11 and 3.14 tests, production build + SSR + Chromium, repeat new stateful browser tests, lint/typecheck/diff check. Use stub provider, disposable saves, scratch tempdirs only.
3. Update README commands and concise behavior docs, commit focused changes, push business SSH if HTTPS lacks workflow scope; open PR with tests, semantics and boundaries.
4. Verify exact remote head, CI and completed Bugbot review; independently adjudicate/fix findings. Do not merge or modify original checkout.

Verification commands:
```
LLM_PROVIDER=stub /opt/homebrew/opt/python@3.14/bin/python3.14 -m unittest discover -s tests -q
uv run --python 3.11 --no-project python -m unittest discover -s tests -q
cd web && npm ci --include=dev && npm test && npm run typecheck && npm run lint
```
