# Running Auto-Agent 24/7

The driver is `run.sh` (a headless `claude -p` loop, one ticket per iteration). Pick a host.

## Foreground (watch one ticket)
```bash
FACTORY_MAX_TICKETS=1 scripts/factory/run.sh
```

## Background (this shell)
```bash
nohup scripts/factory/run.sh >> scripts/factory/factory.log 2>&1 &
tail -f scripts/factory/factory.log
```

## Mac — launchd (survives logout/reboot, keeps the Mac awake)
Edit `com.example.auto-agent.plist.example` (set the absolute paths), then:
```bash
cp com.example.auto-agent.plist.example ~/Library/LaunchAgents/com.example.auto-agent.plist
launchctl load -w ~/Library/LaunchAgents/com.example.auto-agent.plist
```

## Linux server — systemd
Edit `auto-agent.service.example` (paths + `User`), then:
```bash
sudo cp auto-agent.service.example /etc/systemd/system/auto-agent.service
sudo systemctl enable --now auto-agent
```

## Serverless — claude.ai cloud routine
Create a routine ("Claude Code on the web") on a cron. Set `LINEAR_API_KEY` (+ a GH token)
as environment variables, allow `api.linear.app` in network access, and prompt it to run the
`auto-agent-factory` skill in driver mode. Cloud routines can't self-merge (they push only to
`claude/*`), so the repo's `auto-merge` workflow merges their PRs on green CI. Set
`FACTORY_INSTANCE=cloud` so it coordinates with any local loop.

## Controls
- **Steer:** edit `STEER.md` (next cycle, no restart).
- **Stop:** `touch scripts/factory/STOP` (graceful) / `launchctl unload …` / `systemctl stop auto-agent`.

## Why unattended is safe
Branch protection (the required CI check, no force-push) is the wall the agent can't bypass;
the local gate catches issues early; the §F3 rails + two-strike stop + per-machine lock + the
tracker audit trail do the rest. `run.sh` uses `--dangerously-skip-permissions` (needed for
unattended); set `FACTORY_NO_YOLO=1` to force prompts.

## Knobs (env or factory.config)
`FACTORY_MODEL` · `FACTORY_IDLE_SEC` (dry-backoff) · `FACTORY_MAX_TICKETS` · `FACTORY_BREAKER_N`
· `FACTORY_INSTANCE` (distinct per host) · `FACTORY_NO_YOLO`.

Runtime files (`factory.log`, `.lock/`, `STOP`, `state.md`) and secrets (`.env.local`) are gitignored.
