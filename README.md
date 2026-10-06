# Stockroom: Inventory / Product Management System

A mini full-stack inventory app built with **HTML, CSS, JavaScript, Python Flask and SQLite**.

![Stockroom screenshot](docs/screenshot.png)

**Author:** Shashwat Patil | **Branch:** Robotics and AI | **Project:** Mini Project, Aim 6 (Inventory / Product Management System)

## Features

- Add, list, search, edit and delete products (Product ID, Name, Category, Quantity, Price)
- Update stock with +/- buttons or by typing a new quantity; every change is logged
- Stock-health bar and low-stock / out-of-stock alerts that update without a page reload
- Search by name, product ID or category, plus category and stock-level filters
- Validation on both client and server: unique product ID, no negative quantity or price, stock can never drop below zero
- SQLite database and sample data are created automatically on first run

## Tech stack

| Layer    | Technology                                           |
| -------- | ---------------------------------------------------- |
| Frontend | HTML, CSS, JavaScript (Fetch API)                    |
| Backend  | Python 3.9+, Flask (REST API)                        |
| Database | SQLite (`categories`, `products`, `stock_movements`) |

## Run locally

```bash
git clone https://github.com/<your-username>/stockroom.git
cd stockroom
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. Set `SEED_DEMO=0` to start with an empty database.

## API routes

| Method | Route                                | Purpose                                               |
| ------ | ------------------------------------ | ----------------------------------------------------- |
| GET    | `/api/products?q=&category=&status=` | List / search products                                |
| POST   | `/api/products`                      | Add a product                                         |
| GET    | `/api/products/<id>`                 | Get one product                                       |
| PUT    | `/api/products/<id>`                 | Edit name, category, price, reorder level             |
| PATCH  | `/api/products/<id>/stock`           | Adjust stock (`{"change": -3}` or `{"quantity": 40}`) |
| DELETE | `/api/products/<id>`                 | Delete a product                                      |
| GET    | `/api/products/<id>/history`         | Last 20 stock movements                               |
| GET    | `/api/categories`                    | Categories in use                                     |
| GET    | `/api/summary`                       | Totals and low-stock alerts                           |

## Tests

```bash
python -m unittest -v
```

Covers duplicate IDs, negative and non-numeric input, searching for a product that doesn't exist, reducing stock below zero, deleting or updating a missing product, and low-stock alerts.

## Project structure

```
app.py            Flask app, database schema, REST API
templates/        index.html
static/           style.css, app.js
test_app.py       Unit tests
requirements.txt
```
