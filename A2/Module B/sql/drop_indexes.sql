-- ============================================================================
-- QuickBites (Module B) — Drop optimisation indexes
-- ============================================================================
--
-- This script removes every custom index created by indexes.sql so the
-- benchmark_indexing.py script can measure query performance *before* and
-- *after* indexing on an otherwise identical dataset (SubTask 5).
--
-- Usage:
--   mysql -u qb_admin -p QB < drop_indexes.sql
-- ============================================================================

USE QB;

DROP INDEX qb_idx_orders_customer_time ON Orders;
DROP INDEX qb_idx_orders_restaurant_time ON Orders;
DROP INDEX qb_idx_orders_status_time ON Orders;

DROP INDEX qb_idx_delivery_partner_acceptance ON Delivery_Assignments;
DROP INDEX qb_idx_delivery_partner_deliverytime ON Delivery_Assignments;

DROP INDEX qb_idx_menuitem_rest_disc_item ON MenuItem;
DROP INDEX qb_idx_restaurant_active_name ON Restaurant;

DROP INDEX qb_idx_payment_customer_for_time ON Payment;
DROP INDEX qb_idx_payment_for_status_type_time ON Payment;

DROP INDEX qb_idx_address_customer_saved ON Address;
DROP INDEX qb_idx_auditlog_timestamp ON AuditLog;
