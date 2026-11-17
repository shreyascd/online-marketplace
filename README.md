# 🛒 ShopLite — Online Marketplace

A lightweight, full-featured online marketplace web application built with **Python**, **Flask**, **SQLite**, and **Bootstrap 5**. ShopLite supports multi-role users (buyers & sellers), dynamic product discovery, cart management, checkout with ACID-compliant order transactions, and dedicated seller inventory management.

---

## 🌟 Features

### 🛍️ For Customers (Buyers)
- **Product Discovery & Search:** Search products by keyword, filter by categories, and sort by price, date, or name.
- **Product Details & Live Stock:** View detailed product descriptions, prices, categories, and real-time stock levels.
- **Session-Based Cart:** Add products, update quantities, remove items, with automatic stock clamping if inventory changes.
- **Checkout & Transactions:** Place orders with custom delivery addresses. Database transactions ensure stock decrements and order creation occur atomically.
- **Order Tracking:** Track past orders and view status badges (`Pending`, `Processing`, `Shipped`, `Delivered`, `Cancelled`).

### 📦 For Sellers
- **Seller Dashboard:** View metrics and manage listed inventory in real time.
- **Product Management:** Add new listings, edit descriptions, adjust pricing and stock, or toggle active/archive status.
- **Order Fulfillment:** Inspect customer orders for listed items and update fulfillment statuses.

### 🔒 Security & Architecture
- **Password Hashing:** Secure password storage using `werkzeug.security` (PBKDF2/scrypt).
- **Role-Based Access Control (RBAC):** Authenticated route decorators separating customer and seller privileges.
- **SQL Injection Prevention:** 100% parameterized SQLite queries (no raw string interpolation).
- **Automatic Database Initialization:** Schema creation and demo data seeding on initial run.

---

## 🛠️ Tech Stack

- **Backend:** Python 3, Flask, Jinja2
- **Database:** SQLite3 (parameterized queries, foreign keys, transactions)
- **Frontend:** HTML5, CSS3, Bootstrap 5, Bootstrap Icons
- **Security:** Werkzeug security helpers

---

## 📁 Project Structure

```text
├── app.py              # Main Flask application with feature routes & helpers
├── database.py         # SQLite connection helpers, schema, and seed data
├── requirements.txt    # Python dependencies
├── static/
│   └── style.css       # Custom stylesheet & visual enhancements
├── templates/          # Jinja2 HTML templates
│   ├── base.html       # Global navigation and layout shell
│   ├── index.html      # Product catalog, search, and category filters
│   ├── product_detail.html
│   ├── product_form.html
│   ├── cart.html       # Shopping cart view
│   ├── checkout.html   # Order checkout & address entry
│   ├── orders.html     # Customer order history
│   ├── order_detail.html
│   ├── seller_dashboard.html
│   ├── seller_orders.html
│   ├── login.html      # User login
│   ├── register.html   # User registration (Customer or Seller)
│   └── error.html      # Custom HTTP error pages (403, 404, 500)
└── marketplace.db      # SQLite database (auto-generated on startup, ignored in git)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.8+** installed on your system.
- **Git** installed.

### 2. Clone the Repository
```bash
git clone https://github.com/shreyascd/online-marketplace.git
cd online-marketplace
```

### 3. Create a Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the Application
```bash
python app.py
```

The database (`marketplace.db`) will automatically initialize and populate with seed data on first run. Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 👥 Demo Accounts

The application automatically seeds pre-configured demo accounts for testing:

| Role | Username | Password | Notes |
| :--- | :--- | :--- | :--- |
| **Seller** | `seller1` | `seller123` | Preloaded with Electronics & Sports items |
| **Seller** | `seller2` | `seller123` | Preloaded with Books, Fashion, & Beauty items |
| **Customer** | `customer1` | `cust123` | Pre-existing buyer account |

*You can also register a new account at `/register` with either Customer or Seller privileges.*

---

## ⚙️ Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SECRET_KEY` | Session encryption secret key | `shoplite-dev-secret-key` |
| `SHOPLITE_DB` | Path to the SQLite database file | `marketplace.db` in project directory |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
