from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.models import BreakingChange


def compare_openapi(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    vendor: str,
    evidence_url: str | None = None,
) -> list[BreakingChange]:
    """Return deterministic breaking changes between two OpenAPI documents.

    This intentionally stays small and dependency-free. It covers the changes
    that API-Mend can connect directly to source call sites: removed paths,
    removed methods, and removed request-body properties.
    """
    changes: list[BreakingChange] = []
    before_paths = _mapping(before.get("paths"))
    after_paths = _mapping(after.get("paths"))

    for path in sorted(set(before_paths) - set(after_paths)):
        changes.append(
            BreakingChange(
                id=f"{vendor.lower()}-path-removed-{_slug(path)}",
                vendor=vendor,
                change_type="endpoint_removed",
                severity="breaking",
                endpoint_from=path,
                migration_hint=f"Replace calls to {path}; the endpoint is absent from the new OpenAPI document.",
                evidence_url=evidence_url,
                confidence=0.99,
            )
        )

    for path in sorted(set(before_paths) & set(after_paths)):
        before_operations = _operations(before_paths[path])
        after_operations = _operations(after_paths[path])
        for method in sorted(set(before_operations) - set(after_operations)):
            changes.append(
                BreakingChange(
                    id=f"{vendor.lower()}-method-removed-{method}-{_slug(path)}",
                    vendor=vendor,
                    change_type="method_removed",
                    severity="breaking",
                    endpoint_from=f"{method.upper()} {path}",
                    migration_hint=f"Replace {method.upper()} calls to {path}; the operation was removed.",
                    evidence_url=evidence_url,
                    confidence=0.98,
                )
            )

        for method in sorted(set(before_operations) & set(after_operations)):
            old_properties = _request_properties(before_operations[method])
            new_properties = _request_properties(after_operations[method])
            for field in sorted(set(old_properties) - set(new_properties)):
                changes.append(
                    BreakingChange(
                        id=f"{vendor.lower()}-field-removed-{method}-{_slug(path)}-{_slug(field)}",
                        vendor=vendor,
                        change_type="request_field_removed",
                        severity="breaking",
                        endpoint_from=f"{method.upper()} {path}",
                        field_from=field,
                        migration_hint=f"Stop sending request field {field!r} to {method.upper()} {path}.",
                        evidence_url=evidence_url,
                        confidence=0.95,
                    )
                )
    return changes


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _operations(value: Any) -> Mapping[str, Any]:
    methods = {"get", "post", "put", "patch", "delete", "head", "options"}
    return {key: item for key, item in _mapping(value).items() if key.lower() in methods}


def _request_properties(operation: Any) -> set[str]:
    request_body = _mapping(_mapping(operation).get("requestBody"))
    content = _mapping(request_body.get("content"))
    for media_type in sorted(content):
        schema = _mapping(_mapping(content[media_type]).get("schema"))
        properties = _mapping(schema.get("properties"))
        if properties:
            return set(properties)
    return set()


def _slug(value: str) -> str:
    normalized = "".join(char if char.isalnum() else "-" for char in value.lower())
    return "-".join(part for part in normalized.split("-") if part)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Compare two OpenAPI JSON documents for breaking changes.")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--vendor", required=True)
    parser.add_argument("--evidence-url")
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    changes = compare_openapi(before, after, args.vendor, args.evidence_url)
    print(json.dumps([change.model_dump() for change in changes], indent=2))


if __name__ == "__main__":
    _main()
