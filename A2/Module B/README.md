# QuickBites (A2 Module B)

QuickBites is a multi-role food delivery web application built with Flask + MySQL.
It includes separate experiences for:

- Customer
- Restaurant Manager
- Delivery Partner
- Admin (via main portal)

---

## Tech Stack

- Backend: Flask
- Database: MySQL
- Auth: Session token stored in DB (`Sessions` table)
- Frontend: Jinja templates + Vanilla JS + CSS
- Maps: Leaflet + browser geolocation

---

## Project Structure

```text
Module B/
	app/
		app.py
		requirements.txt
		templates/
		static/
	sql/
		SQL_Dump.sql
	logs/
	README.md
```

---

## Prerequisites

1. Python 3.10+ (recommended)
2. MySQL Server 8+
3. pip

---

## 1) Database Setup

1. Open MySQL and run the SQL dump:

```sql
SOURCE path/to/Module B/sql/SQL_Dump.sql;
```

or import it from MySQL Workbench.

2. By default, the app expects:

- Host: `127.0.0.1`
- Port: `3306`
- User: `qb_admin`
- Password: `qb_admin@123`
- Database: `QB`

If your DB credentials are different, set environment variables before running:

- `QB_DB_HOST`
- `QB_DB_PORT`
- `QB_DB_USER`
- `QB_DB_PASSWORD`
- `QB_DB_NAME`

Optional session lifetime env variable:

- `QB_SESSION_HOURS` (default `8`)

---

## 2) Python Environment Setup

From `Module B`:

```powershell
cd app
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Dependencies:

- Flask==3.0.3
- mysql-connector-python==9.0.0
- bcrypt==4.2.0

---

## 3) Run the App

From `Module B/app`:

```powershell
python app.py
```

Open in browser:

- `http://127.0.0.1:5000/`

---

## 4) Role Portals / Routes

- Main login/signup portal: `/`
- Customer portal: `/customer`
- Customer sub-pages: `/customer/restaurants`, `/customer/browse`, `/customer/cart`, `/customer/profile`
- Restaurant dashboard: `/restaurant`
- Delivery dashboard: `/delivery`

After login/signup, users are auto-redirected to their role portal.

---

## Features (Short Overview)

## Authentication & Sessions

- Role-based login (`Customer`, `RestaurantManager`, `DeliveryPartner`, `Admin`)
- Signup flows for customer, restaurant, and delivery partner
- Session token persistence and role-aware redirect

## Customer Features

- Browse restaurants and menu items
- Search menu by item name and restaurant name
- Add/manage cart items
- Place orders with payment mode and special instructions
- Manage delivery addresses with map/geolocation
- View order history and reviews
- Update/delete customer profile

## Restaurant Features

- Dedicated dashboard with overview, menu, orders, profile
- Add/update/discontinue menu items
- Re-enable discontinued items from catalog
- Auto menu item ID assignment per restaurant
- App price auto-calculated from restaurant price
- Update order status (restaurant-limited workflow)
- Profile update with map, email/password, location, open status

## Delivery Partner Features

- Dedicated dashboard with hero, live orders, fulfillment, profile
- Live orders sorted nearest-first (distance score)
- Single active order assignment enforcement
- Fulfillment tab with pickup/drop map and contact details
- Update delivery order status (`OutForDelivery`, `Delivered`)
- Live location updates (periodic geolocation push)
- Completed orders list
- Update/delete delivery profile

## Admin / Management (Core APIs)

- Member management APIs (create, soft delete, restore)
- Cross-role access controls via role mapping tables

---

## Logging

Logs are written under `Module B/logs`:

- `audit.log`: data mutation and audit events
- `activity.log`: auth and activity events

---

## Notes

- This project uses soft-delete patterns for many entities.
- Passwords are handled with bcrypt hashing logic in backend flows.
- Leaflet map features require internet access for map tiles.

---

## Quick Troubleshooting

1. App starts but DB errors appear:
- Verify MySQL is running.
- Check DB credentials/env vars.
- Re-import `sql/SQL_Dump.sql`.

2. Login fails for seeded users:
- Ensure dump loaded successfully.
- Seed data includes plaintext passwords that are migrated to bcrypt on successful login.

3. Map not loading:
- Check internet access and browser geolocation permissions.

