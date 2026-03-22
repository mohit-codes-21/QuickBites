DROP DATABASE IF EXISTS QB;
CREATE DATABASE QB;
USE QB;

-- ================= MEMBER =================
CREATE TABLE Member (
    memberID INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL,
    phoneNumber CHAR(10) NOT NULL,
    createdAt DATETIME NOT NULL,
    isDeleted BOOLEAN NOT NULL DEFAULT 0
);

-- ================= CUSTOMER =================
CREATE TABLE Customer (
    customerID INT PRIMARY KEY,
    loyaltyTier INT NOT NULL CHECK (loyaltyTier BETWEEN 1 AND 5),
    membershipDiscount FLOAT NOT NULL CHECK (membershipDiscount IN (0,10)),
    cartTotalAmount DECIMAL(10,2) NOT NULL CHECK (cartTotalAmount >= 0),
    membershipDueDate DATETIME,
    membership BOOLEAN NOT NULL,
    isDeleted BOOLEAN NOT NULL DEFAULT 0,
    FOREIGN KEY (customerID) REFERENCES Member(memberID) on delete restrict on update cascade
);

-- ================= DELIVERY PARTNER =================
CREATE TABLE DeliveryPartner (
    partnerID INT PRIMARY KEY,
    vehicleNumber VARCHAR(100) NOT NULL,
    licenseID VARCHAR(100) NOT NULL UNIQUE,
    dateOfBirth DATE NOT NULL,
    currentLatitude DOUBLE NOT NULL,
    currentLongitude DOUBLE NOT NULL,
    isOnline BOOLEAN NOT NULL,
    averageRating FLOAT CHECK (averageRating BETWEEN 1 AND 5),
    image BLOB NOT NULL,
    isDeleted BOOLEAN NOT NULL DEFAULT 0,
    FOREIGN KEY (partnerID) REFERENCES Member(memberID) on delete restrict on update cascade
);

-- ================= RESTAURANT =================
CREATE TABLE Restaurant (
    restaurantID INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    contactPhone CHAR(10) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL,
    isOpen BOOLEAN NOT NULL,
    isVerified BOOLEAN NOT NULL,
    averageRating FLOAT CHECK (averageRating BETWEEN 1 AND 5),
    addressLine VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    zipCode CHAR(6) NOT NULL,
    latitude DOUBLE NOT NULL,
    longitude DOUBLE NOT NULL,
    discontinued BOOLEAN NOT NULL,
    isDeleted BOOLEAN NOT NULL DEFAULT 0
);

-- ================= MENU ITEM =================
CREATE TABLE MenuItem (
    restaurantID INT,
    itemID INT,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(100),
    menuCategory VARCHAR(100),
    restaurantPrice DECIMAL(10,2) NOT NULL,
    appPrice DECIMAL(10,2) NOT NULL,
    isVegetarian BOOLEAN NOT NULL,
    averageRating FLOAT CHECK (averageRating BETWEEN 1 AND 5),
    preparationTime INT NOT NULL CHECK (preparationTime BETWEEN 0 AND 60),
    isAvailable BOOLEAN NOT NULL,
    discontinued BOOLEAN NOT NULL,
    PRIMARY KEY (restaurantID, itemID),
    FOREIGN KEY (restaurantID) REFERENCES Restaurant(restaurantID) on delete restrict on update cascade,
    CHECK (appPrice > restaurantPrice)
);

-- ================= ADDRESS =================
CREATE TABLE Address (
    customerID INT,
    addressID INT,
    addressLine VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    zipCode CHAR(6) NOT NULL,
    label VARCHAR(100) NOT NULL,
    latitude DOUBLE NOT NULL,
    longitude DOUBLE NOT NULL,
    isSaved BOOLEAN NOT NULL,
    PRIMARY KEY (customerID, addressID),
    FOREIGN KEY (customerID) REFERENCES Customer(customerID) on delete restrict on update cascade
);

-- ================= CART ITEM =================
CREATE TABLE CartItem (
    customerID INT,
    restaurantID INT,
    itemID INT,
    quantity INT NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (customerID, restaurantID, itemID),
    FOREIGN KEY (customerID) REFERENCES Customer(customerID) on delete restrict on update cascade,
    FOREIGN KEY (restaurantID, itemID) REFERENCES MenuItem(restaurantID, itemID) on delete restrict on update cascade
);

-- ================= PAYMENT =================
CREATE TABLE Payment (
    paymentID INT PRIMARY KEY,
    customerID INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL CHECK (amount > 0),
    paymentType VARCHAR(12) NOT NULL,
    status VARCHAR(7) NOT NULL,
    transactionTime DATETIME NOT NULL,
    paymentFor VARCHAR(10) NOT NULL,
    FOREIGN KEY (customerID) REFERENCES Customer(customerID) on delete restrict on update cascade,
    CHECK (paymentType IN ('OnQuickBites','COD')),
    CHECK (status IN ('Pending','Success','Failed')),
    CHECK (paymentFor IN ('Order','Membership'))
);

-- ================= ORDERS =================
CREATE TABLE Orders (
    orderID INT PRIMARY KEY,
    orderTime DATETIME NOT NULL,
    estimatedTime DATETIME NOT NULL,
    totalAmount DECIMAL(10,2) NOT NULL CHECK (totalAmount > 0),
    orderStatus VARCHAR(20) NOT NULL,
    customerID INT NOT NULL,
    restaurantID INT NOT NULL,
    addressID INT NOT NULL,
    paymentID INT NOT NULL,
    specialInstruction VARCHAR(1000),
    FOREIGN KEY (customerID) REFERENCES Customer(customerID) on delete restrict on update cascade,
    FOREIGN KEY (restaurantID) REFERENCES Restaurant(restaurantID) on delete restrict on update cascade,
    FOREIGN KEY (paymentID) REFERENCES Payment(paymentID) on delete restrict on update cascade,
    FOREIGN KEY (customerID, addressID) REFERENCES Address(customerID, addressID) on delete restrict on update cascade,
    CHECK (orderStatus IN ('Created','Preparing','ReadyForPickup','OutForDelivery','Delivered'))
);

-- ================= ORDER ITEM =================
CREATE TABLE OrderItem (
    orderID INT,
    restaurantID INT,
    itemID INT,
    quantity INT NOT NULL,
    priceAtPurchase DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (orderID, restaurantID, itemID),
    FOREIGN KEY (orderID) REFERENCES Orders(orderID) on delete restrict on update cascade,
    FOREIGN KEY (restaurantID, itemID) REFERENCES MenuItem(restaurantID, itemID) on delete restrict on update cascade
);

-- ================= DELIVERY ASSIGNMENTS =================
CREATE TABLE Delivery_Assignments (
    AssignmentID INT PRIMARY KEY,
    OrderID INT NOT NULL,
    PartnerID INT NOT NULL,
    acceptanceTime DATETIME NOT NULL,
    pickupTime DATETIME NOT NULL,
    deliveryTime DATETIME NOT NULL,
    FOREIGN KEY (OrderID) REFERENCES Orders(orderID) on delete restrict on update cascade,
    FOREIGN KEY (PartnerID) REFERENCES DeliveryPartner(partnerID) on delete restrict on update cascade,
    CHECK (pickupTime > acceptanceTime),
    CHECK (deliveryTime > pickupTime)
);

-- ================= ORDER RATING =================
CREATE TABLE OrderRating (
    orderID INT PRIMARY KEY,
    restaurantRating INT CHECK (restaurantRating BETWEEN 1 AND 5) NOT NULL,
    deliveryRating INT CHECK (deliveryRating BETWEEN 1 AND 5) NOT NULL,
    comment VARCHAR(1000),
    FOREIGN KEY (orderID) REFERENCES Orders(orderID) on delete restrict on update cascade
);

-- ================= MENU ITEM RATING =================
CREATE TABLE MenuItemRating (
    restaurantID INT,
    itemID INT,
    orderID INT,
    rating INT,
    comment VARCHAR(1000),
    PRIMARY KEY (restaurantID, itemID, orderID),
    FOREIGN KEY (restaurantID, itemID) REFERENCES MenuItem(restaurantID, itemID) on delete restrict on update cascade,
    FOREIGN KEY (orderID) REFERENCES Orders(orderID) on delete restrict on update cascade
);

-- ================= CORE SYSTEM TABLES =================

-- Defines roles
CREATE TABLE Roles (
    roleID   INT PRIMARY KEY,
    roleName VARCHAR(50) NOT NULL UNIQUE,  -- 'Admin', 'Customer', 'DeliveryPartner', 'RestaurantManager'
    description VARCHAR(200)
);

INSERT INTO Roles VALUES
(1,'Admin','Full system access'),
(2,'Customer','Place and track orders'), 
(3,'DeliveryPartner','Accept and deliver orders'),
(4,'RestaurantManager','Manage restaurant and menu');

-- Maps members to roles (many-to-many)
CREATE TABLE MemberRoleMapping (
    memberID INT NOT NULL,
    roleID  INT NOT NULL,
    PRIMARY KEY (memberID, roleID),
    FOREIGN KEY (memberID) REFERENCES Member(memberID) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (roleID)  REFERENCES Roles(roleID)  ON DELETE CASCADE ON UPDATE CASCADE
);

-- Stores active sessions for logged-in members
CREATE TABLE Sessions (
    sessionToken CHAR(64) PRIMARY KEY,
    memberID     INT NOT NULL,
    createdAt    DATETIME NOT NULL,
    expiresAt    DATETIME NOT NULL,
    FOREIGN KEY (memberID) REFERENCES Member(memberID) ON DELETE CASCADE
);

-- Audit log for tracking changes (for simplicity, we log memberID as NULL for unauthenticated actions)
CREATE TABLE AuditLog (
    logID       INT AUTO_INCREMENT PRIMARY KEY,
    memberID    INT,          -- who performed the action (NULL if unauthenticated)
    action      VARCHAR(20),  -- 'INSERT', 'UPDATE', 'DELETE'
    tableName   VARCHAR(50),
    recordID    VARCHAR(100),
    timestamp   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details     TEXT
);

-- ================= DATA INSERTION =================

-- Members 
INSERT INTO Member(memberID, name, email, password, phoneNumber, createdAt) VALUES
(1,'Aman Shah','aman.shah1@example.com','pwd1','9876500001','2025-08-01 09:00:00'),
(2,'Riya Patel','riya.patel2@example.com','pwd2','9876500002','2025-08-02 10:00:00'),
(3,'Sameer Khan','sameer.k3@example.com','pwd3','9876500003','2025-08-03 11:00:00'),
(4,'Priya Gupta','priya.g4@example.com','pwd4','9876500004','2025-08-04 12:00:00'),
(5,'Mohit Verma','mohit.v5@example.com','pwd5','9876500005','2025-08-05 13:00:00'),
(6,'Neha Joshi','neha.j6@example.com','pwd6','9876500006','2025-08-06 14:00:00'),
(7,'Tarun Mehta','tarun.m7@example.com','pwd7','9876500007','2025-08-07 15:00:00'),
(8,'Sana Reddy','sana.r8@example.com','pwd8','9876500008','2025-08-08 16:00:00'),
(9,'Vikram Rao','vikram.r9@example.com','pwd9','9876500009','2025-08-09 17:00:00'),
(10,'Isha Nair','isha.n10@example.com','pwd10','9876500010','2025-08-10 18:00:00'),
(11,'Driver One','driver1@example.com','drv1','9000000011','2024-01-01 08:00:00'),
(12,'Driver Two','driver2@example.com','drv2','9000000012','2024-01-02 08:00:00'),
(13,'Driver Three','driver3@example.com','drv3','9000000013','2024-01-03 08:00:00'),
(14,'Driver Four','driver4@example.com','drv4','9000000014','2024-01-04 08:00:00'),
(15,'Driver Five','driver5@example.com','drv5','9000000015','2024-01-05 08:00:00'),
(16,'Driver Six','driver6@example.com','drv6','9000000016','2024-01-06 08:00:00'),
(17,'Driver Seven','driver7@example.com','drv7','9000000017','2024-01-07 08:00:00'),
(18,'Driver Eight','driver8@example.com','drv8','9000000018','2024-01-08 08:00:00'),
(19,'Driver Nine','driver9@example.com','drv9','9000000019','2024-01-09 08:00:00'),
(20,'Driver Ten','driver10@example.com','drv10','9000000020','2024-01-10 08:00:00'),
(21,'Extra One','extra1@example.com','pwd21','9876500021','2025-09-01 09:00:00'),
(22,'Extra Two','extra2@example.com','pwd22','9876500022','2025-09-02 09:00:00'),
(23,'Extra Three','extra3@example.com','pwd23','9876500023','2025-09-03 09:00:00'),
(24,'Extra Four','extra4@example.com','pwd24','9876500024','2025-09-04 09:00:00'),
(25,'Extra Five','extra5@example.com','pwd25','9876500025','2025-09-05 09:00:00'),
(26,'Extra Six','extra6@example.com','pwd26','9876500026','2025-09-06 09:00:00'),
(27,'Extra Seven','extra7@example.com','pwd27','9876500027','2025-09-07 09:00:00'),
(28,'Extra Eight','extra8@example.com','pwd28','9876500028','2025-09-08 09:00:00'),
(29,'Extra Nine','extra9@example.com','pwd29','9876500029','2025-09-09 09:00:00'),
(30,'Extra Ten','extra10@example.com','pwd30','9876500030','2025-09-10 09:00:00');

-- MemberRoleMapping (assign roles to members)
INSERT INTO `MemberRoleMapping`(memberID, roleID) VALUES
-- Customers (memberIDs 1-10) → roleID 2
(2,2),(3,2),(4,2),(5,2),(6,2),(7,2),(8,2),(9,2),(10,2),
-- Delivery Partners (memberIDs 11-20) → roleID 3
(11,3),(12,3),(13,3),(14,3),(15,3),(16,3),(17,3),(18,3),(19,3),(20,3),
-- Extra members (21-30) → roleID 2 (customers by default)
(21,2),(22,2),(23,2),(24,2),(25,2),(26,2),(27,2),(28,2),(29,2),(30,2),
-- Make memberID 1 also an Admin (dual role)
(1,1);

-- Customers 
INSERT INTO Customer(customerID, loyaltyTier, membershipDiscount, cartTotalAmount, membershipDueDate, membership) VALUES
(1,3,10.0,250.00,'2026-07-01 00:00:00',1),
(2,1,0.0,0.00,NULL,0),
(3,5,10.0,499.50,'2026-12-31 00:00:00',1),
(4,2,10.0,120.00,'2026-03-10 00:00:00',1),
(5,4,10.0,350.00,'2026-01-15 00:00:00',1),
(6,1,0.0,0.01,NULL,0),
(7,2,10.0,75.00,'2025-12-31 00:00:00',1),
(8,3,10.0,180.00,'2026-05-01 00:00:00',1),
(9,1,0.0,20.00,NULL,0),
(10,2,10.0,60.00,'2026-02-28 00:00:00',1);

-- DeliveryPartner 
INSERT INTO DeliveryPartner(partnerID, vehicleNumber, licenseID, dateOfBirth, currentLatitude, currentLongitude, isOnline, averageRating, image) VALUES
(11,'MH12AB1234','LICDRV11','1990-05-01',23.0225,72.5714,1,4.6,x'00'),
(12,'MH12AB1235','LICDRV12','1988-07-21',28.7041,77.1025,1,4.3,x'00'),
(13,'MH12AB1236','LICDRV13','1992-11-11',19.0760,72.8777,0,4.8,x'00'),
(14,'MH12AB1237','LICDRV14','1994-03-03',13.0827,80.2707,1,4.1,x'00'),
(15,'MH12AB1238','LICDRV15','1987-10-10',22.5726,88.3639,0,3.9,x'00'),
(16,'MH12AB1239','LICDRV16','1991-12-12',12.9716,77.5946,1,4.5,x'00'),
(17,'MH12AB1240','LICDRV17','1993-01-15',26.9124,75.7873,1,4.2,x'00'),
(18,'MH12AB1241','LICDRV18','1995-09-09',17.3850,78.4867,0,4.0,x'00'),
(19,'MH12AB1242','LICDRV19','1986-08-08',21.1702,72.8311,1,3.8,x'00'),
(20,'MH12AB1243','LICDRV20','1990-02-20',11.0168,76.9558,1,4.7,x'00');

-- Restaurants 
INSERT INTO Restaurant(restaurantID, name, contactPhone, email, password, isOpen, isVerified, averageRating, addressLine, city, zipCode, latitude, longitude, discontinued) VALUES
(201,'Spice Garden','9900000001','restaurant201@quickbites.local','rest201',1,1,4.5,'MG Road 12','Ahmedabad','380001',23.025,72.540,0),
(202,'The Curry Bowl','9900000002','restaurant202@quickbites.local','rest202',1,1,4.2,'Vastrapur Plaza','Ahmedabad','380015',23.030,72.520,0),
(203,'Urban Pizza','9900000003','restaurant203@quickbites.local','rest203',1,1,4.0,'Paldi Street 5','Ahmedabad','380007',23.027,72.530,0),
(204,'Green Leaf','9900000004','restaurant204@quickbites.local','rest204',0,1,4.3,'CBD Area 8','Ahmedabad','380009',23.021,72.543,0),
(205,'Sweet Treats','9900000005','restaurant205@quickbites.local','rest205',1,0,3.9,'Satellite Road','Ahmedabad','380054',23.034,72.550,0),
(206,'Tiffin House','9900000006','restaurant206@quickbites.local','rest206',1,1,4.1,'Navrangpura','Ahmedabad','380009',23.026,72.541,0),
(207,'Seafood Shack','9900000007','restaurant207@quickbites.local','rest207',0,1,4.4,'Beach Road','Surat','395003',21.170,72.831,0),
(208,'Grill King','9900000008','restaurant208@quickbites.local','rest208',1,1,4.6,'Ring Road','Vadodara','390001',22.307,73.181,0),
(209,'Fusion Café','9900000009','restaurant209@quickbites.local','rest209',1,1,4.0,'Ellis Bridge','Ahmedabad','380006',23.028,72.538,0),
(210,'Budget Bites','9900000010','restaurant210@quickbites.local','rest210',1,1,3.8,'College Street','Ahmedabad','380014',23.024,72.535,0);

-- MenuItem 
INSERT INTO MenuItem(restaurantID,itemID,name,description,menuCategory,restaurantPrice,appPrice,isVegetarian,averageRating,preparationTime,isAvailable,discontinued) VALUES
(201,1,'Paneer Butter Masala','Creamy paneer','Main',180.00,200.00,1,4.6,20,1,0),
(201,2,'Garlic Naan','Tandoor bread','Sides',35.00,40.00,1,4.4,6,1,0),
(202,1,'Butter Chicken','Classic butter chicken','Main',220.00,250.00,0,4.5,25,1,0),
(202,2,'Jeera Rice','Fragrant rice','Sides',70.00,85.00,1,4.2,10,1,0),
(203,1,'Margherita Pizza','Classic cheese pizza','Main',240.00,270.00,1,4.1,18,1,0),
(203,2,'Pepperoni Pizza','Spicy pepperoni','Main',300.00,340.00,0,4.3,20,1,0),
(204,1,'Caesar Salad','Healthy greens','Salad',150.00,170.00,1,4.0,8,1,0),
(204,2,'Grilled Sandwich','Veg sandwich','Snack',120.00,135.00,1,3.9,7,1,0),
(205,1,'Chocolate Cake','Dessert slice','Dessert',120.00,140.00,1,4.2,15,1,0),
(205,2,'Vanilla Icecream','Single scoop','Dessert',60.00,75.00,1,4.0,2,1,0),
(206,1,'Masala Dosa','South Indian dosa','Main',90.00,100.00,1,4.4,12,1,0),
(206,2,'Sambar','Lentil stew','Side',60.00,70.00,1,4.1,10,1,0),
(207,1,'Grilled Fish','Local catch','Main',350.00,390.00,0,4.5,22,1,0),
(207,2,'Prawn Fry','Spicy prawns','Main',320.00,360.00,0,4.2,20,1,0),
(208,1,'BBQ Chicken','Grilled chicken','Main',280.00,320.00,0,4.6,22,1,0),
(208,2,'Mashed Potatoes','Creamy mash','Sides',90.00,105.00,1,4.0,8,1,0),
(209,1,'Paneer Wrap','Street-style wrap','Snack',130.00,145.00,1,4.1,10,1,0),
(209,2,'Iced Latte','Cold coffee','Beverage',120.00,140.00,1,4.0,5,1,0),
(210,1,'Veg Thali','Meal plate','Main',150.00,170.00,1,4.0,20,1,0),
(210,2,'Samosa (2 pcs)','Deep fried snack','Snack',50.00,60.00,1,3.8,7,1,0);

-- Addresses 
INSERT INTO Address(customerID,addressID,addressLine,city,zipCode,label,latitude,longitude,isSaved) VALUES
(1,1,'Flat 12, Silver Apartments','Ahmedabad','380001','Home',23.0255,72.5405,1),
(1,2,'Office Tower 5, MG Road','Ahmedabad','380001','Work',23.0260,72.5410,1),
(2,1,'House 7, Lakeview','Ahmedabad','380015','Home',23.0310,72.5190,1),
(2,2,'Cafeteria 3, Vastrapur','Ahmedabad','380015','Work',23.0305,72.5205,1),
(3,1,'Plot 21, Paldi Street','Ahmedabad','380007','Home',23.0275,72.5320,1),
(3,2,'Office 9, Paldi','Ahmedabad','380007','Work',23.0280,72.5315,1),
(4,1,'House 4, CBD Area','Ahmedabad','380009','Home',23.0215,72.5435,1),
(4,2,'Shop 2, CBD Market','Ahmedabad','380009','Work',23.0220,72.5440,1),
(5,1,'12 Satellite Road','Ahmedabad','380054','Home',23.0342,72.5501,1),
(5,2,'Studio 5, Satellite','Ahmedabad','380054','Work',23.0345,72.5505,1),
(6,1,'3 Navrangpura','Ahmedabad','380009','Home',23.0261,72.5411,1),
(6,2,'Tiffin House Pickup','Ahmedabad','380009','Other',23.0260,72.5412,1),
(7,1,'10 Beach Lane','Surat','395003','Home',21.1710,72.8315,1),
(7,2,'Seafood Shack Pickup','Surat','395003','Other',21.1705,72.8310,1),
(8,1,'88 Ring Road','Vadodara','390001','Home',22.3075,73.1815,1),
(8,2,'Grill King Pickup','Vadodara','390001','Other',22.3070,73.1810,1),
(9,1,'2 College Street','Ahmedabad','380014','Home',23.0245,72.5355,1),
(9,2,'Budget Bites Pickup','Ahmedabad','380014','Other',23.0240,72.5350,1),
(10,1,'5 Ellis Bridge','Ahmedabad','380006','Home',23.0285,72.5385,1),
(10,2,'Fusion Café Pickup','Ahmedabad','380006','Other',23.0280,72.5380,1);

-- CartItem 
INSERT INTO CartItem(customerID, restaurantID, itemID, quantity) VALUES
(1,201,1,2),
(1,201,2,3),
(2,203,1,1),
(3,202,1,2),
(4,206,1,1),
(5,205,1,2),
(6,206,2,1),
(7,207,1,1),
(8,208,1,2),
(9,210,2,3),
(10,209,1,1),
(3,202,2,1);

-- Payment 
INSERT INTO Payment(paymentID, customerID, amount, paymentType, status, transactionTime, paymentFor) VALUES
(1001,1,320.00,'OnQuickBites','Success','2026-02-01 12:15:00','Order'),
(1002,2,270.00,'OnQuickBites','Success','2026-02-02 13:00:00','Order'),
(1003,3,500.00,'OnQuickBites','Success','2026-02-03 19:30:00','Order'),
(1004,4,140.00,'COD','Pending','2026-02-04 13:45:00','Order'),
(1005,5,200.00,'OnQuickBites','Success','2026-02-05 20:10:00','Order'),
(1006,6,70.00,'OnQuickBites','Success','2026-02-06 09:00:00','Order'),
(1007,7,380.00,'OnQuickBites','Success','2026-02-07 21:00:00','Order'),
(1008,8,210.00,'OnQuickBites','Success','2026-02-08 18:30:00','Order'),
(1009,9,62.00,'COD','Success','2026-02-09 11:00:00','Order'),
(1010,10,160.00,'OnQuickBites','Success','2026-02-10 14:00:00','Order'),
(1011,3,120.00,'OnQuickBites','Success','2026-01-20 12:00:00','Membership'),
(1012,1,50.00,'OnQuickBites','Success','2026-01-21 08:00:00','Order');

-- Orders 
INSERT INTO Orders(orderID, orderTime, estimatedTime, totalAmount, orderStatus, customerID, restaurantID, addressID, paymentID, specialInstruction) VALUES
(5001,'2026-02-01 12:10:00','2026-02-01 12:40:00',320.00,'Delivered',1,201,1,1001,'No onion'),
(5002,'2026-02-02 12:50:00','2026-02-02 13:20:00',270.00,'Delivered',2,203,1,1002,'Extra cheese'),
(5003,'2026-02-03 19:10:00','2026-02-03 19:45:00',500.00,'Delivered',3,202,1,1003,'Less spicy'),
(5004,'2026-02-04 13:30:00','2026-02-04 14:00:00',140.00,'Created',4,206,2,1004,'Call on arrival'),
(5005,'2026-02-05 19:45:00','2026-02-05 20:20:00',200.00,'Delivered',5,205,1,1005,NULL),
(5006,'2026-02-06 08:50:00','2026-02-06 09:20:00',70.00,'Delivered',6,206,1,1006,'No chutney'),
(5007,'2026-02-07 20:50:00','2026-02-07 21:30:00',380.00,'Delivered',7,207,1,1007,'Extra spicy'),
(5008,'2026-02-08 18:00:00','2026-02-08 18:35:00',210.00,'Delivered',8,208,2,1008,'Cut into halves'),
(5009,'2026-02-09 10:30:00','2026-02-09 11:00:00',62.00,'Delivered',9,210,1,1009,'Pack separately'),
(5010,'2026-02-10 13:40:00','2026-02-10 14:10:00',160.00,'Delivered',10,209,2,1010,NULL),
(5011,'2026-01-20 11:50:00','2026-01-20 12:20:00',120.00,'Delivered',3,205,2,1011,'Subscription order'),
(5012,'2026-01-21 07:50:00','2026-01-21 08:10:00',50.00,'Delivered',1,210,2,1012,'Early morning');

-- OrderItem 
INSERT INTO OrderItem(orderID, restaurantID, itemID, quantity, priceAtPurchase) VALUES
(5001,201,1,1,200.00),
(5001,201,2,3,40.00),
(5002,203,1,1,270.00),
(5003,202,1,2,250.00),
(5003,202,2,1,85.00),
(5004,206,1,1,100.00),
(5005,205,1,2,140.00),
(5006,206,2,1,70.00),
(5007,207,1,1,390.00),
(5007,207,2,1,360.00),
(5008,208,1,2,320.00),
(5008,208,2,1,105.00),
(5009,210,2,3,60.00),
(5010,209,1,1,145.00),
(5011,205,1,1,140.00),
(5011,205,2,1,75.00),
(5012,210,1,1,170.00),
(5012,210,2,1,60.00),
(5002,203,2,1,340.00),
(5005,205,2,1,75.00),
(5004,206,2,1,70.00),
(5009,210,1,1,170.00);

-- Delivery_Assignments 
INSERT INTO Delivery_Assignments(AssignmentID, OrderID, PartnerID, acceptanceTime, pickupTime, deliveryTime) VALUES
(9001,5001,11,'2026-02-01 12:11:00','2026-02-01 12:25:00','2026-02-01 12:38:00'),
(9002,5002,12,'2026-02-02 12:51:00','2026-02-02 13:05:00','2026-02-02 13:18:00'),
(9003,5003,13,'2026-02-03 19:12:00','2026-02-03 19:30:00','2026-02-03 19:44:00'),
(9004,5004,14,'2026-02-04 13:31:00','2026-02-04 13:50:00','2026-02-04 14:05:00'),
(9005,5005,15,'2026-02-05 19:46:00','2026-02-05 20:05:00','2026-02-05 20:18:00'),
(9006,5006,16,'2026-02-06 08:51:00','2026-02-06 09:05:00','2026-02-06 09:18:00'),
(9007,5007,17,'2026-02-07 20:51:00','2026-02-07 21:10:00','2026-02-07 21:28:00'),
(9008,5008,18,'2026-02-08 18:01:00','2026-02-08 18:20:00','2026-02-08 18:33:00'),
(9009,5009,19,'2026-02-09 10:31:00','2026-02-09 10:45:00','2026-02-09 10:58:00'),
(9010,5010,20,'2026-02-10 13:41:00','2026-02-10 13:55:00','2026-02-10 14:05:00'),
(9011,5011,11,'2026-01-20 11:51:00','2026-01-20 12:05:00','2026-01-20 12:18:00'),
(9012,5012,12,'2026-01-21 07:51:00','2026-01-21 07:58:00','2026-01-21 08:05:00');

-- OrderRating 
INSERT INTO OrderRating(orderID, restaurantRating, deliveryRating, comment) VALUES
(5001,5,5,'Great food and quick delivery'),
(5002,4,4,'Tasty but a bit oily'),
(5003,5,5,'Excellent'),
(5004,NULL,NULL,'Order cancelled by restaurant'),
(5005,3,4,'Sweets were okay'),
(5006,4,4,'Good morning tiffin'),
(5007,5,5,'Loved the prawns'),
(5008,4,4,'Nicely packed'),
(5009,3,3,'Samosas a bit soggy'),
(5010,4,5,'Fast delivery'),
(5011,4,4,'Subscription worked fine'),
(5012,3,4,'Small portion but on time');

-- MenuItemRating 
INSERT INTO MenuItemRating(restaurantID, itemID, orderID, rating, comment) VALUES
(201,1,5001,5,'Paneer was soft'),
(201,2,5001,4,'Naan was crisp'),
(203,1,5002,4,'Good cheese'),
(202,1,5003,5,'Perfect spice'),
(202,2,5003,4,'Rice was fragrant'),
(206,1,5004,4,'Dosa slightly soggy'),
(205,1,5005,3,'Cake a bit dry'),
(206,2,5006,4,'Sambar good'),
(207,1,5007,5,'Fish cooked well'),
(207,2,5007,4,'Prawn flavor great'),
(208,1,5008,5,'BBQ excellent'),
(208,2,5008,3,'Potatoes average'),
(210,2,5009,3,'Samosa not hot'),
(209,1,5010,4,'Wrap was fresh'),
(205,1,5011,4,'Good dessert'),
(205,2,5011,4,'Icecream creamy'),
(210,1,5012,3,'Thali portion small'),
(210,2,5012,3,'Samosa small'),
(203,2,5002,4,'Pepperoni tasty'),
(205,2,5005,4,'Icecream good'),
(206,2,5004,4,'Second comment on sambar'),
(210,1,5009,4,'Thali main was fine');