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


def load_fixture(scenario_id: str) -> dict[str, Any]:
    fixture_names = {
        "stripe-paymentintents": "stripe.json",
        "openai-tools": "openai-tools.json",
        "twilio-signature-v2": "twilio-signature-v2.json",
    }
    fixture_name = fixture_names.get(scenario_id)
    if fixture_name is None:
        raise KeyError(scenario_id)
    fixture_path = ROOT / "fixtures" / fixture_name
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def summaries() -> list[ScenarioSummary]:
    return [
        ScenarioSummary(
            id="stripe-paymentintents",
            vendor="stripe",
            title="Stripe Charges → PaymentIntents",
            stylized=True,
            description="A stylized nested-field migration layered on Stripe's real PaymentIntents migration.",
        ),
        ScenarioSummary(
            id="openai-tools",
            vendor="openai",
            title="OpenAI functions → tools",
            stylized=False,
            description="Migrate legacy Chat Completions function calling to the tools protocol.",
        ),
        ScenarioSummary(
            id="twilio-signature-v2",
            vendor="twilio",
            title="Twilio webhook signature hardening",
            stylized=True,
            description="A stylized signature-header migration that demonstrates proxy-safe webhook validation.",
        )
    ]


def get_scenario(scenario_id: str) -> dict[str, Any]:
    scenario = load_fixture(scenario_id)
    if scenario["id"] != scenario_id:
        raise KeyError(scenario_id)
    return scenario


def changes(scenario_id: str) -> list[BreakingChange]:
    return [BreakingChange.model_validate(item) for item in get_scenario(scenario_id)["changes"]]


def patch_plan(scenario_id: str) -> PatchPlan:
    return PatchPlan.model_validate(get_scenario(scenario_id)["patch_plan"])


def apply_plan(scenario_id: str) -> dict[str, str]:
    scenario = get_scenario(scenario_id)
    return apply_plan_to_files(scenario_id, scenario["before"])


def apply_plan_to_files(scenario_id: str, files: dict[str, str]) -> dict[str, str]:
    output = dict(files)
    for edit in patch_plan(scenario_id).edits:
        if edit.file not in output:
            raise ValueError(f"{edit.file}: target file is missing")
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
