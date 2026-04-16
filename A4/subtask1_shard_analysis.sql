-- =============================================================================
--  QuickBites -- Assignment 4, SubTask 1
--  Shard Key Selection & Distribution Analysis (Module B)
-- =============================================================================
--
--  Shard Key  : customerID
--  Strategy   : Hash-based modulo   shard_id = customerID MOD 3
--  Num shards : 3
--
--  This script queries the existing QB database to verify the shard-key
--  choice and to produce the expected data-distribution figures that
--  appear in the SubTask 1 report section.
-- =============================================================================

USE QB;

-- ---------------------------------------------------------------------------
-- 1. Candidate key cardinality survey
-- ---------------------------------------------------------------------------
SELECT 'customerID'  AS candidate_key,
       COUNT(DISTINCT customerID) AS distinct_values,
       COUNT(*)                   AS total_rows
FROM Customer
UNION ALL
SELECT 'restaurantID',
       COUNT(DISTINCT restaurantID),
       COUNT(*)
FROM Restaurant
UNION ALL
SELECT 'city (Restaurant)',
       COUNT(DISTINCT city),
       COUNT(*)
FROM Restaurant
UNION ALL
SELECT 'zipCode (Restaurant)',
       COUNT(DISTINCT zipCode),
       COUNT(*)
FROM Restaurant;


-- ---------------------------------------------------------------------------
-- 2. Per-customer order activity (to validate query-alignment assumption)
-- ---------------------------------------------------------------------------
SELECT
    c.customerID,
    COUNT(DISTINCT o.orderID)   AS total_orders,
    COUNT(DISTINCT p.paymentID) AS total_payments,
    COUNT(DISTINCT a.addressID) AS saved_addresses
FROM Customer c
LEFT JOIN Orders  o ON o.customerID = c.customerID
LEFT JOIN Payment p ON p.customerID = c.customerID
LEFT JOIN Address a ON a.customerID = c.customerID
GROUP BY c.customerID
ORDER BY c.customerID;


-- ---------------------------------------------------------------------------
-- 3. Simulated shard assignment for every customer
--    Formula : shard_id = customerID MOD 3
-- ---------------------------------------------------------------------------
SELECT
    customerID,
    customerID MOD 3             AS shard_id,
    loyaltyTier,
    membership
FROM Customer
ORDER BY shard_id, customerID;


-- ---------------------------------------------------------------------------
-- 4. Expected row distribution across shards (Customer-linked tables)
-- ---------------------------------------------------------------------------

-- 4a. Customer rows per shard
SELECT
    customerID MOD 3           AS shard_id,
    COUNT(*)                   AS customer_rows
FROM Customer
GROUP BY shard_id
ORDER BY shard_id;

-- 4b. Order rows per shard
SELECT
    customerID MOD 3           AS shard_id,
    COUNT(*)                   AS order_rows
FROM Orders
GROUP BY shard_id
ORDER BY shard_id;

-- 4c. Payment rows per shard
SELECT
    customerID MOD 3           AS shard_id,
    COUNT(*)                   AS payment_rows
FROM Payment
GROUP BY shard_id
ORDER BY shard_id;

-- 4d. Address rows per shard
SELECT
    customerID MOD 3           AS shard_id,
    COUNT(*)                   AS address_rows
FROM Address
GROUP BY shard_id
ORDER BY shard_id;

-- 4e. CartItem rows per shard
SELECT
    customerID MOD 3           AS shard_id,
    COUNT(*)                   AS cart_item_rows
FROM CartItem
GROUP BY shard_id
ORDER BY shard_id;


-- ---------------------------------------------------------------------------
-- 5. Combined distribution summary (all customer-linked tables)
-- ---------------------------------------------------------------------------
SELECT
    shard_id,
    SUM(customer_rows)    AS customers,
    SUM(order_rows)       AS orders,
    SUM(payment_rows)     AS payments,
    SUM(address_rows)     AS addresses,
    SUM(cart_item_rows)   AS cart_items,
    SUM(customer_rows + order_rows + payment_rows + address_rows + cart_item_rows) AS total_rows
FROM (
    SELECT customerID MOD 3 AS shard_id,
           1 AS customer_rows, 0 AS order_rows, 0 AS payment_rows,
           0 AS address_rows,  0 AS cart_item_rows
    FROM Customer
    UNION ALL
    SELECT customerID MOD 3, 0, 1, 0, 0, 0 FROM Orders
    UNION ALL
    SELECT customerID MOD 3, 0, 0, 1, 0, 0 FROM Payment
    UNION ALL
    SELECT customerID MOD 3, 0, 0, 0, 1, 0 FROM Address
    UNION ALL
    SELECT customerID MOD 3, 0, 0, 0, 0, 1 FROM CartItem
) sub
GROUP BY shard_id
ORDER BY shard_id;


-- ---------------------------------------------------------------------------
-- 6. Skew coefficient: max_rows / avg_rows  (Orders table)
-- ---------------------------------------------------------------------------
SELECT
    MAX(cnt) / AVG(cnt)  AS skew_coefficient,
    MAX(cnt)             AS max_shard_orders,
    MIN(cnt)             AS min_shard_orders,
    AVG(cnt)             AS avg_shard_orders
FROM (
    SELECT customerID MOD 3 AS shard_id, COUNT(*) AS cnt
    FROM Orders
    GROUP BY shard_id
) t;


-- ---------------------------------------------------------------------------
-- 7. Tables NOT sharded by customerID (reference / global data)
--    These will remain in a single, replicated "global" store.
-- ---------------------------------------------------------------------------
SELECT 'Restaurant'  AS unsharded_table, COUNT(*) AS rows FROM Restaurant
UNION ALL
SELECT 'MenuItem',                        COUNT(*) FROM MenuItem
UNION ALL
SELECT 'DeliveryPartner',                 COUNT(*) FROM DeliveryPartner
UNION ALL
SELECT 'Member',                          COUNT(*) FROM Member
UNION ALL
SELECT 'Delivery_Assignments',            COUNT(*) FROM Delivery_Assignments
UNION ALL
SELECT 'OrderRating',                     COUNT(*) FROM OrderRating
UNION ALL
SELECT 'MenuItemRating',                  COUNT(*) FROM MenuItemRating;
