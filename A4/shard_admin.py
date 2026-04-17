import argparse
import json
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

import mysql.connector
from mysql.connector import Error

from shard_router import ShardRouter, ShardRoutingError


TABLE_COLUMNS: Dict[str, List[str]] = {
    "member": ["memberID", "name", "email", "password", "phoneNumber", "createdAt", "isDeleted"],
    "deliverypartner": [
        "partnerID",
        "vehicleNumber",
        "licenseID",
        "dateOfBirth",
        "currentLatitude",
        "currentLongitude",
        "isOnline",
        "averageRating",
        "image",
        "isDeleted",
    ],
    "restaurant": [
        "restaurantID",
        "name",
        "contactPhone",
        "email",
        "password",
        "isOpen",
        "isVerified",
        "averageRating",
        "addressLine",
        "city",
        "zipCode",
        "latitude",
        "longitude",
        "discontinued",
        "isDeleted",
    ],
    "menuitem": [
        "restaurantID",
        "itemID",
        "name",
        "description",
        "menuCategory",
        "restaurantPrice",
        "appPrice",
        "isVegetarian",
        "averageRating",
        "preparationTime",
        "isAvailable",
        "discontinued",
    ],
    "customer": [
        "customerID",
        "loyaltyTier",
        "membershipDiscount",
        "cartTotalAmount",
        "membershipDueDate",
        "membership",
        "isDeleted",
    ],
    "address": [
        "customerID",
        "addressID",
        "addressLine",
        "city",
        "zipCode",
        "label",
        "latitude",
        "longitude",
        "isSaved",
    ],
    "cartitem": ["customerID", "restaurantID", "itemID", "quantity"],
    "payment": ["paymentID", "customerID", "amount", "paymentType", "status", "transactionTime", "paymentFor"],
    "orders": [
        "orderID",
        "orderTime",
        "estimatedTime",
        "totalAmount",
        "orderStatus",
        "customerID",
        "restaurantID",
        "addressID",
        "paymentID",
        "specialInstruction",
    ],
    "orderitem": ["orderID", "restaurantID", "itemID", "quantity", "priceAtPurchase"],
    "delivery_assignments": ["AssignmentID", "OrderID", "PartnerID", "acceptanceTime", "pickupTime", "deliveryTime"],
    "orderrating": ["orderID", "restaurantRating", "deliveryRating", "comment"],
    "menuitemrating": ["restaurantID", "itemID", "orderID", "rating", "comment"],
}

TABLE_PRIMARY_KEYS: Dict[str, List[str]] = {
    "member": ["memberID"],
    "deliverypartner": ["partnerID"],
    "restaurant": ["restaurantID"],
    "menuitem": ["restaurantID", "itemID"],
    "customer": ["customerID"],
    "address": ["customerID", "addressID"],
    "cartitem": ["customerID", "restaurantID", "itemID"],
    "payment": ["paymentID"],
    "orders": ["orderID"],
    "orderitem": ["orderID", "restaurantID", "itemID"],
    "delivery_assignments": ["AssignmentID"],
    "orderrating": ["orderID"],
    "menuitemrating": ["restaurantID", "itemID", "orderID"],
}

SOURCE_TABLE_NAMES: Dict[str, str] = {
    "member": "Member",
    "deliverypartner": "DeliveryPartner",
    "restaurant": "Restaurant",
    "menuitem": "MenuItem",
    "customer": "Customer",
    "address": "Address",
    "cartitem": "CartItem",
    "payment": "Payment",
    "orders": "Orders",
    "orderitem": "OrderItem",
    "delivery_assignments": "Delivery_Assignments",
    "orderrating": "OrderRating",
    "menuitemrating": "MenuItemRating",
}

TABLE_CREATE_SQL: Dict[str, str] = {
    "member": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            memberID INT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL,
            password VARCHAR(100) NOT NULL,
            phoneNumber CHAR(10) NOT NULL,
            createdAt DATETIME NOT NULL,
            isDeleted BOOLEAN NOT NULL DEFAULT 0
        )
    """,
    "deliverypartner": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            partnerID INT PRIMARY KEY,
            vehicleNumber VARCHAR(100) NOT NULL,
            licenseID VARCHAR(100) NOT NULL,
            dateOfBirth DATE NOT NULL,
            currentLatitude DOUBLE NOT NULL,
            currentLongitude DOUBLE NOT NULL,
            isOnline BOOLEAN NOT NULL,
            averageRating FLOAT,
            image BLOB,
            isDeleted BOOLEAN NOT NULL DEFAULT 0
        )
    """,
    "restaurant": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            restaurantID INT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            contactPhone CHAR(10) NOT NULL,
            email VARCHAR(100) NOT NULL,
            password VARCHAR(100) NOT NULL,
            isOpen BOOLEAN NOT NULL,
            isVerified BOOLEAN NOT NULL,
            averageRating FLOAT,
            addressLine VARCHAR(100) NOT NULL,
            city VARCHAR(100) NOT NULL,
            zipCode CHAR(6) NOT NULL,
            latitude DOUBLE NOT NULL,
            longitude DOUBLE NOT NULL,
            discontinued BOOLEAN NOT NULL,
            isDeleted BOOLEAN NOT NULL DEFAULT 0
        )
    """,
    "menuitem": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            restaurantID INT NOT NULL,
            itemID INT NOT NULL,
            name VARCHAR(100) NOT NULL,
            description VARCHAR(100),
            menuCategory VARCHAR(100),
            restaurantPrice DECIMAL(10,2) NOT NULL,
            appPrice DECIMAL(10,2) NOT NULL,
            isVegetarian BOOLEAN NOT NULL,
            averageRating FLOAT,
            preparationTime INT NOT NULL,
            isAvailable BOOLEAN NOT NULL,
            discontinued BOOLEAN NOT NULL,
            PRIMARY KEY (restaurantID, itemID)
        )
    """,
    "customer": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            customerID INT PRIMARY KEY,
            loyaltyTier INT NOT NULL,
            membershipDiscount FLOAT NOT NULL,
            cartTotalAmount DECIMAL(10,2) NOT NULL,
            membershipDueDate DATETIME NULL,
            membership BOOLEAN NOT NULL,
            isDeleted BOOLEAN NOT NULL DEFAULT 0
        )
    """,
    "address": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            customerID INT NOT NULL,
            addressID INT NOT NULL,
            addressLine VARCHAR(100) NOT NULL,
            city VARCHAR(100) NOT NULL,
            zipCode CHAR(6) NOT NULL,
            label VARCHAR(100) NOT NULL,
            latitude DOUBLE NOT NULL,
            longitude DOUBLE NOT NULL,
            isSaved BOOLEAN NOT NULL,
            PRIMARY KEY (customerID, addressID)
        )
    """,
    "cartitem": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            customerID INT NOT NULL,
            restaurantID INT NOT NULL,
            itemID INT NOT NULL,
            quantity INT NOT NULL,
            PRIMARY KEY (customerID, restaurantID, itemID)
        )
    """,
    "payment": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            paymentID INT PRIMARY KEY,
            customerID INT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            paymentType VARCHAR(12) NOT NULL,
            status VARCHAR(7) NOT NULL,
            transactionTime DATETIME NOT NULL,
            paymentFor VARCHAR(10) NOT NULL
        )
    """,
    "orders": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            orderID INT PRIMARY KEY,
            orderTime DATETIME NOT NULL,
            estimatedTime DATETIME NOT NULL,
            totalAmount DECIMAL(10,2) NOT NULL,
            orderStatus VARCHAR(20) NOT NULL,
            customerID INT NOT NULL,
            restaurantID INT NOT NULL,
            addressID INT NOT NULL,
            paymentID INT NOT NULL,
            specialInstruction VARCHAR(1000)
        )
    """,
    "orderitem": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            orderID INT NOT NULL,
            restaurantID INT NOT NULL,
            itemID INT NOT NULL,
            quantity INT NOT NULL,
            priceAtPurchase DECIMAL(10,2) NOT NULL,
            PRIMARY KEY (orderID, restaurantID, itemID)
        )
    """,
    "delivery_assignments": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            AssignmentID INT PRIMARY KEY,
            OrderID INT NOT NULL,
            PartnerID INT NOT NULL,
            acceptanceTime DATETIME NOT NULL,
            pickupTime DATETIME NOT NULL,
            deliveryTime DATETIME NOT NULL
        )
    """,
    "orderrating": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            orderID INT PRIMARY KEY,
            restaurantRating INT,
            deliveryRating INT,
            comment VARCHAR(1000)
        )
    """,
    "menuitemrating": """
        CREATE TABLE IF NOT EXISTS {table_name} (
            restaurantID INT NOT NULL,
            itemID INT NOT NULL,
            orderID INT NOT NULL,
            rating INT,
            comment VARCHAR(1000),
            PRIMARY KEY (restaurantID, itemID, orderID)
        )
    """,
}

# Tables where routing can be computed directly from customerID.
DIRECT_ROUTE_TABLES: Dict[str, str] = {
    "customer": "customerID",
    "address": "customerID",
    "cartitem": "customerID",
    "payment": "customerID",
    "orders": "customerID",
}

# Tables that remain in the monolith/local DB and are intentionally not sharded.
LOCAL_ONLY_TABLES = {
    "member",
    "deliverypartner",
    "restaurant",
    "menuitem",
    "orderitem",
    "delivery_assignments",
    "orderrating",
    "menuitemrating",
}

# Only direct customerID tables are sharded.
MIGRATION_ORDER = [
    "customer",
    "address",
    "cartitem",
    "payment",
    "orders",
]


def _source_db_config() -> Dict[str, object]:
    return {
        "host": os.getenv("QB_SOURCE_DB_HOST", os.getenv("QB_DB_HOST", "127.0.0.1")),
        "port": int(os.getenv("QB_SOURCE_DB_PORT", os.getenv("QB_DB_PORT", "3306"))),
        "user": os.getenv("QB_SOURCE_DB_USER", os.getenv("QB_DB_USER", "qb_admin")),
        "password": os.getenv("QB_SOURCE_DB_PASSWORD", os.getenv("QB_DB_PASSWORD", "qb_admin@123")),
        "database": os.getenv("QB_SOURCE_DB_NAME", os.getenv("QB_DB_NAME", "QB")),
    }


def _connect_source_db():
    cfg = _source_db_config()
    return mysql.connector.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
    )


def _fetch_source_rows(connection, logical_table: str) -> List[Dict[str, object]]:
    source_table = SOURCE_TABLE_NAMES[logical_table]
    columns = TABLE_COLUMNS[logical_table]
    cursor = connection.cursor(dictionary=True)
    cursor.execute(f"SELECT {', '.join(columns)} FROM {source_table}")
    return cursor.fetchall()


def _table_insert_sql(table_name: str, columns: Iterable[str]) -> str:
    col_sql = ", ".join(columns)
    values_sql = ", ".join(["%s"] * len(list(columns)))
    return f"INSERT INTO {table_name} ({col_sql}) VALUES ({values_sql})"


def create_shard_tables(router: ShardRouter, drop_existing: bool = False) -> None:
    for shard_id in range(router.num_shards):
        conn = router.connect_to_shard(shard_id)
        try:
            cursor = conn.cursor()
            for logical_table in MIGRATION_ORDER:
                table_name = router.table_name(logical_table, shard_id)
                if drop_existing:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                cursor.execute(TABLE_CREATE_SQL[logical_table].format(table_name=table_name))
            conn.commit()
        finally:
            if conn.is_connected():
                conn.close()


def _truncate_sharded_tables(router: ShardRouter) -> None:
    for shard_id in range(router.num_shards):
        conn = router.connect_to_shard(shard_id)
        try:
            cursor = conn.cursor()
            for logical_table in MIGRATION_ORDER:
                table_name = router.table_name(logical_table, shard_id)
                cursor.execute(f"TRUNCATE TABLE {table_name}")
            conn.commit()
        finally:
            if conn.is_connected():
                conn.close()


def migrate_data(router: ShardRouter, truncate_first: bool = True) -> Dict[str, Dict[int, int]]:
    if truncate_first:
        _truncate_sharded_tables(router)

    source_conn = _connect_source_db()
    shard_conns = {shard_id: router.connect_to_shard(shard_id) for shard_id in range(router.num_shards)}
    inserted_counts: Dict[str, Dict[int, int]] = {table: {sid: 0 for sid in range(router.num_shards)} for table in MIGRATION_ORDER}

    try:
        for logical_table in MIGRATION_ORDER:
            rows = _fetch_source_rows(source_conn, logical_table)
            columns = TABLE_COLUMNS[logical_table]

            grouped_rows: Dict[int, List[Tuple[object, ...]]] = defaultdict(list)

            for row in rows:
                if logical_table in DIRECT_ROUTE_TABLES:
                    customer_id = int(row[DIRECT_ROUTE_TABLES[logical_table]])
                else:
                    raise ShardRoutingError(f"Routing rule missing for table '{logical_table}'")

                shard_id = router.shard_for_customer(customer_id)
                grouped_rows[shard_id].append(tuple(row[col] for col in columns))

            for shard_id in range(router.num_shards):
                batch = grouped_rows.get(shard_id, [])
                if not batch:
                    continue

                shard_conn = shard_conns[shard_id]
                table_name = router.table_name(logical_table, shard_id)
                insert_sql = _table_insert_sql(table_name, columns)
                shard_cursor = shard_conn.cursor()
                shard_cursor.executemany(insert_sql, batch)
                inserted_counts[logical_table][shard_id] += len(batch)

        for shard_conn in shard_conns.values():
            shard_conn.commit()

        return inserted_counts
    except Exception:
        for shard_conn in shard_conns.values():
            shard_conn.rollback()
        raise
    finally:
        if source_conn.is_connected():
            source_conn.close()
        for shard_conn in shard_conns.values():
            if shard_conn.is_connected():
                shard_conn.close()


def verify_migration(router: ShardRouter) -> Dict[str, object]:
    source_conn = _connect_source_db()
    shard_conns = {shard_id: router.connect_to_shard(shard_id) for shard_id in range(router.num_shards)}

    report: Dict[str, object] = {
        "source": _source_db_config(),
        "shards": router.shard_summary(),
        "tables": {},
        "ok": True,
    }

    try:
        for logical_table in MIGRATION_ORDER:
            source_table_name = SOURCE_TABLE_NAMES[logical_table]
            src_cur = source_conn.cursor(dictionary=True)
            src_cur.execute(f"SELECT COUNT(*) AS cnt FROM {source_table_name}")
            source_count = int((src_cur.fetchone() or {}).get("cnt", 0))

            key_cols = TABLE_PRIMARY_KEYS[logical_table]
            shard_counts: Dict[int, int] = {}
            per_shard_bad_route: Dict[int, int] = {}

            seen_keys: Dict[Tuple[object, ...], int] = {}
            duplicate_keys: List[Dict[str, object]] = []

            for shard_id in range(router.num_shards):
                conn = shard_conns[shard_id]
                table_name = router.table_name(logical_table, shard_id)
                cursor = conn.cursor(dictionary=True)

                cursor.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}")
                shard_counts[shard_id] = int((cursor.fetchone() or {}).get("cnt", 0))

                cursor.execute(f"SELECT {', '.join(key_cols + TABLE_COLUMNS[logical_table])} FROM {table_name}")
                rows = cursor.fetchall()

                bad_route_count = 0
                for row in rows:
                    key = tuple(row[col] for col in key_cols)
                    if key in seen_keys:
                        duplicate_keys.append(
                            {
                                "key": key,
                                "firstShard": seen_keys[key],
                                "secondShard": shard_id,
                            }
                        )
                    else:
                        seen_keys[key] = shard_id

                    if logical_table in DIRECT_ROUTE_TABLES:
                        customer_id = int(row[DIRECT_ROUTE_TABLES[logical_table]])
                    else:
                        bad_route_count += 1
                        continue

                    expected_shard = router.shard_for_customer(customer_id)
                    if expected_shard != shard_id:
                        bad_route_count += 1

                per_shard_bad_route[shard_id] = bad_route_count

            shard_total = sum(shard_counts.values())
            loss_or_extra = shard_total - source_count
            table_ok = (
                shard_total == source_count
                and not duplicate_keys
                and sum(per_shard_bad_route.values()) == 0
            )

            if not table_ok:
                report["ok"] = False

            report["tables"][logical_table] = {
                "strategy": "partitioned",
                "sourceCount": source_count,
                "shardCounts": shard_counts,
                "shardTotal": shard_total,
                "deltaShardTotalMinusSource": loss_or_extra,
                "duplicateKeyCount": len(duplicate_keys),
                "badRouteCount": sum(per_shard_bad_route.values()),
                "ok": table_ok,
            }

        return report
    finally:
        if source_conn.is_connected():
            source_conn.close()
        for conn in shard_conns.values():
            if conn.is_connected():
                conn.close()


def run_full_pipeline(drop_existing: bool = True, truncate_first: bool = True) -> Dict[str, object]:
    router = ShardRouter()
    create_shard_tables(router, drop_existing=drop_existing)
    migrated_counts = migrate_data(router, truncate_first=truncate_first)
    verification = verify_migration(router)
    verification["migratedCounts"] = migrated_counts
    return verification


def _write_report(report: Dict[str, object], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(description="ScaleOps shard setup + migration + verification")
    parser.add_argument(
        "action",
        choices=["setup", "migrate", "verify", "full"],
        help="Operation to run",
    )
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop existing shard tables before setup",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Do not truncate shard tables before migrate",
    )
    parser.add_argument(
        "--report-path",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "logs", "subtask2_shard_report.json")),
        help="Path to write JSON report for verify/full",
    )
    args = parser.parse_args()

    try:
        router = ShardRouter()
        if args.action == "setup":
            create_shard_tables(router, drop_existing=args.drop_existing)
            print("Shard table setup completed.")
            return 0

        if args.action == "migrate":
            migrated_counts = migrate_data(router, truncate_first=not args.no_truncate)
            print(json.dumps({"migratedCounts": migrated_counts}, indent=2, default=str))
            return 0

        if args.action == "verify":
            verification = verify_migration(router)
            _write_report(verification, args.report_path)
            print(json.dumps(verification, indent=2, default=str))
            return 0 if verification.get("ok") else 2

        if args.action == "full":
            report = run_full_pipeline(drop_existing=args.drop_existing, truncate_first=not args.no_truncate)
            _write_report(report, args.report_path)
            print(json.dumps(report, indent=2, default=str))
            return 0 if report.get("ok") else 2

        return 1
    except (ShardRoutingError, Error, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
