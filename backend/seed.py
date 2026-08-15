import os
from dotenv import load_dotenv

load_dotenv()
if os.getenv("USE_MOCK") == "1":
    import mongomock
    client = mongomock.MongoClient()
    print("[mock] seeding in-memory DB")
else:
    from pymongo import MongoClient
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))

db = client[os.getenv("DB_NAME", "ecommerce")]
db["products"].delete_many({})
db["products"].insert_many([
    {"name": "Wireless Headphones", "category": "Audio", "price": 79.99,
     "description": "Noise-cancelling over-ear headphones with 30h battery.",
     "image": "https://picsum.photos/seed/hp/400/300", "stock": 12, "rating": 4.5},
    {"name": "Smart Watch", "category": "Wearables", "price": 149.00,
     "description": "Fitness tracking, heart-rate, and notifications.",
     "image": "https://picsum.photos/seed/sw/400/300", "stock": 8, "rating": 4.3},
    {"name": "Mechanical Keyboard", "category": "Computing", "price": 119.50,
     "description": "RGB backlit, hot-swappable mechanical switches.",
     "image": "https://picsum.photos/seed/kb/400/300", "stock": 20, "rating": 4.8},
    {"name": "USB-C Hub", "category": "Accessories", "price": 34.99,
     "description": "7-in-1 hub with HDMI, USB 3.0, and SD reader.",
     "image": "https://picsum.photos/seed/hub/400/300", "stock": 30, "rating": 4.2},
    {"name": "Desk Lamp", "category": "Home", "price": 24.00,
     "description": "Adjustable LED, 3 brightness modes, USB charging port.",
     "image": "https://picsum.photos/seed/lamp/400/300", "stock": 15, "rating": 4.0},
    {"name": "Backpack", "category": "Bags", "price": 59.95,
     "description": "Water-resistant 25L backpack with laptop sleeve.",
     "image": "https://picsum.photos/seed/bp/400/300", "stock": 10, "rating": 4.6},
    {"name": "Bluetooth Speaker", "category": "Audio", "price": 45.00,
     "description": "Portable speaker with 12h playback, IPX7 waterproof.",
     "image": "https://picsum.photos/seed/sp/400/300", "stock": 25, "rating": 4.4},
    {"name": "Wireless Mouse", "category": "Computing", "price": 29.99,
     "description": "Ergonomic wireless mouse with silent clicks.",
     "image": "https://picsum.photos/seed/ms/400/300", "stock": 40, "rating": 4.1},
])
print(f"Seeded {db['products'].count_documents({})} products.")
