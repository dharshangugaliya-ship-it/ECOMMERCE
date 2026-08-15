def test_cart_requires_auth(client, fresh_db):
    r = client.get("/api/cart")
    assert r.status_code == 401


def test_add_to_cart(client, user, seeded_products, auth_headers):
    pid = str(seeded_products[0]["_id"])
    r = client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": 2})
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["product_id"] == pid
    assert items[0]["qty"] == 2


def test_add_increments_existing(client, user, seeded_products, auth_headers):
    pid = str(seeded_products[0]["_id"])
    client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": 1})
    r = client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": 2})
    items = r.get_json()
    assert items[0]["qty"] == 3


def test_add_invalid_qty(client, user, seeded_products, auth_headers):
    pid = str(seeded_products[0]["_id"])
    r = client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": "abc"})
    assert r.status_code == 400


def test_add_exceeds_stock(client, user, seeded_products, auth_headers):
    pid = str(seeded_products[0]["_id"])
    # seed products have stock between 8 and 40; 1000 is safely over
    r = client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": 1000})
    assert r.status_code == 400


def test_update_qty(client, user, seeded_products, auth_headers):
    pid = str(seeded_products[0]["_id"])
    client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": 1})
    r = client.patch(f"/api/cart/{pid}", headers=auth_headers, json={"qty": 5})
    assert r.status_code == 200
    assert r.get_json()[0]["qty"] == 5


def test_remove_item(client, user, seeded_products, auth_headers):
    pid = str(seeded_products[0]["_id"])
    client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": 1})
    r = client.delete(f"/api/cart/{pid}", headers=auth_headers)
    assert r.status_code == 200
    assert r.get_json() == []


def test_clear_cart(client, user, seeded_products, auth_headers):
    pid = str(seeded_products[0]["_id"])
    client.post("/api/cart", headers=auth_headers, json={"product_id": pid, "qty": 1})
    r = client.delete("/api/cart", headers=auth_headers)
    assert r.status_code == 200
    assert r.get_json() == []
