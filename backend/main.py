from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.config import get_settings
from backend.github_client import GitHubClient, GitHubError
from backend.models import PlanRequest, ScanRequest, ShipRequest, SseEvent
from backend.muscles.analyzer import analyze_files
from backend.scenarios import (
    apply_plan,
    changes,
    get_scenario,
    graph,
    impacts,
    patch_plan,
    sites,
    summaries,
    verification,
)

settings = get_settings()
app = FastAPI(title="API-Mend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_origin_regex=r"https://api-mend.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "ok": True,
        "service": "api-mend",
        "architecture": "Python Brain, Rust Muscles",
        "github_configured": bool(settings.github_token),
        "demo_mode": settings.demo_mode,
    }


@app.get("/github/access")
async def github_access() -> dict[str, object]:
    try:
        async with GitHubClient(settings) as github:
            return await github.access()
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/scenarios")
async def list_scenarios() -> list[dict[str, object]]:
    return [item.model_dump() for item in summaries()]


@app.post("/scan")
async def scan(request: ScanRequest) -> dict[str, object]:
    try:
        async with GitHubClient(settings) as github:
            result = await github.scan_repository(request.owner, request.repo, request.branch)
        call_sites = analyze_files(result["files"])
        return {
            "branch": result["branch"],
            "head_sha": result["head_sha"],
            "scanned_files": result["scanned_files"],
            "sites": [site.model_dump() for site in call_sites],
            "architecture": "Rust-backed ast-grep-py",
        }
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/simulate/{scenario_id}")
async def simulate(scenario_id: str) -> dict[str, object]:
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


@app.post("/plan")
async def plan(request: PlanRequest) -> dict[str, object]:
    try:
        scenario = get_scenario(request.scenario_id)
        patched = apply_plan(request.scenario_id)
        diffs = [
            {"path": path, "before": before, "after": patched[path]}
            for path, before in scenario["before"].items()
            if before != patched[path]
        ]
        return {
            "scenario": request.scenario_id,
            "plan": patch_plan(request.scenario_id).model_dump(),
            "diffs": diffs,
            "gates": verification(request.scenario_id).model_dump(),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown scenario") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/ship")
async def ship(request: ShipRequest) -> dict[str, object]:
    scenario = get_scenario(request.scenario_id)
    patched = apply_plan(request.scenario_id)
    if request.dry_run:
        return {
            "dry_run": True,
            "approved_by": request.approved_by,
            "scenario": request.scenario_id,
            "files": sorted(patched),
            "verification": verification(request.scenario_id).model_dump(),
        }
    if not request.owner or not request.repo:
        raise HTTPException(status_code=422, detail="owner and repo are required when dry_run=false")
    branch = f"apimend/{request.scenario_id}-{uuid.uuid4().hex[:8]}"
    body = json.dumps(
        {"scenario": scenario["title"], "verification": verification(request.scenario_id).model_dump()},
        indent=2,
    )
    try:
        async with GitHubClient(settings) as github:
            result = await github.create_pr(
                request.owner,
                request.repo,
                request.base,
                branch,
                patched,
                f"API-Mend: {scenario['title']}",
                body,
            )
        return {"dry_run": False, "approved_by": request.approved_by, **result}
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/events/{run_id}")
async def events(run_id: str) -> StreamingResponse:
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
