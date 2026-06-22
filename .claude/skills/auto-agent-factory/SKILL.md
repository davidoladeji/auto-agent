---
name: auto-agent-factory
description: Autonomous engineering factory. Grooms the tracker backlog, decides what to build, builds it, verifies it against the CI gate, opens a PR, merges on green, and loops — no human checkpoints. Use when the operator says "run the factory", "work the backlog", "ship the next ticket", or the headless driver invokes it.
---

# Auto-Agent Factory — the autonomous loop

You orchestrate Auto-Agent. **The tracker (Linear) is the source of truth. CI is the only
gate. No human checkpoints.** Pick the work, build it, ship it, repeat.

Read first, every run: `../../CLAUDE-FACTORY.md`, `../../LINEAR-INTEGRATION.md`, `factory.config`
(at the repo root), and the repo's own `CLAUDE.md` if present. Obey §F3 rails without exception.
All project specifics (gate commands, CI check name, branch prefix, tracker names) come from
`factory.config` — never hardcode them.

## 0. Preflight (once per loop start)

1. `git fetch origin <DEFAULT_BRANCH>:<DEFAULT_BRANCH>`; ensure a clean tree on a fresh branch
   off the default branch. Dirty tree → stash/abort.
2. Tracker reachable? (interactive: MCP; headless: `python3 scripts/factory/linear.py
   list-eligible`). If neither works → **halt** (no blind runs, no unrecorded ships).
3. Bootstrap control labels if missing (§F5).
4. Confirm the gate is green on the default branch before starting (so you don't inherit red).

## 1. Pick + claim the next ticket

`list-eligible` returns eligible tickets (excludes `factory-skip`, `factory-blocked`, human
In-Progress-without-`factory-building`, and tickets claimed by **another** instance). Then:

1. **Resume your own first.** If a ticket is `In Progress` + `factory-building` with a latest
   `[factory:claim]` matching your `FACTORY_INSTANCE`, resume it. Another instance's claim is
   off-limits (stale >3h ⇒ reclaim allowed).
2. **Classify:** *Buildable* (Tech Debt / Performance / Bug / small Improvement / single-PR
   Feature → run end-to-end) · *Epic* (large → backlog-groomer decomposes first) · *Thin*
   (under-specified → groomer adds scope).
3. **Rank Buildable** by priority then smallest scope (tight, high-confidence wins first).
4. Pick the top. None buildable but epics/thin exist → run the groomer, re-pick. Truly dry → §6.

**Honor steering + consensus:** read `scripts/factory/STEER.md` + `scripts/factory/state.md`
first. **Claim atomically** (LINEAR §4): `In Progress` + `factory-building` +
`[factory:claim] instance=<FACTORY_INSTANCE> ts=<ISO>`, then re-read; if another instance
claimed earlier, **yield and re-pick**. Proceed only if your claim is earliest.

## 2. The per-ticket chain (dispatch as subagents)

One at a time, each given only the ticket id + the prior sign-off. Each posts its
`[factory:<agent>]` comment + the §F6 sign-off.

```
researcher → planner → builder ⇄ test-verifier → reviewer → release-manager → prod-verifier
```
- builder ⇄ test-verifier until acceptance criteria pass.
- reviewer Critical → back to builder; re-run. **Two strikes** same root cause → `factory-blocked`, stop, move on.
- Risky ticket (auth/billing/migrations/core) or fresh epic child → planner writes a one-paragraph pre-mortem.

## 3. Merge (replaces the human PR gate)

The release-manager merges **only** when the local gate (`factory.config` GATE_* commands)
AND the required GitHub check `CI_CHECK_NAME` are green and the PR is mergeable.
- **Local/self-merge instance:** `gh pr merge --squash --delete-branch`.
- **Cloud routine** (`claude/*` branch — can't self-merge): open the PR and **stop**; the
  `auto-merge` workflow squash-merges it once CI is green.
Then set the ticket `Done`, remove `factory-building`, post the prod-verify surface note.

## 4. Grooming (autonomous PM)

The backlog-groomer decides what's most valuable, decomposes epics into PR-sized
`from-factory` children, adds scope to thin tickets, nudges priorities — announced, never
silent. Then control returns to §1.

## 5. Telemetry

After each merge, post an orchestrator comment (timeline) + append a line to
`scripts/factory/factory.log`, and overwrite `scripts/factory/state.md` with a ≤15-line
handoff (shipped, next candidate, blockers, counts).

## 6. Idle / stop

Backlog dry → log + exit 0 (driver re-wakes). Tracker down → halt, exit non-zero. Gate
un-greenable on the default branch itself (infra) → halt + `factory-blocked`.

## 7. Driver (one-ticket) mode

When invoked by `scripts/factory/run.sh`, do ONE ticket then stop and print exactly one
sentinel as the final line: `FACTORY_SHIPPED <id>` · `FACTORY_GROOMED` ·
`FACTORY_BLOCKED <id>` · `FACTORY_IDLE` · `FACTORY_HALT <reason>`.

## 8. Not this skill

One-off fixes with no ticket (create one first) · weakening CI/branch protection · editing
the repo's `CLAUDE.md` · deleting data · force-pushing.
