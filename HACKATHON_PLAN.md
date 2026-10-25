# API-Mend — Winning Demo Plan

## Decision

Proceed. The project has a credible hackathon-winning shape if we present a **verified migration loop**, not a general-purpose coding agent:

```text
vendor drift → exact call-site blast radius → surgical patch → Rust-backed validation → GitHub PR
```

The demo must prove one complete path in under 60 seconds and be honest about unresolved multi-step migrations.

The initial public repository is live at `divuakaza22077/api_mendy`, with the first CI run passing on October 25, 2026.

## Architecture rule

### Python Brain

- FastAPI endpoints and SSE.
- Pydantic contracts and scenario orchestration.
- GitHub REST tree/blob scanning, Git Data commits, PRs, labels, and Actions.
- LLM calls and deterministic cache fallback.

### Rust Muscles

- `ast-grep-py` for AST/static call-site extraction.
- `ruff` subprocess for Python target validation.
- `oxlint` subprocess for JavaScript/TypeScript target validation.
- No custom pure-Python AST parser.
- No Node-based ESLint dependency on target repositories.

## Scope update

### Build first

1. Stripe Charges → PaymentIntents fixture with a visible stylized-field migration.
2. Real GitHub token access check and zero-clone scan.
3. Call-site graph and blast-radius count.
4. Deterministic patch plan with exact-match gates.
5. Dry-run PR preview, then explicit non-dry-run GitHub ship.
6. Offline cache fallback for every stage.

### Build second

- OpenAI `functions` → `tools` scenario.
- Twilio webhook signature scenario, clearly marked stylized where necessary.
- LLM-generated `PatchPlan` behind a timeout/cache boundary.
- Frontend graph/diff/approval screens.
- Optional Hugging Face inference is deferred; deterministic fixtures and verification remain authoritative.

### Do not build before the first live rehearsal

- GitHub App installation flow.
- Multi-repository orchestration.
- Runtime traffic inference.
- Full user accounts or GitHub App installation flow.
- A claim that every API migration is automatically solvable.

## Acceptance criteria

- `GET /github/access` succeeds without exposing the token.
- `/scan` reads a repository through GitHub REST without cloning it.
- Rust-backed `ast-grep-py` finds Python and TypeScript external API calls.
- `/simulate/stripe-paymentintents` returns changes, impacts, and graph JSON.
- `/plan` applies every cached edit exactly once.
- `/ship` is dry-run by default and requires an explicit repository plus `dry_run=false` for a real PR.
- `ruff` and `oxlint` validate rewritten target files without installing target dependencies.
- Tests pass with no network dependency.
- Offline frontend flow renders graph → blast radius → diff gates → approval.
- Frontend typecheck, production build, and Oxlint pass in CI.
- Public backend deployments remain dry-run-only unless an allowlisted repository and explicit write flag are configured.
- Real writes also require both `API_MEND_API_KEY` and `GITHUB_TOKEN`; health readiness stays false until both are present.
- Docker CI builds the backend image and smoke-tests `/livez`, `/readyz`, and `/plan`.
- `/drift` and `backend.drift` provide a deterministic OpenAPI breaking-change collector for removed endpoints, methods, and request fields.

## Judge positioning

> “Dependabot updates packages. API-Mend updates the code that breaks when the vendor contract changes — then proves the patch before opening the PR.”

The strongest proof is not the LLM. It is the combination of a real GitHub scan, a visible blast radius, deterministic edits, and a PR that carries verification evidence.

## Next milestone

Choose a small target repository, call `/scan`, render its external API call sites, and use that output to drive the Stripe fixture plan.
