from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_healthz_reports_architecture() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["architecture"] == "Python Brain, Rust Muscles"


def test_scenario_plan_is_deterministic() -> None:
    response = client.post("/plan", json={"scenario_id": "stripe-paymentintents"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["diffs"]) == 2
    assert payload["gates"]["passed"] is True


def test_ship_defaults_to_dry_run() -> None:
    response = client.post("/ship", json={"scenario_id": "stripe-paymentintents"})
    assert response.status_code == 200
    assert response.json()["dry_run"] is True
