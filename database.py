"""Database helpers for ShopLite.

Creates the SQLite schema, hands out connections, and seeds demo data once.
No ORM is used - every query in the project is plain sqlite3 with parameters.
"""

import os
import sqlite3

from flask import g
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# SHOPLITE_DB lets you point the app at another file (useful for tests).
DB_PATH = os.environ.get("SHOPLITE_DB", os.path.join(BASE_DIR, "marketplace.db"))

CATEGORIES = ["Electronics", "Books", "Home & Kitchen", "Fashion", "Sports", "Beauty"]

# Emoji used as the product image placeholder in the UI.
CATEGORY_EMOJI = {
    "Electronics": "💻",
    "Books": "📚",
    "Home & Kitchen": "🍳",
    "Fashion": "👕",
    "Sports": "⚽",
    "Beauty": "💄",
}
FALLBACK_EMOJI = "📦"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('customer','seller')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seller_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  category TEXT NOT NULL,
  price REAL NOT NULL CHECK (price > 0),
  stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES users(id),
  total REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'Pending'
    CHECK (status IN ('Pending','Processing','Shipped','Delivered','Cancelled')),
  shipping_address TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  price_at_purchase REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
"""

# username, plain password (hashed on insert), role
SEED_USERS = [
    ("seller1", "seller123", "seller"),
    ("seller2", "seller123", "seller"),
    ("customer1", "cust123", "customer"),
]

# seller username, name, category, price, stock, description
SEED_PRODUCTS = [
    ("seller1", "Wireless Mouse M200", "Electronics", 799.00, 25,
     "Ergonomic 2.4GHz wireless mouse with silent clicks."),
    ("seller1", "Mechanical Keyboard K10", "Electronics", 2499.00, 15,
     "Tenkeyless mechanical keyboard, blue switches, RGB."),
    ("seller1", "USB-C Fast Charger 65W", "Electronics", 1299.00, 40,
     "GaN fast charger, dual USB-C, PD 3.0."),
    ("seller2", "Clean Code by Robert Martin", "Books", 549.00, 30,
     "Classic handbook of agile software craftsmanship."),
    ("seller2", "Flask Web Development Guide", "Books", 399.00, 18,
     "Practical guide to Python and Flask web apps."),
    ("seller2", "Steel Water Bottle 1L", "Home & Kitchen", 349.00, 60,
     "Insulated bottle, hot/cold for 12 hours."),
    ("seller1", "Non-stick Frying Pan 24cm", "Home & Kitchen", 699.00, 22,
     "Induction-compatible pan, heat-resistant handle."),
    ("seller2", "Cotton Round-Neck T-Shirt", "Fashion", 299.00, 80,
     "100% combed cotton, pre-shrunk."),
    ("seller2", "Running Shoes FlexFit", "Fashion", 1899.00, 12,
     "Lightweight running shoes, breathable mesh."),
    ("seller1", "Yoga Mat 6mm Anti-Slip", "Sports", 599.00, 35,
     "High-density anti-slip mat with carrying strap."),
    ("seller1", "Adjustable Dumbbell Set 10kg", "Sports", 2299.00, 4,
     "Space-saving dumbbells, 2kg-10kg per hand."),
    ("seller2", "Vitamin C Face Serum 30ml", "Beauty", 749.00, 20,
     "Brightening serum, 10% Vitamin C."),
]


def connect():
    """Open a new SQLite connection with row access by column name.

    isolation_level=None puts the connection in autocommit mode, so the
    checkout route can control its own BEGIN/COMMIT/ROLLBACK transaction.
    """
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Return the connection for the current request (one per request)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(exception=None):
    """Close the request connection - registered as a Flask teardown hook."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables/indexes if needed, then seed demo data on a fresh file."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        seed_if_empty(conn)
    finally:
        conn.close()


def seed_if_empty(conn):
    """Insert the demo users and products, but only when the DB has no users."""
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return

    try:
        conn.execute("BEGIN")
        user_ids = {}
        for username, password, role in SEED_USERS:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
            user_ids[username] = cursor.lastrowid

        for seller, name, category, price, stock, description in SEED_PRODUCTS:
            conn.execute(
                """INSERT INTO products
                       (seller_id, name, description, category, price, stock)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_ids[seller], name, description, category, price, stock),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
