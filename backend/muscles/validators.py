from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _run(command: list[str], cwd: str) -> dict[str, object]:
    executable = shutil.which(command[0])
    if not executable:
        return {"tool": command[0], "status": "unavailable", "exit_code": None, "output": ""}
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return {
        "tool": command[0],
        "status": "pass" if completed.returncode == 0 else "fail",
        "exit_code": completed.returncode,
        "output": (completed.stdout + completed.stderr)[-4000:],
    }


def validate_target(repo_dir: str, paths: list[str]) -> list[dict[str, object]]:
    """Run Rust-backed/native linters without installing target dependencies."""
    python_files = [p for p in paths if p.endswith(".py")]
    js_files = [p for p in paths if p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))]
    reports: list[dict[str, object]] = []
    if python_files:
        reports.append(_run(["ruff", "check", *python_files], repo_dir))
    if js_files:
        oxlint = Path(repo_dir) / "node_modules" / ".bin" / ("oxlint.cmd" if os.name == "nt" else "oxlint")
        if oxlint.exists():
            reports.append(_run([str(oxlint), *js_files], repo_dir))
        else:
            reports.append({"tool": "oxlint", "status": "unavailable", "exit_code": None, "output": ""})
    return reports
