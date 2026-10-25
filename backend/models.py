from typing import Any, Literal

from pydantic import BaseModel, Field


class BreakingChange(BaseModel):
    id: str
    vendor: str
    change_type: str
    severity: Literal["breaking", "deprecation", "additive"]
    endpoint_from: str | None = None
    endpoint_to: str | None = None
    sdk_symbol_from: str | None = None
    sdk_symbol_to: str | None = None
    field_from: str | None = None
    field_to: str | None = None
    migration_hint: str
    evidence_quote: str | None = None
    evidence_url: str | None = None
    confidence: float = Field(ge=0, le=1)


class CallSite(BaseModel):
    id: str
    file: str
    language: Literal["python", "typescript", "tsx", "javascript"]
    kind: Literal["sdk_call", "http_call", "field_read"]
    vendor: str | None = None
    callee: str | None = None
    url: str | None = None
    function: str = "<module>"
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    snippet: str = Field(max_length=2000)
    payload_keys: list[str] = Field(default_factory=list)


class Impact(BaseModel):
    change_id: str
    site_id: str
    reason: str


class EditBlock(BaseModel):
    file: str
    site_id: str | None = None
    search: str = Field(min_length=1)
    replace: str
    change_ids: list[str] = Field(min_length=1)
    rationale: str


class PatchPlan(BaseModel):
    edits: list[EditBlock]
    unresolved: list[str] = Field(default_factory=list)


class Gate(BaseModel):
    id: Literal["G1", "G2", "G3", "G4", "G5", "G6"]
    name: str
    status: Literal["pass", "fail", "warn", "pending", "skipped"]
    details: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    passed: bool
    gates: list[Gate]
    lines_added: int = 0
    lines_removed: int = 0
    ci_run_url: str | None = None


class ScenarioSummary(BaseModel):
    id: str
    vendor: str
    title: str
    stylized: bool


class GraphNode(BaseModel):
    id: str
    type: str
    position: dict[str, float] = {"x": 0, "y": 0}
    data: dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    animated: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class DependencyGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    meta: dict[str, Any] = Field(default_factory=dict)


class ScanRequest(BaseModel):
    owner: str
    repo: str
    branch: str | None = None


class PlanRequest(BaseModel):
    scenario_id: str


class ShipRequest(BaseModel):
    scenario_id: str
    owner: str | None = None
    repo: str | None = None
    base: str = "main"
    dry_run: bool = True
    approved_by: Literal["voice", "click"] = "click"


class SseEvent(BaseModel):
    run_id: str
    step: str
    progress: float = Field(ge=0, le=1)
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
