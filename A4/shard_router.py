import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import mysql.connector
from mysql.connector import Error


DEFAULT_SHARD_HOST = "10.0.116.184"
DEFAULT_SHARD_PORTS = "3307,3308,3309"
DEFAULT_SHARD_USER = "ScaleOps"
DEFAULT_SHARD_PASSWORD = "password@123"
DEFAULT_SHARD_DATABASE = "ScaleOps"
DEFAULT_SHARD_COUNT = 3

# Logical table names used by the sharded implementation.
SHARDED_TABLES = {
    "customer",
    "address",
    "cartitem",
    "payment",
    "orders",
}

CUSTOMER_TABLE_COLUMNS = [
    "customerID",
    "loyaltyTier",
    "membershipDiscount",
    "cartTotalAmount",
    "membershipDueDate",
    "membership",
    "isDeleted",
]


class ShardRoutingError(Exception):
    """Raised for invalid shard configuration or invalid shard inputs."""


@dataclass(frozen=True)
class ShardNode:
    shard_id: int
    host: str
    port: int
    user: str
    password: str
    database: str



def _parse_shard_ports(raw_ports: str, shard_count: int) -> List[int]:
    ports = []
    for token in str(raw_ports or "").split(","):
        token = token.strip()
        if not token:
            continue
        ports.append(int(token))

    if len(ports) != shard_count:
        raise ShardRoutingError(
            f"QB_SHARD_PORTS must contain exactly {shard_count} ports, got {len(ports)}"
        )
    return ports



def load_shard_nodes_from_env() -> List[ShardNode]:
    shard_count = int(os.getenv("QB_SHARD_COUNT", str(DEFAULT_SHARD_COUNT)))
    host = os.getenv("QB_SHARD_HOST", DEFAULT_SHARD_HOST)
    ports = _parse_shard_ports(os.getenv("QB_SHARD_PORTS", DEFAULT_SHARD_PORTS), shard_count)
    user = os.getenv("QB_SHARD_USER", DEFAULT_SHARD_USER)
    password = os.getenv("QB_SHARD_PASSWORD", DEFAULT_SHARD_PASSWORD)
    database = os.getenv("QB_SHARD_DB", DEFAULT_SHARD_DATABASE)

    return [
        ShardNode(
            shard_id=i,
            host=host,
            port=ports[i],
            user=user,
            password=password,
            database=database,
        )
        for i in range(shard_count)
    ]


class ShardRouter:
    def __init__(self, nodes: Optional[List[ShardNode]] = None):
        self.nodes = nodes or load_shard_nodes_from_env()
        if not self.nodes:
            raise ShardRoutingError("No shard nodes configured")
        self.num_shards = len(self.nodes)

    def shard_for_customer(self, customer_id: int) -> int:
        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError) as exc:
            raise ShardRoutingError("customer_id must be an integer") from exc

        if customer_id < 0:
            raise ShardRoutingError("customer_id must be non-negative")

        return customer_id % self.num_shards

    def table_name(self, logical_table: str, shard_id: int) -> str:
        logical = str(logical_table or "").strip().lower()
        if logical not in SHARDED_TABLES:
            raise ShardRoutingError(f"Unsupported sharded table: {logical_table}")
        if shard_id < 0 or shard_id >= self.num_shards:
            raise ShardRoutingError(f"Invalid shard_id: {shard_id}")
        return f"shard_{shard_id}_{logical}"

    def connect_to_shard(self, shard_id: int):
        if shard_id < 0 or shard_id >= self.num_shards:
            raise ShardRoutingError(f"Invalid shard_id: {shard_id}")

        node = self.nodes[shard_id]
        connection = mysql.connector.connect(
            host=node.host,
            port=node.port,
            user=node.user,
            password=node.password,
            database=node.database,
        )
        cursor = connection.cursor()
        cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cursor.execute("SET time_zone = '+05:30'")
        cursor.close()
        return connection

    def connect_for_customer(self, customer_id: int):
        shard_id = self.shard_for_customer(customer_id)
        connection = self.connect_to_shard(shard_id)
        return shard_id, connection

    def shard_summary(self) -> List[Dict[str, object]]:
        result = []
        for node in self.nodes:
            result.append(
                {
                    "shardID": node.shard_id,
                    "host": node.host,
                    "port": node.port,
                    "database": node.database,
                    "user": node.user,
                }
            )
        return result

    def upsert_customer(self, payload: Dict[str, object]) -> Dict[str, object]:
        if not isinstance(payload, dict):
            raise ShardRoutingError("payload must be a JSON object")

        if "customerID" not in payload:
            raise ShardRoutingError("customerID is required")

        customer_id = int(payload["customerID"])
        shard_id, connection = self.connect_for_customer(customer_id)
        table_name = self.table_name("customer", shard_id)

        loyalty_tier = int(payload.get("loyaltyTier", 1))
        membership_discount = float(payload.get("membershipDiscount", 0.0))
        cart_total_amount = float(payload.get("cartTotalAmount", 0.0))
        membership_due_date = payload.get("membershipDueDate")
        membership = int(bool(payload.get("membership", 0)))
        is_deleted = int(bool(payload.get("isDeleted", 0)))

        if isinstance(membership_due_date, str) and not membership_due_date.strip():
            membership_due_date = None

        try:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO {table_name}
                (customerID, loyaltyTier, membershipDiscount, cartTotalAmount, membershipDueDate, membership, isDeleted)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    loyaltyTier = VALUES(loyaltyTier),
                    membershipDiscount = VALUES(membershipDiscount),
                    cartTotalAmount = VALUES(cartTotalAmount),
                    membershipDueDate = VALUES(membershipDueDate),
                    membership = VALUES(membership),
                    isDeleted = VALUES(isDeleted)
                """,
                (
                    customer_id,
                    loyalty_tier,
                    membership_discount,
                    cart_total_amount,
                    membership_due_date,
                    membership,
                    is_deleted,
                ),
            )
            connection.commit()
        finally:
            if connection.is_connected():
                connection.close()

        return {
            "customerID": customer_id,
            "shardID": shard_id,
            "table": table_name,
        }

    def get_customer(self, customer_id: int) -> Optional[Dict[str, object]]:
        shard_id, connection = self.connect_for_customer(customer_id)
        table_name = self.table_name("customer", shard_id)

        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                f"""
                SELECT customerID, loyaltyTier, membershipDiscount, cartTotalAmount,
                       membershipDueDate, membership, isDeleted
                FROM {table_name}
                WHERE customerID = %s
                LIMIT 1
                """,
                (int(customer_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            row["shardID"] = shard_id
            return row
        finally:
            if connection.is_connected():
                connection.close()

    def get_customers_in_range(self, start_customer_id: int, end_customer_id: int, limit: int = 1000):
        start_customer_id = int(start_customer_id)
        end_customer_id = int(end_customer_id)
        if start_customer_id > end_customer_id:
            raise ShardRoutingError("start_customer_id must be <= end_customer_id")
        if limit <= 0:
            raise ShardRoutingError("limit must be positive")

        rows = []
        for shard_id in range(self.num_shards):
            connection = self.connect_to_shard(shard_id)
            table_name = self.table_name("customer", shard_id)
            try:
                cursor = connection.cursor(dictionary=True)
                cursor.execute(
                    f"""
                    SELECT customerID, loyaltyTier, membershipDiscount, cartTotalAmount,
                           membershipDueDate, membership, isDeleted
                    FROM {table_name}
                    WHERE customerID BETWEEN %s AND %s
                    ORDER BY customerID ASC
                    LIMIT %s
                    """,
                    (start_customer_id, end_customer_id, int(limit)),
                )
                shard_rows = cursor.fetchall()
                for row in shard_rows:
                    row["shardID"] = shard_id
                rows.extend(shard_rows)
            finally:
                if connection.is_connected():
                    connection.close()

        rows.sort(key=lambda item: int(item.get("customerID", 0)))
        return rows[:limit]


__all__ = [
    "ShardNode",
    "ShardRouter",
    "ShardRoutingError",
    "SHARDED_TABLES",
    "CUSTOMER_TABLE_COLUMNS",
    "load_shard_nodes_from_env",
]
