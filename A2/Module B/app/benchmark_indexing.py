"""
QuickBites Module B — SubTask 5: Before / After Index Benchmarking
===================================================================

Measures raw SQL query latency (via direct DB connection) and Flask API
endpoint latency (via the test client) both *before* and *after* the
composite indexes defined in ``sql/indexes.sql`` are applied.

Usage examples
--------------
    # Full round-trip: drop → benchmark → apply → benchmark
    python benchmark_indexing.py --mode full

    # Only benchmark (indexes assumed already absent / present)
    python benchmark_indexing.py --mode before
    python benchmark_indexing.py --mode after

    # Manage indexes manually
    python benchmark_indexing.py --mode apply
    python benchmark_indexing.py --mode drop
"""

import argparse
import json
import os
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import mysql.connector

# Reuse the exact DB configuration used by the app.
from app import app as flask_app  # noqa: E402
from app import get_db_connection  # noqa: E402


# ---------------------------------------------------------------------------
# Index catalogue — must match sql/indexes.sql and sql/drop_indexes.sql
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexSpec:
    table: str
    name: str


INDEX_SPECS = [
    IndexSpec("Orders", "qb_idx_orders_customer_time"),
    IndexSpec("Orders", "qb_idx_orders_restaurant_time"),
    IndexSpec("Orders", "qb_idx_orders_status_time"),
    IndexSpec("Delivery_Assignments", "qb_idx_delivery_partner_acceptance"),
    IndexSpec("Delivery_Assignments", "qb_idx_delivery_partner_deliverytime"),
    IndexSpec("MenuItem", "qb_idx_menuitem_rest_disc_item"),
    IndexSpec("Restaurant", "qb_idx_restaurant_active_name"),
    IndexSpec("Payment", "qb_idx_payment_customer_for_time"),
    IndexSpec("Payment", "qb_idx_payment_for_status_type_time"),
    IndexSpec("Address", "qb_idx_address_customer_saved"),
    IndexSpec("AuditLog", "qb_idx_auditlog_timestamp"),
]


# ---------------------------------------------------------------------------
# Benchmark queries — 17 representative SELECT statements taken from app.py
# ---------------------------------------------------------------------------

def build_benchmark_queries(customer_id: int, restaurant_id: int, partner_id: int):
    return {
        # ── existing 9 ──────────────────────────────────────────────
        "restaurants_list": {
            "sql": """
                SELECT restaurantID, name, city, isOpen, isVerified, averageRating,
                       latitude, longitude
                FROM Restaurant
                WHERE discontinued = 0 AND isDeleted = 0
                ORDER BY name
            """,
            "params": (),
        },
        "menu_items_by_restaurant": {
            "sql": """
                SELECT mi.restaurantID, mi.itemID, mi.name, mi.description, mi.menuCategory,
                       mi.restaurantPrice, mi.appPrice, mi.isVegetarian, mi.preparationTime,
                       mi.isAvailable, mi.discontinued,
                       r.name AS restaurantName
                FROM MenuItem mi
                JOIN Restaurant r ON r.restaurantID = mi.restaurantID
                WHERE r.isDeleted = 0 AND mi.discontinued = 0 AND mi.restaurantID = %s
                ORDER BY mi.restaurantID, mi.itemID
            """,
            "params": (restaurant_id,),
        },
        "customer_orders_list": {
            "sql": """
                SELECT o.orderID, o.orderTime, o.orderStatus, o.totalAmount,
                       r.name AS restaurantName, p.status AS paymentStatus
                FROM Orders o
                JOIN Restaurant r ON r.restaurantID = o.restaurantID
                LEFT JOIN Payment p ON p.paymentID = o.paymentID
                WHERE o.customerID = %s
                ORDER BY o.orderTime DESC
                LIMIT 50
            """,
            "params": (customer_id,),
        },
        "restaurant_orders_list": {
            "sql": """
                SELECT o.orderID, o.orderTime, o.estimatedTime, o.totalAmount, o.orderStatus,
                       o.customerID, o.addressID,
                       p.status AS paymentStatus, p.paymentType AS paymentMode,
                       da.AssignmentID, da.PartnerID, da.acceptanceTime, da.pickupTime, da.deliveryTime
                FROM Orders o
                LEFT JOIN Payment p ON p.paymentID = o.paymentID
                LEFT JOIN Delivery_Assignments da ON da.OrderID = o.orderID
                WHERE o.restaurantID = %s
                ORDER BY o.orderTime DESC
                LIMIT 200
            """,
            "params": (restaurant_id,),
        },
        "delivery_live_orders": {
            "sql": """
                SELECT o.orderID, o.orderTime, o.estimatedTime, o.totalAmount, o.orderStatus,
                       o.customerID, o.restaurantID, o.addressID,
                       r.name AS restaurantName, r.contactPhone AS restaurantPhone, r.addressLine AS restaurantAddress,
                       r.city AS restaurantCity, r.zipCode AS restaurantZip,
                       r.latitude AS restaurantLatitude, r.longitude AS restaurantLongitude,
                       m.name AS customerName, m.phoneNumber AS customerPhone,
                       a.addressLine AS customerAddress, a.city AS customerCity, a.zipCode AS customerZip,
                       a.latitude AS customerLatitude, a.longitude AS customerLongitude
                FROM Orders o
                JOIN Restaurant r ON r.restaurantID = o.restaurantID
                JOIN Member m ON m.memberID = o.customerID
                JOIN Address a ON a.customerID = o.customerID AND a.addressID = o.addressID
                LEFT JOIN Delivery_Assignments da ON da.OrderID = o.orderID
                WHERE o.orderStatus IN ('Created', 'Preparing', 'ReadyForPickup')
                  AND da.OrderID IS NULL
                ORDER BY o.orderTime DESC
                LIMIT 200
            """,
            "params": (),
        },
        "delivery_assignments": {
            "sql": """
                SELECT da.AssignmentID, da.OrderID, da.acceptanceTime, da.pickupTime, da.deliveryTime,
                       o.orderStatus, r.name AS restaurantName
                FROM Delivery_Assignments da
                JOIN Orders o ON o.orderID = da.OrderID
                JOIN Restaurant r ON r.restaurantID = o.restaurantID
                WHERE da.PartnerID = %s
                ORDER BY da.acceptanceTime DESC
                LIMIT 50
            """,
            "params": (partner_id,),
        },
        "customer_last_payment": {
            "sql": """
                SELECT paymentID, amount, paymentType, status, transactionTime
                FROM Payment
                WHERE customerID = %s AND paymentFor = 'Order'
                ORDER BY transactionTime DESC, paymentID DESC
                LIMIT 1
            """,
            "params": (customer_id,),
        },
        "saved_address_lookup": {
            "sql": """
                SELECT addressID
                FROM Address
                WHERE customerID = %s AND isSaved = 1
                ORDER BY addressID
                LIMIT 1
            """,
            "params": (customer_id,),
        },
        "admin_overview_recent": {
            "sql": """
                SELECT o.orderID, o.orderStatus, o.totalAmount, o.orderTime,
                       r.name AS restaurantName, p.paymentType, p.status AS paymentStatus
                FROM Orders o
                LEFT JOIN Restaurant r ON r.restaurantID = o.restaurantID
                LEFT JOIN Payment p ON p.paymentID = o.paymentID
                ORDER BY o.orderTime DESC
                LIMIT 12
            """,
            "params": (),
        },

        # ── 8 new queries ──────────────────────────────────────────
        "menu_items_search": {
            "sql": """
                SELECT mi.restaurantID, mi.itemID, mi.name, mi.description, mi.menuCategory,
                       mi.restaurantPrice, mi.appPrice, mi.isVegetarian, mi.preparationTime,
                       mi.isAvailable, mi.discontinued,
                       r.name AS restaurantName
                FROM MenuItem mi
                JOIN Restaurant r ON r.restaurantID = mi.restaurantID
                WHERE r.isDeleted = 0 AND mi.discontinued = 0 AND mi.name LIKE %s
                ORDER BY mi.restaurantID, mi.itemID
            """,
            "params": ("%Paneer%",),
        },
        "customer_cart": {
            "sql": """
                SELECT ci.customerID, ci.restaurantID, ci.itemID, ci.quantity,
                       mi.name AS itemName, mi.appPrice,
                       r.name AS restaurantName
                FROM CartItem ci
                JOIN MenuItem mi ON mi.restaurantID = ci.restaurantID AND mi.itemID = ci.itemID
                JOIN Restaurant r ON r.restaurantID = ci.restaurantID
                WHERE ci.customerID = %s
                  AND mi.discontinued = 0
                  AND r.isDeleted = 0
                ORDER BY ci.restaurantID, ci.itemID
            """,
            "params": (customer_id,),
        },
        "customer_profile_orders": {
            "sql": """
                SELECT o.orderID, o.orderTime, o.orderStatus, o.totalAmount,
                       r.name AS restaurantName, p.status AS paymentStatus,
                       r.addressLine AS restaurantAddress, r.city AS restaurantCity,
                       r.latitude AS restaurantLatitude, r.longitude AS restaurantLongitude,
                       a.addressLine AS deliveryAddress, a.city AS deliveryCity,
                       a.latitude AS deliveryLatitude, a.longitude AS deliveryLongitude,
                       orr.restaurantRating, orr.deliveryRating, orr.comment AS orderComment,
                       da.PartnerID, dpm.name AS deliveryPartnerName,
                       dpm.phoneNumber AS deliveryPartnerPhone,
                       dp.currentLatitude AS deliveryPartnerLatitude,
                       dp.currentLongitude AS deliveryPartnerLongitude
                FROM Orders o
                JOIN Restaurant r ON r.restaurantID = o.restaurantID
                JOIN Address a ON a.customerID = o.customerID AND a.addressID = o.addressID
                LEFT JOIN Payment p ON p.paymentID = o.paymentID
                LEFT JOIN OrderRating orr ON orr.orderID = o.orderID
                LEFT JOIN Delivery_Assignments da ON da.OrderID = o.orderID
                LEFT JOIN DeliveryPartner dp ON dp.partnerID = da.PartnerID
                LEFT JOIN Member dpm ON dpm.memberID = da.PartnerID
                WHERE o.customerID = %s
                ORDER BY o.orderTime DESC
                LIMIT 100
            """,
            "params": (customer_id,),
        },
        "customer_order_reviews": {
            "sql": """
                SELECT orr.orderID, o.orderTime, r.name AS restaurantName,
                       orr.restaurantRating, orr.deliveryRating, orr.comment
                FROM OrderRating orr
                JOIN Orders o ON o.orderID = orr.orderID
                JOIN Restaurant r ON r.restaurantID = o.restaurantID
                WHERE o.customerID = %s
                ORDER BY o.orderTime DESC
            """,
            "params": (customer_id,),
        },
        "customer_item_reviews": {
            "sql": """
                SELECT mir.orderID, mir.restaurantID, mir.itemID, mir.rating, mir.comment,
                       o.orderTime, r.name AS restaurantName, mi.name AS itemName
                FROM MenuItemRating mir
                JOIN Orders o ON o.orderID = mir.orderID
                JOIN Restaurant r ON r.restaurantID = mir.restaurantID
                JOIN MenuItem mi ON mi.restaurantID = mir.restaurantID AND mi.itemID = mir.itemID
                WHERE o.customerID = %s
                ORDER BY o.orderTime DESC, mir.orderID DESC, mir.itemID
            """,
            "params": (customer_id,),
        },
        "customer_addresses": {
            "sql": """
                SELECT addressID, addressLine, city, zipCode, label, latitude, longitude, isSaved
                FROM Address
                WHERE customerID = %s
                ORDER BY addressID
            """,
            "params": (customer_id,),
        },
        # NOTE: The real expire_pending_order_payments() runs an UPDATE, but we
        # benchmark a SELECT with the same WHERE clause to avoid mutating data.
        # The WHERE clause is what determines index usage, so results are equivalent.
        "expire_pending_payments": {
            "sql": """
                SELECT paymentID, customerID, transactionTime
                FROM Payment
                WHERE paymentFor = 'Order'
                  AND status = 'Pending'
                  AND paymentType = 'OnQuickBites'
                  AND transactionTime <= (NOW() - INTERVAL 2 MINUTE)
            """,
            "params": (),
        },
        "delivery_completed_orders": {
            "sql": """
                SELECT da.AssignmentID, da.OrderID, da.acceptanceTime, da.pickupTime, da.deliveryTime,
                       o.totalAmount, o.specialInstruction,
                       r.name AS restaurantName,
                       m.name AS customerName
                FROM Delivery_Assignments da
                JOIN Orders o ON o.orderID = da.OrderID
                JOIN Restaurant r ON r.restaurantID = o.restaurantID
                JOIN Member m ON m.memberID = o.customerID
                WHERE da.PartnerID = %s AND o.orderStatus = 'Delivered'
                ORDER BY da.deliveryTime DESC
                LIMIT 100
            """,
            "params": (partner_id,),
        },
        "admin_audits": {
            "sql": """
                SELECT logID, memberID, action, tableName, recordID, timestamp, details
                FROM AuditLog
                ORDER BY timestamp DESC, logID DESC
                LIMIT 200
            """,
            "params": (),
        },
    }


# ---------------------------------------------------------------------------
# API endpoint benchmarks — 12 representative GET endpoints
# ---------------------------------------------------------------------------

def build_api_benchmarks(customer_id: int, restaurant_id: int):
    return [
        # ── existing 6 (paths verified against app.py) ─────────────
        {
            "name": "api_restaurants",
            "method": "GET",
            "path": "/api/restaurants",
            "role": "Customer",
        },
        {
            "name": "api_menu_items",
            "method": "GET",
            "path": f"/api/menu-items?restaurantID={restaurant_id}",
            "role": "Customer",
        },
        {
            "name": "api_customer_orders",
            "method": "GET",
            "path": "/api/customer/orders",
            "role": "Customer",
        },
        {
            "name": "api_restaurant_orders",
            "method": "GET",
            "path": f"/api/restaurant/orders?restaurantID={restaurant_id}",
            "role": "Admin",
        },
        {
            "name": "api_customer_last_payment",
            "method": "GET",
            "path": "/api/customer/payments/last",
            "role": "Customer",
        },
        {
            "name": "api_delivery_live_orders",
            "method": "GET",
            "path": "/api/delivery/live-orders",
            "role": "DeliveryPartner",
        },

        # ── 6 new endpoints ────────────────────────────────────────
        {
            "name": "api_menu_items_search",
            "method": "GET",
            "path": "/api/menu-items?search=Paneer",
            "role": "Customer",
        },
        {
            "name": "api_customer_cart",
            "method": "GET",
            "path": "/api/customer/cart",
            "role": "Customer",
        },
        {
            "name": "api_customer_profile_orders",
            "method": "GET",
            "path": "/api/customer/profile/orders",
            "role": "Customer",
        },
        {
            "name": "api_delivery_assignments",
            "method": "GET",
            "path": "/api/delivery/assignments",
            "role": "DeliveryPartner",
        },
        {
            "name": "api_delivery_completed_orders",
            "method": "GET",
            "path": "/api/delivery/completed-orders",
            "role": "DeliveryPartner",
        },
        {
            "name": "api_admin_overview",
            "method": "GET",
            "path": "/api/admin/overview",
            "role": "Admin",
        },
        {
            "name": "api_admin_audits",
            "method": "GET",
            "path": "/api/admin/audits",
            "role": "Admin",
        },
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_execute(cursor, statement, params=None):
    try:
        cursor.execute(statement, params or ())
        return True, None
    except mysql.connector.Error as exc:
        return False, {"errno": exc.errno, "sqlstate": exc.sqlstate, "msg": str(exc)}


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

# When a composite index has an FK column as its leading column, MySQL may be
# using it to enforce the FK constraint.  Dropping it directly fails with
# errno 1553.  We work around this by creating temporary single-column FK
# replacement indexes first, then dropping the composite ones.
_FK_REPLACEMENTS = [
    ("Orders",                "_tmp_fk_orders_restaurantid",  "restaurantID"),
    ("Delivery_Assignments",  "_tmp_fk_da_partnerid",         "PartnerID"),
    ("Payment",               "_tmp_fk_payment_customerid",   "customerID"),
]


def drop_indexes(connection):
    results = []
    cursor = connection.cursor()

    # 1. Create temporary FK replacement indexes so MySQL lets us drop composites.
    for table, tmp_name, col in _FK_REPLACEMENTS:
        _safe_execute(cursor, f"CREATE INDEX {tmp_name} ON {table}({col})")

    # 2. Drop our composite indexes.
    for spec in INDEX_SPECS:
        ok, err = _safe_execute(cursor, f"DROP INDEX {spec.name} ON {spec.table}")
        results.append({"table": spec.table, "index": spec.name, "dropped": ok, "error": err})

    # 3. Also drop any old-named indexes from previous implementations.
    old_indexes = [
        ("Delivery_Assignments", "qb_idx_delivery_order"),
        ("MenuItemRating",       "qb_idx_menuitemrating_order"),
        ("Payment",              "qb_idx_payment_for_status_time"),
    ]
    for table, name in old_indexes:
        _safe_execute(cursor, f"DROP INDEX {name} ON {table}")

    connection.commit()
    return results


def apply_indexes(connection):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sql_path = os.path.join(base_dir, "..", "sql", "indexes.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_text = f.read()

    # Remove comment-only lines before splitting into statements.
    filtered_lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        filtered_lines.append(line)

    sql_text = "\n".join(filtered_lines)

    # Split on semicolons (file contains only USE + CREATE INDEX statements).
    statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]

    cursor = connection.cursor()
    results = []
    for stmt in statements:
        ok, err = _safe_execute(cursor, stmt)
        results.append({"statement": stmt, "applied": ok, "error": err})

    # Clean up temporary FK replacement indexes (composite indexes now cover FKs).
    for table, tmp_name, _ in _FK_REPLACEMENTS:
        _safe_execute(cursor, f"DROP INDEX {tmp_name} ON {table}")

    connection.commit()
    return results


# ---------------------------------------------------------------------------
# SQL-level benchmarking
# ---------------------------------------------------------------------------

def explain_query(connection, sql, params):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(f"EXPLAIN {sql}", params)
    return cursor.fetchall()


def time_select_query(connection, sql, params, runs, warmup):
    durations = []
    cursor = connection.cursor(dictionary=True)

    for _ in range(warmup):
        cursor.execute(sql, params)
        cursor.fetchall()

    for _ in range(runs):
        t0 = time.perf_counter()
        cursor.execute(sql, params)
        cursor.fetchall()
        durations.append((time.perf_counter() - t0) * 1000.0)

    durations_sorted = sorted(durations)
    return {
        "runs": runs,
        "warmup": warmup,
        "ms": {
            "min": min(durations_sorted),
            "p50": statistics.median(durations_sorted),
            "p95": durations_sorted[int(0.95 * (len(durations_sorted) - 1))],
            "max": max(durations_sorted),
            "mean": statistics.mean(durations_sorted),
        },
    }


# ---------------------------------------------------------------------------
# API-level benchmarking
# ---------------------------------------------------------------------------

def _login(client, email, password, login_as):
    resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "loginAs": login_as},
    )
    payload = resp.get_json(silent=True) or {}
    token = (payload.get("data") or {}).get("token")
    return resp.status_code, token, payload


def _call_endpoint(client, method, path, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if method == "GET":
        return client.get(path, headers=headers)
    if method == "POST":
        return client.post(path, headers=headers)
    if method == "PUT":
        return client.put(path, headers=headers)
    if method == "DELETE":
        return client.delete(path, headers=headers)
    raise ValueError(f"Unsupported method: {method}")


def time_api_endpoint(client, method, path, token, runs, warmup):
    for _ in range(warmup):
        r = _call_endpoint(client, method, path, token)
        _ = r.get_data(as_text=False)

    durations = []
    statuses = []
    for _ in range(runs):
        t0 = time.perf_counter()
        r = _call_endpoint(client, method, path, token)
        _ = r.get_data(as_text=False)
        durations.append((time.perf_counter() - t0) * 1000.0)
        statuses.append(r.status_code)

    durations_sorted = sorted(durations)
    return {
        "runs": runs,
        "warmup": warmup,
        "statusCodes": {str(code): statuses.count(code) for code in sorted(set(statuses))},
        "ms": {
            "min": min(durations_sorted),
            "p50": statistics.median(durations_sorted),
            "p95": durations_sorted[int(0.95 * (len(durations_sorted) - 1))],
            "max": max(durations_sorted),
            "mean": statistics.mean(durations_sorted),
        },
    }


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------

def run_benchmarks(runs, warmup, *, customer_id: int, restaurant_id: int, partner_id: int, creds: dict):
    connection = get_db_connection()
    try:
        benchmark_queries = build_benchmark_queries(customer_id, restaurant_id, partner_id)
        api_benchmarks = build_api_benchmarks(customer_id, restaurant_id)
        explain = {}
        query_timings = {}

        for name, spec in benchmark_queries.items():
            sql = " ".join(line.strip() for line in spec["sql"].splitlines() if line.strip())
            params = spec["params"]
            explain[name] = explain_query(connection, sql, params)
            query_timings[name] = time_select_query(connection, sql, params, runs=runs, warmup=warmup)

        api_timings = {}
        api_auth = {}
        with flask_app.test_client() as client:
            # Pre-login once per role and reuse tokens.
            admin_status, admin_token, admin_payload = _login(
                client,
                email=creds["admin_email"],
                password=creds["admin_password"],
                login_as="Admin",
            )
            api_auth["Admin"] = {"status": admin_status, "tokenPresent": bool(admin_token), "response": admin_payload}

            customer_status, customer_token, customer_payload = _login(
                client,
                email=creds["customer_email"],
                password=creds["customer_password"],
                login_as="Customer",
            )
            api_auth["Customer"] = {
                "status": customer_status,
                "tokenPresent": bool(customer_token),
                "response": customer_payload,
            }

            partner_status, partner_token, partner_payload = _login(
                client,
                email=creds["partner_email"],
                password=creds["partner_password"],
                login_as="DeliveryPartner",
            )
            api_auth["DeliveryPartner"] = {
                "status": partner_status,
                "tokenPresent": bool(partner_token),
                "response": partner_payload,
            }

            role_tokens = {
                "Admin": admin_token,
                "Customer": customer_token,
                "DeliveryPartner": partner_token,
            }

            for item in api_benchmarks:
                role = item["role"]
                token = role_tokens.get(role)
                api_timings[item["name"]] = {
                    "method": item["method"],
                    "path": item["path"],
                    "role": role,
                    "timing": time_api_endpoint(
                        client,
                        method=item["method"],
                        path=item["path"],
                        token=token,
                        runs=runs,
                        warmup=warmup,
                    ),
                }

        return {
            "queries": {
                "explain": explain,
                "timings": query_timings,
            },
            "api": {
                "auth": api_auth,
                "timings": api_timings,
            },
        }
    finally:
        if connection and connection.is_connected():
            connection.close()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="QuickBites Module B - SubTask 5 benchmarking (before/after SQL indexes)"
    )
    parser.add_argument("--runs", type=int, default=25, help="Timed runs per query/endpoint")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup runs per query/endpoint")
    parser.add_argument("--customer-id", type=int, default=1, help="CustomerID used for query benchmarks")
    parser.add_argument("--restaurant-id", type=int, default=201, help="RestaurantID used for query benchmarks")
    parser.add_argument("--partner-id", type=int, default=11, help="Delivery partnerID used for query benchmarks")
    parser.add_argument("--admin-email", default="aman.shah1@example.com", help="Admin login email")
    parser.add_argument("--admin-password", default="pwd1", help="Admin login password")
    parser.add_argument("--customer-email", default="riya.patel2@example.com", help="Customer login email")
    parser.add_argument("--customer-password", default="pwd2", help="Customer login password")
    parser.add_argument("--partner-email", default="driver1@example.com", help="Delivery partner login email")
    parser.add_argument("--partner-password", default="drv1", help="Delivery partner login password")
    parser.add_argument(
        "--mode",
        choices=["full", "before", "after", "apply", "drop"],
        default="full",
        help="full=drop->benchmark->apply->benchmark, before=benchmark only, after=benchmark only, apply=apply indexes, drop=drop indexes",
    )

    args = parser.parse_args()

    logs_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs"))
    os.makedirs(logs_dir, exist_ok=True)

    meta = {
        "timestamp": _now_iso(),
        "db": {
            "host": os.getenv("QB_DB_HOST", "127.0.0.1"),
            "port": int(os.getenv("QB_DB_PORT", "3306")),
            "user": os.getenv("QB_DB_USER", "qb_admin"),
            "database": os.getenv("QB_DB_NAME", "QB"),
        },
        "runs": args.runs,
        "warmup": args.warmup,
        "sampleIDs": {
            "customerID": args.customer_id,
            "restaurantID": args.restaurant_id,
            "partnerID": args.partner_id,
        },
        "indexes": [{"table": s.table, "name": s.name} for s in INDEX_SPECS],
    }

    creds = {
        "admin_email": args.admin_email,
        "admin_password": args.admin_password,
        "customer_email": args.customer_email,
        "customer_password": args.customer_password,
        "partner_email": args.partner_email,
        "partner_password": args.partner_password,
    }

    connection = get_db_connection()
    try:
        if args.mode == "drop":
            drop_result = drop_indexes(connection)
            out = {"meta": meta, "drop": drop_result}
        elif args.mode == "apply":
            apply_result = apply_indexes(connection)
            out = {"meta": meta, "apply": apply_result}
        elif args.mode == "before":
            out = {
                "meta": meta,
                "before": run_benchmarks(
                    args.runs,
                    args.warmup,
                    customer_id=args.customer_id,
                    restaurant_id=args.restaurant_id,
                    partner_id=args.partner_id,
                    creds=creds,
                ),
            }
        elif args.mode == "after":
            out = {
                "meta": meta,
                "after": run_benchmarks(
                    args.runs,
                    args.warmup,
                    customer_id=args.customer_id,
                    restaurant_id=args.restaurant_id,
                    partner_id=args.partner_id,
                    creds=creds,
                ),
            }
        else:
            drop_result = drop_indexes(connection)
            before = run_benchmarks(
                args.runs,
                args.warmup,
                customer_id=args.customer_id,
                restaurant_id=args.restaurant_id,
                partner_id=args.partner_id,
                creds=creds,
            )
            apply_result = apply_indexes(connection)
            after = run_benchmarks(
                args.runs,
                args.warmup,
                customer_id=args.customer_id,
                restaurant_id=args.restaurant_id,
                partner_id=args.partner_id,
                creds=creds,
            )
            out = {
                "meta": meta,
                "drop": drop_result,
                "apply": apply_result,
                "before": before,
                "after": after,
            }

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(logs_dir, f"index_benchmark_{stamp}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True)

        print(out_path)
    finally:
        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()
