-- =============================================================================
-- QuickBites - Assignment 4 - SubTask 2
-- Per-shard verification queries for hash-based customerID sharding.
--
-- Usage:
-- 1) Connect to one shard node (3307 / 3308 / 3309)
-- 2) USE ScaleOps;
-- 3) Set @shard_id for that node (0, 1, or 2)
-- 4) Run this script
--
-- Note: Replace table prefixes if you use a different naming convention.
-- =============================================================================

SET @num_shards = 3;
SET @shard_id = 0; -- Change to 1 for port 3308, 2 for port 3309

-- -----------------------------------------------------------------------------
-- 1) Direct-route table checks (must all be 0 bad rows)
-- -----------------------------------------------------------------------------

SELECT 'customer_bad_route' AS check_name, COUNT(*) AS bad_rows
FROM shard_0_customer
WHERE MOD(customerID, @num_shards) <> @shard_id;

SELECT 'address_bad_route' AS check_name, COUNT(*) AS bad_rows
FROM shard_0_address
WHERE MOD(customerID, @num_shards) <> @shard_id;

SELECT 'cartitem_bad_route' AS check_name, COUNT(*) AS bad_rows
FROM shard_0_cartitem
WHERE MOD(customerID, @num_shards) <> @shard_id;

SELECT 'payment_bad_route' AS check_name, COUNT(*) AS bad_rows
FROM shard_0_payment
WHERE MOD(customerID, @num_shards) <> @shard_id;

SELECT 'orders_bad_route' AS check_name, COUNT(*) AS bad_rows
FROM shard_0_orders
WHERE MOD(customerID, @num_shards) <> @shard_id;

-- -----------------------------------------------------------------------------
-- 2) Row count snapshot for this shard
-- -----------------------------------------------------------------------------

SELECT 'customer' AS table_name, COUNT(*) AS shard_rows FROM shard_0_customer
UNION ALL
SELECT 'address', COUNT(*) FROM shard_0_address
UNION ALL
SELECT 'cartitem', COUNT(*) FROM shard_0_cartitem
UNION ALL
SELECT 'payment', COUNT(*) FROM shard_0_payment
UNION ALL
SELECT 'orders', COUNT(*) FROM shard_0_orders;

-- -----------------------------------------------------------------------------
-- IMPORTANT:
-- This file assumes shard_0_* names for demonstration.
-- For shard 1 and shard 2, replace prefix `shard_0_` with `shard_1_` or `shard_2_`
-- and set @shard_id accordingly.
-- -----------------------------------------------------------------------------
