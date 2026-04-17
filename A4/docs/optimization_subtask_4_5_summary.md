# Module B — SubTask 4 & 5 (Indexing + Benchmarking)

This document summarizes the indexing strategy (SubTask 4) and the quantitative benchmarking + EXPLAIN evidence (SubTask 5).

## SubTask 4: Indexing strategy (what and why)
Indexes applied via `sql/indexes.sql` (names use the `qb_idx_*` prefix). They directly target the `WHERE`, `JOIN`, and `ORDER BY` clauses used in `app/app.py` endpoints:

- `qb_idx_orders_customer_time` on `Orders(customerID, orderTime)` → customer order history (filters by `customerID`, sorts by `orderTime DESC`)
- `qb_idx_orders_restaurant_time` on `Orders(restaurantID, orderTime)` → restaurant order dashboard (filters by `restaurantID`, sorts by `orderTime DESC`)
- `qb_idx_orders_status_time` on `Orders(orderStatus, orderTime)` → delivery live orders feed (filters by `orderStatus`, sorts by `orderTime DESC`)
- `qb_idx_delivery_partner_acceptance` on `Delivery_Assignments(PartnerID, acceptanceTime)` → delivery assignments list (filters by `PartnerID`, sorts by `acceptanceTime DESC`)
- `qb_idx_delivery_order` on `Delivery_Assignments(OrderID)` → assignment lookup/join by `OrderID`
- `qb_idx_menuitem_rest_disc_item` on `MenuItem(restaurantID, discontinued, itemID)` → menu browsing (filters by `restaurantID`/`discontinued`, ordered by `(restaurantID,itemID)`)
- `qb_idx_restaurant_active_name` on `Restaurant(isDeleted, discontinued, name)` → restaurant listing (filters by flags, ordered by `name`)
- `qb_idx_payment_customer_for_time` on `Payment(customerID, paymentFor, transactionTime, paymentID)` → last payment lookup (filters by `customerID`+`paymentFor`, ordered by time/id)
- `qb_idx_payment_for_status_time` on `Payment(paymentFor, status, transactionTime, customerID)` → expiring pending payments (filters by `paymentFor`+`status`+time; optional `customerID`)
- `qb_idx_address_customer_saved` on `Address(customerID, isSaved, addressID)` → saved-address selection (filters by `customerID`+`isSaved`, ordered by `addressID`)
- `qb_idx_menuitemrating_order` on `MenuItemRating(orderID)` → rating joins that start from an `orderID` list

## SubTask 5: Benchmarking methodology
The benchmark runner `app/benchmark_indexing.py` performs:

1. Drop optimisation indexes (baseline BEFORE)
2. Measure SQL query execution time (warmup + repeated runs, reported as min/mean/p50/p95/max)
3. Measure API response time using Flask test client + session-authenticated tokens
4. Capture `EXPLAIN` for each benchmark query
5. Apply optimisation indexes and repeat the same measurements (AFTER)

Raw output file: `logs/index_benchmark_20260320T192318Z.json`

## Results (p50 timings)

### SQL queries

| Query | p50 before (ms) | p50 after (ms) |
|---|---:|---:|
| `customer_last_payment` | 0.190 | 0.173 |
| `customer_orders_list` | 0.216 | 0.207 |
| `delivery_assignments` | 0.213 | 0.214 |
| `delivery_live_orders` | 0.286 | 0.344 |
| `menu_item_rating_join_helper` | 0.287 | 0.195 |
| `menu_items_by_restaurant` | 0.219 | 0.212 |
| `restaurant_orders_list` | 0.325 | 0.349 |
| `restaurants_list` | 0.208 | 0.256 |
| `saved_address_lookup` | 0.162 | 0.136 |

### API endpoints

| Endpoint | p50 before (ms) | p50 after (ms) |
|---|---:|---:|
| `api_customer_last_payment` | 28.023 | 27.072 |
| `api_customer_orders` | 28.435 | 28.068 |
| `api_delivery_live_orders` | 28.897 | 29.001 |
| `api_menu_items` | 28.559 | 28.193 |
| `api_restaurant_orders` | 28.055 | 29.347 |
| `api_restaurants` | 28.710 | 27.706 |

## EXPLAIN evidence (examples)

### `customer_last_payment`
- BEFORE: `type=ref`, `key=customerID`, `Extra=Using where; Using filesort`
- AFTER:  `type=ref`, `key=qb_idx_payment_customer_for_time`, `Extra=Backward index scan`

### `customer_orders_list`
- BEFORE: `type=ref`, `key=customerID`, `Extra=Using filesort`
- AFTER:  `type=ref`, `key=qb_idx_orders_customer_time`, `Extra=Backward index scan`

### `delivery_assignments`
- BEFORE: `type=ref`, `key=PartnerID`, `Extra=Using filesort`
- AFTER:  `type=ref`, `key=qb_idx_delivery_partner_acceptance`, `Extra=Backward index scan`

