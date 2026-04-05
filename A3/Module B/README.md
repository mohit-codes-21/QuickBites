# ScaleOps - QuickBites (Module B)

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
	tests/
	sql/
	logs/
	figures/
	docs/
		assignment_report.md
		explaination.txt
		optimization_subtask_4_5_summary.md
	report/
		assignment_report.tex
		assignment_report.pdf
	locustfile.py
	generate_test_case_figures.py
	generate_figures.py
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

## 3.1) Run with Makefile (Linux/macOS or Windows with make installed)

From `Module B`:

```powershell
make run
```

Useful targets:

- `make venv` -> create virtual environment if missing
- `make install` -> install dependencies in virtual environment
- `make run` -> venv + install + run app
- `make clean` -> remove virtual environment

If PowerShell says `make` is not recognized, use `run.ps1` (below).

---

## 3.2) Run with PowerShell Script (Windows)

From `Module B`:

```powershell
.\run.ps1 -Target run
```

Useful targets:

- `.\run.ps1 -Target venv`
- `.\run.ps1 -Target install`
- `.\run.ps1 -Target run`
- `.\run.ps1 -Target clean`
- `.\run.ps1 -Target help`

If script execution is blocked:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Target run
```

---

## 4) Role Portals / Routes

- Main login/signup portal: `/`
- Customer portal: `/customer`
- Customer sub-pages: `/customer/restaurants`, `/customer/browse`, `/customer/cart`, `/customer/profile`
- Restaurant dashboard: `/restaurant`
- Delivery dashboard: `/delivery`

After login/signup, users are auto-redirected to their role portal.

---

## 5) Reliability Test Scripts

These scripts validate transactional correctness, conflict handling, failure safety, and load robustness.

Run from `Module B` with the app running (recommended on `http://127.0.0.1:5001`).

```bash
python tests/concurrent_test.py
python tests/race_condition_test.py
python tests/failure_simulation_test.py
python tests/acid_verification.py
python tests/stress_test.py
locust -f locustfile.py --headless -u 60 -r 20 -t 1m --host http://127.0.0.1:5001

```

What each script covers:

- `tests/concurrent_test.py`: parallel read/write/delete scenarios and shared-cart contention.
- `tests/race_condition_test.py`: signup race (50 contenders) and delivery acceptance race (10 contenders).
- `tests/failure_simulation_test.py`: mid-transaction failure, timeout handling, and forced disconnect rollback checks.
- `tests/acid_verification.py`: explicit Atomicity, Consistency, Isolation, and Durability verification.
- `tests/stress_test.py`: threaded mixed CRUD stress run (request-rate, latency, error-rate metrics).
- `locustfile.py`: user-simulated load profile with headless Locust and endpoint-level CSV metrics.

Generated artifacts from test/report flow:

- `logs/test_case_metrics_latest.csv`
- `logs/test_case_metrics_summary.json`
- `figures/test_cases/*.png`
- `report/assignment_report.pdf`

---

## Indexing + Benchmarking (SubTask 4-5)

This repo includes:

- SQL indexes targeting the app's most frequent WHERE/JOIN/ORDER BY patterns: `sql/indexes.sql`
- A reproducible benchmark runner that captures timings + `EXPLAIN` plans before vs after indexing: `app/benchmark_indexing.py`

### Apply Indexes (SubTask 4)

After importing `sql/SQL_Dump.sql`, apply the indexes:

```sql
USE QB;
SOURCE path/to/Module B/sql/indexes.sql;
```

### Benchmark Before vs After (SubTask 5)

From `Module B/app` (inside the same venv you use to run the app):

```bash
python3 benchmark_indexing.py --mode full
```

If you changed the seed credentials or want to benchmark different sample IDs, pass them explicitly (example):

```bash
python3 benchmark_indexing.py --mode full \
	--customer-id 2 --restaurant-id 202 --partner-id 12 \
	--admin-email aman.shah1@example.com --admin-password pwd1 \
	--customer-email riya.patel2@example.com --customer-password pwd2 \
	--partner-email driver1@example.com --partner-password drv1
```

This will:

- Drop the optimisation indexes (if present)
- Record query timings + API timings + `EXPLAIN` output (BEFORE)
- Apply the optimisation indexes
- Record the same metrics again (AFTER)

It prints the path to a JSON report written under `Module B/logs/` (for example `logs/index_benchmark_YYYYMMDDTHHMMSSZ.json`).

If you only want to apply or drop indexes:

```bash
python3 benchmark_indexing.py --mode apply
python3 benchmark_indexing.py --mode drop
```

---

## Features (Short Overview)

## Authentication & Sessions

- Role-based login (`Customer`, `RestaurantManager`, `DeliveryPartner`, `Admin`)
- Signup flows for customer, restaurant, and delivery partner
- Session token persistence and role-aware redirect

## Customer Features

- Browse restaurants and menu items
- Search menu by item name and restaurant name
- Add/manage cart items with restaurant availability checks
- Place orders with payment mode and special instructions
- 30 km delivery radius enforcement from selected delivery address
- Restaurant closed-state enforcement for cart and checkout
- Loyalty tier progression for members on every 10 successful orders (max tier 5)
- Loyalty tier discount applied to cart and checkout totals:
	- Tier 1 (or non-member): 0%
	- Tier 2: 5%
	- Tier 3: 8%
	- Tier 4: 11%
	- Tier 5: 14%
- Cart summary breakdown with subtotal, discount percent, discount amount, and payable total
- Manage delivery addresses with map/geolocation
- View order history and reviews
- Live delivery tracking map in profile for active orders
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
- Customer/restaurant/delivery-partner soft delete + restore flows
- Cross-role access controls via role mapping tables
- Audits API backed by database logs with file fallback/sync behavior

---

## Logging

Logs are written under `Module B/logs`:

- `audit.log`: data mutation and audit events
- `activity.log`: auth and activity events
- `audit_sync_state.json`: tracks DB-to-file audit sync progress

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

---

## Video Link

[https://drive.google.com/drive/folders/1OtolgynR4hzeLOUcxGp0q0B9xwqfdKdS?usp=sharing](https://drive.google.com/drive/folders/1OtolgynR4hzeLOUcxGp0q0B9xwqfdKdS?usp=sharing)