#!/usr/bin/env bash
# Auto-Agent — Slack assistant listener (OPTIONAL, off by default).
#
# Polls Slack for messages that @-mention you and hands each to the `slack-assistant`
# skill, which DRAFTS a reply and routes it to your review DM. Nothing is sent to anyone
# until you approve it there — this loop never posts to a team channel itself.
#
#   Start:   bash scripts/factory/slack-run.sh        (or via launchd/systemd, see *.example)
#   Pause:   touch scripts/factory/SLACK_OFF          (stops the next tick; engineering loop unaffected)
#   Resume:  rm scripts/factory/SLACK_OFF
#   Hard stop: touch scripts/factory/STOP             (stops BOTH this and the engineering loop)
#
# Separate process from run.sh on purpose: killing Slack never touches the factory.
# Config: factory.config (repo root) + scripts/factory/.env.local (secrets).
set -euo pipefail

FDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$FDIR/../.." && pwd)"
OFF="$FDIR/SLACK_OFF"; STOP="$FDIR/STOP"
LOG="$FDIR/slack.log"

set -a
[ -f "$REPO_ROOT/factory.config" ] && . "$REPO_ROOT/factory.config"
[ -f "$FDIR/.env.local" ] && . "$FDIR/.env.local"
set +a

POLL_SEC="${SLACK_POLL_SEC:-45}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG" >&2; }

if [ "${SLACK_ENABLED:-false}" != "true" ]; then
  log "SLACK_ENABLED != true — Slack assistant disabled. Set SLACK_ENABLED=true in factory.config to use it."
  exit 0
fi

log "Slack assistant listener up (poll ${POLL_SEC}s). Pause: touch $OFF"

while true; do
  [ -f "$STOP" ] && { log "STOP present — shutting down."; break; }
  if [ -f "$OFF" ]; then log "SLACK_OFF present — paused."; sleep "$POLL_SEC"; continue; fi

  # New mentions since last tick (JSON array). slack.py advances its own cursor.
  mentions="$(python3 "$FDIR/slack.py" poll 2>>"$LOG" || echo '[]')"
  count="$(printf '%s' "$mentions" | python3 -c 'import sys,json; print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"

  if [ "$count" != "0" ]; then
    log "$count new mention(s) — handing to slack-assistant for drafting."
    # Headless Claude Code runs the skill. The skill drafts + routes to the review DM;
    # it sends to a team thread ONLY after you approve in the DM. It re-checks the kill
    # switch itself, so a race on SLACK_OFF can't slip a send through.
    claude -p "Run the slack-assistant skill. New mentions to process (JSON): $mentions
Follow SKILL.md exactly: draft in my voice, route to my review DM, and send ONLY what I explicitly approve. Honor SLACK_OFF/STOP." \
      >>"$LOG" 2>&1 || log "claude invocation returned non-zero (see log)."
  fi

  sleep "$POLL_SEC"
done
