from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _ensure_import_path() -> None:
    # Add db_management_system/ to sys.path so `import database` works
    base_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(base_dir))


def main() -> int:
    _ensure_import_path()

    from database import DatabaseManager

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--mode", choices=["commit", "crash"], required=True)
    parser.add_argument("--order-id", type=int, default=1000)
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--product-id", type=int, default=101)
    parser.add_argument("--amount", type=float, default=10.0)
    parser.add_argument("--flush", action="store_true", help="Force snapshots to disk before finishing")
    args = parser.parse_args()

    db = DatabaseManager(data_dir=args.data_dir, recover=True)

    with db.transaction() as tx:
        user = tx.get("users", args.user_id)
        product = tx.get("products", args.product_id)

        if user is None:
            raise SystemExit(f"Missing user {args.user_id}")
        if product is None:
            raise SystemExit(f"Missing product {args.product_id}")

        # Multi-relation transaction: update user balance, update product stock, insert order.
        user["balance"] = user["balance"] - int(args.amount)
        product["stock"] = product["stock"] - 1

        tx.update("users", args.user_id, user)
        tx.update("products", args.product_id, product)

        tx.insert(
            "orders",
            {
                "order_id": args.order_id,
                "user_id": args.user_id,
                "product_id": args.product_id,
                "amount": float(args.amount),
            },
        )

        if args.flush:
            db.flush()

        if args.mode == "crash":
            os._exit(1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
