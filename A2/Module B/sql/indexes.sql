-- ============================================================================
-- QuickBites (Module B) — SubTask 4: SQL Indexing & Query Optimisation
-- ============================================================================
--
-- Strategy
-- --------
-- Each index below is a *composite B-Tree* whose column order is chosen to
-- satisfy three goals in priority order:
--
--   1.  Equality predicates first   (WHERE col = ?)
--   2.  Range / IN predicates next  (WHERE col IN (...), col <= ?)
--   3.  Sort columns last           (ORDER BY col DESC)
--
-- Where possible the index *covers* all columns the query touches so the
-- engine can answer entirely from the index ("covering index") without a
-- table-data lookup.
--
-- Naming convention:  qb_idx_<table>_<short_description>
--
-- Apply after loading SQL_Dump.sql:
--   USE QB;
--   SOURCE path/to/indexes.sql;
-- ============================================================================

USE QB;

-- 1. Orders: customer order history
-- WHERE customerID = ? ORDER BY orderTime DESC
-- Serves: /api/customer/orders, /api/customer/profile/orders
CREATE INDEX qb_idx_orders_customer_time ON Orders(customerID, orderTime);

-- 2. Orders: restaurant order dashboard
-- WHERE restaurantID = ? ORDER BY orderTime DESC
-- Serves: /api/restaurant/orders
CREATE INDEX qb_idx_orders_restaurant_time ON Orders(restaurantID, orderTime);

-- 3. Orders: delivery live-orders feed (continuously polled)
-- WHERE orderStatus IN ('Created','Preparing','ReadyForPickup') ORDER BY orderTime DESC
-- Serves: /api/delivery/live-orders
CREATE INDEX qb_idx_orders_status_time ON Orders(orderStatus, orderTime);

-- 4. Delivery_Assignments: partner assignment list
-- WHERE PartnerID = ? ORDER BY acceptanceTime DESC
-- Serves: /api/delivery/assignments, active order lookup
CREATE INDEX qb_idx_delivery_partner_acceptance ON Delivery_Assignments(PartnerID, acceptanceTime);

-- 5. Delivery_Assignments: completed deliveries
-- WHERE PartnerID = ? ORDER BY deliveryTime DESC
-- Serves: /api/delivery/completed-orders
CREATE INDEX qb_idx_delivery_partner_deliverytime ON Delivery_Assignments(PartnerID, deliveryTime);

-- 6. MenuItem: menu browsing with discontinuation filter
-- WHERE restaurantID = ? AND discontinued = 0 ORDER BY restaurantID, itemID
-- Serves: /api/menu-items
CREATE INDEX qb_idx_menuitem_rest_disc_item ON MenuItem(restaurantID, discontinued, itemID);

-- 7. Restaurant: active restaurant listing
-- WHERE isDeleted = 0 AND discontinued = 0 ORDER BY name
-- Serves: /api/restaurants
CREATE INDEX qb_idx_restaurant_active_name ON Restaurant(isDeleted, discontinued, name);

-- 8. Payment: last payment lookup (covering index)
-- WHERE customerID = ? AND paymentFor = 'Order' ORDER BY transactionTime DESC, paymentID DESC
-- Serves: /api/customer/payments/last
CREATE INDEX qb_idx_payment_customer_for_time ON Payment(customerID, paymentFor, transactionTime, paymentID);

-- 9. Payment: expire pending payments batch
-- WHERE paymentFor = 'Order' AND status = 'Pending' AND paymentType = 'OnQuickBites' AND transactionTime <= ...
-- Serves: expire_pending_order_payments() helper
CREATE INDEX qb_idx_payment_for_status_type_time ON Payment(paymentFor, status, paymentType, transactionTime);

-- 10. Address: saved address selection
-- WHERE customerID = ? AND isSaved = 1 ORDER BY addressID
-- Serves: get_selected_address_location(), /api/customer/addresses
CREATE INDEX qb_idx_address_customer_saved ON Address(customerID, isSaved, addressID);

-- 11. AuditLog: admin audit log listing
-- ORDER BY timestamp DESC, logID DESC LIMIT ?
-- Serves: /api/admin/audits
CREATE INDEX qb_idx_auditlog_timestamp ON AuditLog(timestamp, logID);
