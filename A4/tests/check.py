import os
import sys
import json
import unittest
from pathlib import Path

import mysql.connector


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as qb_app  # noqa: E402
from shard_router import ShardRouter  # noqa: E402


class RoutingValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = qb_app.app.test_client()
        cls.router = ShardRouter()

        cls.admin_email = os.getenv("QB_TEST_ADMIN_EMAIL", "aman.shah1@example.com")
        cls.admin_password = os.getenv("QB_TEST_ADMIN_PASSWORD", "pwd1")

        cls.range_start = int(os.getenv("QB_TEST_RANGE_START", "1"))
        cls.range_end = int(os.getenv("QB_TEST_RANGE_END", "10"))
        cls.range_limit = int(os.getenv("QB_TEST_RANGE_LIMIT", "100"))
        cls.point_customer_id = int(os.getenv("QB_TEST_CUSTOMER_ID", "1"))

        cls.admin_token = cls._login_as_admin()

    @classmethod
    def _login_as_admin(cls):
        response = cls.client.post(
            "/api/auth/login",
            json={
                "email": cls.admin_email,
                "password": cls.admin_password,
                "loginAs": "Admin",
            },
        )
        body = response.get_json(silent=True) or {}
        if response.status_code != 200:
            raise AssertionError(f"Admin login failed ({response.status_code}): {body}")

        token = ((body.get("data") or {}).get("token") or "").strip()
        if not token:
            raise AssertionError(f"Admin login did not return token: {body}")
        return token

    @classmethod
    def _connect_source_db(cls):
        return mysql.connector.connect(
            host=os.getenv("QB_SOURCE_DB_HOST", os.getenv("QB_DB_HOST", "127.0.0.1")),
            port=int(os.getenv("QB_SOURCE_DB_PORT", os.getenv("QB_DB_PORT", "3306"))),
            user=os.getenv("QB_SOURCE_DB_USER", os.getenv("QB_DB_USER", "qb_admin")),
            password=os.getenv("QB_SOURCE_DB_PASSWORD", os.getenv("QB_DB_PASSWORD", "qb_admin@123")),
            database=os.getenv("QB_SOURCE_DB_NAME", os.getenv("QB_DB_NAME", "QB")),
        )

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.admin_token}"}

    def test_query_is_routed_to_expected_shard(self):
        customer_id = self.point_customer_id

        route_response = self.client.get(
            f"/api/sharded/route/customer/{customer_id}",
            headers=self._auth_headers(),
        )
        route_body = route_response.get_json(silent=True) or {}
        self.assertEqual(route_response.status_code, 200, route_body)

        route_data = route_body.get("data") or {}
        expected_shard = self.router.shard_for_customer(customer_id)
        expected_table = self.router.table_name("customer", expected_shard)

        self.assertEqual(int(route_data.get("customerID", -1)), customer_id)
        self.assertEqual(int(route_data.get("shardID", -1)), expected_shard)
        self.assertEqual(route_data.get("table"), expected_table)

        print("\n[POINT QUERY ROUTING]")
        print(f"searched customerID: {customer_id}")
        print(f"expected shard: {expected_shard}")
        print(f"found shard: {route_data.get('shardID')}")
        print(f"found table: {route_data.get('table')}")
        print(f"match: {'YES' if int(route_data.get('shardID', -1)) == expected_shard else 'NO'}")
        print("route response record:")
        print(json.dumps(route_data, indent=2, sort_keys=True, default=str))

        customer_response = self.client.get(
            f"/api/sharded/customers/{customer_id}",
            headers=self._auth_headers(),
        )
        customer_body = customer_response.get_json(silent=True) or {}
        self.assertEqual(customer_response.status_code, 200, customer_body)

        customer_row = customer_body.get("data") or {}
        self.assertEqual(int(customer_row.get("customerID", -1)), customer_id)
        self.assertEqual(int(customer_row.get("shardID", -1)), expected_shard)

        print("customer record from API:")
        print(json.dumps(customer_row, indent=2, sort_keys=True, default=str))

        shard_record = None
        shard_conn = self.router.connect_to_shard(expected_shard)
        try:
            shard_cursor = shard_conn.cursor(dictionary=True)
            shard_cursor.execute(
                f"""
                SELECT customerID, loyaltyTier, membershipDiscount, cartTotalAmount,
                       membershipDueDate, membership, isDeleted
                FROM {expected_table}
                WHERE customerID = %s
                LIMIT 1
                """,
                (customer_id,),
            )
            shard_record = shard_cursor.fetchone() or {}
        finally:
            if shard_conn.is_connected():
                shard_conn.close()

        print("customer record from physical shard table:")
        print(json.dumps(shard_record, indent=2, sort_keys=True, default=str))

        # Demonstrate physical placement: customer row must exist on exactly one shard.
        presence_by_shard = {}
        for shard_id in range(self.router.num_shards):
            conn = self.router.connect_to_shard(shard_id)
            try:
                cursor = conn.cursor()
                table_name = self.router.table_name("customer", shard_id)
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE customerID = %s",
                    (customer_id,),
                )
                presence_by_shard[shard_id] = int(cursor.fetchone()[0])
            finally:
                if conn.is_connected():
                    conn.close()

        self.assertEqual(
            presence_by_shard[expected_shard],
            1,
            f"Expected customer {customer_id} on shard {expected_shard}, got {presence_by_shard}",
        )
        for shard_id, count in presence_by_shard.items():
            if shard_id != expected_shard:
                self.assertEqual(
                    count,
                    0,
                    f"Customer {customer_id} unexpectedly present on shard {shard_id}: {presence_by_shard}",
                )

        print("physical shard presence (customer row count by shard):")
        for shard_id in sorted(presence_by_shard.keys()):
            print(f"  shard {shard_id}: {presence_by_shard[shard_id]}")

    def test_range_query_spans_multiple_shards_with_correct_results(self):
        response = self.client.get(
            f"/api/sharded/customers/range?start={self.range_start}&end={self.range_end}&limit={self.range_limit}",
            headers=self._auth_headers(),
        )
        body = response.get_json(silent=True) or {}
        self.assertEqual(response.status_code, 200, body)

        data = body.get("data") or {}
        rows = data.get("rows") or []

        self.assertEqual(int(data.get("start", -1)), self.range_start)
        self.assertEqual(int(data.get("end", -1)), self.range_end)
        self.assertEqual(int(data.get("count", -1)), len(rows))
        self.assertLessEqual(len(rows), self.range_limit)
        self.assertGreater(len(rows), 0, "Range query returned no rows; choose a wider test range")

        returned_ids = []
        shard_ids = set()
        for row in rows:
            customer_id = int(row["customerID"])
            shard_id = int(row["shardID"])
            returned_ids.append(customer_id)
            shard_ids.add(shard_id)

            self.assertGreaterEqual(customer_id, self.range_start)
            self.assertLessEqual(customer_id, self.range_end)
            self.assertEqual(shard_id, self.router.shard_for_customer(customer_id))

        self.assertEqual(returned_ids, sorted(returned_ids), "Range rows should be globally sorted by customerID")
        self.assertGreaterEqual(
            len(shard_ids),
            2,
            f"Expected multi-shard fanout, but got shard set {sorted(shard_ids)}",
        )

        print("\n[RANGE QUERY ROUTING]")
        print(f"searched range: start={self.range_start}, end={self.range_end}, limit={self.range_limit}")
        print(f"rows returned: {len(rows)}")
        print(f"shards touched: {sorted(shard_ids)}")
        print("returned rows (full records):")
        for row in rows:
            print(json.dumps(row, sort_keys=True, default=str))

        source_conn = self._connect_source_db()
        try:
            source_cursor = source_conn.cursor(dictionary=True)
            source_cursor.execute(
                """
                SELECT customerID, loyaltyTier, membershipDiscount, cartTotalAmount,
                       membershipDueDate, membership, isDeleted
                FROM Customer
                WHERE customerID BETWEEN %s AND %s
                ORDER BY customerID ASC
                LIMIT %s
                """,
                (self.range_start, self.range_end, self.range_limit),
            )
            source_rows = source_cursor.fetchall()
        finally:
            if source_conn.is_connected():
                source_conn.close()

        source_ids = [int(row["customerID"]) for row in source_rows]

        print("source rows from monolith Customer table (full records):")
        for row in source_rows:
            print(json.dumps(row, sort_keys=True, default=str))

        self.assertEqual(
            returned_ids,
            source_ids,
            "Range query results do not match source Customer table for same bounds",
        )

        print(f"matches source Customer rows: {'YES' if returned_ids == source_ids else 'NO'}")


if __name__ == "__main__":
    unittest.main(verbosity=2)