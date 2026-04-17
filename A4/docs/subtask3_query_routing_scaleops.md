# SubTask 3 - Query Routing (Team ScaleOps)

This document summarizes the SubTask 3 implementation for routing queries to the correct shard.

## Routing strategy

- Shard key: `customerID`
- Routing formula: `shard_id = customerID % 3`
- Local-only tables (not sharded): `Member`, `DeliveryPartner`, `Restaurant`, `MenuItem`, `OrderItem`, `Delivery_Assignments`, `OrderRating`, `MenuItemRating`
- Physical nodes:
  - shard 0 -> `10.0.116.184:3307`
  - shard 1 -> `10.0.116.184:3308`
  - shard 2 -> `10.0.116.184:3309`

## Helper layer

Shared sharding helper utilities are implemented in:

- `app/app.py`:
  - `_get_customer_shard_context(customer_id)`
  - `_fetch_restaurant_name_map(...)`
  - `_fetch_menu_item_map(...)`

These helpers are used by existing API endpoints so each request routes using the customer key extracted from auth context, URL params, or request body.

## Lookup query routing implemented

Single-key lookups are routed to a single shard for customer-scoped data:

- `GET /api/customer/orders`
- `GET /api/customer/addresses`
- `GET /api/customer/cart`
- `GET /api/customer/payments/last`
- `GET /api/portfolio/<member_id>` (customer profile portion)

## Insert/update/delete routing implemented

Writes to customer-scoped records are routed to the customer's shard:

- `POST /api/customer/addresses`
- `PUT /api/customer/addresses/select`
- `PUT /api/customer/cart/item`
- `DELETE /api/customer/cart/item`
- `DELETE /api/customer/cart`
- `POST /api/customer/cart/payment-demo`
- `POST /api/customer/cart/payment-demo/recheck`
- `POST /api/customer/membership/purchase`

## Range query routing implemented

Scatter-gather range routing is implemented on existing endpoint:

- `GET /api/customer/orders?startCustomerID=<id>&endCustomerID=<id>&limit=<n>` (Admin)

Behavior:

1. Identify relevant shards (for modulo hash, all shards may contain range values)
2. Query each shard's `shard_<id>_orders` + `shard_<id>_payment`
3. Merge results in app layer
4. Sort by `orderTime` descending
5. Apply global limit

## Data consistency checks

Payment timeout updates now route to shard payment tables via:

- `expire_pending_order_payments(...)`

Loyalty, selected address, and cart total helper functions were also routed to shard tables:

- `get_customer_loyalty_context(...)`
- `get_selected_address_id(...)`
- `get_selected_address_location(...)`
- `calculate_customer_cart_total(...)`
- `update_customer_cart_total(...)`
- `apply_loyalty_tier_progression(...)`

## Validation done

The following checks were executed after implementation:

- Python compile check:
  - `python -m py_compile app/app.py shard_router.py shard_admin.py`
- Helper smoke test with live DB/shards:
  - cart total lookup
  - loyalty lookup
  - selected address lookup
  - pending payment expiration
- API smoke test using Flask test client:
  - customer login
  - `GET /api/customer/orders`
  - `GET /api/customer/addresses`
  - `GET /api/customer/cart`
  - `GET /api/customer/payments/last`
  - admin range query on `GET /api/customer/orders` with start/end params
