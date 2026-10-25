from backend.drift import compare_openapi


def test_compare_openapi_finds_removed_path_method_and_field() -> None:
    before = {
        "openapi": "3.0.0",
        "paths": {
            "/charges": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"properties": {"amount": {}, "currency": {}}}}}
                    }
                },
                "delete": {},
            },
            "/customers": {"get": {}},
        },
    }
    after = {
        "openapi": "3.0.0",
        "paths": {
            "/charges": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"properties": {"currency": {}}}}}
                    }
                }
            }
        },
    }

    changes = compare_openapi(before, after, "Stripe", "https://example.test/changelog")

    assert {change.change_type for change in changes} == {
        "endpoint_removed",
        "method_removed",
        "request_field_removed",
    }
    assert all(change.evidence_url == "https://example.test/changelog" for change in changes)
