# Tracker Integration — Auto-Agent's source-of-truth contract

The tracker is the canonical record: the ticket is the brief, the comments are the audit
trail, the state transitions are the workflow. v1 supports **Linear**; the tracker is
isolated here + in `scripts/factory/linear.py` so other trackers can be added as adapters.

## 1. Config + access

All tracker specifics come from `factory.config`: `LINEAR_TEAM` (name), `LINEAR_PROJECT`
(name, optional). IDs (team, project, workflow states, labels) are **resolved from these
names at runtime** — nothing is hardcoded.

- **Interactive Claude sessions:** use the Linear **MCP** tools if available
  (`list_issues`, `save_issue`, `save_comment`, …).
- **Headless (the 24/7 driver / cloud routines): NO MCP.** Use the CLI:
  `python3 scripts/factory/linear.py <list-eligible|get|state|comment|label|subissue>`
  (auth: `LINEAR_API_KEY` in `scripts/factory/.env.local`). Same operations, different
  transport. If neither MCP nor `LINEAR_API_KEY` works → **halt** (don't ship unrecorded work).

> Linear MCP string values take **real newlines**, not `\n`.

## 2. Workflow states

Resolved by name from the team. Defaults: `Backlog`, `Todo`, `In Progress`, `Done`,
`Canceled`. Transition rule: `Backlog`/`Todo` → `In Progress` (claim) → `Done` (PR merged).
No agent flips backward except to leave a ticket `In Progress` when blocked.

## 3. Labels

Taxonomy labels (e.g. `Bug`, `Performance`, `Tech Debt`, `Feature`, `Improvement`) are read,
never removed. Control labels (`CLAUDE-FACTORY.md` §F5) are created on first run if missing.

## 4. Pick-next + claim (the loop's heart)

`linear.py list-eligible` returns project/team issues in `backlog`/`unstarted`/`started`,
excluding `factory-skip` + `factory-blocked` + tickets claimed by another instance. Rank by
priority (Urgent→Low) then smallest scope. **Claim** the chosen ticket atomically: set
`In Progress` + `factory-building` + a `[factory:claim] instance=<FACTORY_INSTANCE>` comment,
then re-read — if another instance claimed earlier, yield and re-pick. See skill §1.

## 5. Branch / PR / commit convention

- **Branch:** `<BRANCH_PREFIX>/<ticket-id>-<slug>` for local self-merge instances; cloud
  routines must use `claude/<ticket-id>-<slug>` (push is restricted to `claude/*` there).
  Branch off the latest `<DEFAULT_BRANCH>`.
- **Commit + PR titles:** conventional-commit carrying the ticket id, e.g.
  `feat(ABC-123): …`, `fix(ABC-123): …`, `perf(…)`, `refactor(…)`, `chore(…)`.
- Honor the repo's own commit conventions (`CLAUDE.md`) — e.g. co-author trailers on/off.
- **PR body:** what changed · how it works · files · verified (gate ✓ + a prod-check note).

## 6. Comment templates

Header line `[factory:<agent>] <one-line outcome>`, then body, then a footer
`— run: <ISO> · <ticket-id>`. The release-manager posts the merge + the prod surface to
eyeball; the prod-verifier posts PASS/FAIL (or a DEGRADED manual-verify note when headless).

## 7. Acceptance criteria = checkboxes

The planner writes acceptance criteria into the ticket **description** as checkboxes;
test-verifier ticks the ones that pass; the reviewer confirms coverage.

## 8. Sub-issues

Epic decomposition (groomer) and deferred findings (reviewer) → child issues in the same
project, label `from-factory`, parented to the source, announced in a comment. Never silent.

## 9. Degraded / failure modes

Tracker unreachable → halt. Ticket gone/Done/Canceled → skip. Missing label → create it.
A write fails → retry once, else write the intended content into the PR body + run log.

## 10. What the factory will NOT do in the tracker

Move to Done before merge · delete/edit human comments · change team/project · reassign
away from the owner unless told · remove taxonomy labels.

— end —
