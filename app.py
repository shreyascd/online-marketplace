"""ShopLite - a small online marketplace built with Flask + SQLite + Jinja2.

All routes live here, grouped by feature. Database access is plain sqlite3
with parameterized queries; the schema and seed data are in database.py.
"""

import os
import sqlite3
from functools import wraps

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from database import (CATEGORIES, CATEGORY_EMOJI, FALLBACK_EMOJI, close_db,
                      get_db, init_db)

app = Flask(__name__)
# Set SECRET_KEY in the environment (e.g. Replit Secrets) for real deployments.
app.secret_key = os.environ.get("SECRET_KEY", "shoplite-dev-secret-key")
app.teardown_appcontext(close_db)

ORDER_STATUSES = ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]
STATUS_CLASSES = {
    "Pending": "text-bg-warning",
    "Processing": "text-bg-info",
    "Shipped": "text-bg-primary",
    "Delivered": "text-bg-success",
    "Cancelled": "text-bg-secondary",
}

# Whitelisted ORDER BY fragments - the sort form value is never put into SQL.
SORT_ORDERS = {
    "newest": "p.created_at DESC, p.id DESC",
    "price_asc": "p.price ASC, p.id ASC",
    "price_desc": "p.price DESC, p.id ASC",
    "name_asc": "p.name COLLATE NOCASE ASC",
}
SORT_OPTIONS = [
    ("newest", "Newest"),
    ("price_asc", "Price: low to high"),
    ("price_desc", "Price: high to low"),
    ("name_asc", "Name A-Z"),
]


# --------------------------------------------------------------------------
# Template helpers
# --------------------------------------------------------------------------
@app.template_filter("money")
def money(value):
    """Format a number as rupees with two decimals, e.g. 1299 -> ₹1,299.00."""
    return f"₹{float(value):,.2f}"


@app.template_filter("emoji")
def emoji(category):
    """Pick the category emoji used as the product image placeholder."""
    return CATEGORY_EMOJI.get(category, FALLBACK_EMOJI)


@app.context_processor
def inject_layout_data():
    """Values every template needs: navbar state, flash badge count, lookups."""
    cart = session.get("cart", {})
    return {
        "user": session.get("user"),
        "cart_count": sum(cart.values()),
        "CATEGORIES": CATEGORIES,
        "STATUS_CLASSES": STATUS_CLASSES,
    }


# --------------------------------------------------------------------------
# Session cart helpers
# --------------------------------------------------------------------------
def read_cart():
    """Read the session cart as {int product_id: int quantity}."""
    cart = {}
    for key, quantity in session.get("cart", {}).items():
        try:
            cart[int(key)] = int(quantity)
        except (TypeError, ValueError):
            continue
    return cart


def write_cart(cart):
    """Store the cart back in the session (JSON needs string keys)."""
    session["cart"] = {str(pid): qty for pid, qty in cart.items() if qty > 0}


def cart_items():
    """Join cart quantities with live product rows.

    Archived/deleted products and out-of-stock items are dropped, and any
    quantity above current stock is clamped - both with a warning flash.
    Returns (items, grand_total) where each item is {product, quantity, subtotal}.
    """
    cart = read_cart()
    db = get_db()
    items = []
    kept = {}

    if cart:
        placeholders = ", ".join("?" for _ in cart)
        rows = db.execute(
            f"SELECT * FROM products WHERE is_active = 1 AND id IN ({placeholders})",
            tuple(cart.keys()),
        ).fetchall()
        products = {row["id"]: row for row in rows}

        for product_id, quantity in cart.items():
            product = products.get(product_id)
            if product is None or product["stock"] <= 0:
                flash("An item in your cart is no longer available and was removed.", "warning")
                continue
            if quantity > product["stock"]:
                quantity = product["stock"]
                flash(f"Only {product['stock']} in stock — quantity adjusted.", "warning")
            kept[product_id] = quantity
            items.append({
                "product": product,
                "quantity": quantity,
                "subtotal": product["price"] * quantity,
            })

        if kept != cart:
            write_cart(kept)

    items.sort(key=lambda item: item["product"]["name"].lower())
    return items, sum(item["subtotal"] for item in items)


def cart_total_units(items):
    """Total number of units in the cart (used on the checkout summary)."""
    return sum(item["quantity"] for item in items)


# --------------------------------------------------------------------------
# Access control helpers
# --------------------------------------------------------------------------
def login_required(view):
    """Send guests to the login page, returning them to the requested path."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            flash("Please log in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def seller_required(view):
    """Allow only signed-in sellers; other roles get a message, not a 403 page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = session.get("user")
        if not user:
            flash("Please log in as a seller to continue.", "info")
            return redirect(url_for("login", next=request.path))
        if user["role"] != "seller":
            flash("Seller access only.", "danger")
            return redirect(url_for("index"))
        return view(*args, **kwargs)
    return wrapped


def safe_next(target, fallback):
    """Only follow local redirect targets (blocks ?next=https://evil.example)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return fallback


# ==========================================================================
# 1. Product browsing
# ==========================================================================
@app.route("/")
def index():
    """Product grid with search, category filter and sorting combined."""
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "newest").strip()
    if category not in CATEGORIES:
        category = ""
    if sort not in SORT_ORDERS:
        sort = "newest"

    sql = """SELECT p.*, u.username AS seller_name
               FROM products p
               JOIN users u ON u.id = p.seller_id
              WHERE p.is_active = 1"""
    params = []
    if query:
        sql += " AND (p.name LIKE ? OR p.description LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like])
    if category:
        sql += " AND p.category = ?"
        params.append(category)
    sql += " ORDER BY " + SORT_ORDERS[sort]

    products = get_db().execute(sql, params).fetchall()
    return render_template(
        "index.html",
        products=products,
        query=query,
        category=category,
        sort=sort,
        sort_options=SORT_OPTIONS,
        has_filters=bool(query or category or sort != "newest"),
    )


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    """Single product page; archived or unknown ids give a 404."""
    product = get_db().execute(
        """SELECT p.*, u.username AS seller_name
             FROM products p
             JOIN users u ON u.id = p.seller_id
            WHERE p.id = ? AND p.is_active = 1""",
        (product_id,),
    ).fetchone()
    if product is None:
        abort(404)
    return render_template("product_detail.html", product=product)


# ==========================================================================
# 2. Cart (session based, works for guests too)
# ==========================================================================
@app.route("/cart")
def cart():
    items, total = cart_items()
    return render_template("cart.html", items=items, total=total)


@app.route("/cart/add/<int:product_id>", methods=["POST"])
def cart_add(product_id):
    db = get_db()
    product = db.execute(
        "SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)
    ).fetchone()
    if product is None:
        abort(404)

    try:
        quantity = int(request.form.get("quantity", "1"))
    except (TypeError, ValueError):
        flash("Quantity must be a whole number.", "danger")
        return redirect(url_for("product_detail", product_id=product_id))

    if quantity < 1:
        flash("Quantity must be at least 1.", "danger")
        return redirect(url_for("product_detail", product_id=product_id))
    if product["stock"] <= 0:
        flash(f"{product['name']} is out of stock.", "danger")
        return redirect(url_for("product_detail", product_id=product_id))

    cart = read_cart()
    new_quantity = cart.get(product_id, 0) + quantity
    if new_quantity > product["stock"]:
        new_quantity = product["stock"]
        flash(f"Only {product['stock']} in stock — quantity adjusted.", "warning")
    cart[product_id] = new_quantity
    write_cart(cart)

    flash(f"Added {product['name']} to your cart.", "success")
    return redirect(safe_next(request.form.get("next"), url_for("cart")))


@app.route("/cart/update/<int:product_id>", methods=["POST"])
def cart_update(product_id):
    cart = read_cart()
    if product_id not in cart:
        flash("That item is not in your cart.", "warning")
        return redirect(url_for("cart"))

    try:
        quantity = int(request.form.get("quantity", "0"))
    except (TypeError, ValueError):
        flash("Quantity must be a whole number.", "danger")
        return redirect(url_for("cart"))

    product = get_db().execute(
        "SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)
    ).fetchone()
    if product is None:
        cart.pop(product_id, None)
        write_cart(cart)
        flash("That product is no longer available.", "warning")
        return redirect(url_for("cart"))

    if quantity < 1:
        flash("Quantity must be at least 1. Use Remove to delete the item.", "danger")
        return redirect(url_for("cart"))

    if quantity > product["stock"]:
        quantity = product["stock"]
        flash(f"Only {product['stock']} in stock — quantity adjusted.", "warning")

    cart[product_id] = quantity
    write_cart(cart)
    flash("Cart updated.", "success")
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:product_id>", methods=["POST"])
def cart_remove(product_id):
    cart = read_cart()
    cart.pop(product_id, None)
    write_cart(cart)
    flash("Item removed from your cart.", "info")
    return redirect(url_for("cart"))


# ==========================================================================
# 3. Checkout and orders
# ==========================================================================
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    """Validate the address and cart, then create the order atomically."""
    items, total = cart_items()
    if not items:
        flash("Your cart is empty — add a product before checking out.", "info")
        return redirect(url_for("cart"))

    if request.method == "POST":
        address = request.form.get("shipping_address", "").strip()
        if len(address) < 10:
            flash("Shipping address is required and must be at least 10 characters.", "danger")
            return render_template("checkout.html", items=items, total=total, address=address)

        user = session["user"]
        db = get_db()
        quantities = {item["product"]["id"]: item["quantity"] for item in items}

        try:
            # One transaction: every stock decrement and both inserts must succeed.
            db.execute("BEGIN IMMEDIATE")
            prices = {}
            charged_total = 0.0
            for product_id, quantity in quantities.items():
                row = db.execute(
                    "SELECT name, price, stock FROM products WHERE id = ? AND is_active = 1",
                    (product_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("An item in your cart is no longer available.")
                if row["stock"] < quantity:
                    raise ValueError(
                        f"Only {row['stock']} of {row['name']} left in stock. Please update your cart."
                    )

                # Conditional decrement: 0 rows affected means someone else
                # bought the last unit between our check and this update.
                updated = db.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                    (quantity, product_id, quantity),
                )
                if updated.rowcount != 1:
                    raise ValueError(f"{row['name']} just went out of stock. Please try again.")

                prices[product_id] = row["price"]
                charged_total += row["price"] * quantity

            cursor = db.execute(
                """INSERT INTO orders (customer_id, total, shipping_address)
                   VALUES (?, ?, ?)""",
                (user["id"], round(charged_total, 2), address),
            )
            order_id = cursor.lastrowid

            for product_id, quantity in quantities.items():
                # price_at_purchase snapshots the price so later edits do not
                # rewrite the history of this order.
                db.execute(
                    """INSERT INTO order_items
                           (order_id, product_id, quantity, price_at_purchase)
                       VALUES (?, ?, ?, ?)""",
                    (order_id, product_id, quantity, prices[product_id]),
                )
            db.execute("COMMIT")
        except ValueError as exc:
            db.execute("ROLLBACK")
            flash(str(exc), "danger")
            return render_template("checkout.html", items=items, total=total, address=address)
        except sqlite3.Error:
            try:
                db.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            flash("We could not place your order. Please try again.", "danger")
            return render_template("checkout.html", items=items, total=total, address=address)

        session.pop("cart", None)
        flash("Order placed successfully!", "success")
        return redirect(url_for("order_detail", order_id=order_id, placed=1))

    return render_template("checkout.html", items=items, total=total, address="")


@app.route("/orders")
@login_required
def orders():
    """The signed-in customer's own order history."""
    user = session["user"]
    order_rows = get_db().execute(
        """SELECT o.*,
                  COALESCE((SELECT SUM(oi.quantity)
                              FROM order_items oi
                             WHERE oi.order_id = o.id), 0) AS units
             FROM orders o
            WHERE o.customer_id = ?
            ORDER BY o.id DESC""",
        (user["id"],),
    ).fetchall()
    return render_template("orders.html", orders=order_rows)


@app.route("/orders/<int:order_id>")
def order_detail(order_id):
    """Order confirmation/receipt. Customers see only their own orders."""
    user = session.get("user")
    if not user:
        flash("Please log in to view that order.", "info")
        return redirect(url_for("login", next=url_for("order_detail", order_id=order_id)))

    db = get_db()
    order_row = db.execute(
        """SELECT o.*, u.username AS customer_name
             FROM orders o
             JOIN users u ON u.id = o.customer_id
            WHERE o.id = ?""",
        (order_id,),
    ).fetchone()
    if order_row is None:
        abort(404)
    if user["role"] == "customer" and order_row["customer_id"] != user["id"]:
        flash("You can only view your own orders.", "danger")
        return redirect(url_for("orders"))

    item_rows = db.execute(
        """SELECT oi.*, p.name AS product_name, p.category
             FROM order_items oi
             JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
            ORDER BY oi.id""",
        (order_id,),
    ).fetchall()
    return render_template(
        "order_detail.html",
        order=order_row,
        items=item_rows,
        placed=request.args.get("placed") == "1",
    )


# ==========================================================================
# 4. Authentication
# ==========================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next", "")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("login.html", username=username, next=next_url)

        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        # Same message for unknown user and wrong password (no account probing).
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "danger")
            return render_template("login.html", username=username, next=next_url)

        session["user"] = {"id": user["id"], "username": user["username"], "role": user["role"]}
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(safe_next(next_url, url_for("index")))

    return render_template("login.html", username="", next=next_url)


@app.route("/register", methods=["GET", "POST"])
def register():
    form = {"username": "", "role": "customer"}
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        role = request.form.get("role", "customer")
        form = {"username": username, "role": role}

        errors = []
        if len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if role not in ("customer", "seller"):
            errors.append("Choose a valid account type.")

        if not errors:
            db = get_db()
            try:
                cursor = db.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), role),
                )
            except sqlite3.IntegrityError:
                errors.append("That username is already taken.")
            else:
                session["user"] = {
                    "id": cursor.lastrowid,
                    "username": username,
                    "role": role,
                }
                flash(f"Account created — welcome, {username}!", "success")
                return redirect(url_for("index"))

        for message in errors:
            flash(message, "danger")

    return render_template("register.html", form=form)


@app.route("/logout")
def logout():
    # Only the user entry is removed: the cart survives logging out.
    session.pop("user", None)
    flash("You are logged out. Your cart is saved for next time.", "info")
    return redirect(url_for("index"))


# ==========================================================================
# 5. Seller area
# ==========================================================================
@app.route("/seller")
@seller_required
def seller_dashboard():
    user = session["user"]
    db = get_db()
    stats = {
        "active_listings": db.execute(
            "SELECT COUNT(*) AS c FROM products WHERE seller_id = ? AND is_active = 1",
            (user["id"],),
        ).fetchone()["c"],
        "units_in_stock": db.execute(
            "SELECT COALESCE(SUM(stock), 0) AS units FROM products WHERE seller_id = ? AND is_active = 1",
            (user["id"],),
        ).fetchone()["units"],
        # Orders and revenue are marketplace-wide, matching the seller orders page.
        "total_orders": db.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"],
        "pending_orders": db.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE status = 'Pending'"
        ).fetchone()["c"],
        "total_revenue": db.execute(
            "SELECT COALESCE(SUM(total), 0) AS revenue FROM orders"
        ).fetchone()["revenue"],
    }
    products = db.execute(
        """SELECT * FROM products
            WHERE seller_id = ?
            ORDER BY is_active DESC, id DESC""",
        (user["id"],),
    ).fetchall()
    return render_template("seller_dashboard.html", stats=stats, products=products)


def parse_product_form(form):
    """Validate the product form; returns (values, errors, price, stock)."""
    values = {
        "name": form.get("name", "").strip(),
        "category": form.get("category", "").strip(),
        "price": form.get("price", "").strip(),
        "stock": form.get("stock", "").strip(),
        "description": form.get("description", "").strip(),
    }
    errors = []

    if not values["name"]:
        errors.append("Product name is required.")
    elif len(values["name"]) > 100:
        errors.append("Product name must be 100 characters or fewer.")

    if values["category"] not in CATEGORIES:
        errors.append("Choose a category from the list.")

    price = None
    try:
        price = float(values["price"])
    except ValueError:
        errors.append("Price must be a number.")
    else:
        if price <= 0:
            errors.append("Price must be greater than 0.")

    stock = None
    try:
        stock = int(values["stock"])
    except ValueError:
        errors.append("Stock must be a whole number.")
    else:
        if stock < 0:
            errors.append("Stock cannot be negative.")

    return values, errors, price, stock


@app.route("/seller/products/new", methods=["GET", "POST"])
@seller_required
def product_new():
    form = {"name": "", "category": "", "price": "", "stock": "", "description": ""}
    if request.method == "POST":
        form, errors, price, stock = parse_product_form(request.form)
        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            db = get_db()
            db.execute(
                """INSERT INTO products (seller_id, name, description, category, price, stock)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session["user"]["id"], form["name"], form["description"],
                 form["category"], round(price, 2), stock),
            )
            flash(f"Added {form['name']} to your listings.", "success")
            return redirect(url_for("seller_dashboard"))

    return render_template("product_form.html", form=form, mode="new", product=None)


@app.route("/seller/products/<int:product_id>/edit", methods=["GET", "POST"])
@seller_required
def product_edit(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        abort(404)
    if product["seller_id"] != session["user"]["id"]:
        flash("You can only edit your own products.", "danger")
        return redirect(url_for("seller_dashboard"))

    form = {
        "name": product["name"],
        "category": product["category"],
        "price": f"{product['price']:.2f}",
        "stock": str(product["stock"]),
        "description": product["description"] or "",
    }
    if request.method == "POST":
        form, errors, price, stock = parse_product_form(request.form)
        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            db.execute(
                """UPDATE products
                      SET name = ?, description = ?, category = ?, price = ?, stock = ?
                    WHERE id = ? AND seller_id = ?""",
                (form["name"], form["description"], form["category"],
                 round(price, 2), stock, product_id, session["user"]["id"]),
            )
            flash("Product updated.", "success")
            return redirect(url_for("seller_dashboard"))

    return render_template("product_form.html", form=form, mode="edit", product=product)


@app.route("/seller/products/<int:product_id>/delete", methods=["POST"])
@seller_required
def product_delete(product_id):
    """Soft delete: the row stays so past order lines keep resolving."""
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        abort(404)
    if product["seller_id"] != session["user"]["id"]:
        flash("You can only delete your own products.", "danger")
        return redirect(url_for("seller_dashboard"))

    db.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
    flash(f"Archived {product['name']}. It is hidden from shoppers.", "info")
    return redirect(url_for("seller_dashboard"))


@app.route("/seller/products/<int:product_id>/restore", methods=["POST"])
@seller_required
def product_restore(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        abort(404)
    if product["seller_id"] != session["user"]["id"]:
        flash("You can only restore your own products.", "danger")
        return redirect(url_for("seller_dashboard"))

    db.execute("UPDATE products SET is_active = 1 WHERE id = ?", (product_id,))
    flash(f"Restored {product['name']} to your live listings.", "success")
    return redirect(url_for("seller_dashboard"))


@app.route("/seller/orders")
@seller_required
def seller_orders():
    """Every order in the marketplace, with a status control per row."""
    order_rows = get_db().execute(
        """SELECT o.*, u.username AS customer_name,
                  COALESCE((SELECT SUM(oi.quantity)
                              FROM order_items oi
                             WHERE oi.order_id = o.id), 0) AS units
             FROM orders o
             JOIN users u ON u.id = o.customer_id
            ORDER BY o.id DESC"""
    ).fetchall()
    return render_template("seller_orders.html", orders=order_rows, statuses=ORDER_STATUSES)


@app.route("/seller/orders/<int:order_id>/status", methods=["POST"])
@seller_required
def seller_order_status(order_id):
    status = request.form.get("status", "")
    if status not in ORDER_STATUSES:
        flash("That order status is not valid.", "danger")
        return redirect(url_for("seller_orders"))

    db = get_db()
    order = db.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        abort(404)

    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    flash(f"Order #{order_id} set to {status}.", "success")
    return redirect(url_for("seller_orders"))


# ==========================================================================
# 6. Error handlers
# ==========================================================================
@app.errorhandler(404)
def not_found(error):
    return render_template(
        "error.html",
        code=404,
        title="Page not found",
        message="We could not find the page or product you were looking for.",
    ), 404


@app.errorhandler(500)
def server_error(error):
    return render_template(
        "error.html",
        code=500,
        title="Something went wrong",
        message="An unexpected error occurred. Please try again in a moment.",
    ), 500


# Create the database and demo data on first run (also when Replit imports us).
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
