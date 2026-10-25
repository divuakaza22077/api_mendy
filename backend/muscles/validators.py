from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str], cwd: str) -> dict[str, object]:
    python_module = command[0] == "python"
    executable = sys.executable if python_module else shutil.which(command[0])
    if not executable:
        return {"tool": command[0], "status": "unavailable", "exit_code": None, "output": ""}
    args = [executable, "-m", *command[1:]] if python_module else [executable, *command[1:]]
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "tool": command[0],
            "status": "fail",
            "exit_code": None,
            "output": f"{command[0]} timed out after 20 seconds",
        }
    except OSError as exc:
        return {"tool": command[0], "status": "unavailable", "exit_code": None, "output": str(exc)[:4000]}
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
        reports.append(_run(["python", "ruff", "check", *python_files], repo_dir))
    if js_files:
        binary_name = "oxlint.cmd" if os.name == "nt" else "oxlint"
        candidates = [
            Path(repo_dir) / "node_modules" / ".bin" / binary_name,
            Path(__file__).resolve().parents[2] / "node_modules" / ".bin" / binary_name,
            Path(__file__).resolve().parents[2] / "tooling" / "node_modules" / ".bin" / binary_name,
        ]
        oxlint = next((candidate for candidate in candidates if candidate.exists()), None)
        if oxlint is None:
            reports.append({"tool": "oxlint", "status": "unavailable", "exit_code": None, "output": ""})
        else:
            reports.append(_run([str(oxlint), *js_files], repo_dir))
    return reports
