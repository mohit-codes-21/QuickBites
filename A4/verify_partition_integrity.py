#!/usr/bin/env python3
"""Verify SubTask 2 partition integrity.

Checks implemented:
1) Each shard contains only its designated subset of rows.
2) No records are lost or duplicated across shards after migration.

Usage:
  python verify_partition_integrity.py
  python verify_partition_integrity.py --report-path logs/subtask2_partition_verification.json
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Set, Tuple

import mysql.connector
from mysql.connector import Error

from shard_admin import DIRECT_ROUTE_TABLES, MIGRATION_ORDER, SOURCE_TABLE_NAMES, TABLE_PRIMARY_KEYS
from shard_router import ShardRouter, ShardRoutingError


def source_db_config() -> Dict[str, object]:
    return {
        "host": os.getenv("QB_SOURCE_DB_HOST", os.getenv("QB_DB_HOST", "127.0.0.1")),
        "port": int(os.getenv("QB_SOURCE_DB_PORT", os.getenv("QB_DB_PORT", "3306"))),
        "user": os.getenv("QB_SOURCE_DB_USER", os.getenv("QB_DB_USER", "qb_admin")),
        "password": os.getenv("QB_SOURCE_DB_PASSWORD", os.getenv("QB_DB_PASSWORD", "qb_admin@123")),
        "database": os.getenv("QB_SOURCE_DB_NAME", os.getenv("QB_DB_NAME", "QB")),
    }


def connect_source_db():
    cfg = source_db_config()
    return mysql.connector.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
    )


def _sample_keys(keys: Set[Tuple[object, ...]], sample_size: int) -> List[List[object]]:
    sample: List[List[object]] = []
    for key in list(keys)[:sample_size]:
        sample.append(list(key))
    return sample


def verify_partition_integrity(sample_size: int = 5) -> Dict[str, object]:
    router = ShardRouter()
    source_conn = connect_source_db()
    shard_conns = {sid: router.connect_to_shard(sid) for sid in range(router.num_shards)}

    report: Dict[str, object] = {
        "source": source_db_config(),
        "shards": router.shard_summary(),
        "tables": {},
        "checks": {
            "designatedSubset": "Each shard contains only rows routed to that shard",
            "noLossOrDuplication": "No missing keys, no extra keys, no cross-shard duplicate keys",
        },
        "ok": True,
    }

    try:
        for logical_table in MIGRATION_ORDER:
            source_table = SOURCE_TABLE_NAMES[logical_table]
            key_cols = TABLE_PRIMARY_KEYS[logical_table]
            route_col = DIRECT_ROUTE_TABLES[logical_table]

            src_cur = source_conn.cursor(dictionary=True)
            src_cur.execute(f"SELECT {', '.join(key_cols)} FROM {source_table}")
            source_rows = src_cur.fetchall()
            source_keys: Set[Tuple[object, ...]] = {
                tuple(row[col] for col in key_cols)
                for row in source_rows
            }

            shard_counts: Dict[int, int] = {}
            per_shard_bad_route: Dict[int, int] = {}
            seen_keys: Dict[Tuple[object, ...], int] = {}
            shard_keys: Set[Tuple[object, ...]] = set()
            duplicate_details: List[Dict[str, object]] = []

            for shard_id in range(router.num_shards):
                conn = shard_conns[shard_id]
                shard_table = router.table_name(logical_table, shard_id)
                cur = conn.cursor(dictionary=True)
                cur.execute(f"SELECT {', '.join(key_cols + [route_col])} FROM {shard_table}")
                rows = cur.fetchall()

                shard_counts[shard_id] = len(rows)
                bad_route_count = 0

                for row in rows:
                    key = tuple(row[col] for col in key_cols)
                    shard_keys.add(key)

                    if key in seen_keys:
                        duplicate_details.append(
                            {
                                "key": list(key),
                                "firstShard": seen_keys[key],
                                "secondShard": shard_id,
                            }
                        )
                    else:
                        seen_keys[key] = shard_id

                    expected_shard = router.shard_for_customer(int(row[route_col]))
                    if expected_shard != shard_id:
                        bad_route_count += 1

                per_shard_bad_route[shard_id] = bad_route_count

            missing_keys = source_keys - shard_keys
            extra_keys = shard_keys - source_keys
            duplicate_count = len(duplicate_details)
            bad_route_total = sum(per_shard_bad_route.values())

            designated_subset_ok = bad_route_total == 0
            no_loss_dup_ok = len(missing_keys) == 0 and len(extra_keys) == 0 and duplicate_count == 0
            table_ok = designated_subset_ok and no_loss_dup_ok

            if not table_ok:
                report["ok"] = False

            report["tables"][logical_table] = {
                "sourceCount": len(source_keys),
                "shardCounts": shard_counts,
                "shardTotal": sum(shard_counts.values()),
                "badRouteCount": bad_route_total,
                "missingKeyCount": len(missing_keys),
                "extraKeyCount": len(extra_keys),
                "crossShardDuplicateKeyCount": duplicate_count,
                "sampleMissingKeys": _sample_keys(missing_keys, sample_size),
                "sampleExtraKeys": _sample_keys(extra_keys, sample_size),
                "sampleDuplicateKeys": duplicate_details[:sample_size],
                "okDesignatedSubset": designated_subset_ok,
                "okNoLossOrDuplication": no_loss_dup_ok,
                "ok": table_ok,
            }

        return report
    finally:
        if source_conn.is_connected():
            source_conn.close()
        for conn in shard_conns.values():
            if conn.is_connected():
                conn.close()


def print_summary(report: Dict[str, object]) -> None:
    print("SubTask 2 Partition Integrity Verification")
    print("=" * 72)
    for table, info in (report.get("tables") or {}).items():
        subset_status = "PASS" if info.get("okDesignatedSubset") else "FAIL"
        integrity_status = "PASS" if info.get("okNoLossOrDuplication") else "FAIL"
        print(
            f"[{table}] subset={subset_status}, no-loss-dup={integrity_status}, "
            f"badRoute={info.get('badRouteCount')}, missing={info.get('missingKeyCount')}, "
            f"extra={info.get('extraKeyCount')}, dup={info.get('crossShardDuplicateKeyCount')}"
        )

    print("-" * 72)
    print(f"OVERALL STATUS: {'PASS' if report.get('ok') else 'FAIL'}")


def write_report(report: Dict[str, object], report_path: str) -> None:
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify designated subset routing and no-loss/no-dup integrity for sharded tables"
    )
    parser.add_argument(
        "--report-path",
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "logs", "subtask2_partition_verification.json")),
        help="Path to write JSON verification report",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="How many sample keys to include for missing/extra/duplicate findings",
    )
    args = parser.parse_args()

    try:
        report = verify_partition_integrity(sample_size=max(1, int(args.sample_size)))
        write_report(report, args.report_path)
        print_summary(report)
        print(f"Report written to: {args.report_path}")
        return 0 if report.get("ok") else 2
    except (ShardRoutingError, Error, ValueError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
