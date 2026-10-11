# Combat Awareness Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make danger and resource depletion salient without changing combat balance or automating player decisions.

**Architecture:** Derive presentation from authoritative snapshots and structured events. Preserve API/save compatibility and add only minimal event metadata if required. Keep warnings near action controls on mobile and desktop; no modal confirmations or forced recovery.

**Tech Stack:** Python engine/unittest, React/TypeScript/CSS, Playwright with disposable SQLite fixtures.

## Acceptance and scope
- Persistent low-health warning near actions for living player at <=25% max HP (includes Naria at5/20), explicit current/max HP and actionable potion suggestion only when usable/available. Clearly distinguish companion danger, dead actors and game-over. Do not conflate warnings with transport role=alert errors.
- Low/depleted mana feedback for casters near actions: show exact current/max, distinguish zero mana from inability to afford offensive spells, avoid alerts for noncasters or suggesting unavailable spells. Informational; do not alter actual action mechanics or disable valid alternative abilities.
- Clear per-command damage feedback naming actor, actual damage and remaining HP. Use structured authoritative event data, not regex over narrative. Do not mislabel net round HP loss as gross attack damage or claim poison/attack provenance that is absent. If existing events are net deltas, label honestly (e.g. health fell by X this turn) rather than implying single-hit damage. Preserve accessible event log, do not repeatedly announce old damage on reload/navigation.
- Post-fight party status near actions: named HP/mana and available recovery cue/Camp button through existing preview flow. Appears on actual victory (not every exploration room), no victory after death, no stale last-battle damage replay, update or dismiss appropriately after recovery/movement/new battle. Derive from current state/cleared-room facts if persistence avoids new save fields.
- Replace hardcoded watchtower death line with campaign-neutral or actual campaign/room wording in shared rules; no character restoration/save edits.
- No difficulty, damage, resource costs, AI/audio, new dependencies or broad UI rewrite. Original main checkout/user databases untouched. Worktree branch feat/combat-awareness from ec4d09e; one PR, no merge.

## Task 1 — Reproduce and implement (implementer)
Files: web/app/page.tsx, web/app/globals.css; small web/app helper/component if useful; app/engine.py event fields only if necessary, app/rules/combat.py death text; relevant Python tests and new web/tests/browser/combat-awareness.spec.mjs with guarded fixture additions to web/tests/progression-fixture.mjs.
1. Inspect existing metrics/events, spell/action availability and recovery flow before design.
2. Add failing tests for5/20 health, healed threshold dismissal, caster0mana, noncaster no mana warning, terminal states, victory summary/recovery, and accurate round delta display including simultaneous healing/damage.
3. Implement minimal accessible presentation, responsive near action controls. Keep player choice and existing Camp confirmation.
4. Actual Python browser fixtures for low-health, depleted mana and post-fight summary/camp; assert reload behavior, no duplicate submissions, unchanged rules. Mock only transport/fault scenarios as needed. Never user's DB.
5. Tests: full Python on3.11/3.14; npm ci --include=dev; npm test; npm run typecheck; npm run lint; repeat new stateful browser suite twice; git diff --check. Root/web README concise behavior docs.

## Task 2 — Review (parent)
Independent spec review then quality review, resolve findings and rerun. Verify actual diff and outputs. Keep changes focused.

## Task 3 — Publish (parent)
Commit/push/open PR; verify exact-head CI and completed Bugbot findings (independently assess; autofix off). Report URL, file count, checks and merge boundary. Do not update original playtest checkout until user requests after merge.
