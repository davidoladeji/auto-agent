#!/usr/bin/env python3
"""Slack access for the HEADLESS factory (no MCP). Stdlib only.

Powers the optional `slack-assistant` skill. Posts AS YOU via a Slack USER token
(xoxp-), so every message appears under your own name — which is exactly why nothing
is ever sent without your explicit approval (the skill drafts, you approve; see
.claude/skills/slack-assistant/SKILL.md). This module only exposes primitives; the
skill orchestrates the always-ask flow.

Config via env (set in factory.config / .env.local, exported by slack-run.sh):
  SLACK_USER_TOKEN   (required; xoxp- USER token — keep in .env.local, never commit)
  SLACK_REVIEW_DM    (required; channel/DM id where drafts go for your approval)
  SLACK_CHANNELS     (optional; comma-separated channel ids to watch for @-mentions
                      of you; blank = watch DMs only)
  SLACK_SELF_ID      (optional; your Slack user id — auto-resolved via auth.test if unset)

Usage:
  slack.py whoami                                   # auth.test → your user/team
  slack.py poll                                     # new msgs that @-mention you → JSON
  slack.py approvals                                # new replies in your review DM → JSON
  slack.py review --text "…"                        # send a DRAFT to your review DM
  slack.py post --channel C123 --text "…" [--thread 169...]   # send AS YOU (consequential)

The kill switch lives outside this module: slack-run.sh stops polling the moment
`scripts/factory/SLACK_OFF` exists (or the global `STOP`). This module never loops.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

API = "https://slack.com/api/"
FDIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(FDIR, ".slack-state.json")


def token() -> str:
    t = os.environ.get("SLACK_USER_TOKEN", "").strip()
    if not t:
        sys.exit("SLACK_USER_TOKEN not set (put your xoxp- user token in scripts/factory/.env.local)")
    return t


def api(method: str, payload: dict | None = None) -> dict:
    """POST to the Slack Web API. Returns parsed JSON; exits on transport/ok=false."""
    body = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        API + method,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + token(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
    except urllib.error.URLError as e:
        sys.exit(f"Slack API transport error on {method}: {e}")
    if not out.get("ok"):
        # rate-limited or scope/token problem — surface it, don't guess.
        sys.exit(f"Slack API error on {method}: {out.get('error', 'unknown')}")
    return out


def self_id() -> str:
    sid = os.environ.get("SLACK_SELF_ID", "").strip()
    if sid:
        return sid
    return api("auth.test")["user_id"]


def _state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(s: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.replace(tmp, STATE_PATH)


def _watch_channels() -> list[str]:
    raw = os.environ.get("SLACK_CHANNELS", "").strip()
    return [c.strip() for c in raw.split(",") if c.strip()]


def _history(channel: str, oldest: str | None) -> list[dict]:
    payload = {"channel": channel, "limit": 50}
    if oldest:
        payload["oldest"] = oldest
        payload["inclusive"] = False
    return api("conversations.history", payload).get("messages", [])


def cmd_whoami(_args) -> None:
    who = api("auth.test")
    print(json.dumps({"user": who.get("user"), "user_id": who.get("user_id"), "team": who.get("team")}, indent=2))


def cmd_poll(_args) -> None:
    """Emit (as JSON) messages that @-mention you, across your watched channels, since
    the last poll. Author == you is skipped (you don't reply to yourself). Updates the
    per-channel cursor so each message surfaces once."""
    me = self_id()
    mention = f"<@{me}>"
    state = _state()
    cursors = state.setdefault("channels", {})
    found: list[dict] = []
    for ch in _watch_channels():
        last = cursors.get(ch)
        msgs = _history(ch, last)
        # conversations.history returns newest-first; walk oldest-first for stable cursoring.
        for m in sorted(msgs, key=lambda x: float(x.get("ts", "0"))):
            ts = m.get("ts")
            if ts:
                cursors[ch] = ts  # advance cursor past everything we've now seen
            if m.get("user") == me:
                continue
            if mention in (m.get("text") or ""):
                found.append({
                    "channel": ch,
                    "ts": ts,
                    "thread_ts": m.get("thread_ts") or ts,
                    "user": m.get("user"),
                    "text": m.get("text"),
                })
    _save_state(state)
    print(json.dumps(found, indent=2))


def cmd_approvals(_args) -> None:
    """Emit (as JSON) new messages YOU posted in the review DM since the last check —
    these carry your approve/edit/discard decisions back to the skill."""
    dm = os.environ.get("SLACK_REVIEW_DM", "").strip()
    if not dm:
        sys.exit("SLACK_REVIEW_DM not set")
    me = self_id()
    state = _state()
    last = state.get("review_cursor")
    msgs = _history(dm, last)
    out: list[dict] = []
    for m in sorted(msgs, key=lambda x: float(x.get("ts", "0"))):
        ts = m.get("ts")
        if ts:
            state["review_cursor"] = ts
        if m.get("user") == me:
            out.append({"ts": ts, "text": m.get("text")})
    _save_state(state)
    print(json.dumps(out, indent=2))


def cmd_review(args) -> None:
    """Send a DRAFT to your review DM. This is NOT a team-facing send."""
    dm = os.environ.get("SLACK_REVIEW_DM", "").strip()
    if not dm:
        sys.exit("SLACK_REVIEW_DM not set")
    res = api("chat.postMessage", {"channel": dm, "text": args.text})
    print(json.dumps({"ok": True, "ts": res.get("ts"), "channel": res.get("channel")}))


def cmd_post(args) -> None:
    """Send a message AS YOU to a channel/thread. Consequential — the skill only calls
    this AFTER you approve the draft in the review DM."""
    payload = {"channel": args.channel, "text": args.text}
    if args.thread:
        payload["thread_ts"] = args.thread
    res = api("chat.postMessage", payload)
    print(json.dumps({"ok": True, "ts": res.get("ts"), "channel": res.get("channel")}))


def main() -> None:
    p = argparse.ArgumentParser(description="Slack access for the headless factory (self identity, human-approved sends).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami").set_defaults(fn=cmd_whoami)
    sub.add_parser("poll").set_defaults(fn=cmd_poll)
    sub.add_parser("approvals").set_defaults(fn=cmd_approvals)
    pr = sub.add_parser("review"); pr.add_argument("--text", required=True); pr.set_defaults(fn=cmd_review)
    pp = sub.add_parser("post")
    pp.add_argument("--channel", required=True)
    pp.add_argument("--text", required=True)
    pp.add_argument("--thread", default=None)
    pp.set_defaults(fn=cmd_post)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
