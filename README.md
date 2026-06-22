# Auto-Agent

**A drop-in autonomous engineering factory for [Claude Code](https://claude.com/claude-code).**

Point it at your repo and your Linear backlog and it works like an engineer who never
sleeps: it picks the highest-value ticket, researches the code, writes a plan + acceptance
criteria, builds it with tests, self-reviews, opens a PR, waits for CI, **merges on green**,
and moves to the next one — continuously, 24/7, with no human in the loop.

> **The CI gate replaces the human gate.** Auto-Agent never merges code that isn't green.
> Your branch protection is the safety net — it literally cannot ship broken work.

It runs anywhere Claude Code runs: your Mac (launchd), a Linux server (systemd), or
serverless as a [claude.ai cloud routine](#run-it-247). Add it to an existing project, or
use it to start a new one.

---

## What it does each cycle

```
pick the next eligible ticket  (grooms/decomposes epics; respects your priorities + STEER.md)
   → research the codebase      → plan + acceptance criteria (written into the ticket)
   → build with tests           → verify against the criteria
   → adversarial self-review    → open a PR
   → wait for the required CI check → merge (squash) → set the ticket Done
   → loop
```

Every step is logged to the ticket as a `[factory:*]` comment, so the ticket is the audit
trail. Idle when the backlog is dry; resume when there's new work.

## Why it's safe to run unattended

Human checkpoints are replaced by hard gates the agent **cannot** bypass:

1. **Branch protection** — your required CI check must pass; force-push/deletion off. The
   agent cannot merge red code even if it tries.
2. **Local gate** before every PR — runs your lint/typecheck/test (+ optional build).
3. **Safety rails** (`.claude/CLAUDE-FACTORY.md` §F3) — never push to the default branch
   directly, never force-push, never weaken CI, no destructive migrations, two-strike stop,
   single-instance lock per machine.
4. **Linear is the record** — every run is a comment chain on the ticket.

## Requirements

- **Claude Code** (a Claude Pro/Max/Team/Enterprise subscription; the headless loop uses a
  long-lived token from `claude setup-token`).
- **Linear** (v1 tracker) + a personal API key.
- **GitHub** repo with: a CI workflow exposing a required status check, and branch
  protection requiring that check. `gh` CLI authenticated (or a token).
- **Node/your toolchain** for the gate commands (configurable — works for any stack).

---

## Quickstart — add to an existing repo

```bash
# from the root of your project:
curl -fsSL https://raw.githubusercontent.com/davidoladeji/auto-agent/main/install.sh | bash
# (or: git clone the repo and run ./install.sh /path/to/your/project)
```

The installer copies `.claude/` + `scripts/factory/` into your repo, drops in
`factory.config` + the CI/auto-merge workflow templates, and prints the remaining steps:

1. **Fill `factory.config`** — your Linear team/project names, the CI check name, your
   gate commands, branch prefix. (See [`factory.config.example`](factory.config.example).)
2. **Add secrets** to `scripts/factory/.env.local` (gitignored):
   `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) and `LINEAR_API_KEY`.
3. **Set up branch protection** on your default branch requiring your CI check, and
   **enable "Allow auto-merge"** in the repo settings.
4. **Start it** (see below). That's it — it'll start draining your backlog.

## Quickstart — start a new project

```bash
gh repo create my-app --private --clone && cd my-app
curl -fsSL https://raw.githubusercontent.com/davidoladeji/auto-agent/main/install.sh | bash
# scaffold your app + a CI workflow, create a Linear project, fill factory.config, then start.
```

The factory grooms an empty/seed backlog: give it a few Linear tickets (or an epic it can
decompose) and it builds them out.

---

## Run it 24/7

Auto-Agent's brain is the [`auto-agent-factory`](.claude/skills/auto-agent-factory/SKILL.md)
skill; the driver is [`scripts/factory/run.sh`](scripts/factory/run.sh) (a headless
`claude -p` loop, one ticket per iteration). Pick a host:

- **Your Mac** — `scripts/factory/com.example.auto-agent.plist.example` (launchd, KeepAlive,
  caffeinated so the Mac stays awake while it runs).
- **A Linux server** — `scripts/factory/auto-agent.service.example` (systemd).
- **Serverless** — a **claude.ai cloud routine** ("Claude Code on the web"): 16 GB RAM, free
  compute, cron-scheduled. Cloud routines can't self-merge (push is restricted to `claude/*`
  branches), so the included [`auto-merge.example.yml`](.github/workflows/auto-merge.example.yml)
  workflow merges their PRs on green CI.

You can run **several instances at once** (e.g. Mac + cloud) — they coordinate through
Linear (each *claims* a ticket before working it), so they never collide. One loop per
machine; many machines welcome.

**Controls:** edit `scripts/factory/STEER.md` to steer it live (focus/skip/priorities,
picked up next cycle, no restart). `touch scripts/factory/STOP` to stop gracefully.

---

## How it's built

| Piece | What |
|---|---|
| `.claude/CLAUDE-FACTORY.md` | Operating contract + the safety rails |
| `.claude/LINEAR-INTEGRATION.md` | Tracker contract (resolves your team/project by name) |
| `.claude/skills/auto-agent-factory/` | The orchestrator loop |
| `.claude/skills/build-with-tests/` | The build standard every builder follows |
| `.claude/agents/0{1..8}-*.md` | researcher · planner · builder · test-verifier · reviewer · release-manager · backlog-groomer · prod-verifier |
| `scripts/factory/run.sh` | 24/7 headless driver (lock, circuit breaker, rate-limit backoff, steering, consensus memory) |
| `scripts/factory/linear.py` | Linear access for headless runs (no MCP needed) |
| `factory.config` | Your project specifics (the only file you edit) |

Design influences: the OgenticAI software factory and
[Auto-Company](https://github.com/MaxMiksa/Auto-Company) (consensus memory, file-based
steering, resilience) — extended here with CI-gated auto-merge and browser prod-verification.

## Limitations / extension points (v1)

- **Tracker = Linear.** The tracker is isolated behind `linear.py` + `LINEAR-INTEGRATION.md`;
  a GitHub-Issues/Jira adapter is the natural next contribution.
- **Prod-verification** (the prod-verifier agent using Claude in Chrome) is interactive-only
  — headless runs degrade to a "manual-verify" note. Verify on prod yourself, or run that
  agent from an interactive session.
- It uses **your Claude account's quota** — multiple instances don't add throughput, they
  add coverage; it backs off on rate limits.

## Contributing

Issues and PRs welcome — especially tracker adapters, more language gate presets, and a
headless prod-verify path. MIT licensed.

## License

[MIT](LICENSE) © David Oladeji
