# QuickBites Sharding Report (Assignment 4)

Date: 17 April 2026

## First Page Details

- GitHub repository link: https://github.com/mohit-codes-21/QuickBites
- Video link: https://drive.google.com/file/d/11_qTASPAAZiH_r3rJKdd1T1OuKAl3c3_/view?usp=sharing

---

## 1. Shard Key Chosen and Justification

### Chosen shard key

- Shard key: `customerID`

### Justification used (reused from SubTask 1 where correct)

The SubTask 1 analysis selected `customerID` because it satisfies the required criteria:

1. High cardinality
- `customerID` is unique per customer and grows with registrations.
- Higher distinct values support better hash distribution.

2. Query alignment
- Dominant customer workflows naturally filter by customer context: cart, addresses, payment history, and customer order views.
- Using `customerID` keeps most customer-path reads/writes single-shard.

3. Stability
- `customerID` is assigned once and does not change, so records do not need key-change-driven migration.

### Distribution evidence from SubTask 1 (seed analysis)

- Seed split for customers was 4-3-3 (for `customerID` 1-10 over 3 shards).
- Seed skew coefficient was approximately 1.20 (low skew).
- Interpretation: acceptable initial balance for modulo-hash partitioning.

## 2. Partitioning Strategy Used and Why

### Strategy

- Hash-based modulo partitioning
- Routing formula: `shard_id = customerID % 3`

### Why this strategy

- O(1) deterministic routing without directory lookup.
- Better write spread than simple range partitioning under sequential customer IDs.
- Keeps customer-scoped rows co-located by customer key.

### Why alternatives were not chosen

- Range partitioning can hotspot the newest range during growth.
- Directory-based partitioning adds metadata lookup overhead and operational complexity that was not required for this assignment scope.

## 3. How Query Routing Is Implemented in the Application

### Routing helper layer

Routing is implemented through reusable helpers:

- `shard_router.py`
  - `ShardRouter.shard_for_customer(customer_id)`
  - `ShardRouter.connect_for_customer(customer_id)`
  - `ShardRouter.table_name(logical_table, shard_id)`
- `app/app.py`
  - `_get_customer_shard_context(customer_id)`

### Routed table scope

Per the accepted instructor scope, direct customer-key tables are shard-routed:

- `Customer`
- `Address`
- `CartItem`
- `Payment`
- `Orders`

Local-only tables remain on monolith MySQL:

- `Member`, `DeliveryPartner`, `Restaurant`, `MenuItem`, `OrderItem`, `Delivery_Assignments`, `OrderRating`, `MenuItemRating`

### Query routing patterns implemented

1. Point route (single customer)
- Example endpoint: `GET /api/sharded/route/customer/<customer_id>`
- Returns calculated shard and physical table name.

2. Single-shard lookup/update for customer-scoped data
- Example endpoints:
  - `GET /api/sharded/customers/<customer_id>`
  - `GET /api/customer/orders`
  - `GET /api/customer/payments/last`

3. Range query fan-out (scatter-gather)
- Example endpoint: `GET /api/sharded/customers/range?start=&end=&limit=`
- Process:
  - query each shard table in parallel/loop,
  - merge application-side,
  - sort globally,
  - apply global limit.

### Test-case proof added

Integration tests were added and executed:

- `tests/check.py`
  - verifies point route maps to expected shard and physical placement,
  - verifies range query spans multiple shards and matches source-table results.
  - prints full returned records for both scenarios.

- `tests/check_show.py`
  - demonstration runner that prints complete point/range records in a presentation-friendly format.

Execution result:

- `Ran 2 tests ... OK`

## 4. Which SQL Shard Tables Were Created and How Data Was Migrated

### Shard tables created

For each shard `s in {0,1,2}`, these physical tables are created:

- `shard_s_customer`
- `shard_s_address`
- `shard_s_cartitem`
- `shard_s_payment`
- `shard_s_orders`

This gives 15 shard tables total (5 logical x 3 shards).

### Migration pipeline

Implemented in `shard_admin.py`:

1. `setup`:
- Creates shard tables on all nodes.

2. `migrate`:
- Reads source rows from monolith (`QB`),
- computes `customerID % 3`,
- inserts row into designated shard table.

3. `verify`:
- checks source count vs shard total,
- checks duplicate primary keys across shards,
- checks wrong-shard placement (`badRouteCount`).

### Migration verification results (from `logs/subtask2_shard_report.json`)

Global status:

- `ok: true`

Per-table summary:

| Table | Source Count | Shard Counts (0/1/2) | Delta | Duplicate Keys | Bad Route |
|---|---:|---|---:|---:|---:|
| customer | 33 | 10 / 12 / 11 | 0 | 0 | 0 |
| address  | 20 | 6 / 8 / 6 | 0 | 0 | 0 |
| cartitem | 13 | 4 / 7 / 2 | 0 | 0 | 0 |
| payment  | 26 | 5 / 6 / 15 | 0 | 0 | 0 |
| orders   | 24 | 4 / 5 / 15 | 0 | 0 | 0 |

Conclusion: no data loss, no duplication, and correct routing for all sharded rows.

## 5. Sharding Approach Used and How Shard Isolation Was Achieved

### Approach used

- Multiple MySQL databases/instances (logical shard nodes), not Docker in this implementation.
- Topology:
  - Monolith/source DB: `127.0.0.1:3306` (`QB`)
  - Shard node 0: `10.0.116.184:3307` (`ScaleOps`)
  - Shard node 1: `10.0.116.184:3308` (`ScaleOps`)
  - Shard node 2: `10.0.116.184:3309` (`ScaleOps`)

### Isolation mechanisms

Shard isolation is achieved using:

1. Connection-level isolation
- Router opens connections to one shard port at a time based on computed shard id.

2. Physical table isolation
- Each shard has its own physical table namespace (`shard_0_*`, `shard_1_*`, `shard_2_*`).

3. Deterministic ownership
- A row belongs to exactly one shard by formula (`customerID % 3`).

4. Verification safeguards
- Post-migration checks guarantee no cross-shard duplication and no wrong placement.

## 6. Results of Scalability and Trade-offs Analysis

### Observed scaling behavior

1. Hash distribution quality
- For seed analysis, customer skew was low (~1.20 max/avg).
- On live migrated data:
  - `customer`: 10/12/11, skew = 12 / (33/3) = 1.09 (well balanced)
  - `orders`: 4/5/15, skew = 15 / (24/3) = 1.88 (workload concentration)

2. Query scalability by type
- Point customer queries scale well because they hit one shard.
- Range queries require fan-out across shards and merge/sort in app layer.

3. Supporting index observations
- From SubTask 4/5 benchmark summary, targeted indexes reduce sorts and improve several hot query plans (for example backward index scans replacing filesort for customer payment/order history queries).
- API p50 latencies remained in a close range (~27-29 ms) in benchmarked endpoints after index tuning.

### Trade-offs

Pros:

- Fast deterministic routing.
- Lower contention for customer-scoped workload.
- Straightforward operational model for assignment scope.

Cons:

- Fan-out cost for global/range workloads.
- Potential shard hotspot if a subset of high-activity customers map to same shard.
- More operational complexity than a single DB (migration, verification, environment variables, multi-node troubleshooting).

## 7. Observations and Limitations

### Observations

- The accepted scope (direct `customerID` table routing only) is fully implemented and verified.
- Migration integrity checks passed (`ok: true`) with zero duplicate keys and zero bad-route rows.
- Added SubTask 3 tests demonstrate both required cases:
  - correct point routing,
  - correct multi-shard range fan-out results.

### Limitations

1. Mixed local-plus-shard model
- Local-only tables remain in monolith by design.
- Some non-customer lifecycle workflows still operate on local representations for compatibility.

2. No automatic rebalancing yet
- If workload skew grows, there is no automatic re-sharding or virtual-node rebalance mechanism.

3. Fan-out query overhead
- Cross-shard range/report queries scale with shard count and require application merge logic.

4. Topology constraints
- Shards are isolated by ports and table namespaces, but still within a controlled lab topology; this is not a multi-region production deployment.

## 8. Conclusion

The implemented sharding design uses `customerID` hash partitioning with three shard nodes and deterministic routing. It satisfies the assignment requirements for shard-key justification, partition strategy, query routing, shard-table migration, and isolation setup under the accepted instructor interpretation. Verification and tests confirm correctness for point routing and multi-shard range querying, while observed trade-offs and limitations are documented for future scaling improvements.
