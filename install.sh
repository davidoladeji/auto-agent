#!/usr/bin/env bash
# Auto-Agent installer — drop the factory into a target repo.
#
#   From your project root:   curl -fsSL https://raw.githubusercontent.com/davidoladeji/auto-agent/main/install.sh | bash
#   Or from a clone:          ./install.sh /path/to/your/project   (defaults to $PWD)
#
# Copies .claude/ + scripts/factory/ + the workflow templates into the target repo,
# scaffolds factory.config, and prints the remaining setup steps. Idempotent: it never
# overwrites an existing factory.config or .env.local.
set -euo pipefail

REPO_URL="https://github.com/davidoladeji/auto-agent.git"
TARGET="${1:-$PWD}"
say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }

# --- locate the source (this clone, or fetch a fresh one) -------------------
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$SELF_DIR" ] && [ -d "$SELF_DIR/.claude/skills/auto-agent-factory" ]; then
  SRC="$SELF_DIR"
else
  SRC="$(mktemp -d)"; say "Fetching auto-agent…"; git clone --depth 1 -q "$REPO_URL" "$SRC"
fi

[ -d "$TARGET/.git" ] || { echo "✗ $TARGET is not a git repo. cd into your project (or 'git init') first."; exit 1; }
say "Installing Auto-Agent into $TARGET"

# --- copy the factory -------------------------------------------------------
mkdir -p "$TARGET/.claude" "$TARGET/scripts" "$TARGET/.github/workflows"
cp -R "$SRC/.claude/agents" "$SRC/.claude/skills" "$TARGET/.claude/"
cp "$SRC/.claude/CLAUDE-FACTORY.md" "$SRC/.claude/LINEAR-INTEGRATION.md" "$TARGET/.claude/"
cp -R "$SRC/scripts/factory" "$TARGET/scripts/"
cp "$SRC/.github/workflows/auto-merge.example.yml" "$TARGET/.github/workflows/auto-agent-auto-merge.yml"

# --- scaffold config (never clobber) ---------------------------------------
cp -n "$SRC/factory.config.example" "$TARGET/factory.config" 2>/dev/null || true
cp -n "$SRC/scripts/factory/.env.local.example" "$TARGET/scripts/factory/.env.local" 2>/dev/null || true

# --- gitignore the runtime + secrets ---------------------------------------
GI="$TARGET/.gitignore"; touch "$GI"
for line in "factory.config" "scripts/factory/.env.local" "scripts/factory/factory.log" \
            "scripts/factory/factory.log.prev" "scripts/factory/.lock/" \
            "scripts/factory/STOP" "scripts/factory/state.md"; do
  grep -qxF "$line" "$GI" || echo "$line" >> "$GI"
done
chmod +x "$TARGET/scripts/factory/run.sh" "$TARGET/scripts/factory/linear.py" 2>/dev/null || true

cat <<EOF

✅ Auto-Agent installed. Next steps:

  1. Edit  factory.config          — Linear team/project names, CI check name, gate commands.
  2. Edit  scripts/factory/.env.local — add CLAUDE_CODE_OAUTH_TOKEN (run: claude setup-token)
                                        and LINEAR_API_KEY. (gitignored)
  3. GitHub: protect your default branch (require your CI check) + enable "Allow auto-merge".
  4. Commit the factory:  git add .claude scripts/factory .github/workflows .gitignore && git commit
  5. Start it:            FACTORY_MAX_TICKETS=1 scripts/factory/run.sh    # one supervised ticket
                          (then 24/7 via launchd/systemd/cloud — see scripts/factory/README.md)

  Docs: https://github.com/davidoladeji/auto-agent
EOF
