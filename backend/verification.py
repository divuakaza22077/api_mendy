from __future__ import annotations

import difflib
import tempfile
from pathlib import Path

from backend.models import Gate, PatchPlan, VerificationReport
from backend.muscles.validators import validate_target


def _line_delta(before: str, after: str) -> tuple[int, int]:
    diff = list(difflib.ndiff(before.splitlines(), after.splitlines()))
    added = sum(line.startswith("+ ") for line in diff)
    removed = sum(line.startswith("- ") for line in diff)
    return added, removed


def verify_patch(
    before: dict[str, str],
    after: dict[str, str],
    plan: PatchPlan,
    old_residue: list[str],
    contract_residue: list[str] | None = None,
) -> VerificationReport:
    gates: list[Gate] = []
    exact_ok = True
    for edit in plan.edits:
        count = before.get(edit.file, "").count(edit.search)
        if count != 1:
            exact_ok = False
            gates.append(
                Gate(
                    id="G1",
                    name="Exact-match apply",
                    status="fail",
                    details=[f"{edit.file}: expected one match, found {count}"],
                )
            )
    if exact_ok:
        gates.append(
            Gate(
                id="G1",
                name="Exact-match apply",
                status="pass",
                details=[f"{len(plan.edits)} edits matched once"],
            )
        )

    syntax_ok = True
    with tempfile.TemporaryDirectory(prefix="api-mend-verify-") as directory:
        root = Path(directory)
        for path, source in after.items():
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source, encoding="utf-8", newline="")
        reports = validate_target(str(root), list(after))
        failures = [report for report in reports if report["status"] == "fail"]
        if failures:
            syntax_ok = False
            details = [f"{report['tool']}: {report['output']}" for report in failures]
            gates.append(Gate(id="G2", name="Rust-backed syntax validation", status="fail", details=details))
        else:
            unavailable = [report["tool"] for report in reports if report["status"] == "unavailable"]
            status = "warn" if unavailable else "pass"
            details = [f"{report['tool']}: {report['status']}" for report in reports]
            gates.append(Gate(id="G2", name="Rust-backed syntax validation", status=status, details=details))

    changed_paths = {path for path in before if before[path] != after.get(path)}
    planned_paths = {edit.file for edit in plan.edits}
    scope_ok = changed_paths <= planned_paths
    gates.append(
        Gate(
            id="G3",
            name="Scope",
            status="pass" if scope_ok else "fail",
            details=[f"changed={sorted(changed_paths)}", f"planned={sorted(planned_paths)}"],
        )
    )

    contract_residue = contract_residue or []
    contract_hits = [needle for needle in contract_residue if any(needle in source for source in after.values())]
    contract_ok = not contract_hits
    gates.append(
        Gate(
            id="G4",
            name="Contract shape",
            status="pass" if contract_ok else "fail",
            details=[
                "strict fixture contract has no legacy fields"
                if contract_ok
                else f"legacy contract fields: {contract_hits}"
            ],
        )
    )

    residue_hits = [needle for needle in old_residue if any(needle in source for source in after.values())]
    gates.append(
        Gate(
            id="G5",
            name="Residue scan",
            status="pass" if not residue_hits else "fail",
            details=["zero legacy residue" if not residue_hits else f"legacy residue: {residue_hits}"],
        )
    )
    gates.append(Gate(id="G6", name="GitHub Actions", status="pending", details=["runs after a real PR is opened"]))

    added = removed = 0
    for path in changed_paths:
        path_added, path_removed = _line_delta(before[path], after[path])
        added += path_added
        removed += path_removed
    passed = all(gate.status in {"pass", "warn", "pending"} for gate in gates)
    return VerificationReport(passed=passed and syntax_ok, gates=gates, lines_added=added, lines_removed=removed)
