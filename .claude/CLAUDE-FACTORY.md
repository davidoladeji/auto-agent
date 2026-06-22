# CLAUDE-FACTORY.md — the Auto-Agent contract

This is the operating contract for **Auto-Agent**: an autonomous engineering agent that
grooms your tracker backlog, decides what to build, builds it, verifies it, and ships it —
continuously, with **no human checkpoints**. The CI gate replaces the human gate.

Everything project-specific lives in **`factory.config`** (see `factory.config.example`).
This file and the agents/skills stay generic and read that config.

---

## §F1 — Where the factory lives

- Agents: `.claude/agents/` (researcher, planner, builder, test-verifier, reviewer, release-manager, backlog-groomer, prod-verifier)
- Orchestrator skill: `.claude/skills/auto-agent-factory/` — the continuous loop
- Build standard: `.claude/skills/build-with-tests/`
- Tracker contract: `.claude/LINEAR-INTEGRATION.md`
- Driver + config: `scripts/factory/run.sh`, `scripts/factory/STEER.md`, `scripts/factory/state.md`, `factory.config`
- Your project rules (stack, conventions): your repo's own `CLAUDE.md`, if present — the factory reads it and obeys it.

## §F2 — Autonomy policy

- **No approval gates.** The planner formalizes scope + acceptance criteria, then builds.
- **No PR gate.** The release-manager opens the PR and, once the required CI check is green,
  merges it (squash) → your deploy. Self-merge for local instances; GitHub-native auto-merge
  for cloud-routine (`claude/*`) PRs.
- **The factory decides what to build** — grooms the backlog, decomposes epics into buildable
  sub-issues, picks the highest-value eligible work — honoring `STEER.md`.
- **Runs continuously** until the eligible backlog is dry, then idles.

**The CI gate is the only gate.** Your protected branch requires the `CI_CHECK_NAME` check
and disallows force-push/deletion. The factory cannot merge broken code. **Do not weaken it.**

## §F3 — Safety rails (non-negotiable)

An agent that would violate one of these **stops and files a `factory-blocked` comment.**

1. **Never push to the default branch directly.** Always branch → PR → CI-green → squash-merge.
2. **Never force-push. Never delete branches/data/history.** `git push --force*` is banned.
3. **Merge only when green:** the local gate (from `factory.config`) AND the required GitHub
   check pass. No exceptions.
4. **Migrations are high-caution.** Never drop a column/table without a backfill. A schema
   change MUST ship with its generated migration file (else it won't reach prod via
   `migrate deploy`-style flows). Validate against CI.
5. **Never log or commit secrets.** `factory.config`/`.env.local` are gitignored — keep them so.
6. **No new runtime dependencies** unless the ticket needs one; note any addition in the PR.
7. **No destructive prod actions.** DB changes go through reviewed migrations, never ad-hoc.
8. **One loop per machine** (lockfile). Multiple hosts coordinate via the tracker claim
   protocol (skill §1) — each instance has a distinct `FACTORY_INSTANCE`.
9. **Two strikes → blocked.** Same root cause fails twice → label `factory-blocked`, comment
   the diagnosis, move on. Never thrash.
10. **Respect the repo's own `CLAUDE.md`** conventions (commit style, code rules) if present.
11. **Prod verification is READ-ONLY** and never enters credentials (uses an existing session).

## §F4 — State machine

Tracker workflow states are configurable (Linear defaults: `Backlog`, `Todo`,
`In Progress`, `Done`). The factory owns the transitions:

```
Backlog / Todo ──(claim: In Progress + factory-building)──► In Progress
   builder → test-verifier → reviewer → release-manager → PR → CI green → squash-merge
                                                                              │
                                                                              ▼
                                                                            Done
   prod-verifier (read-only) → PASS stays Done · FAIL → reopen + factory-blocked
```

## §F5 — Control labels (auto-created on first run)

| Label | Meaning |
|---|---|
| `factory-building` | A run is actively on this ticket (carries the claim) |
| `factory-blocked` | Stuck; needs a human. Never auto-picked. |
| `factory-skip` | Human-owned; never auto-picked. |
| `from-factory` | A sub-issue the factory created |

## §F6 — Sign-off block (every agent ends with this)

```
SUMMARY
- Ticket: <ID>
- Did: <one line>
- Files: +added / ~edited
- Gate: <which checks passed>
- Next: <next agent, or "blocked: <reason>">
```

## §F7 — Operating mechanisms (adapted from Auto-Company)

- **Consensus memory** (`scripts/factory/state.md`): read before each cycle, overwritten
  after with a ≤15-line handoff. Survives restarts.
- **File-based steering** (`scripts/factory/STEER.md`): operator edits it live; injected each
  cycle. Steers *what*/*priority*, never the rails or the gate.
- **Resilience** (`run.sh`): single-instance lock, circuit breaker, rate-limit auto-sleep.
- **Pre-mortem** before risky/large work; **every cycle ships or shapes** — never just talks.

## §F8 — What the factory will NOT do

Move to Done before merge · delete/edit human tracker comments · change a ticket's
team/project · weaken branch protection/CI · edit your repo's `CLAUDE.md`.

— end of contract —
