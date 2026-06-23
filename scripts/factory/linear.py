#!/usr/bin/env python3
"""Linear access for the HEADLESS factory (no MCP). Stdlib only.

Resolves team / project / state / label by NAME at runtime (nothing hardcoded), so it
works for any Linear workspace. Config via env (set in factory.config, exported by run.sh):
  LINEAR_API_KEY   (required; a Linear personal API key — keep in .env.local)
  LINEAR_TEAM      (required; team NAME)
  LINEAR_PROJECT   (optional; project NAME — scopes list-eligible)

Usage:
  linear.py list-eligible
  linear.py get ABC-123
  linear.py state ABC-123 "In Progress" | "Done"
  linear.py comment ABC-123 "body"            (or: … | linear.py comment ABC-123 --stdin)
  linear.py label ABC-123 add|remove factory-building
  linear.py subissue --parent ABC-123 --title "…" --desc "…" --labels Performance,from-factory
"""
import argparse, json, os, re, ssl, sys, urllib.request

API = "https://api.linear.app/graphql"
SKIP = {"factory-skip", "factory-blocked"}


def key() -> str:
    k = os.environ.get("LINEAR_API_KEY", "").strip()
    if not k:
        sys.exit("LINEAR_API_KEY not set (put it in scripts/factory/.env.local)")
    return k


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def gql(query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body,
        headers={"Content-Type": "application/json", "Authorization": key()})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_ctx()))
    with opener.open(req, timeout=30) as r:
        out = json.loads(r.read())
    if out.get("errors"):
        sys.exit("Linear API error: " + json.dumps(out["errors"]))
    return out["data"]


_cache: dict = {}

def team() -> dict:
    if "team" not in _cache:
        name = os.environ.get("LINEAR_TEAM", "").strip()
        if not name:
            sys.exit("LINEAR_TEAM not set (team name)")
        d = gql("query($n:String!){teams(filter:{name:{eq:$n}}){nodes{id key name}}}", {"n": name})
        nodes = d["teams"]["nodes"]
        if not nodes:
            sys.exit(f"Linear team '{name}' not found")
        _cache["team"] = nodes[0]
    return _cache["team"]


def project_id() -> str | None:
    name = os.environ.get("LINEAR_PROJECT", "").strip()
    if not name:
        return None
    if "project" not in _cache:
        d = gql("query($n:String!){projects(filter:{name:{eq:$n}}){nodes{id name}}}", {"n": name})
        nodes = d["projects"]["nodes"]
        if not nodes:
            sys.exit(f"Linear project '{name}' not found")
        _cache["project"] = nodes[0]["id"]
    return _cache["project"]


def state_id(name: str) -> str:
    states = _cache.get("states")
    if states is None:
        d = gql("query($t:ID!){workflowStates(filter:{team:{id:{eq:$t}}}){nodes{id name}}}", {"t": team()["id"]})
        states = {s["name"]: s["id"] for s in d["workflowStates"]["nodes"]}
        _cache["states"] = states
    if name not in states:
        sys.exit(f"state '{name}' not found; have: {list(states)}")
    return states[name]


def label_id(name: str) -> str:
    d = gql("query($n:String!){issueLabels(filter:{name:{eq:$n}}){nodes{id}}}", {"n": name})
    nodes = d["issueLabels"]["nodes"]
    if nodes:
        return nodes[0]["id"]
    created = gql("mutation($n:String!,$t:String!){issueLabelCreate(input:{name:$n,teamId:$t}){issueLabel{id}}}",
                  {"n": name, "t": team()["id"]})
    return created["issueLabelCreate"]["issueLabel"]["id"]


def resolve(identifier: str) -> dict:
    m = re.search(r"(\d+)", identifier)
    if not m:
        sys.exit(f"bad issue id: {identifier}")
    d = gql("query($t:ID!,$n:Float!){issues(filter:{team:{id:{eq:$t}},number:{eq:$n}}){nodes{id identifier title}}}",
            {"t": team()["id"], "n": int(m.group(1))})
    nodes = d["issues"]["nodes"]
    if not nodes:
        sys.exit(f"{identifier} not found")
    return nodes[0]


def cmd_list_eligible(_):
    pid = project_id()
    filt = '{team:{id:{eq:$t}},state:{type:{in:["backlog","unstarted","started"]}}'
    filt += ',project:{id:{eq:$p}}}' if pid else "}"
    q = ("query($t:ID!" + (",$p:ID!" if pid else "") + "){issues(filter:" + filt +
         ",first:250){nodes{identifier title priority labels{nodes{name}} state{name}}}}")
    vars = {"t": team()["id"]} | ({"p": pid} if pid else {})
    rows = []
    for n in gql(q, vars)["issues"]["nodes"]:
        names = {l["name"] for l in n["labels"]["nodes"]}
        if names & SKIP:
            continue
        rows.append((n["priority"] or 99, n["identifier"], n["state"]["name"], sorted(names), n["title"]))
    rows.sort(key=lambda r: (r[0], r[1]))
    for pr, ident, st, labels, title in rows:
        print(f"{ident}\tP{pr}\t{st}\t[{','.join(labels)}]\t{title}")


def cmd_get(a):
    iss = resolve(a.id)
    d = gql("query($id:String!){issue(id:$id){identifier title state{name} priority labels{nodes{name}} description comments{nodes{body createdAt user{name}}}}}",
            {"id": iss["id"]})["issue"]
    print(f"{d['identifier']} [{d['state']['name']}] P{d.get('priority')}  {d['title']}")
    print("labels:", ",".join(l["name"] for l in d["labels"]["nodes"]))
    print("\n--- description ---\n" + (d.get("description") or "(none)"))
    print("\n--- comments ---")
    for c in d["comments"]["nodes"]:
        print(f"[{c['createdAt']} {(c.get('user') or {}).get('name','?')}] {c['body'][:500]}")


def cmd_state(a):
    gql("mutation($id:String!,$s:String!){issueUpdate(id:$id,input:{stateId:$s}){success}}",
        {"id": resolve(a.id)["id"], "s": state_id(a.state)})
    print(f"{a.id} -> {a.state}")


def cmd_comment(a):
    body = sys.stdin.read() if a.stdin else a.body
    if not body:
        sys.exit("empty comment")
    gql("mutation($i:String!,$b:String!){commentCreate(input:{issueId:$i,body:$b}){success}}",
        {"i": resolve(a.id)["id"], "b": body})
    print(f"commented on {a.id}")


def cmd_label(a):
    iss = resolve(a.id)
    cur = gql("query($id:String!){issue(id:$id){labels{nodes{id}}}}", {"id": iss["id"]})["issue"]["labels"]["nodes"]
    ids = {l["id"] for l in cur}
    lid = label_id(a.name)
    ids.add(lid) if a.op == "add" else ids.discard(lid)
    gql("mutation($id:String!,$l:[String!]){issueUpdate(id:$id,input:{labelIds:$l}){success}}",
        {"id": iss["id"], "l": list(ids)})
    print(f"{a.id} label {a.op} {a.name}")


def cmd_subissue(a):
    labels = [label_id(x.strip()) for x in (a.labels or "").split(",") if x.strip()]
    inp = {"teamId": team()["id"], "parentId": resolve(a.parent)["id"], "title": a.title,
           "description": a.desc or "", "labelIds": labels, "stateId": state_id("Backlog")}
    pid = project_id()
    if pid:
        inp["projectId"] = pid
    d = gql("mutation($i:IssueCreateInput!){issueCreate(input:$i){issue{identifier url}}}", {"i": inp})["issueCreate"]["issue"]
    print(f"created {d['identifier']}  {d['url']}")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("list-eligible").set_defaults(fn=cmd_list_eligible)
    g = s.add_parser("get"); g.add_argument("id"); g.set_defaults(fn=cmd_get)
    st = s.add_parser("state"); st.add_argument("id"); st.add_argument("state"); st.set_defaults(fn=cmd_state)
    c = s.add_parser("comment"); c.add_argument("id"); c.add_argument("body", nargs="?", default=""); c.add_argument("--stdin", action="store_true"); c.set_defaults(fn=cmd_comment)
    l = s.add_parser("label"); l.add_argument("id"); l.add_argument("op", choices=["add", "remove"]); l.add_argument("name"); l.set_defaults(fn=cmd_label)
    su = s.add_parser("subissue"); su.add_argument("--parent", required=True); su.add_argument("--title", required=True); su.add_argument("--desc", default=""); su.add_argument("--labels", default=""); su.set_defaults(fn=cmd_subissue)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
