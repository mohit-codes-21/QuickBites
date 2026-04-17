import os
import sys
import json
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


def login_admin(client, email, password):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "loginAs": "Admin"},
    )
    body = response.get_json(silent=True) or {}
    if response.status_code != 200:
        raise RuntimeError(f"Admin login failed ({response.status_code}): {body}")
    token = ((body.get("data") or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError(f"Missing token in login response: {body}")
    return token


def connect_source_db():
    return mysql.connector.connect(
        host=os.getenv("QB_SOURCE_DB_HOST", os.getenv("QB_DB_HOST", "127.0.0.1")),
        port=int(os.getenv("QB_SOURCE_DB_PORT", os.getenv("QB_DB_PORT", "3306"))),
        user=os.getenv("QB_SOURCE_DB_USER", os.getenv("QB_DB_USER", "qb_admin")),
        password=os.getenv("QB_SOURCE_DB_PASSWORD", os.getenv("QB_DB_PASSWORD", "qb_admin@123")),
        database=os.getenv("QB_SOURCE_DB_NAME", os.getenv("QB_DB_NAME", "QB")),
    )


def main():
    client = qb_app.app.test_client()
    router = ShardRouter()

    admin_email = os.getenv("QB_TEST_ADMIN_EMAIL", "aman.shah1@example.com")
    admin_password = os.getenv("QB_TEST_ADMIN_PASSWORD", "pwd1")
    customer_id = int(os.getenv("QB_TEST_CUSTOMER_ID", "1"))
    range_start = int(os.getenv("QB_TEST_RANGE_START", "1"))
    range_end = int(os.getenv("QB_TEST_RANGE_END", "10"))
    range_limit = int(os.getenv("QB_TEST_RANGE_LIMIT", "100"))

    token = login_admin(client, admin_email, admin_password)
    headers = {"Authorization": f"Bearer {token}"}

    print("=" * 72)
    print("Routing Validation Demo")
    print("=" * 72)

    # Point-query routing demonstration.
    route_response = client.get(f"/api/sharded/route/customer/{customer_id}", headers=headers)
    route_body = route_response.get_json(silent=True) or {}
    route_data = route_body.get("data") or {}

    expected_shard = router.shard_for_customer(customer_id)
    found_shard = int(route_data.get("shardID", -1))
    found_table = route_data.get("table")

    print("\n[1] POINT QUERY")
    print(f"searched customerID        : {customer_id}")
    print(f"expected shard (id % {router.num_shards}): {expected_shard}")
    print(f"found shard               : {found_shard}")
    print(f"found table               : {found_table}")
    print(f"routing match             : {'YES' if expected_shard == found_shard else 'NO'}")
    print("route response record:")
    print(json.dumps(route_data, indent=2, sort_keys=True, default=str))

    customer_response = client.get(f"/api/sharded/customers/{customer_id}", headers=headers)
    customer_body = customer_response.get_json(silent=True) or {}
    customer_row = customer_body.get("data") or {}
    print("customer record from API:")
    print(json.dumps(customer_row, indent=2, sort_keys=True, default=str))

    shard_record = None
    expected_table = router.table_name("customer", expected_shard)
    shard_conn = router.connect_to_shard(expected_shard)
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

    presence_by_shard = {}
    for shard_id in range(router.num_shards):
        conn = router.connect_to_shard(shard_id)
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT COUNT(*) FROM {router.table_name('customer', shard_id)} WHERE customerID = %s",
                (customer_id,),
            )
            presence_by_shard[shard_id] = int(cursor.fetchone()[0])
        finally:
            if conn.is_connected():
                conn.close()

    print("physical presence by shard :")
    for shard_id in sorted(presence_by_shard.keys()):
        print(f"  shard {shard_id}: {presence_by_shard[shard_id]}")

    # Range-query fanout demonstration.
    range_response = client.get(
        f"/api/sharded/customers/range?start={range_start}&end={range_end}&limit={range_limit}",
        headers=headers,
    )
    range_body = range_response.get_json(silent=True) or {}
    range_data = range_body.get("data") or {}
    rows = range_data.get("rows") or []

    returned_ids = [int(row["customerID"]) for row in rows]
    returned_shards = sorted({int(row["shardID"]) for row in rows})

    print("\n[2] RANGE QUERY")
    print(f"searched range            : start={range_start}, end={range_end}, limit={range_limit}")
    print(f"rows returned             : {len(rows)}")
    print(f"shards touched            : {returned_shards}")
    print("returned rows (full records):")
    for row in rows:
        print(json.dumps(row, sort_keys=True, default=str))

    source_conn = connect_source_db()
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
            (range_start, range_end, range_limit),
        )
        source_rows = source_cursor.fetchall()
    finally:
        if source_conn.is_connected():
            source_conn.close()

    source_ids = [int(row["customerID"]) for row in source_rows]

    print("source rows from monolith Customer table (full records):")
    for row in source_rows:
        print(json.dumps(row, sort_keys=True, default=str))

    print(f"matches source table rows : {'YES' if returned_ids == source_ids else 'NO'}")
    print(f"multi-shard fanout shown  : {'YES' if len(returned_shards) >= 2 else 'NO'}")

    overall_ok = (
        expected_shard == found_shard
        and presence_by_shard.get(expected_shard, 0) == 1
        and all(presence_by_shard.get(sid, 0) == 0 for sid in range(router.num_shards) if sid != expected_shard)
        and returned_ids == source_ids
        and len(returned_shards) >= 2
    )

    print("\n" + "=" * 72)
    print(f"OVERALL DEMO STATUS: {'PASS' if overall_ok else 'FAIL'}")
    print("=" * 72)


if __name__ == "__main__":
    main()