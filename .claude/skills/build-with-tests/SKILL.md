---
name: build-with-tests
description: The Auto-Agent build standard. Every builder follows it when writing or editing source. Short on purpose.
---

# Build with tests — the Auto-Agent standard

## 1. Read before you write
Start from the brief + researcher findings + the repo's own `CLAUDE.md` (stack, conventions).
If similar code exists, read it and copy the pattern — matching what's there is the fastest
path to consistency.

## 2. Tests live next to code
Every public function: one happy-path test + one failure-path test. A refactor/perf change
still needs a **regression test** that pins the behavior you must not change. The headless
loop can't always run a UI — prove logic with unit/integration tests; that's how the gate
verifies behavior.

## 3. Defend the boundaries
Validate inputs; derive the user/tenant from the session, never the request body. Treat
persisted/external data as untrusted at the load boundary. Never expose raw exceptions.

## 4. Migrations are special
A schema change MUST ship with its generated migration file (e.g. `prisma migrate dev`,
`alembic revision`) committed in the same PR — otherwise it won't reach prod via
`migrate deploy`-style deploys. No destructive migration without a backfill.

## 5. Smallest correct diff
Touch only what the ticket needs. Reuse before adding. No new dependency unless the ticket
needs it (note it in the PR). Follow the repo's icon/style/lint conventions.

## 6. Gate before you hand off
Run the project's gate (the `GATE_*` commands from `factory.config`) and don't pass the
ticket on until it's green. End with the §F6 sign-off stating the gate result.
