from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    kind: Literal["sdk_call", "http_call", "field_read", "webhook_handler", "import"]
    vendor: str | None = None
    callee: str | None = None
    url: str | None = None
    function: str = "<module>"
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_byte: int | None = Field(default=None, ge=0)
    end_byte: int | None = Field(default=None, ge=0)
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
    description: str = ""


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


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Diff(BaseModel):
    path: str
    before: str
    after: str


class HealthResponse(BaseModel):
    ok: bool
    service: str
    architecture: str
    github_configured: bool
    github_writes_enabled: bool
    api_key_configured: bool
    production_writes_ready: bool
    demo_mode: bool
    ready: bool


class LivenessResponse(BaseModel):
    ok: bool
    service: str


class ReadinessResponse(BaseModel):
    ok: bool
    ready: bool
    mode: Literal["demo", "live"]
    checks: dict[str, bool]


class GitHubAccessResponse(BaseModel):
    login: str | None = None
    id: int | None = None
    rate_limit_remaining: int | None = None
    api_version: str


class ScanResponse(BaseModel):
    branch: str
    head_sha: str
    scanned_files: int
    sites: list[CallSite]
    graph: DependencyGraph
    architecture: str


class PlanResponse(BaseModel):
    scenario: str
    plan: PatchPlan
    diffs: list[Diff]
    gates: VerificationReport


class SimulationResponse(BaseModel):
    scenario: str
    changes: list[BreakingChange]
    sites: list[CallSite]
    impacts: list[Impact]
    graph: DependencyGraph


class DriftRequest(RequestModel):
    vendor: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._ -]+$")
    before: dict[str, Any]
    after: dict[str, Any]
    evidence_url: str | None = Field(default=None, max_length=500)


class DriftResponse(BaseModel):
    vendor: str
    changes: list[BreakingChange]


class ShipResponse(BaseModel):
    dry_run: bool
    approved_by: Literal["voice", "click"]
    scenario: str
    files: list[str] = Field(default_factory=list)
    verification: VerificationReport | None = None
    number: int | None = None
    url: str | None = None
    commit: str | None = None
    reused: bool | None = None


class ScanRequest(RequestModel):
    owner: str = Field(min_length=1, max_length=39, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
    repo: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    branch: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._/\-]+$")

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if any(token in value for token in ("..", "//", "@{", "?", "#", "\\")):
            raise ValueError("branch contains an invalid ref sequence")
        if value.startswith("/") or value.endswith("/") or any(ord(char) < 32 for char in value):
            raise ValueError("branch is not a valid Git ref")
        return value


class PlanRequest(RequestModel):
    scenario_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")


class ShipRequest(RequestModel):
    scenario_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9-]+$")
    owner: str | None = Field(default=None, min_length=1, max_length=39, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
    repo: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    base: str = Field(default="main", min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._/\-]+$")
    dry_run: bool = True
    approved_by: Literal["voice", "click"] = "click"

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str) -> str:
        if any(token in value for token in ("..", "//", "@{", "?", "#", "\\")):
            raise ValueError("base contains an invalid ref sequence")
        if value.startswith("/") or value.endswith("/") or any(ord(char) < 32 for char in value):
            raise ValueError("base is not a valid Git ref")
        return value


class SseEvent(BaseModel):
    run_id: str = Field(min_length=1, max_length=100)
    step: str = Field(min_length=1, max_length=40)
    progress: float = Field(ge=0, le=1)
    message: str = Field(max_length=500)
    data: dict[str, Any] = Field(default_factory=dict)
