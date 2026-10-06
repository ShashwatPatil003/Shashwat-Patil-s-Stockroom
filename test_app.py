"""Stockroom tests (Shashwat Patil, Robotics and AI).
Run with:  python -m unittest -v"""
import os
import tempfile
import unittest

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["STOCKROOM_DB"] = _tmp.name
os.environ["SEED_DEMO"] = "0"

import app as stockroom  # noqa: E402


def make(code="TST-001", **over):
    body = {"product_code": code, "name": "Test Item", "category": "Testing",
            "quantity": 20, "price": 99.5, "reorder_level": 5}
    body.update(over)
    return body


class InventoryTests(unittest.TestCase):
    def setUp(self):
        stockroom.app.config["TESTING"] = True
        db = stockroom.sqlite3.connect(_tmp.name)
        db.executescript("DELETE FROM stock_movements; DELETE FROM products; DELETE FROM categories;")
        db.commit()
        db.close()
        self.c = stockroom.app.test_client()

    # ---- create ----------------------------------------------------------
    def test_add_and_list_product(self):
        r = self.c.post("/api/products", json=make())
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["status"], "ok")
        self.assertEqual(len(self.c.get("/api/products").get_json()), 1)

    def test_duplicate_product_id_rejected(self):
        self.c.post("/api/products", json=make("DUP-1"))
        r = self.c.post("/api/products", json=make("dup-1"))  # case-insensitive
        self.assertEqual(r.status_code, 409)

    def test_negative_quantity_and_price_rejected(self):
        self.assertEqual(self.c.post("/api/products", json=make(quantity=-1)).status_code, 400)
        self.assertEqual(self.c.post("/api/products", json=make("TST-2", price=-5)).status_code, 400)

    def test_non_numeric_values_rejected(self):
        self.assertEqual(self.c.post("/api/products", json=make(quantity="abc")).status_code, 400)
        self.assertEqual(self.c.post("/api/products", json=make("TST-3", quantity=2.5)).status_code, 400)
        self.assertEqual(self.c.post("/api/products", json=make("TST-4", price="free")).status_code, 400)

    def test_required_fields(self):
        self.assertEqual(self.c.post("/api/products", json=make(name="  ")).status_code, 400)
        self.assertEqual(self.c.post("/api/products", json=make("")).status_code, 400)
        self.assertEqual(self.c.post("/api/products", data="not json").status_code, 400)

    # ---- search ----------------------------------------------------------
    def test_search_by_name_id_and_category(self):
        self.c.post("/api/products", json=make("ABC-1", name="Blue Pen", category="Stationery"))
        self.c.post("/api/products", json=make("XYZ-9", name="Rice", category="Grocery"))
        for q, expected in [("pen", 1), ("xyz", 1), ("grocery", 1), ("zzz", 0)]:
            got = self.c.get(f"/api/products?q={q}").get_json()
            self.assertEqual(len(got), expected, q)

    def test_search_unavailable_product_returns_empty_list(self):
        r = self.c.get("/api/products?q=does-not-exist")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    # ---- stock -----------------------------------------------------------
    def test_stock_increase_and_decrease(self):
        pid = self.c.post("/api/products", json=make()).get_json()["id"]
        r = self.c.patch(f"/api/products/{pid}/stock", json={"change": 5})
        self.assertEqual(r.get_json()["quantity"], 25)
        r = self.c.patch(f"/api/products/{pid}/stock", json={"change": -25})
        self.assertEqual(r.get_json()["quantity"], 0)
        self.assertEqual(r.get_json()["status"], "out")

    def test_reducing_stock_below_zero_is_blocked(self):
        pid = self.c.post("/api/products", json=make(quantity=3)).get_json()["id"]
        r = self.c.patch(f"/api/products/{pid}/stock", json={"change": -4})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.get(f"/api/products/{pid}").get_json()["quantity"], 3)

    def test_set_absolute_quantity_and_negative_blocked(self):
        pid = self.c.post("/api/products", json=make()).get_json()["id"]
        self.assertEqual(self.c.patch(f"/api/products/{pid}/stock", json={"quantity": 7}).get_json()["quantity"], 7)
        self.assertEqual(self.c.patch(f"/api/products/{pid}/stock", json={"quantity": -1}).status_code, 400)

    def test_stock_history_is_recorded(self):
        pid = self.c.post("/api/products", json=make()).get_json()["id"]
        self.c.patch(f"/api/products/{pid}/stock", json={"change": -2, "note": "Sold"})
        hist = self.c.get(f"/api/products/{pid}/history").get_json()
        self.assertEqual([h["change"] for h in hist], [-2, 20])

    # ---- low stock -------------------------------------------------------
    def test_low_stock_alerts(self):
        self.c.post("/api/products", json=make("LOW-1", quantity=3, reorder_level=5))
        self.c.post("/api/products", json=make("OUT-1", quantity=0))
        self.c.post("/api/products", json=make("OK-1", quantity=50))
        s = self.c.get("/api/summary").get_json()
        self.assertEqual((s["low_count"], s["out_count"], s["ok_count"]), (1, 1, 1))
        self.assertEqual([a["product_code"] for a in s["alerts"]], ["OUT-1", "LOW-1"])
        self.assertEqual(len(self.c.get("/api/products?status=low").get_json()), 1)

    # ---- update / delete -------------------------------------------------
    def test_update_product_details(self):
        pid = self.c.post("/api/products", json=make()).get_json()["id"]
        r = self.c.put(f"/api/products/{pid}", json={"price": 150, "name": "Renamed", "category": "New Cat"})
        body = r.get_json()
        self.assertEqual((body["price"], body["name"], body["category"]), (150, "Renamed", "New Cat"))
        self.assertEqual(self.c.put(f"/api/products/{pid}", json={"price": -1}).status_code, 400)

    def test_delete_product_and_missing_product(self):
        pid = self.c.post("/api/products", json=make()).get_json()["id"]
        self.assertEqual(self.c.delete(f"/api/products/{pid}").status_code, 200)
        self.assertEqual(self.c.delete(f"/api/products/{pid}").status_code, 404)
        self.assertEqual(self.c.put("/api/products/9999", json={"price": 1}).status_code, 404)
        self.assertEqual(self.c.patch("/api/products/9999/stock", json={"change": 1}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
