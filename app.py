"""Stockroom - Inventory / Product Management System (Flask + SQLite).

Mini project by Shashwat Patil, Robotics and AI.
"""
import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REORDER_LEVEL = 10

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get("STOCKROOM_DB", os.path.join(BASE_DIR, "stockroom.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code  TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL,
    category_id   INTEGER NOT NULL REFERENCES categories(id),
    quantity      INTEGER NOT NULL CHECK (quantity >= 0),
    price         REAL    NOT NULL CHECK (price >= 0),
    reorder_level INTEGER NOT NULL DEFAULT 10 CHECK (reorder_level >= 0),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    change     INTEGER NOT NULL,
    note       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

DEMO_PRODUCTS = [
    ("ELC-1001", "USB-C Charging Cable 1m", "Electronics", 120, 349.00, 25),
    ("ELC-1002", "Wireless Mouse", "Electronics", 8, 799.00, 15),
    ("ELC-1003", "Bluetooth Earbuds", "Electronics", 0, 1499.00, 10),
    ("ELC-1004", "Power Bank 10000mAh", "Electronics", 34, 1199.00, 12),
    ("STN-2001", "A4 Notebook (200 pages)", "Stationery", 240, 65.00, 50),
    ("STN-2002", "Gel Pen Blue (Pack of 10)", "Stationery", 18, 90.00, 30),
    ("STN-2003", "Sticky Notes 3x3", "Stationery", 75, 45.00, 20),
    ("GRC-3001", "Basmati Rice 5kg", "Grocery", 42, 540.00, 20),
    ("GRC-3002", "Sunflower Oil 1L", "Grocery", 6, 165.00, 15),
    ("GRC-3003", "Green Tea (25 bags)", "Grocery", 55, 210.00, 15),
    ("HSE-4001", "LED Bulb 9W", "Household", 150, 99.00, 40),
    ("HSE-4002", "Steel Water Bottle 750ml", "Household", 27, 420.00, 10),
]


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db(seed_demo=True):
    """Create tables on first run; optionally load sample data into an empty DB."""
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    empty = db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0
    if seed_demo and empty:
        for code, name, cat, qty, price, reorder in DEMO_PRODUCTS:
            db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
            cat_id = db.execute("SELECT id FROM categories WHERE name = ?", (cat,)).fetchone()[0]
            cur = db.execute(
                "INSERT INTO products (product_code, name, category_id, quantity, price, reorder_level, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, name, cat_id, qty, price, reorder, now()),
            )
            db.execute(
                "INSERT INTO stock_movements (product_id, change, note, created_at) VALUES (?, ?, ?, ?)",
                (cur.lastrowid, qty, "Opening stock", now()),
            )
    db.commit()
    db.close()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
PRODUCT_SELECT = """
    SELECT p.id, p.product_code, p.name, c.name AS category, p.quantity, p.price,
           p.reorder_level, p.created_at,
           CASE WHEN p.quantity = 0 THEN 'out'
                WHEN p.quantity <= p.reorder_level THEN 'low'
                ELSE 'ok' END AS status
    FROM products p JOIN categories c ON c.id = p.category_id
"""


def error(message, status=400, field=None):
    body = {"error": message}
    if field:
        body["field"] = field
    return jsonify(body), status


def parse_int(value, label, minimum=0):
    """Return (int, None) or (None, error message). Rejects floats, bools and text."""
    if isinstance(value, bool):
        return None, f"{label} must be a whole number."
    if isinstance(value, str):
        value = value.strip()
        if not re.fullmatch(r"-?\d+", value):
            return None, f"{label} must be a whole number."
    elif not isinstance(value, int):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        else:
            return None, f"{label} must be a whole number."
    value = int(value)
    if value < minimum:
        return None, f"{label} cannot be less than {minimum}."
    return value, None


def parse_price(value):
    if isinstance(value, bool) or value is None or value == "":
        return None, "Price is required."
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None, "Price must be a number."
    if price != price or price in (float("inf"), float("-inf")):
        return None, "Price must be a number."
    if price < 0:
        return None, "Price cannot be negative."
    return round(price, 2), None


def get_or_create_category(db, name):
    db.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    return db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()["id"]


def validate_product(data, partial=False):
    """Validate a product payload. Returns (clean_dict, error_response)."""
    clean = {}
    code = (data.get("product_code") or "").strip()
    if not partial or "product_code" in data:
        if not code:
            return None, error("Product ID is required.", field="product_code")
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,20}", code):
            return None, error("Product ID must be 2-20 letters, digits, '-' or '_'.", field="product_code")
        clean["product_code"] = code.upper()

    if not partial or "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return None, error("Product name is required.", field="name")
        if len(name) > 80:
            return None, error("Product name must be 80 characters or fewer.", field="name")
        clean["name"] = name

    if not partial or "category" in data:
        category = (data.get("category") or "").strip()
        if not category:
            return None, error("Category is required.", field="category")
        if len(category) > 40:
            return None, error("Category must be 40 characters or fewer.", field="category")
        clean["category"] = category

    if not partial or "price" in data:
        price, msg = parse_price(data.get("price"))
        if msg:
            return None, error(msg, field="price")
        clean["price"] = price

    if "quantity" in data or not partial:
        qty, msg = parse_int(data.get("quantity", ""), "Quantity")
        if msg:
            return None, error(msg, field="quantity")
        clean["quantity"] = qty

    if "reorder_level" in data and data["reorder_level"] != "":
        lvl, msg = parse_int(data["reorder_level"], "Reorder level")
        if msg:
            return None, error(msg, field="reorder_level")
        clean["reorder_level"] = lvl
    elif not partial:
        clean["reorder_level"] = DEFAULT_REORDER_LEVEL
    return clean, None


def fetch_product(db, product_id):
    return db.execute(PRODUCT_SELECT + " WHERE p.id = ?", (product_id,)).fetchone()


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/products")
def list_products():
    """List products. Optional filters: q (name / ID / category), category, status."""
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    status = (request.args.get("status") or "").strip()

    sql, params, where = PRODUCT_SELECT, [], []
    if q:
        like = f"%{q}%"
        where.append("(p.name LIKE ? OR p.product_code LIKE ? OR c.name LIKE ?)")
        params += [like, like, like]
    if category:
        where.append("c.name = ? COLLATE NOCASE")
        params.append(category)
    if status in ("ok", "low", "out"):
        if status == "out":
            where.append("p.quantity = 0")
        elif status == "low":
            where.append("p.quantity > 0 AND p.quantity <= p.reorder_level")
        else:
            where.append("p.quantity > p.reorder_level")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.name COLLATE NOCASE"
    rows = get_db().execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/products/<int:product_id>")
def get_product(product_id):
    row = fetch_product(get_db(), product_id)
    if row is None:
        return error("Product not found.", 404)
    return jsonify(dict(row))


@app.post("/api/products")
def add_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send the product details as JSON.")
    clean, err = validate_product(data)
    if err:
        return err
    db = get_db()
    if db.execute("SELECT 1 FROM products WHERE product_code = ?", (clean["product_code"],)).fetchone():
        return error(f"Product ID {clean['product_code']} already exists.", 409, "product_code")
    cat_id = get_or_create_category(db, clean["category"])
    cur = db.execute(
        "INSERT INTO products (product_code, name, category_id, quantity, price, reorder_level, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (clean["product_code"], clean["name"], cat_id, clean["quantity"], clean["price"],
         clean["reorder_level"], now()),
    )
    db.execute(
        "INSERT INTO stock_movements (product_id, change, note, created_at) VALUES (?, ?, ?, ?)",
        (cur.lastrowid, clean["quantity"], "Opening stock", now()),
    )
    db.commit()
    return jsonify(dict(fetch_product(db, cur.lastrowid))), 201


@app.put("/api/products/<int:product_id>")
def update_product(product_id):
    """Edit name, category, price and reorder level. Stock changes go through /stock."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send the product details as JSON.")
    db = get_db()
    if db.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
        return error("Product not found.", 404)
    data = {k: v for k, v in data.items() if k in ("name", "category", "price", "reorder_level")}
    if not data:
        return error("Nothing to update.")
    clean, err = validate_product(data, partial=True)
    if err:
        return err
    sets, params = [], []
    if "category" in clean:
        sets.append("category_id = ?")
        params.append(get_or_create_category(db, clean["category"]))
    for col in ("name", "price", "reorder_level"):
        if col in clean:
            sets.append(f"{col} = ?")
            params.append(clean[col])
    db.execute(f"UPDATE products SET {', '.join(sets)} WHERE id = ?", params + [product_id])
    db.commit()
    return jsonify(dict(fetch_product(db, product_id)))


@app.patch("/api/products/<int:product_id>/stock")
def update_stock(product_id):
    """Adjust stock by a signed `change`, or set an absolute `quantity`."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send the stock update as JSON.")
    db = get_db()
    row = db.execute("SELECT quantity, name FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        return error("Product not found.", 404)

    current = row["quantity"]
    if "quantity" in data:
        new_qty, msg = parse_int(data["quantity"], "Quantity")
        if msg:
            return error(msg, field="quantity")
    elif "change" in data:
        change, msg = parse_int(data["change"], "Change", minimum=-10**9)
        if msg:
            return error(msg, field="change")
        new_qty = current + change
        if new_qty < 0:
            return error(
                f"Cannot remove {abs(change)} {'unit' if abs(change) == 1 else 'units'}: "
                f"only {current} in stock for {row['name']}.",
                400, "change",
            )
    else:
        return error("Provide either 'change' or 'quantity'.")

    delta = new_qty - current
    if delta != 0:
        note = (data.get("note") or "").strip()[:120] or ("Stock added" if delta > 0 else "Stock removed")
        db.execute("UPDATE products SET quantity = ? WHERE id = ?", (new_qty, product_id))
        db.execute(
            "INSERT INTO stock_movements (product_id, change, note, created_at) VALUES (?, ?, ?, ?)",
            (product_id, delta, note, now()),
        )
        db.commit()
    return jsonify(dict(fetch_product(db, product_id)))


@app.delete("/api/products/<int:product_id>")
def delete_product(product_id):
    db = get_db()
    cur = db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    if cur.rowcount == 0:
        return error("Product not found.", 404)
    return jsonify({"deleted": product_id})


@app.get("/api/products/<int:product_id>/history")
def product_history(product_id):
    db = get_db()
    if db.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
        return error("Product not found.", 404)
    rows = db.execute(
        "SELECT change, note, created_at FROM stock_movements WHERE product_id = ? "
        "ORDER BY id DESC LIMIT 20",
        (product_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/categories")
def list_categories():
    rows = get_db().execute(
        "SELECT c.name FROM categories c WHERE EXISTS (SELECT 1 FROM products p WHERE p.category_id = c.id) "
        "ORDER BY c.name COLLATE NOCASE"
    ).fetchall()
    return jsonify([r["name"] for r in rows])


@app.get("/api/summary")
def summary():
    """Headline numbers plus the list of products that need restocking."""
    db = get_db()
    totals = db.execute(
        "SELECT COUNT(*) AS products, COALESCE(SUM(quantity), 0) AS units, "
        "COALESCE(SUM(quantity * price), 0) AS value, "
        "COALESCE(SUM(quantity = 0), 0) AS out_count, "
        "COALESCE(SUM(quantity > 0 AND quantity <= reorder_level), 0) AS low_count, "
        "COALESCE(SUM(quantity > reorder_level), 0) AS ok_count FROM products"
    ).fetchone()
    alerts = db.execute(
        PRODUCT_SELECT + " WHERE p.quantity <= p.reorder_level ORDER BY p.quantity ASC, p.name COLLATE NOCASE"
    ).fetchall()
    return jsonify({**dict(totals), "alerts": [dict(a) for a in alerts]})


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return error("Route not found.", 404)
    return render_template("index.html"), 404


@app.errorhandler(405)
def bad_method(_e):
    return error("Method not allowed.", 405)


init_db(seed_demo=os.environ.get("SEED_DEMO", "1") != "0")

if __name__ == "__main__":
    app.run(debug=True)
