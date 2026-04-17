# SubTask 2 - Data Partitioning (Team ScaleOps)

This document implements SubTask 2 requirements for QuickBites using:

- Shard key: `customerID`
- Strategy: hash-based modulo routing (`customerID % 3`)
- Shards:
  - Shard 0 -> `10.0.116.184:3307`
  - Shard 1 -> `10.0.116.184:3308`
  - Shard 2 -> `10.0.116.184:3309`
- Team DB / user: `ScaleOps`

## What was implemented

1. Simulated shard tables on all 3 nodes with required naming:
   - `shard_0_customer`, `shard_0_orders`, ... on shard node 0
   - `shard_1_customer`, `shard_1_orders`, ... on shard node 1
   - `shard_2_customer`, `shard_2_orders`, ... on shard node 2
2. Migration script with direct routing rule:
   - `customerID` tables routed directly by `customerID % 3`
3. Verification that checks:
   - source row count vs total across shards
   - duplicate keys across shards
   - wrong-shard placement
4. Non-sharded/reference tables remain in local monolith DB (not migrated to shard tables).
5. Application-level sharded routes for:
   - insert/upsert (`POST /api/sharded/customers`)
   - point lookup (`GET /api/sharded/customers/<customerID>`)
   - range query fan-out (`GET /api/sharded/customers/range?start=&end=`)

## Files added

- `shard_router.py` - deterministic shard routing + customer shard operations
- `shard_admin.py` - shard table setup, data migration, and validation
- `sql/subtask2_verify_shards.sql` - manual per-shard SQL verification checks

## Source DB configuration (monolith input)

By default, migration reads source rows from current monolith env (`QB_DB_*`).
You can override source using:

- `QB_SOURCE_DB_HOST`
- `QB_SOURCE_DB_PORT`
- `QB_SOURCE_DB_USER`
- `QB_SOURCE_DB_PASSWORD`
- `QB_SOURCE_DB_NAME`

## Shard DB configuration (ScaleOps cluster)

Defaults are already set in code for your cluster.
You can override with:

- `QB_SHARD_HOST` (default `10.0.116.184`)
- `QB_SHARD_PORTS` (default `3307,3308,3309`)
- `QB_SHARD_USER` (default `ScaleOps`)
- `QB_SHARD_PASSWORD` (default `password@123`)
- `QB_SHARD_DB` (default `ScaleOps`)
- `QB_SHARD_COUNT` (default `3`)

## Run commands

From workspace root:

```bash
python shard_admin.py setup --drop-existing
python shard_admin.py migrate
python shard_admin.py verify
```

Or run full pipeline in one command:

```bash
python shard_admin.py full --drop-existing
```

Verification JSON report is written to:

- `logs/subtask2_shard_report.json`

## Routing behavior

### Direct customer-routed tables

Rows are routed by `customerID % 3`:

- `customer`
- `address`
- `cartitem`
- `payment`
- `orders`

### Local-only (not sharded)

These tables stay in monolith/local SQL:

- `member`
- `deliverypartner`
- `restaurant`
- `menuitem`
- `orderitem`
- `delivery_assignments`
- `orderrating`
- `menuitemrating`

## API checks (after login as Admin)

```bash
# Show shard nodes
GET /api/sharded/shards

# Route probe
GET /api/sharded/route/customer/10

# Upsert customer into correct shard
POST /api/sharded/customers
{
  "customerID": 42,
  "loyaltyTier": 1,
  "membershipDiscount": 0,
  "cartTotalAmount": 0,
  "membershipDueDate": null,
  "membership": 0,
  "isDeleted": 0
}

# Point lookup
GET /api/sharded/customers/42

# Range fan-out query (scatter-gather)
GET /api/sharded/customers/range?start=1&end=200&limit=500
```

## Requirement mapping

- Create at least 3 simulated shard tables/nodes: satisfied by setup script on all 3 nodes.
- Migrate existing data to correct shards: satisfied by `shard_admin.py migrate`.
- Ensure each shard has designated subset only: verified via route checks in `verify` for all sharded tables.
- Ensure no record loss/duplication: verified by count parity + duplicate key detection on sharded tables.
- Tables without direct `customerID` are intentionally local-only and excluded from shard migration.
