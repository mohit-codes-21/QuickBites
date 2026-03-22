-- =============================================================================
--  QuickBites — Audit Triggers for Unauthorized Modification Detection
--
--  These triggers fire on every INSERT, UPDATE, and DELETE across all 13 data
--  tables.  The Flask application sets the MySQL session variable
--      @api_source = TRUE
--  on every connection it opens (see get_db_connection()).  When a modification
--  arrives through the API, the trigger sees @api_source = TRUE and does nothing
--  (the API already writes its own AuditLog entry).  When a modification is made
--  directly via the MySQL CLI or any other non-API client, @api_source is NULL,
--  and the trigger inserts an AuditLog row with:
--      • memberID  = NULL
--      • action    = 'UNAUTH_INSERT' / 'UNAUTH_UPDATE' / 'UNAUTH_DELETE'
--      • details   = JSON identifying the source as DIRECT_DB
--
--  This makes every direct database change immediately visible when reviewing
--  the AuditLog table or the audit.log file.
-- =============================================================================

DELIMITER //

-- ========================== 1. Member ========================================

CREATE TRIGGER trg_member_unauth_insert
AFTER INSERT ON Member FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'Member', NEW.memberID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_member_unauth_update
AFTER UPDATE ON Member FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'Member', NEW.memberID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_member_unauth_delete
AFTER DELETE ON Member FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'Member', OLD.memberID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 2. Customer ======================================

CREATE TRIGGER trg_customer_unauth_insert
AFTER INSERT ON Customer FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'Customer', NEW.customerID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_customer_unauth_update
AFTER UPDATE ON Customer FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'Customer', NEW.customerID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_customer_unauth_delete
AFTER DELETE ON Customer FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'Customer', OLD.customerID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 3. DeliveryPartner ===============================

CREATE TRIGGER trg_deliverypartner_unauth_insert
AFTER INSERT ON DeliveryPartner FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'DeliveryPartner', NEW.partnerID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_deliverypartner_unauth_update
AFTER UPDATE ON DeliveryPartner FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'DeliveryPartner', NEW.partnerID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_deliverypartner_unauth_delete
AFTER DELETE ON DeliveryPartner FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'DeliveryPartner', OLD.partnerID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 4. Restaurant ====================================

CREATE TRIGGER trg_restaurant_unauth_insert
AFTER INSERT ON Restaurant FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'Restaurant', NEW.restaurantID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_restaurant_unauth_update
AFTER UPDATE ON Restaurant FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'Restaurant', NEW.restaurantID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_restaurant_unauth_delete
AFTER DELETE ON Restaurant FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'Restaurant', OLD.restaurantID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 5. MenuItem ======================================

CREATE TRIGGER trg_menuitem_unauth_insert
AFTER INSERT ON MenuItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'MenuItem',
            CONCAT(NEW.restaurantID, '-', NEW.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_menuitem_unauth_update
AFTER UPDATE ON MenuItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'MenuItem',
            CONCAT(NEW.restaurantID, '-', NEW.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_menuitem_unauth_delete
AFTER DELETE ON MenuItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'MenuItem',
            CONCAT(OLD.restaurantID, '-', OLD.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 6. Address =======================================

CREATE TRIGGER trg_address_unauth_insert
AFTER INSERT ON Address FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'Address',
            CONCAT(NEW.customerID, '-', NEW.addressID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_address_unauth_update
AFTER UPDATE ON Address FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'Address',
            CONCAT(NEW.customerID, '-', NEW.addressID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_address_unauth_delete
AFTER DELETE ON Address FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'Address',
            CONCAT(OLD.customerID, '-', OLD.addressID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 7. CartItem ======================================

CREATE TRIGGER trg_cartitem_unauth_insert
AFTER INSERT ON CartItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'CartItem',
            CONCAT(NEW.customerID, '-', NEW.restaurantID, '-', NEW.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_cartitem_unauth_update
AFTER UPDATE ON CartItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'CartItem',
            CONCAT(NEW.customerID, '-', NEW.restaurantID, '-', NEW.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_cartitem_unauth_delete
AFTER DELETE ON CartItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'CartItem',
            CONCAT(OLD.customerID, '-', OLD.restaurantID, '-', OLD.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 8. Payment =======================================

CREATE TRIGGER trg_payment_unauth_insert
AFTER INSERT ON Payment FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'Payment', NEW.paymentID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_payment_unauth_update
AFTER UPDATE ON Payment FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'Payment', NEW.paymentID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_payment_unauth_delete
AFTER DELETE ON Payment FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'Payment', OLD.paymentID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 9. Orders ========================================

CREATE TRIGGER trg_orders_unauth_insert
AFTER INSERT ON Orders FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'Orders', NEW.orderID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_orders_unauth_update
AFTER UPDATE ON Orders FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'Orders', NEW.orderID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_orders_unauth_delete
AFTER DELETE ON Orders FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'Orders', OLD.orderID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 10. OrderItem ====================================

CREATE TRIGGER trg_orderitem_unauth_insert
AFTER INSERT ON OrderItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'OrderItem',
            CONCAT(NEW.orderID, '-', NEW.restaurantID, '-', NEW.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_orderitem_unauth_update
AFTER UPDATE ON OrderItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'OrderItem',
            CONCAT(NEW.orderID, '-', NEW.restaurantID, '-', NEW.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_orderitem_unauth_delete
AFTER DELETE ON OrderItem FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'OrderItem',
            CONCAT(OLD.orderID, '-', OLD.restaurantID, '-', OLD.itemID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 11. Delivery_Assignments =========================

CREATE TRIGGER trg_delivery_unauth_insert
AFTER INSERT ON Delivery_Assignments FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'Delivery_Assignments', NEW.AssignmentID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_delivery_unauth_update
AFTER UPDATE ON Delivery_Assignments FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'Delivery_Assignments', NEW.AssignmentID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_delivery_unauth_delete
AFTER DELETE ON Delivery_Assignments FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'Delivery_Assignments', OLD.AssignmentID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 12. OrderRating ==================================

CREATE TRIGGER trg_orderrating_unauth_insert
AFTER INSERT ON OrderRating FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'OrderRating', NEW.orderID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_orderrating_unauth_update
AFTER UPDATE ON OrderRating FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'OrderRating', NEW.orderID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_orderrating_unauth_delete
AFTER DELETE ON OrderRating FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'OrderRating', OLD.orderID,
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

-- ========================== 13. MenuItemRating ===============================

CREATE TRIGGER trg_menuitemrating_unauth_insert
AFTER INSERT ON MenuItemRating FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_INSERT', 'MenuItemRating',
            CONCAT(NEW.restaurantID, '-', NEW.itemID, '-', NEW.orderID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_menuitemrating_unauth_update
AFTER UPDATE ON MenuItemRating FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_UPDATE', 'MenuItemRating',
            CONCAT(NEW.restaurantID, '-', NEW.itemID, '-', NEW.orderID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

CREATE TRIGGER trg_menuitemrating_unauth_delete
AFTER DELETE ON MenuItemRating FOR EACH ROW
BEGIN
    IF @api_source IS NULL OR @api_source != TRUE THEN
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (NULL, 'UNAUTH_DELETE', 'MenuItemRating',
            CONCAT(OLD.restaurantID, '-', OLD.itemID, '-', OLD.orderID),
            JSON_OBJECT('source','DIRECT_DB','warning','Modification bypassed API'));
    END IF;
END //

DELIMITER ;
