from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


# Make `import database` work from anywhere.
_DBMS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_DBMS_DIR))

from database import DatabaseManager  # noqa: E402


_SCENARIO_RUNNER = Path(__file__).with_name("scenario_runner.py")


class ModuleAACIDTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

        self.db = DatabaseManager(data_dir=self.data_dir, recover=True)

        # Three relations (tables)
        self.db.create_table(
            "users",
            {
                "user_id": {"type": "int"},
                "name": {"type": "str"},
                "balance": {"type": "int", "min": 0},
                "city": {"type": "str"},
            },
            order=4,
            search_key="user_id",
        )
        self.db.create_table(
            "products",
            {
                "product_id": {"type": "int"},
                "name": {"type": "str"},
                "stock": {"type": "int", "min": 0},
                "price": {"type": "float", "min": 0},
            },
            order=4,
            search_key="product_id",
        )
        self.db.create_table(
            "orders",
            {
                "order_id": {"type": "int"},
                "user_id": {"type": "int"},
                "product_id": {"type": "int"},
                "amount": {"type": "float", "min": 0},
            },
            order=4,
            search_key="order_id",
        )

        # Foreign keys (consistency)
        self.db.add_foreign_key("orders", "user_id", "users", "user_id")
        self.db.add_foreign_key("orders", "product_id", "products", "product_id")

        # Seed data
        self.db.insert(
            "users",
            {"user_id": 1, "name": "Alice", "balance": 100, "city": "NYC"},
        )
        self.db.insert(
            "products",
            {"product_id": 101, "name": "Burger", "stock": 5, "price": 10.0},
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run_scenario(self, *, mode: str, flush: bool, order_id: int = 1000) -> subprocess.CompletedProcess[str]:
        cmd = [
            sys.executable,
            str(_SCENARIO_RUNNER),
            "--data-dir",
            self.data_dir,
            "--mode",
            mode,
            "--order-id",
            str(order_id),
        ]
        if flush:
            cmd.append("--flush")

        return subprocess.run(cmd, capture_output=True, text=True)

    def test_atomicity_crash_rolls_back_multi_table_txn(self) -> None:
        # Persist uncommitted changes, then crash. Recovery must undo them.
        proc = self._run_scenario(mode="crash", flush=True, order_id=1000)
        self.assertNotEqual(proc.returncode, 0, msg=proc.stderr)

        db2 = DatabaseManager(data_dir=self.data_dir, recover=True)

        self.assertEqual(db2.get("users", 1)["balance"], 100)
        self.assertEqual(db2.get("products", 101)["stock"], 5)
        self.assertIsNone(db2.get("orders", 1000))

    def test_durability_commit_persists_across_restart(self) -> None:
        proc = self._run_scenario(mode="commit", flush=False, order_id=1001)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        db2 = DatabaseManager(data_dir=self.data_dir, recover=True)

        self.assertEqual(db2.get("users", 1)["balance"], 90)
        self.assertEqual(db2.get("products", 101)["stock"], 4)
        self.assertIsNotNone(db2.get("orders", 1001))

    def test_consistency_foreign_key_enforced_on_commit(self) -> None:
        with self.assertRaises(ValueError):
            with self.db.transaction() as tx:
                tx.insert(
                    "orders",
                    {"order_id": 2000, "user_id": 999, "product_id": 101, "amount": 10.0},
                )

        # Ensure rollback happened and database is still consistent.
        self.assertIsNone(self.db.get("orders", 2000))

    def test_consistency_non_negative_check_enforced(self) -> None:
        with self.assertRaises(ValueError):
            with self.db.transaction() as tx:
                product = tx.get("products", 101)
                assert product is not None
                product["stock"] = -1
                tx.update("products", 101, product)

        self.assertEqual(self.db.get("products", 101)["stock"], 5)

    def test_isolation_serializes_concurrent_transactions(self) -> None:
        # Set stock to 1 so only one order can succeed.
        product = self.db.get("products", 101)
        assert product is not None
        product["stock"] = 1
        self.db.update("products", 101, product)

        results: list[bool] = []
        results_lock = threading.Lock()

        def worker(order_id: int) -> None:
            ok = False
            try:
                with self.db.transaction() as tx:
                    prod = tx.get("products", 101)
                    assert prod is not None
                    if prod["stock"] <= 0:
                        raise ValueError("out_of_stock")

                    prod["stock"] = prod["stock"] - 1
                    tx.update("products", 101, prod)
                    tx.insert(
                        "orders",
                        {"order_id": order_id, "user_id": 1, "product_id": 101, "amount": 10.0},
                    )
                ok = True
            except ValueError:
                ok = False

            with results_lock:
                results.append(ok)

        t1 = threading.Thread(target=worker, args=(3000,))
        t2 = threading.Thread(target=worker, args=(3001,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.db.get("products", 101)["stock"], 0)
        orders_table = self.db.get_table("orders")
        assert orders_table is not None
        self.assertEqual(len(orders_table.get_all()), 1)


if __name__ == "__main__":
    unittest.main()
