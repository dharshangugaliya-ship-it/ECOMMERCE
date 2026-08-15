import io


def test_upload_requires_admin(client, user, auth_headers, seeded_products):
    pid = str(seeded_products[0]["_id"])
    data = {"file": (io.BytesIO(b"fake png bytes"), "test.png")}
    r = client.post(f"/api/admin/products/{pid}/image", headers=auth_headers,
                    data=data, content_type="multipart/form-data")
    assert r.status_code == 403


def test_upload_happy_path(client, admin_headers, seeded_products):
    pid = str(seeded_products[0]["_id"])
    data = {"file": (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 100), "hello.png")}
    r = client.post(f"/api/admin/products/{pid}/image", headers=admin_headers,
                    data=data, content_type="multipart/form-data")
    assert r.status_code == 201
    body = r.get_json()
    assert body["image"].startswith("/uploads/")
    # Should be retrievable
    r2 = client.get(body["image"])
    assert r2.status_code == 200


def test_upload_rejects_bad_extension(client, admin_headers, seeded_products):
    pid = str(seeded_products[0]["_id"])
    data = {"file": (io.BytesIO(b"exe"), "bad.exe")}
    r = client.post(f"/api/admin/products/{pid}/image", headers=admin_headers,
                    data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_upload_unknown_product(client, admin_headers):
    r = client.post("/api/admin/products/000000000000000000000000/image",
                    headers=admin_headers,
                    data={"file": (io.BytesIO(b"x"), "x.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 404
