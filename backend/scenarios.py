from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.models import (
    BreakingChange,
    CallSite,
    DependencyGraph,
    Impact,
    PatchPlan,
    ScenarioSummary,
    VerificationReport,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "stripe.json"


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def summaries() -> list[ScenarioSummary]:
    return [
        ScenarioSummary(
            id="stripe-paymentintents",
            vendor="stripe",
            title="Stripe Charges → PaymentIntents",
            stylized=True,
        )
    ]


def get_scenario(scenario_id: str) -> dict[str, Any]:
    scenario = load_fixture()
    if scenario["id"] != scenario_id:
        raise KeyError(scenario_id)
    return scenario


def changes(scenario_id: str) -> list[BreakingChange]:
    return [BreakingChange.model_validate(item) for item in get_scenario(scenario_id)["changes"]]


def patch_plan(scenario_id: str) -> PatchPlan:
    return PatchPlan.model_validate(get_scenario(scenario_id)["patch_plan"])


def apply_plan(scenario_id: str) -> dict[str, str]:
    scenario = get_scenario(scenario_id)
    output = dict(scenario["before"])
    for edit in patch_plan(scenario_id).edits:
        if output[edit.file].count(edit.search) != 1:
            raise ValueError(f"{edit.file}: search did not match exactly once")
        output[edit.file] = output[edit.file].replace(edit.search, edit.replace, 1)
    return output


def sites(scenario_id: str) -> list[CallSite]:
    return [CallSite.model_validate(item) for item in get_scenario(scenario_id)["sites"]]


def impacts(scenario_id: str) -> list[Impact]:
    return [Impact.model_validate(item) for item in get_scenario(scenario_id)["impacts"]]


def graph(scenario_id: str) -> DependencyGraph:
    return DependencyGraph.model_validate(get_scenario(scenario_id)["graph"])


def verification(scenario_id: str) -> VerificationReport:
    return VerificationReport.model_validate(get_scenario(scenario_id)["verification"])
