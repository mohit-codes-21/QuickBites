-- QuickBites (Module B) - SubTask 4: SQL Indexing and Query Optimisation
--
-- This file adds logical indexes that directly target the WHERE / JOIN / ORDER BY
-- clauses used by the Flask API queries in app/app.py.
--
-- Apply after loading SQL_Dump.sql:
--   USE QB;
--   SOURCE path/to/Module B/sql/indexes.sql;

USE QB;

-- Orders lists (Customer / Restaurant dashboards)
-- WHERE customerID = ? ORDER BY orderTime DESC
CREATE INDEX qb_idx_orders_customer_time ON Orders(customerID, orderTime);

-- WHERE restaurantID = ? ORDER BY orderTime DESC
CREATE INDEX qb_idx_orders_restaurant_time ON Orders(restaurantID, orderTime);

-- Delivery live-orders feed
-- WHERE orderStatus IN (...) ORDER BY orderTime DESC
CREATE INDEX qb_idx_orders_status_time ON Orders(orderStatus, orderTime);

-- Delivery_Assignments lookups
-- WHERE PartnerID = ? ORDER BY acceptanceTime DESC
CREATE INDEX qb_idx_delivery_partner_acceptance ON Delivery_Assignments(PartnerID, acceptanceTime);

-- JOIN/lookup by OrderID (used across accept/active-order/live-orders)
CREATE INDEX qb_idx_delivery_order ON Delivery_Assignments(OrderID);

-- Menu browsing
-- WHERE mi.restaurantID = ? AND mi.discontinued = 0 ORDER BY mi.restaurantID, mi.itemID
CREATE INDEX qb_idx_menuitem_rest_disc_item ON MenuItem(restaurantID, discontinued, itemID);

-- Restaurant listing
-- WHERE discontinued = 0 AND isDeleted = 0 ORDER BY name
CREATE INDEX qb_idx_restaurant_active_name ON Restaurant(isDeleted, discontinued, name);

-- Payment lookups
-- WHERE customerID = ? AND paymentFor = 'Order' ORDER BY transactionTime DESC, paymentID DESC
CREATE INDEX qb_idx_payment_customer_for_time ON Payment(customerID, paymentFor, transactionTime, paymentID);

-- Expiring pending payments
-- WHERE paymentFor='Order' AND status='Pending' AND transactionTime <= ... [and sometimes customerID]
CREATE INDEX qb_idx_payment_for_status_time ON Payment(paymentFor, status, transactionTime, customerID);

-- Saved address selection
-- WHERE customerID = ? AND isSaved = 1 ORDER BY addressID LIMIT 1
CREATE INDEX qb_idx_address_customer_saved ON Address(customerID, isSaved, addressID);

-- Reviews join helper
-- MenuItemRating is keyed by (restaurantID,itemID,orderID) so joins by orderID benefit from a separate index
CREATE INDEX qb_idx_menuitemrating_order ON MenuItemRating(orderID);
