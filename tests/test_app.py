import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import backend.main as main_module
from backend.config import Settings
from backend.main import app, settings

client = TestClient(app)


def test_healthz_reports_architecture() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["architecture"] == "Python Brain, Rust Muscles"


def test_livez_is_always_available() -> None:
    response = client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "api-mend"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-request-id"]


def test_readyz_supports_demo_mode_without_github_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "github_token", None)
    try:
        response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json()["mode"] == "demo"
    finally:
        monkeypatch.setattr(settings, "demo_mode", False)


def test_readyz_fails_when_live_github_configuration_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    original_token = settings.github_token
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "github_token", None)
    monkeypatch.setattr(settings, "allow_github_writes", False)
    try:
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["detail"]["checks"]["github_token"] is False
    finally:
        monkeypatch.setattr(settings, "github_token", original_token)


def test_scenario_plan_is_deterministic() -> None:
    response = client.post("/plan", json={"scenario_id": "stripe-paymentintents"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["diffs"]) == 2
    assert payload["gates"]["passed"] is True


def test_drift_endpoint_returns_breaking_changes() -> None:
    response = client.post(
        "/drift",
        json={
            "vendor": "Stripe",
            "before": {"paths": {"/charges": {"post": {}}}},
            "after": {"paths": {}},
        },
    )
    assert response.status_code == 200
    assert response.json()["changes"][0]["change_type"] == "endpoint_removed"


def test_ship_defaults_to_dry_run() -> None:
    response = client.post("/ship", json={"scenario_id": "stripe-paymentintents"})
    assert response.status_code == 200
    assert response.json()["dry_run"] is True


def test_real_ship_is_disabled_without_server_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    original_key = settings.api_key
    monkeypatch.setattr(settings, "api_key", "test-key")
    try:
        response = client.post(
            "/ship",
            json={"scenario_id": "stripe-paymentintents", "owner": "acme", "repo": "shop", "dry_run": False},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 403
    finally:
        monkeypatch.setattr(settings, "api_key", original_key)


def test_ship_unknown_scenario_is_a_client_error() -> None:
    response = client.post("/ship", json={"scenario_id": "does-not-exist"})
    assert response.status_code == 404


def test_request_models_reject_unknown_fields() -> None:
    response = client.post("/plan", json={"scenario_id": "stripe-paymentintents", "unexpected": True})
    assert response.status_code == 422


def test_openapi_documents_api_key_security() -> None:
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"].values()
    assert any(scheme.get("name") == "X-API-Key" for scheme in schemes)
    assert "/scan" in schema["paths"]
    assert schema["paths"]["/scan"]["post"]["security"]


def test_rate_limit_returns_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    getattr(main_module, "_request_windows").clear()
    try:
        first = client.post("/ship", json={"scenario_id": "stripe-paymentintents"})
        second = client.post("/ship", json={"scenario_id": "stripe-paymentintents"})
        assert first.status_code == 200
        assert second.status_code == 429
        assert second.headers["retry-after"] == "60"
    finally:
        getattr(main_module, "_request_windows").clear()
        monkeypatch.setattr(settings, "rate_limit_per_minute", 60)


def test_request_size_limit_returns_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_request_bytes", 10)
    try:
        response = client.post("/ship", json={"scenario_id": "stripe-paymentintents"})
        assert response.status_code == 413
    finally:
        monkeypatch.setattr(settings, "max_request_bytes", 1_000_000)


def test_all_demo_scenarios_have_passing_plans() -> None:
    scenarios = client.get("/scenarios").json()
    assert {item["id"] for item in scenarios} == {
        "stripe-paymentintents",
        "openai-tools",
        "twilio-signature-v2",
    }
    for scenario in scenarios:
        response = client.post("/plan", json={"scenario_id": scenario["id"]})
        assert response.status_code == 200
        assert response.json()["gates"]["passed"] is True


def test_frontend_fixtures_match_backend_canonical_fixtures() -> None:
    root = Path(__file__).resolve().parents[1]
    for fixture_name in ("stripe.json", "openai-tools.json", "twilio-signature-v2.json"):
        backend_fixture = json.loads((root / "fixtures" / fixture_name).read_text(encoding="utf-8"))
        frontend_fixture = json.loads(
            (root / "frontend" / "public" / "fixtures" / fixture_name).read_text(encoding="utf-8")
        )
        assert frontend_fixture == backend_fixture


def test_github_request_rejects_path_injection_values() -> None:
    response = client.post("/scan", json={"owner": "../user", "repo": "shop"})
    assert response.status_code == 422


def test_cors_rejects_lookalike_vercel_origin() -> None:
    response = client.options(
        "/healthz",
        headers={"Origin": "https://api-mend.evil.vercel.app", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_config_rejects_unsafe_github_api_destination() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, github_token="test", github_api_base="http://127.0.0.1:8080")


def test_write_configuration_requires_api_key() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, github_token="test", allow_github_writes=True, allowed_repositories="acme/shop")


def test_write_configuration_requires_github_token() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            github_token="",
            api_key="test-key",
            allow_github_writes=True,
            allowed_repositories="acme/shop",
        )


def test_configured_api_key_protects_github_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_key", "test-key")
    try:
        response = client.get("/github/access")
        assert response.status_code == 401
        response = client.get("/github/access", headers={"X-API-Key": "wrong"})
        assert response.status_code == 401
    finally:
        monkeypatch.setattr(settings, "api_key", None)


def test_live_github_access_fails_closed_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    original_token = settings.github_token
    monkeypatch.setattr(settings, "github_token", "test-token")
    monkeypatch.setattr(settings, "api_key", None)
    try:
        response = client.get("/github/access")
        assert response.status_code == 503
    finally:
        monkeypatch.setattr(settings, "github_token", original_token)
