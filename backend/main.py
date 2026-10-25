from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader

from backend.config import get_settings
from backend.drift import compare_openapi
from backend.github_client import GitHubClient, GitHubConflictError, GitHubError, create_github_http_client
from backend.graph import graph_from_sites
from backend.models import (
    DriftRequest,
    DriftResponse,
    GitHubAccessResponse,
    HealthResponse,
    LivenessResponse,
    PlanRequest,
    PlanResponse,
    ReadinessResponse,
    ScanRequest,
    ScanResponse,
    ScenarioSummary,
    ShipRequest,
    ShipResponse,
    SimulationResponse,
    SseEvent,
)
from backend.muscles.analyzer import analyze_files
from backend.scenarios import (
    apply_plan,
    apply_plan_to_files,
    changes,
    get_scenario,
    graph,
    impacts,
    patch_plan,
    sites,
    summaries,
)
from backend.verification import verify_patch

settings = get_settings()
logger = logging.getLogger("api_mend")

openapi_tags = [
    {"name": "health", "description": "Process and deployment health probes."},
    {"name": "demo", "description": "Deterministic migration scenarios and verification."},
    {"name": "github", "description": "Authenticated GitHub scanning and shipping operations."},
]


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.github_http = create_github_http_client(settings)
    try:
        yield
    finally:
        await application.state.github_http.aclose()


app = FastAPI(
    title="API-Mend",
    version="0.1.0",
    description="Verified vendor API migrations: scan call sites, prove a surgical patch, and ship safely.",
    openapi_tags=openapi_tags,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)

_request_windows: dict[str, deque[float]] = defaultdict(deque)
_rate_limited_paths = {"/github/access", "/scan", "/ship"}
_max_rate_limit_keys = 10_000
api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Server-side API-Mend key required for live GitHub operations.",
)
ApiKey = Annotated[str | None, Security(api_key_header)]


@app.middleware("http")
async def request_limits(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.max_request_bytes:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body is too large"},
            headers={
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
            },
        )
    if request.method != "OPTIONS" and request.url.path in _rate_limited_paths:
        client_host = request.client.host if request.client else "unknown"
        key = f"{client_host}:{request.url.path}"
        now = time.monotonic()
        for stale_key, stale_window in list(_request_windows.items()):
            while stale_window and now - stale_window[0] >= 60:
                stale_window.popleft()
            if not stale_window:
                del _request_windows[stale_key]
        if len(_request_windows) >= _max_rate_limit_keys and key not in _request_windows:
            oldest_key = min(_request_windows, key=lambda item: _request_windows[item][0])
            del _request_windows[oldest_key]
        window = _request_windows.setdefault(key, deque())
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded; retry after one minute"},
                headers={
                    "Retry-After": "60",
                    "X-Request-ID": request_id,
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                },
            )
        window.append(now)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    logger.info(
        "request_complete method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request_id,
    )
    return response


def _readiness_payload() -> dict[str, object]:
    checks = {
        "github_token": bool(settings.github_token),
        "api_key": bool(settings.api_key),
        "write_allowlist": bool(settings.repository_allowlist),
    }
    if settings.demo_mode:
        ready = True
        mode = "demo"
    else:
        ready = checks["github_token"] and (
            not settings.allow_github_writes
            or (checks["api_key"] and checks["write_allowlist"])
        )
        mode = "live"
    return {"ok": ready, "ready": ready, "mode": mode, "checks": checks}


@app.get("/livez", response_model=LivenessResponse, tags=["health"])
async def livez() -> dict[str, object]:
    return {"ok": True, "service": "api-mend"}


@app.get("/readyz", response_model=ReadinessResponse, tags=["health"])
async def readyz() -> dict[str, object]:
    payload = _readiness_payload()
    if not payload["ready"]:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> dict[str, object]:
    readiness = _readiness_payload()
    return {
        "ok": True,
        "service": "api-mend",
        "architecture": "Python Brain, Rust Muscles",
        "github_configured": bool(settings.github_token),
        "github_writes_enabled": settings.allow_github_writes,
        "api_key_configured": bool(settings.api_key),
        "production_writes_ready": bool(settings.allow_github_writes and settings.api_key and settings.github_token),
        "demo_mode": settings.demo_mode,
        "ready": bool(readiness["ready"]),
    }


@app.get("/github/access", response_model=GitHubAccessResponse, tags=["github"])
async def github_access(request: Request, api_key: ApiKey) -> dict[str, object]:
    _authorize(request, api_key)
    try:
        async with GitHubClient(settings, client=_shared_github_client(request)) as github:
            return await github.access()
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="GitHub access request timed out") from exc


@app.get("/scenarios", response_model=list[ScenarioSummary], tags=["demo"])
async def list_scenarios() -> list[dict[str, object]]:
    return [item.model_dump() for item in summaries()]


@app.post("/scan", response_model=ScanResponse, tags=["github"])
async def scan(request: ScanRequest, http_request: Request, api_key: ApiKey) -> dict[str, object]:
    _authorize(http_request, api_key)
    try:
        async with GitHubClient(settings, client=_shared_github_client(http_request)) as github:
            result = await asyncio.wait_for(
                github.scan_repository(request.owner, request.repo, request.branch), timeout=45
            )
        call_sites = analyze_files(result["files"])
        dependency_graph = graph_from_sites(
            request.owner,
            request.repo,
            result["head_sha"],
            call_sites,
            result["scanned_files"],
        )
        return {
            "branch": result["branch"],
            "head_sha": result["head_sha"],
            "scanned_files": result["scanned_files"],
            "sites": [site.model_dump() for site in call_sites],
            "graph": dependency_graph.model_dump(),
            "architecture": "Rust-backed ast-grep-py",
        }
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="GitHub scan timed out") from exc


@app.post("/simulate/{scenario_id}", response_model=SimulationResponse, tags=["demo"])
async def simulate(
    scenario_id: Annotated[str, Path(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")],
) -> dict[str, object]:
    try:
        get_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown scenario") from exc
    return {
        "scenario": scenario_id,
        "changes": [item.model_dump() for item in changes(scenario_id)],
        "sites": [item.model_dump() for item in sites(scenario_id)],
        "impacts": [item.model_dump() for item in impacts(scenario_id)],
        "graph": graph(scenario_id).model_dump(),
    }


@app.post("/drift", response_model=DriftResponse, tags=["demo"])
async def drift(request: DriftRequest) -> dict[str, object]:
    return {
        "vendor": request.vendor,
        "changes": [
            change.model_dump()
            for change in compare_openapi(request.before, request.after, request.vendor, request.evidence_url)
        ],
    }


@app.post("/plan", response_model=PlanResponse, tags=["demo"])
async def plan(request: PlanRequest) -> dict[str, object]:
    try:
        scenario = get_scenario(request.scenario_id)
        patched = apply_plan(request.scenario_id)
        diffs = [
            {"path": path, "before": before, "after": patched[path]}
            for path, before in scenario["before"].items()
            if before != patched[path]
        ]
        report = verify_patch(
            scenario["before"],
            patched,
            patch_plan(request.scenario_id),
            _old_residue(request.scenario_id),
            _contract_residue(request.scenario_id),
        )
        return {
            "scenario": request.scenario_id,
            "plan": patch_plan(request.scenario_id).model_dump(),
            "diffs": diffs,
            "gates": report.model_dump(),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown scenario") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/ship", response_model=ShipResponse, tags=["github", "demo"])
async def ship(request: ShipRequest, http_request: Request, api_key: ApiKey) -> dict[str, object]:
    try:
        scenario = get_scenario(request.scenario_id)
        fixture_patched = apply_plan(request.scenario_id)
        if request.dry_run:
            report = verify_patch(
                scenario["before"],
                fixture_patched,
                patch_plan(request.scenario_id),
                _old_residue(request.scenario_id),
                _contract_residue(request.scenario_id),
            )
            return {
                "dry_run": True,
                "approved_by": request.approved_by,
                "scenario": request.scenario_id,
                "files": sorted(fixture_patched),
                "verification": report.model_dump(),
            }
        if not request.owner or not request.repo:
            raise HTTPException(status_code=422, detail="owner and repo are required when dry_run=false")
        if not settings.can_write_repository(request.owner, request.repo):
            raise HTTPException(
                status_code=403,
                detail="Real GitHub writes are disabled or the repository is not on the server allowlist",
            )
        _authorize(http_request, api_key, write=True)
        async with GitHubClient(settings, client=_shared_github_client(http_request)) as github:
            scanned = await asyncio.wait_for(
                github.scan_repository(request.owner, request.repo, request.base), timeout=45
            )
            expected_paths = set(scenario["before"])
            target_files = {path: scanned["files"].get(path) for path in expected_paths}
            if any(target_files[path] is None for path in expected_paths):
                raise HTTPException(status_code=409, detail="Target repository does not contain the scenario files")
            target_files = {path: value for path, value in target_files.items() if value is not None}
            if target_files != scenario["before"]:
                raise HTTPException(
                    status_code=409,
                    detail="Target files changed or do not match the scanned scenario baseline",
                )
            patched = apply_plan_to_files(request.scenario_id, target_files)
            report = verify_patch(
                target_files,
                patched,
                patch_plan(request.scenario_id),
                _old_residue(request.scenario_id),
                _contract_residue(request.scenario_id),
            )
            if not report.passed:
                raise HTTPException(status_code=422, detail="Verification gates did not pass")
            branch = f"apimend/{request.scenario_id}-{scanned['head_sha'][:12]}"
            body = json.dumps(
                {
                    "scenario": scenario["title"],
                    "scan_head_sha": scanned["head_sha"],
                    "verification": report.model_dump(),
                },
                indent=2,
            )
            result = await github.create_pr(
                request.owner,
                request.repo,
                request.base,
                branch,
                patched,
                f"API-Mend: {scenario['title']}",
                body,
                expected_head_sha=scanned["head_sha"],
            )
        return {"dry_run": False, "approved_by": request.approved_by, **result}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown scenario") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="GitHub scan timed out") from exc
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/events/{run_id}", tags=["github"])
async def events(
    run_id: Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")],
    request: Request,
    api_key: ApiKey,
) -> StreamingResponse:
    _authorize(request, api_key)
    async def stream() -> AsyncIterator[str]:
        steps = [
            SseEvent(
                run_id=run_id,
                step="scan",
                progress=0.2,
                message="Scanning repository with Rust-backed ast-grep",
                data={},
            ),
            SseEvent(run_id=run_id, step="drift", progress=0.4, message="Normalizing vendor contract drift", data={}),
            SseEvent(run_id=run_id, step="verify", progress=0.8, message="Running syntax and contract gates", data={}),
            SseEvent(run_id=run_id, step="done", progress=1.0, message="Ready for approval", data={}),
        ]
        for event in steps:
            yield f"data: {event.model_dump_json()}\n\n"
            await asyncio.sleep(0.05)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _old_residue(scenario_id: str) -> list[str]:
    return {
        "stripe-paymentintents": ["stripe.Charge.create", "/v1/charges", "amount_cents"],
        "openai-tools": ["openai.ChatCompletion.create", "functions", "function_call"],
        "twilio-signature-v2": ["X-Twilio-Signature\"", "str(request.url)"],
    }[scenario_id]


def _contract_residue(scenario_id: str) -> list[str]:
    return {
        "stripe-paymentintents": ["amount_cents"],
        "openai-tools": ["functions=", "function_call=", ".get(\"function_call\")"],
        "twilio-signature-v2": ["X-Twilio-Signature\""],
    }[scenario_id]


def _shared_github_client(request: Request) -> Any:
    return getattr(request.app.state, "github_http", None)


def _authorize(request: Request | None, presented: str | None = None, write: bool = False) -> None:
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="API_MEND_API_KEY must be configured for live GitHub operations")
    if request is None:
        raise HTTPException(status_code=401, detail="API key required")
    presented = presented or request.headers.get("x-api-key")
    authorization = request.headers.get("authorization", "")
    if not presented and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    if not presented or not hmac.compare_digest(presented, settings.api_key):
        raise HTTPException(status_code=401, detail="Valid API key required")
    if not settings.github_token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN must be configured for live GitHub operations")
