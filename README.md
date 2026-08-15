# Mini Shop — Full-Stack E-commerce

Flask + MongoDB REST API + vanilla HTML/CSS/JS frontend with **auth, per-user cart, order history, search, categories, sort, and dark mode**.

## Prerequisites
- Python 3.10+
- MongoDB running locally on `mongodb://localhost:27017/`

## Backend setup
```bash
cd D:\ecommerce\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python seed.py
python app.py
```
Runs on `http://localhost:5000`.

## Frontend
```bash
cd D:\ecommerce\frontend
python -m http.server 8080
```
Open `http://localhost:8080`.

## API Endpoints

### Auth
- `POST /api/auth/signup` — `{name,email,password}` → `{token,user}`
- `POST /api/auth/login` — `{email,password}` → `{token,user}`
- `GET  /api/auth/me` — current user (auth)

### Products
- `GET  /api/products?q=&category=&sort=` — list/filter/sort
- `GET  /api/products/:id` — single product
- `GET  /api/categories` — all categories

### Cart (auth required, per-user, auto-saved in MongoDB)
- `GET    /api/cart`
- `POST   /api/cart` — `{product_id, qty}`
- `PATCH  /api/cart/:product_id` — `{qty}`
- `DELETE /api/cart/:product_id`
- `DELETE /api/cart` — clear

### Orders (auth required)
- `POST /api/orders` — `{customer:{name,email,address}}` — places order, decrements stock, clears cart
- `GET  /api/orders` — current user order history

## Features
- ✅ JWT auth (7-day token, persisted across browser sessions)
- ✅ Per-user cart stored in MongoDB (auto-saves on every add/update)
- ✅ Cart auto-initializes on order placement
- ✅ Search, category filter, sort
- ✅ Product detail modal
- ✅ Stock validation (add-to-cart + checkout)
- ✅ Order history per user
- ✅ Dark mode toggle (persisted)
- ✅ Toast notifications
- ✅ Responsive design
