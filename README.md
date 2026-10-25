# API-Mend implementation

Repository: https://github.com/divuakaza22077/api_mendy

## Architecture

**Python Brain, Rust Muscles.**

- Python owns FastAPI orchestration, Pydantic contracts, GitHub REST, deterministic scenario flow, and future LLM calls.
- Rust-backed `ast-grep-py` owns static call-site matching.
- `ruff` validates Python target files through subprocess.
- `oxlint` validates JavaScript/TypeScript target files through subprocess when installed.
- The Python Brain can compare two OpenAPI JSON documents through `/drift` or `python -m backend.drift` and normalize removed endpoints, methods, and request fields into `BreakingChange` records.
- No custom pure-Python AST parser is used.

## Install backend tools

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements-dev.txt
npm install
```

Python 3.12 is the intended production runtime. The current workstation must be checked before deployment.

Set `GITHUB_TOKEN` in the shell or a local `.env` file copied from `.env.example`. Never commit the token. The implementation uses it only from the Python backend for `/github/access`, repository scanning, and explicit non-dry-run shipping.

Real GitHub writes are **disabled by default**. To enable a controlled demo write path, set both `ALLOW_GITHUB_WRITES=true` and `ALLOWED_REPOSITORIES=owner/repo` on the backend. The server re-scans the allowlisted repository and requires the target files to match the scenario baseline before creating a PR.

For any deployment that exposes GitHub-backed endpoints, set `API_MEND_API_KEY` and send it as `X-API-Key` (or `Authorization: Bearer …`). The key protects `/github/access`, `/scan`, and real `/ship` requests. `ALLOW_GITHUB_WRITES=true` is rejected unless the API key is configured. Keep public judging deployments in dry-run mode.

## Run

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```powershell
npm run dev
```

Open `http://localhost:5173/?demo=offline` for the deterministic judge-safe demo, or omit `demo=offline` to use the FastAPI backend. A production frontend must be built with `VITE_API_BASE`; otherwise it displays an unconfigured API status instead of attempting the viewer's localhost.

## Verify

```powershell
pytest -q
ruff check backend tests
```

GitHub Actions runs the same Python checks plus `npm ci`, Oxlint verification, a Docker build, and `/livez`/`/readyz`/`/plan` container smoke tests on every push and pull request.

OpenAPI drift check:

```powershell
python -m backend.drift .\specs\vendor-before.json .\specs\vendor-after.json --vendor Stripe --evidence-url https://example.com/changelog
```

The `/drift` endpoint accepts two bounded JSON OpenAPI documents and returns deterministic breaking-change records. It does not fetch arbitrary URLs; fetch and authentication should remain in a controlled vendor-source job or deployment layer.

## Deploy

- Frontend: Vercel uses `vercel.json`, `npm run build`, and `frontend/dist`.
- Backend: build the root `Dockerfile`, expose port `7860`, and inject `GITHUB_TOKEN` only as a backend secret.
- Keep the frontend in `?demo=offline` mode for a network-safe judging fallback.
- Set `VITE_API_BASE` in the frontend deployment; deployed frontend builds must not rely on the viewer's `localhost`.
- Set `ALLOWED_ORIGINS` to the exact deployed frontend origin(s); broad wildcard or regex origins are intentionally not enabled.
- Set `API_MEND_API_KEY` before exposing live GitHub scan/access endpoints, and never enable real writes on an unauthenticated public deployment.
- GitHub-backed endpoints enforce bounded request size, per-client in-memory rate limits, scan file/byte budgets, and a 45-second scan deadline. Use an external rate limiter for multi-instance deployments.
- Probe `/livez` for process liveness and `/readyz` for deployment readiness. Demo containers should set `DEMO_MODE=true`; live GitHub mode requires `GITHUB_TOKEN`, and write mode additionally requires `API_MEND_API_KEY` plus a repository allowlist.
