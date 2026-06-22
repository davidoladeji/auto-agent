#!/usr/bin/env bash
# Auto-Agent — 24/7 headless driver. Runs Claude Code (`claude -p`) in a loop, shipping ONE
# eligible ticket per iteration via the auto-agent-factory skill, then repeating until the
# backlog is dry. Per-ticket invocation keeps each run's context bounded + crash-resumable.
#
#   Start:   nohup scripts/factory/run.sh >> scripts/factory/factory.log 2>&1 &
#   Watch:   tail -f scripts/factory/factory.log
#   Steer:   edit scripts/factory/STEER.md   (picked up next cycle)
#   Stop:    touch scripts/factory/STOP       (graceful, after current ticket)
#
# Config: factory.config (repo root) + scripts/factory/.env.local (secrets). The safety
# rails + your branch protection are what make unattended operation safe.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$REPO_ROOT"
FDIR="$REPO_ROOT/scripts/factory"
LOCK="$FDIR/.lock"; STOP="$FDIR/STOP"; STEER="$FDIR/STEER.md"; STATE="$FDIR/state.md"

# Load config + secrets, exporting all so `claude -p`, linear.py, and subshells inherit them.
set -a
[ -f "$REPO_ROOT/factory.config" ] && . "$REPO_ROOT/factory.config"
[ -f "$FDIR/.env.local" ] && . "$FDIR/.env.local"
set +a

IDLE_SEC="${FACTORY_IDLE_SEC:-900}"
MAX="${FACTORY_MAX_TICKETS:-0}"
BREAKER_N="${FACTORY_BREAKER_N:-3}"
export FACTORY_INSTANCE="${FACTORY_INSTANCE:-$(hostname -s 2>/dev/null || echo local)}"
export DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

log() { printf '%s | %s\n' "$(date -u +%FT%TZ)" "$*"; }

# PID-aware single-instance lock: self-heals an orphaned lock (dead/missing holder PID)
# instead of stranding forever when a loop dies via SIGKILL/crash/reboot (trap skipped).
acquire_lock() {
  if mkdir "$LOCK" 2>/dev/null; then echo $$ > "$LOCK/pid"; return 0; fi
  local pid; pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then return 1; fi  # live holder
  log "reclaiming stale lock (holder pid=${pid:-none} not alive)"; rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null && { echo $$ > "$LOCK/pid"; return 0; } || return 1
}
if ! acquire_lock; then log "another live loop holds the lock — exiting."; exit 0; fi
trap 'rm -rf "$LOCK" 2>/dev/null || true' EXIT INT TERM
command -v claude >/dev/null || { log "FATAL: claude not on PATH"; exit 1; }
command -v gh    >/dev/null || { log "FATAL: gh not on PATH";     exit 1; }
[ -f "$STATE" ] || printf '# Auto-Agent consensus state\n\n(no cycles yet)\n' > "$STATE"

YOLO="--dangerously-skip-permissions"; [ "${FACTORY_NO_YOLO:-0}" = "1" ] && YOLO=""
MODEL_ARG=""; [ -n "${FACTORY_MODEL:-}" ] && MODEL_ARG="--model $FACTORY_MODEL"

build_prompt() {
  local steer="" state=""
  [ -f "$STEER" ] && steer="$(cat "$STEER")"
  [ -f "$STATE" ] && state="$(cat "$STATE")"
  cat <<EOF
Invoke the auto-agent-factory skill in DRIVER (one-ticket) mode.

Your FACTORY_INSTANCE is "$FACTORY_INSTANCE". Other instances may run concurrently — follow
the skill's §1 claim protocol (claim with a [factory:claim] instance=$FACTORY_INSTANCE
comment, verify you won, never work another instance's claimed ticket).

Read .claude/CLAUDE-FACTORY.md, .claude/LINEAR-INTEGRATION.md, factory.config, and the repo's
own CLAUDE.md (if present) first; obey every §F3 safety rail.

HEADLESS: there is no Linear/Chrome MCP here. Use \`python3 scripts/factory/linear.py\` for
every tracker read/write (list-eligible/get/state/comment/label/subissue). The local gate is:
  ${GATE_LINT:+$GATE_LINT && }${GATE_TYPECHECK:+$GATE_TYPECHECK && }${GATE_TEST:-true}
and the required GitHub check is "${CI_CHECK_NAME:-CI}". Branch prefix: ${BRANCH_PREFIX:-auto-agent}.

=== OPERATOR STEERING (scripts/factory/STEER.md) ===
$steer

=== CONSENSUS STATE (scripts/factory/state.md) ===
$state

TASK: take exactly ONE eligible ticket end-to-end (research → plan → build → test → review →
open PR → wait for the required CI check → squash-merge to $DEFAULT_BRANCH → set Done), then
overwrite scripts/factory/state.md with a ≤15-line handoff. Merge ONLY when local gate + the
GitHub check are green. Never push to $DEFAULT_BRANCH directly, never force-push.

End with EXACTLY ONE final line:
  FACTORY_SHIPPED <id> | FACTORY_GROOMED | FACTORY_BLOCKED <id> | FACTORY_IDLE | FACTORY_HALT <reason>
EOF
}

shipped=0; breaker=0
log "=== Auto-Agent driver up (instance=$FACTORY_INSTANCE, model=${FACTORY_MODEL:-default}, breaker_n=$BREAKER_N) ==="
while true; do
  [ -f "$STOP" ] && { log "STOP present — shutting down."; rm -f "$STOP"; break; }
  [ "$MAX" -gt 0 ] && [ "$shipped" -ge "$MAX" ] && { log "reached FACTORY_MAX_TICKETS=$MAX."; break; }
  log "--- iteration (breaker $breaker/$BREAKER_N) ---"
  out="$(claude -p "$(build_prompt)" $YOLO $MODEL_ARG 2>&1)"; rc=$?
  printf '%s\n' "$out"
  sentinel="$(printf '%s\n' "$out" | grep -Eo 'FACTORY_(SHIPPED|GROOMED|BLOCKED|IDLE|HALT).*' | tail -n1)"
  if printf '%s' "$out" | grep -qiE 'rate limit|429|usage limit|quota|overloaded'; then
    log "rate/usage limit — sleeping 1h."; sleep 3600; continue
  fi
  if [ $rc -ne 0 ] && [ -z "$sentinel" ]; then breaker=$((breaker+1)); log "rc=$rc no sentinel (breaker $breaker/$BREAKER_N)."
  else case "$sentinel" in
      FACTORY_SHIPPED*) shipped=$((shipped+1)); breaker=0; log "shipped #$shipped: ${sentinel#FACTORY_SHIPPED }"; continue ;;
      FACTORY_GROOMED*) breaker=0; log "groomed — re-picking."; continue ;;
      FACTORY_IDLE*)    breaker=0; log "backlog dry — idling ${IDLE_SEC}s."; sleep "$IDLE_SEC"; continue ;;
      FACTORY_BLOCKED*) breaker=$((breaker+1)); log "blocked: ${sentinel#FACTORY_BLOCKED }." ;;
      FACTORY_HALT*)    breaker=$((breaker+1)); log "HALT: ${sentinel#FACTORY_HALT }." ;;
      *)                breaker=$((breaker+1)); log "no sentinel parsed." ;;
    esac
  fi
  if [ "$breaker" -ge "$BREAKER_N" ]; then log "circuit breaker — backing off 1h."; sleep 3600; breaker=0; else sleep "$IDLE_SEC"; fi
done
log "=== driver down (shipped $shipped) ==="
