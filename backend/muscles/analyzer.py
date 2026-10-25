from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from ast_grep_py import SgRoot

from backend.models import CallSite

EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
VENDOR_NAMES = ("stripe", "openai", "twilio", "slack", "discord", "anthropic")
URL_RE = re.compile(r"https?://[^\s'\"`]+", re.IGNORECASE)


def language_for(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix == ".tsx":
        return "tsx"
    if suffix == ".ts":
        return "typescript"
    return "javascript"


def _line_number(source: str, snippet: str) -> int:
    index = source.find(snippet)
    return source.count("\n", 0, index) + 1 if index >= 0 else 1


def _vendor(text: str) -> str | None:
    lowered = text.lower()
    for name in VENDOR_NAMES:
        if name in lowered:
            return name
    return None


def _site_kind(text: str) -> str:
    if "http" in text or "fetch(" in text or ".request(" in text:
        return "http_call"
    return "sdk_call"


def analyze_source(path: str, source: str) -> list[CallSite]:
    """Find calls using ast-grep's Rust parser; no Python AST fallback."""
    if PurePosixPath(path).suffix.lower() not in EXTENSIONS:
        return []

    language = language_for(path)
    root = SgRoot(source, language).root()
    call_kind = "call" if language == "python" else "call_expression"
    sites: list[CallSite] = []
    for node in root.find_all(kind=call_kind):
        snippet = node.text().strip()
        vendor = _vendor(snippet)
        url_match = URL_RE.search(snippet)
        if not vendor and not url_match:
            continue
        line = _line_number(source, snippet)
        site_id = hashlib.sha1(f"{path}:{line}:{snippet}".encode()).hexdigest()[:12]
        sites.append(
            CallSite(
                id=site_id,
                file=path,
                language=language_for(path),
                kind=_site_kind(snippet),
                vendor=vendor,
                callee=snippet.split("(", 1)[0].strip(),
                url=url_match.group(0) if url_match else None,
                start_line=line,
                end_line=line + snippet.count("\n"),
                snippet=snippet[:2000],
                payload_keys=sorted(
                    set(
                        re.findall(
                            r"(?:amount_cents|unit_amount|functions|tools|function_call|tool_choice)",
                            snippet,
                        )
                    )
                ),
            )
        )
    return sites


def analyze_files(files: dict[str, str]) -> list[CallSite]:
    sites: list[CallSite] = []
    for path, source in files.items():
        sites.extend(analyze_source(path, source))
    return sites
