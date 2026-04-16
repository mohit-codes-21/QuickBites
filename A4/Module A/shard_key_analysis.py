"""
SubTask 1 -- Shard Key Selection & Justification (Module A)
===========================================================
QuickBites -- CS 432 Databases, Assignment 4

This module documents and verifies the shard-key decision for the
Module-A custom B+Tree database.

Decision summary
----------------
  Shard Key  : customerID
  Strategy   : Hash-based   shard_id = customerID % NUM_SHARDS
  Num shards : 3
"""

from __future__ import annotations

NUM_SHARDS = 3


# ---------------------------------------------------------------------------
# Shard routing function
# ---------------------------------------------------------------------------

def get_shard(customer_id: int, num_shards: int = NUM_SHARDS) -> int:
    """Return the shard index for a given customerID.

    Uses modulo hashing so that every customerID deterministically maps
    to exactly one shard without any external lookup table.
    """
    return customer_id % num_shards


# ---------------------------------------------------------------------------
# Dataset extracted from the A1 SQL dump
# ---------------------------------------------------------------------------

CUSTOMERS = list(range(1, 11))          # customerIDs 1-10

ORDERS = [
    (5001, 1), (5002, 2), (5003, 3), (5004, 4),
    (5005, 5), (5006, 6), (5007, 7), (5008, 8),
    (5009, 9), (5010, 10), (5011, 3), (5012, 1),
]  # (orderID, customerID)

PAYMENTS = [
    (1001, 1), (1002, 2), (1003, 3), (1004, 4),
    (1005, 5), (1006, 6), (1007, 7), (1008, 8),
    (1009, 9), (1010, 10), (1011, 3), (1012, 1),
]  # (paymentID, customerID)

# Two addresses per customer
ADDRESSES = [(cid, aid) for cid in CUSTOMERS for aid in (1, 2)]

CART_ITEMS = [
    (1, 201, 1), (1, 201, 2), (2, 203, 1), (3, 202, 1),
    (4, 206, 1), (5, 205, 1), (6, 206, 2), (7, 207, 1),
    (8, 208, 1), (9, 210, 2), (10, 209, 1), (3, 202, 2),
]  # (customerID, restaurantID, itemID)


# ---------------------------------------------------------------------------
# Distribution analysis
# ---------------------------------------------------------------------------

def analyse_distribution(num_shards: int = NUM_SHARDS) -> dict:
    """Compute per-shard row counts and balance metrics."""
    shards: dict[int, dict] = {
        i: {"customers": 0, "orders": 0, "payments": 0, "addresses": 0, "cart_items": 0}
        for i in range(num_shards)
    }

    for cid in CUSTOMERS:
        shards[get_shard(cid, num_shards)]["customers"] += 1

    for _oid, cid in ORDERS:
        shards[get_shard(cid, num_shards)]["orders"] += 1

    for _pid, cid in PAYMENTS:
        shards[get_shard(cid, num_shards)]["payments"] += 1

    for cid, _aid in ADDRESSES:
        shards[get_shard(cid, num_shards)]["addresses"] += 1

    for cid, _rid, _iid in CART_ITEMS:
        shards[get_shard(cid, num_shards)]["cart_items"] += 1

    return shards


def print_report(num_shards: int = NUM_SHARDS) -> None:
    shards = analyse_distribution(num_shards)

    print("=" * 62)
    print(f"QuickBites -- Shard Distribution Analysis  ({num_shards} shards)")
    print(f"Shard Key   : customerID")
    print(f"Strategy    : Hash-based  (customerID % {num_shards})")
    print("=" * 62)

    # Per-shard breakdown
    totals: dict[str, int] = {}
    header = f"{'Table':<14}" + "".join(f"  Shard {i:1d}" for i in range(num_shards)) + "   Total"
    print(header)
    print("-" * len(header))

    tables = ["customers", "orders", "payments", "addresses", "cart_items"]
    for tbl in tables:
        counts = [shards[i][tbl] for i in range(num_shards)]
        total = sum(counts)
        totals[tbl] = total
        row = f"{tbl:<14}" + "".join(f"  {c:6d}" for c in counts) + f"   {total:5d}"
        print(row)

    print()
    print("Per-shard percentages (customers):")
    total_cust = totals["customers"]
    for i in range(num_shards):
        pct = shards[i]["customers"] / total_cust * 100
        cids = [c for c in CUSTOMERS if get_shard(c, num_shards) == i]
        print(f"  Shard {i}: {shards[i]['customers']:2d} customers ({pct:5.1f}%)  IDs={cids}")

    # Skew coefficient (max/avg ratio)
    counts = [shards[i]["customers"] for i in range(num_shards)]
    avg = total_cust / num_shards
    skew = max(counts) / avg
    print(f"\nSkew coefficient (max / avg): {skew:.3f}  (ideal = 1.000)")
    if skew < 1.25:
        print("Assessment: LOW SKEW -- acceptable balance.")
    elif skew < 1.5:
        print("Assessment: MODERATE SKEW -- monitor under scale.")
    else:
        print("Assessment: HIGH SKEW -- consider virtual nodes or re-sharding.")

    print("=" * 62)


# ---------------------------------------------------------------------------
# Justification text (printed as reference)
# ---------------------------------------------------------------------------

JUSTIFICATION = """
SHARD KEY JUSTIFICATION
=======================

Chosen shard key : customerID

1. High Cardinality
   customerID is a unique integer assigned to every registered user.
   With N customers there are N distinct values, guaranteeing that the
   hash function can spread rows evenly across any number of shards.

2. Query-Aligned
   Almost every API call in QuickBites begins with a customer context:
     * Place order / view cart       (customerID lookup)
     * Payment history               (customerID lookup)
     * Address book                  (customerID lookup)
     * Order tracking                (orderID -> customerID lookup)
   Routing on customerID therefore minimises cross-shard fan-out for
   the dominant read/write workloads.

3. Stable
   customerID is assigned once at registration and never updated.
   It satisfies the "does not change frequently" stability criterion,
   which means a record never needs to be migrated between shards
   after its initial insertion.

PARTITIONING STRATEGY
=====================
Strategy chosen : Hash-based modulo
Formula         : shard_id = customerID % NUM_SHARDS

Why hash-based over range-based:
  * Range partitioning on customerIDs 1-10 would create hotspots if
    new customers arrive sequentially (shard N always gets new writes).
  * Hash-based partitioning distributes writes uniformly across all
    shards irrespective of the ID sequence.
  * The formula is deterministic and O(1) -- no directory lookup needed.

Why not directory-based:
  * Directory lookup adds a network hop (or an extra DB read) on every
    query.  For a food-delivery app with high QPS this is undesirable.
  * Directory-based sharding is more useful when shards need to be
    remapped without rehashing, which is not a requirement here.

SKEW RISKS
==========
  * Small dataset (10 customers, 3 shards): inherent remainder imbalance
    (4-3-3 split).  At production scale (>10k customers) the modulo hash
    converges to near-uniform distribution.
  * Power users placing many orders do NOT create key skew because every
    shard still routes on customerID; a single customer's orders all go
    to the same shard, keeping individual queries local.
  * Future risk: if customerIDs cluster in multiples of NUM_SHARDS
    (e.g., all even IDs for a batch import) then shard(even) = 0 or 2
    only.  Mitigation: use a murmur/fnv hash instead of plain modulo for
    large-scale deployment.
"""


if __name__ == "__main__":
    print(JUSTIFICATION)
    print()
    print_report(NUM_SHARDS)
