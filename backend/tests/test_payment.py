# Test card numbers (all pass Luhn and are not real).
VISA = "4242424242424242"
MASTERCARD = "5555555555554444"
AMEX = "378282246310005"


def _good_payment():
    return {
        "card_number": VISA,
        "card_holder": "Alice Tester",
        "exp_month": 12,
        "exp_year": 2099,
        "cvc": "123",
    }


def _seed_cart(client, auth_headers):
    import app as _app
    pid_s = str(list(_app.products.find())[0]["_id"])
    client.post("/api/cart", headers=auth_headers, json={"product_id": pid_s, "qty": 1})


def test_checkout_without_payment_marks_confirmed(client, user, auth_headers):
    _seed_cart(client, auth_headers)
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
    })
    assert r.status_code == 201
    assert r.get_json()["status"] == "confirmed"
    assert r.get_json()["payment"] is None


def test_checkout_with_valid_payment_marks_paid(client, user, auth_headers):
    _seed_cart(client, auth_headers)
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
        "payment": _good_payment(),
    })
    assert r.status_code == 201
    body = r.get_json()
    assert body["status"] == "paid"
    assert body["payment"]["brand"] == "visa"
    assert body["payment"]["last4"] == "4242"


def test_checkout_with_bad_luhn_fails(client, user, auth_headers):
    _seed_cart(client, auth_headers)
    bad = dict(_good_payment())
    bad["card_number"] = "4242424242424241"  # fails Luhn
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
        "payment": bad,
    })
    assert r.status_code == 400
    assert "card" in r.get_json()["error"].lower()


def test_checkout_with_expired_card_fails(client, user, auth_headers):
    _seed_cart(client, auth_headers)
    bad = dict(_good_payment())
    bad["exp_year"] = 2000
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
        "payment": bad,
    })
    assert r.status_code == 400
    assert "expired" in r.get_json()["error"].lower()


def test_payment_failure_releases_stock(client, user, auth_headers):
    _seed_cart(client, auth_headers)
    import app as _app
    p_before = list(_app.products.find())[0]["stock"]
    bad = dict(_good_payment())
    bad["card_number"] = "4242424242424241"
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
        "payment": bad,
    })
    assert r.status_code == 400
    p_after = list(_app.products.find())[0]["stock"]
    assert p_after == p_before, f"stock not rolled back: {p_before} -> {p_after}"


def test_checkout_with_mastercard(client, user, auth_headers):
    _seed_cart(client, auth_headers)
    p = dict(_good_payment())
    p["card_number"] = MASTERCARD
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
        "payment": p,
    })
    assert r.status_code == 201
    assert r.get_json()["payment"]["brand"] == "mastercard"
