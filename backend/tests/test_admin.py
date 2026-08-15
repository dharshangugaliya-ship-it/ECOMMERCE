import io
import os


def test_admin_requires_auth(client, fresh_db):
    r = client.get("/api/admin/orders")
    assert r.status_code == 401


def test_non_admin_cannot_list_orders(client, user, auth_headers):
    r = client.get("/api/admin/orders", headers=auth_headers)
    assert r.status_code == 403


def test_admin_can_create_product(client, admin_headers):
    r = client.post("/api/admin/products", headers=admin_headers, json={
        "name": "Test Mug", "category": "Home", "price": 12.5, "stock": 5, "description": "ceramic",
    })
    assert r.status_code == 201
    assert r.get_json()["name"] == "Test Mug"


def test_admin_can_update_product(client, admin_headers, seeded_products):
    pid = str(seeded_products[0]["_id"])
    r = client.patch(f"/api/admin/products/{pid}", headers=admin_headers, json={"price": 199.0})
    assert r.status_code == 200
    assert r.get_json()["price"] == 199.0


def test_admin_can_delete_product(client, admin_headers, seeded_products):
    pid = str(seeded_products[0]["_id"])
    r = client.delete(f"/api/admin/products/{pid}", headers=admin_headers)
    assert r.status_code == 200
    r2 = client.get(f"/api/products/{pid}")
    assert r2.status_code == 404


def test_admin_can_list_all_orders(client, admin_headers, user, auth_headers):
    # Place an order as a regular user.
    import app as _app
    pid = list(_app.products.find())[0]["_id"]
    pid_s = str(pid)
    client.post("/api/cart", headers=auth_headers, json={"product_id": pid_s, "qty": 1})
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
    })
    assert r.status_code == 201
    r2 = client.get("/api/admin/orders", headers=admin_headers)
    assert r2.status_code == 200
    assert len(r2.get_json()) == 1


def test_admin_can_update_order_status(client, admin_headers, user, auth_headers):
    import app as _app
    pid_s = str(list(_app.products.find())[0]["_id"])
    client.post("/api/cart", headers=auth_headers, json={"product_id": pid_s, "qty": 1})
    r = client.post("/api/orders", headers=auth_headers, json={
        "customer": {"name": "Alice", "email": "alice@example.com", "address": "1 Main St"},
    })
    oid = r.get_json()["_id"]
    r2 = client.patch(f"/api/admin/orders/{oid}", headers=admin_headers, json={"status": "shipped"})
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "shipped"


def test_admin_rejects_invalid_status(client, admin_headers):
    r = client.patch("/api/admin/orders/000000000000000000000000", headers=admin_headers, json={"status": "bogus"})
    assert r.status_code == 400
