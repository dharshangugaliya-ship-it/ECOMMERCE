import importlib
import sys


def test_security_headers_present(client, fresh_db):
    r = client.get("/api/products")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "same-origin"
    assert "geolocation=()" in r.headers.get("Permissions-Policy", "")


def test_cors_preflight_allows_listed_origin(client, fresh_db):
    r = client.options("/api/auth/login", headers={
        "Origin": "http://localhost:8080",
        "Access-Control-Request-Method": "POST",
    })
    assert r.status_code in (200, 204)
    assert r.headers.get("Access-Control-Allow-Origin") == "http://localhost:8080"


def test_jwt_guard_refuses_placeholder_secret(monkeypatch):
    """Importing app.py with a placeholder JWT secret and USE_MOCK != "1" must raise."""
    import pytest
    monkeypatch.setenv("USE_MOCK", "0")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-prod")
    # Make sure dotenv doesn't sneak the real .env in either.
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017/")
    monkeypatch.setenv("DB_NAME", "ecommerce_test")
    sys.modules.pop("app", None)
    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            importlib.import_module("app")
    finally:
        sys.modules.pop("app", None)
        # Restore the test-friendly env for any tests that run after.
        monkeypatch.setenv("USE_MOCK", "1")
        monkeypatch.setenv("JWT_SECRET", "test-secret-not-for-prod-1234567890")
        importlib.import_module("app")
