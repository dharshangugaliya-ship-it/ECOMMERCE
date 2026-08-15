"""Mini Shop - Flask + MongoDB e-commerce API.

Boot modes (USE_MOCK=1):
  - In-memory mongomock for dev/tests.
  - Auto-seeds catalog if products collection is empty.
  - In mock mode, auto-creates a default admin (printed to stdout) so the admin
    UI is reachable out of the box. NEVER does this in non-mock mode.
"""
import os
import re
import uuid
import datetime as dt
from datetime import timezone
import logging
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, g, send_from_directory, abort
from flask_cors import CORS
from bson import ObjectId
from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr, Field, ValidationError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import jwt
import bcrypt

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if o.strip()]
CORS(app, resources={r"/api/*": {"origins": _cors_origins}, r"/uploads/*": {"origins": _cors_origins}})

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    default_limits=["200 per minute"],
    headers_enabled=True,
)
limiter.init_app(app)


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return resp


@app.errorhandler(429)
def _on_rate_limit(e):
    return jsonify({"error": "rate limit exceeded"}), 429


log = logging.getLogger("ecommerce")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "ecommerce")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-prod")
JWT_TTL_DAYS = 7

USE_MOCK = os.getenv("USE_MOCK") == "1"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent / "uploads"))).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_PLACEHOLDER_SECRETS = {
    "change-me-in-prod",
    "change-this-to-a-long-random-string",
    "demo-secret-please-change-in-prod-12345",
}
if not USE_MOCK and (not JWT_SECRET or JWT_SECRET in _PLACEHOLDER_SECRETS):
    raise RuntimeError(
        "JWT_SECRET is unset or still the placeholder. Set a long random value in .env "
        "before running in non-mock mode."
    )

if USE_MOCK:
    import mongomock
    client = mongomock.MongoClient()
    print("[mock] using in-memory MongoDB via mongomock")
else:
    from pymongo import MongoClient as _MC
    client = _MC(MONGO_URI, serverSelectionTimeoutMS=3000)

db = client[DB_NAME]
users = db["users"]
products = db["products"]
carts = db["carts"]
orders = db["orders"]
payments = db["payments"]


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CartItemIn(BaseModel):
    # product_id is required for POST but optional on PATCH (URL carries it).
    product_id: str | None = Field(default=None, min_length=1, max_length=64)
    qty: int = Field(default=1, ge=1, le=999)


class CheckoutCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    address: str = Field(min_length=1, max_length=500)


class PaymentIn(BaseModel):
    card_number: str = Field(min_length=12, max_length=19)
    card_holder: str = Field(min_length=1, max_length=80)
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2000, le=2100)
    cvc: str = Field(min_length=3, max_length=4)


class CheckoutIn(BaseModel):
    customer: CheckoutCustomer
    payment: "PaymentIn | None" = None


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    price: float = Field(gt=0)
    description: str = Field(default="", max_length=2000)
    image: str = Field(default="", max_length=500)
    stock: int = Field(default=0, ge=0, le=100000)
    rating: float = Field(default=4.0, ge=0, le=5)


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    price: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=2000)
    image: str | None = Field(default=None, max_length=500)
    stock: int | None = Field(default=None, ge=0, le=100000)
    rating: float | None = Field(default=None, ge=0, le=5)


class OrderStatusPatch(BaseModel):
    status: str = Field(min_length=1, max_length=40)


def parse_json(model_cls):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            data = request.get_json(silent=True) or {}
            try:
                g.payload = model_cls.model_validate(data)
            except ValidationError as e:
                return jsonify({"error": "invalid request", "details": e.errors()}), 400
            return fn(*a, **kw)
        return wrapper
    return deco


def oid(s):
    try:
        return ObjectId(s)
    except Exception:
        return None


def serialize(doc):
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


def serialize_user(u):
    if not u:
        return None
    return {
        "_id": str(u["_id"]),
        "name": u.get("name"),
        "email": u.get("email"),
        "is_admin": bool(u.get("is_admin", False)),
    }


def issue_token(user_id, is_admin=False):
    payload = {
        "sub": str(user_id),
        "is_admin": bool(is_admin),
        "iat": dt.datetime.now(timezone.utc),
        "exp": dt.datetime.now(timezone.utc) + dt.timedelta(days=JWT_TTL_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def auth_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "missing token"}), 401
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            g.user_id = payload["sub"]
            g.is_admin = bool(payload.get("is_admin", False))
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expired"}), 401
        except Exception:
            return jsonify({"error": "invalid token"}), 401
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @auth_required
    def wrapper(*a, **kw):
        if not g.is_admin:
            return jsonify({"error": "admin only"}), 403
        return fn(*a, **kw)
    return wrapper


def _release_stock(reserved):
    for prod_oid, qty in reserved:
        try:
            products.update_one({"_id": prod_oid}, {"$inc": {"stock": qty}})
        except Exception as e:
            print(f"[stock] failed to release {qty} for {prod_oid}: {e}")


@app.errorhandler(Exception)
def _on_unhandled(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    log.exception("unhandled error")
    return jsonify({"error": "internal server error"}), 500


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/api/auth/signup", methods=["POST"])
@limiter.limit("5 per minute")
@parse_json(SignupIn)
def signup():
    payload: SignupIn = g.payload
    name = payload.name.strip()
    email = payload.email.lower()
    password = payload.password
    if users.find_one({"email": email}):
        return jsonify({"error": "email already registered"}), 409
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    res = users.insert_one({"name": name, "email": email, "password": hashed, "is_admin": False})
    return jsonify({
        "token": issue_token(res.inserted_id, is_admin=False),
        "user": serialize_user({"_id": res.inserted_id, "name": name, "email": email, "is_admin": False}),
    }), 201


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
@parse_json(LoginIn)
def login():
    payload: LoginIn = g.payload
    email = payload.email.lower()
    u = users.find_one({"email": email})
    if not u or not bcrypt.checkpw(payload.password.encode(), u["password"]):
        return jsonify({"error": "invalid email or password"}), 401
    return jsonify({
        "token": issue_token(u["_id"], is_admin=u.get("is_admin", False)),
        "user": serialize_user(u),
    })


@app.route("/api/auth/me", methods=["GET"])
@auth_required
def me():
    u = users.find_one({"_id": oid(g.user_id)})
    if not u:
        return jsonify({"error": "user not found"}), 404
    return jsonify(serialize_user(u))


@app.route("/api/products", methods=["GET"])
def list_products():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "").strip()
    sort = request.args.get("sort", "")
    flt = {}
    if q:
        flt["name"] = {"$regex": re.escape(q), "$options": "i"}
    if cat and cat != "all":
        flt["category"] = cat
    cur = products.find(flt)
    items = [serialize(p) for p in cur]
    if sort == "price_asc":
        items.sort(key=lambda p: p["price"])
    elif sort == "price_desc":
        items.sort(key=lambda p: -p["price"])
    elif sort == "name":
        items.sort(key=lambda p: p["name"])
    return jsonify(items)


@app.route("/api/products/<id>", methods=["GET"])
def get_product(id):
    doc = products.find_one({"_id": oid(id)})
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(serialize(doc))


@app.route("/api/categories", methods=["GET"])
def categories():
    return jsonify(sorted({p.get("category", "Other") for p in products.find()}))


def _cart_doc(user_id):
    d = carts.find_one({"user_id": oid(user_id)})
    if not d:
        d = {"user_id": oid(user_id), "items": []}
    return d


@app.route("/api/cart", methods=["GET"])
@auth_required
def get_cart():
    return jsonify(_cart_doc(g.user_id).get("items", []))


@app.route("/api/cart", methods=["POST"])
@auth_required
@limiter.limit("60 per minute")
@parse_json(CartItemIn)
def add_to_cart():
    payload: CartItemIn = g.payload
    product_id = payload.product_id
    if not product_id:
        return jsonify({"error": "product_id required"}), 400
    qty = payload.qty
    p = products.find_one({"_id": oid(product_id)})
    if not p:
        return jsonify({"error": "product not found"}), 404
    if p.get("stock", 0) < qty:
        return jsonify({"error": "insufficient stock"}), 400

    cart = _cart_doc(g.user_id)
    items = cart.get("items", [])
    found = False
    for it in items:
        if it["product_id"] == product_id:
            if it["qty"] + qty > p["stock"]:
                return jsonify({"error": "exceeds stock"}), 400
            it["qty"] += qty
            found = True
            break
    if not found:
        items.append({
            "product_id": product_id,
            "name": p["name"],
            "price": p["price"],
            "image": p.get("image", ""),
            "qty": qty,
        })
    carts.update_one({"user_id": oid(g.user_id)}, {"$set": {"items": items}}, upsert=True)
    return jsonify(items), 200


@app.route("/api/cart/<product_id>", methods=["PATCH"])
@auth_required
@parse_json(CartItemIn)
def update_cart_item(product_id):
    payload: CartItemIn = g.payload
    qty = payload.qty
    p = products.find_one({"_id": oid(product_id)})
    if not p:
        return jsonify({"error": "product not found"}), 404
    if qty < 1:
        return remove_from_cart(product_id)
    if qty > p.get("stock", 0):
        return jsonify({"error": "exceeds stock"}), 400
    cart = _cart_doc(g.user_id)
    items = [it for it in cart.get("items", []) if it["product_id"] != product_id]
    items.append({
        "product_id": product_id,
        "name": p["name"],
        "price": p["price"],
        "image": p.get("image", ""),
        "qty": qty,
    })
    carts.update_one({"user_id": oid(g.user_id)}, {"$set": {"items": items}}, upsert=True)
    return jsonify(items)


@app.route("/api/cart/<product_id>", methods=["DELETE"])
@auth_required
def remove_from_cart(product_id):
    cart = _cart_doc(g.user_id)
    items = [it for it in cart.get("items", []) if it["product_id"] != product_id]
    carts.update_one({"user_id": oid(g.user_id)}, {"$set": {"items": items}}, upsert=True)
    return jsonify(items)


@app.route("/api/cart", methods=["DELETE"])
@auth_required
def clear_cart():
    carts.update_one({"user_id": oid(g.user_id)}, {"$set": {"items": []}}, upsert=True)
    return jsonify([])


def _detect_brand(pan: str) -> str:
    s = pan.lstrip()
    if s.startswith("4"):
        return "visa"
    if s[:2] in {"51", "52", "53", "54", "55"}:
        return "mastercard"
    if s[:2] in {"34", "37"}:
        return "amex"
    if s.startswith("6011") or s[:2] == "65":
        return "discover"
    return "card"


def _luhn_ok(pan: str) -> bool:
    digits = [int(c) for c in pan if c.isdigit()]
    if len(digits) < 12:
        return False
    checksum = 0
    parity = (len(digits) - 2) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _validate_payment(p: PaymentIn) -> tuple:
    pan = re.sub(r"\s+", "", p.card_number)
    if not _luhn_ok(pan):
        return {}, "card number failed validation"
    if not pan.isdigit():
        return {}, "card number must be digits"
    now = dt.datetime.now(timezone.utc)
    if p.exp_year < now.year or (p.exp_year == now.year and p.exp_month < now.month):
        return {}, "card expired"
    if not p.cvc.isdigit():
        return {}, "cvc must be digits"
    return {
        "brand": _detect_brand(pan),
        "last4": pan[-4:],
        "card_holder": p.card_holder.strip(),
        "exp": f"{p.exp_month:02d}/{p.exp_year % 100:02d}",
        "charged_at": now,
    }, None


@app.route("/api/orders", methods=["POST"])
@auth_required
@limiter.limit("10 per minute")
@parse_json(CheckoutIn)
def place_order():
    payload: CheckoutIn = g.payload
    customer = payload.customer.model_dump()
    cart = _cart_doc(g.user_id)
    items = cart.get("items", [])
    if not items:
        return jsonify({"error": "cart is empty"}), 400

    try:
        for it in items:
            int(it["qty"]); float(it["price"])
    except (TypeError, ValueError, KeyError):
        return jsonify({"error": "cart contains invalid line items"}), 400

    user_oid = oid(g.user_id)
    reserved = []
    for it in items:
        try:
            qty = int(it["qty"])
        except (TypeError, ValueError):
            _release_stock(reserved)
            return jsonify({"error": f"invalid qty for {it.get('name', 'item')}"}), 400
        prod_oid = oid(it["product_id"])
        updated = products.find_one_and_update(
            {"_id": prod_oid, "stock": {"$gte": qty}},
            {"$inc": {"stock": -qty}},
        )
        if not updated:
            _release_stock(reserved)
            return jsonify({"error": f"insufficient stock for {it['name']}"}), 409
        reserved.append((prod_oid, qty))

    try:
        total = sum(float(i["price"]) * int(i["qty"]) for i in items)
    except (TypeError, ValueError):
        _release_stock(reserved)
        return jsonify({"error": "cart contains invalid prices"}), 400

    payment_record = None
    status = "confirmed"
    if payload.payment is not None:
        stored, err = _validate_payment(payload.payment)
        if err:
            _release_stock(reserved)
            return jsonify({"error": err}), 400
        payment_record = stored
        status = "paid"

    order = {
        "user_id": user_oid,
        "items": items,
        "customer": customer,
        "total": total,
        "status": status,
        "payment": payment_record,
        "created_at": dt.datetime.now(timezone.utc),
    }
    try:
        res = orders.insert_one(order)
    except Exception:
        _release_stock(reserved)
        return jsonify({"error": "could not place order, please retry"}), 500

    carts.update_one({"user_id": user_oid}, {"$set": {"items": []}}, upsert=True)
    order["_id"] = str(res.inserted_id)
    order["user_id"] = str(order["user_id"])
    order["created_at"] = order["created_at"].isoformat()
    if order.get("payment") and isinstance(order["payment"].get("charged_at"), dt.datetime):
        order["payment"]["charged_at"] = order["payment"]["charged_at"].isoformat()
    return jsonify(order), 201


@app.route("/api/orders", methods=["GET"])
@auth_required
def my_orders():
    out = []
    for o in orders.find({"user_id": oid(g.user_id)}).sort("created_at", -1):
        o["_id"] = str(o["_id"])
        o["user_id"] = str(o["user_id"])
        if isinstance(o.get("created_at"), dt.datetime):
            o["created_at"] = o["created_at"].isoformat()
        if o.get("payment") and isinstance(o["payment"].get("charged_at"), dt.datetime):
            o["payment"]["charged_at"] = o["payment"]["charged_at"].isoformat()
        out.append(o)
    return jsonify(out)


ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@app.route("/api/admin/products", methods=["POST"])
@admin_required
@parse_json(ProductIn)
def admin_create_product():
    p: ProductIn = g.payload
    doc = p.model_dump()
    res = products.insert_one(doc)
    doc["_id"] = str(res.inserted_id)
    return jsonify(doc), 201


@app.route("/api/admin/products/<id>", methods=["PATCH"])
@admin_required
@parse_json(ProductPatch)
def admin_update_product(id):
    p: ProductPatch = g.payload
    update = {k: v for k, v in p.model_dump().items() if v is not None}
    if not update:
        return jsonify({"error": "no fields to update"}), 400
    res = products.find_one_and_update({"_id": oid(id)}, {"$set": update}, return_document=True)
    if not res:
        return jsonify({"error": "not found"}), 404
    return jsonify(serialize(res))


@app.route("/api/admin/products/<id>", methods=["DELETE"])
@admin_required
def admin_delete_product(id):
    res = products.delete_one({"_id": oid(id)})
    if res.deleted_count == 0:
        return jsonify({"error": "not found"}), 404
    carts.update_many({}, {"$pull": {"items": {"product_id": id}}})
    return jsonify({"deleted": id})


@app.route("/api/admin/products/<id>/image", methods=["POST"])
@admin_required
def admin_upload_image(id):
    if not products.find_one({"_id": oid(id)}, {"_id": 1}):
        return jsonify({"error": "product not found"}), 404
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "no file uploaded"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        return jsonify({"error": f"unsupported file type: {ext}"}), 400
    new_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / new_name
    f.save(dest)
    url = f"/uploads/{new_name}"
    products.update_one({"_id": oid(id)}, {"$set": {"image": url}})
    return jsonify({"image": url}), 201


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    candidate = (UPLOAD_DIR / filename).resolve()
    try:
        candidate.relative_to(UPLOAD_DIR)
    except ValueError:
        abort(404)
    if not candidate.is_file():
        abort(404)
    return send_from_directory(str(UPLOAD_DIR), filename)


VALID_STATUSES = {"pending", "confirmed", "paid", "shipped", "delivered", "cancelled"}


@app.route("/api/admin/orders", methods=["GET"])
@admin_required
def admin_list_orders():
    out = []
    for o in orders.find({}).sort("created_at", -1):
        o["_id"] = str(o["_id"])
        o["user_id"] = str(o["user_id"])
        if isinstance(o.get("created_at"), dt.datetime):
            o["created_at"] = o["created_at"].isoformat()
        if o.get("payment") and isinstance(o["payment"].get("charged_at"), dt.datetime):
            o["payment"]["charged_at"] = o["payment"]["charged_at"].isoformat()
        u = users.find_one({"_id": oid(o["user_id"])})
        if u:
            o["user"] = {"name": u.get("name"), "email": u.get("email")}
        out.append(o)
    return jsonify(out)


@app.route("/api/admin/orders/<id>", methods=["PATCH"])
@admin_required
@parse_json(OrderStatusPatch)
def admin_update_order_status(id):
    p: OrderStatusPatch = g.payload
    new_status = p.status.strip().lower()
    if new_status not in VALID_STATUSES:
        return jsonify({"error": f"invalid status; must be one of {sorted(VALID_STATUSES)}"}), 400
    o = orders.find_one_and_update(
        {"_id": oid(id)},
        {"$set": {"status": new_status}},
        return_document=True,
    )
    if not o:
        return jsonify({"error": "not found"}), 404
    o["_id"] = str(o["_id"])
    o["user_id"] = str(o["user_id"])
    if isinstance(o.get("created_at"), dt.datetime):
        o["created_at"] = o["created_at"].isoformat()
    return jsonify(o)


DEFAULT_PRODUCTS = [
    {"name": "Wireless Headphones", "category": "Audio",       "price": 79.99,
     "description": "Noise-cancelling over-ear headphones with 30h battery.",
     "image": "https://picsum.photos/seed/hp/400/300",  "stock": 12, "rating": 4.5},
    {"name": "Smart Watch",        "category": "Wearables",   "price": 149.00,
     "description": "Fitness tracking, heart-rate, and notifications.",
     "image": "https://picsum.photos/seed/sw/400/300",  "stock": 8,  "rating": 4.3},
    {"name": "Mechanical Keyboard","category": "Computing",   "price": 119.50,
     "description": "RGB backlit, hot-swappable mechanical switches.",
     "image": "https://picsum.photos/seed/kb/400/300",  "stock": 20, "rating": 4.8},
    {"name": "USB-C Hub",          "category": "Accessories", "price": 34.99,
     "description": "7-in-1 hub with HDMI, USB 3.0, and SD reader.",
     "image": "https://picsum.photos/seed/hub/400/300", "stock": 30, "rating": 4.2},
    {"name": "Desk Lamp",          "category": "Home",        "price": 24.00,
     "description": "Adjustable LED, 3 brightness modes, USB charging port.",
     "image": "https://picsum.photos/seed/lamp/400/300","stock": 15, "rating": 4.0},
    {"name": "Backpack",           "category": "Bags",        "price": 59.95,
     "description": "Water-resistant 25L backpack with laptop sleeve.",
     "image": "https://picsum.photos/seed/bp/400/300",  "stock": 10, "rating": 4.6},
    {"name": "Bluetooth Speaker",  "category": "Audio",       "price": 45.00,
     "description": "Portable speaker with 12h playback, IPX7 waterproof.",
     "image": "https://picsum.photos/seed/sp/400/300",  "stock": 25, "rating": 4.4},
    {"name": "Wireless Mouse",     "category": "Computing",   "price": 29.99,
     "description": "Ergonomic wireless mouse with silent clicks.",
     "image": "https://picsum.photos/seed/ms/400/300",  "stock": 40, "rating": 4.1},
]


def _seed_if_empty():
    if products.count_documents({}) == 0:
        products.insert_many(DEFAULT_PRODUCTS)
        print(f"[seed] inserted {products.count_documents({})} products")


def _ensure_default_admin():
    if not USE_MOCK:
        return
    email = os.getenv("ADMIN_EMAIL", "admin@minishop.io").lower()
    password = os.getenv("ADMIN_PASSWORD", "admin12345")
    if users.find_one({"email": email}):
        users.update_one({"email": email}, {"$set": {"is_admin": True}})
        return
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    users.insert_one({
        "name": "Store Admin",
        "email": email,
        "password": hashed,
        "is_admin": True,
    })
    print(f"[mock-admin] created default admin: {email} / {password}")


_seed_if_empty()
_ensure_default_admin()


@app.route("/")
def index():
    return jsonify({"service": "ecommerce-api", "status": "ok", "version": "1.1.0"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)