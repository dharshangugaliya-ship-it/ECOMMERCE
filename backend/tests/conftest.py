import os
import sys
import mongomock
import pytest

# Force the test session to use the in-memory MongoDB.
os.environ["USE_MOCK"] = "1"
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-prod-1234567890")

# Drop any cached app module so env vars are re-read at import.
sys.modules.pop("app", None)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app as _app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Reset flask-limiter's in-memory counters between tests.

    Without this, the per-route limits (10 login/min, 5 signup/min, etc.)
    accumulate across the whole test session and cause late tests to fail
    at the login fixture with 429s. We don't change production behavior,
    only clear the test storage.
    """
    limiter = getattr(_app, "limiter", None)
    if limiter is not None and hasattr(limiter, "reset"):
        try:
            limiter.reset()
        except Exception:
            storage = getattr(limiter, "_storage", None)
            if storage is not None and hasattr(storage, "storage"):
                storage.storage.clear()


@pytest.fixture
def fresh_db():
    app = _app.app
    app.config["TESTING"] = True
    _app.client = mongomock.MongoClient()
    _app.db = _app.client[_app.DB_NAME]
    _app.users = _app.db["users"]
    _app.products = _app.db["products"]
    _app.carts = _app.db["carts"]
    _app.orders = _app.db["orders"]
    _app.payments = _app.db["payments"]
    _app.products.delete_many({})
    _app._seed_if_empty()
    yield


@pytest.fixture
def client(fresh_db):
    return _app.app.test_client()


def _make_user(email, password, name, is_admin=False):
    import bcrypt
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    res = _app.users.insert_one({"name": name, "email": email.lower(),
                                 "password": hashed, "is_admin": bool(is_admin)})
    return {"_id": str(res.inserted_id), "name": name, "email": email.lower()}


@pytest.fixture
def user(fresh_db):
    return _make_user("alice@example.com", "hunter22", "Alice")


@pytest.fixture
def admin_user(fresh_db):
    return _make_user("admin@example.com", "adminpass", "Admin", is_admin=True)


@pytest.fixture
def seeded_products(fresh_db):
    return list(_app.products.find())


def _login_token(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["token"]


@pytest.fixture
def auth_headers(user):
    client = _app.app.test_client()
    token = _login_token(client, user["email"], "hunter22")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user):
    client = _app.app.test_client()
    token = _login_token(client, admin_user["email"], "adminpass")
    return {"Authorization": f"Bearer {token}"}