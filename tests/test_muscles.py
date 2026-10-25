from backend.muscles.analyzer import analyze_files
from backend.scenarios import apply_plan, get_scenario, patch_plan
from backend.verification import verify_patch


def test_rust_backed_analyzer_finds_python_and_typescript_calls() -> None:
    sites = analyze_files(
        {
            "checkout.py": "import stripe\nstripe.Charge.create(amount_cents=1)\n",
            "pay.ts": 'fetch("https://api.stripe.com/v1/charges", { body: JSON.stringify({ amount_cents: 1 }) })',
        }
    )
    assert {site.language for site in sites} == {"python", "typescript"}
    assert {site.vendor for site in sites} == {"stripe"}


def test_verification_gates_pass_for_cached_stripe_patch() -> None:
    scenario = get_scenario("stripe-paymentintents")
    after = apply_plan("stripe-paymentintents")
    report = verify_patch(
        scenario["before"],
        after,
        patch_plan("stripe-paymentintents"),
        ["stripe.Charge.create", "/v1/charges", "amount_cents"],
    )
    assert report.passed is True
    assert {gate.id for gate in report.gates} == {"G1", "G2", "G3", "G4", "G5", "G6"}
