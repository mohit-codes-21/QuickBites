-- QuickBites (Module B) - helper to remove optimisation indexes
-- This enables before/after benchmarking for SubTask 5.

USE QB;

DROP INDEX qb_idx_orders_customer_time ON Orders;
DROP INDEX qb_idx_orders_restaurant_time ON Orders;
DROP INDEX qb_idx_orders_status_time ON Orders;

DROP INDEX qb_idx_delivery_partner_acceptance ON Delivery_Assignments;
DROP INDEX qb_idx_delivery_order ON Delivery_Assignments;

DROP INDEX qb_idx_menuitem_rest_disc_item ON MenuItem;
DROP INDEX qb_idx_restaurant_active_name ON Restaurant;

DROP INDEX qb_idx_payment_customer_for_time ON Payment;
DROP INDEX qb_idx_payment_for_status_time ON Payment;

DROP INDEX qb_idx_address_customer_saved ON Address;
DROP INDEX qb_idx_menuitemrating_order ON MenuItemRating;
