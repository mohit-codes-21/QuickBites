import csv
import os
import threading
import time
from collections import defaultdict

from locust import HttpUser, between, events, task


LOG_CSV = os.path.abspath(os.path.join(os.path.dirname(__file__), "logs", "stress_results.csv"))

RESTAURANT_EMAIL = os.getenv("QB_RESTAURANT_EMAIL", "restaurant202@quickbites.local")
RESTAURANT_PASSWORD = os.getenv("QB_RESTAURANT_PASSWORD", "rest202")

_CREATED_LOCK = threading.Lock()
_CREATED_ITEMS = set()


def _extract_token(response):
    try:
        body = response.json()
    except Exception:
        return None
    return ((body or {}).get("data") or {}).get("token")


def _p95_from_histogram(response_times):
    # response_times is a histogram dict {ms: count}
    if not response_times:
        return 0.0

    total = sum(response_times.values())
    target = max(1, int(total * 0.95))
    running = 0
    for ms in sorted(response_times.keys()):
        running += response_times[ms]
        if running >= target:
            return float(ms)
    return float(max(response_times.keys()))


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    os.makedirs(os.path.dirname(LOG_CSV), exist_ok=True)

    with open(LOG_CSV, "w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["endpoint", "avg_response_ms", "p95_response_ms", "error_rate_percent", "rps"])

        for (name, method), entry in environment.stats.entries.items():
            total = entry.num_requests or 0
            fails = entry.num_failures or 0
            error_rate = (fails / total * 100.0) if total else 0.0
            p95 = _p95_from_histogram(entry.response_times)

            writer.writerow(
                [
                    f"{method} {name}",
                    round(entry.avg_response_time or 0.0, 3),
                    round(p95, 3),
                    round(error_rate, 3),
                    round(entry.current_rps or 0.0, 3),
                ]
            )


class QuickBitesUser(HttpUser):
    wait_time = between(0.2, 1.2)

    def on_start(self):
        self.restaurant_id = 202
        self.item_id = 1
        self.temp_created_item_ids = set()
        self.headers = {"Content-Type": "application/json"}

        with self.client.post(
            "/api/auth/login",
            json={
                "email": RESTAURANT_EMAIL,
                "password": RESTAURANT_PASSWORD,
                "loginAs": "RestaurantManager",
            },
            name="POST /api/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login_failed status={response.status_code}")
                return

            token = _extract_token(response)
            if not token:
                response.failure("login_failed missing JWT token")
                return

            self.headers["Authorization"] = f"Bearer {token}"
            response.success()

    def on_stop(self):
        # Best-effort cleanup of records created by this simulated user.
        for item_id in list(self.temp_created_item_ids):
            self.client.delete(
                f"/api/menu-items/{self.restaurant_id}/{item_id}",
                headers=self.headers,
                name="DELETE /api/menu-items/<rid>/<iid>",
            )

    @task(3)
    def get_main_listing(self):
        self.client.get(
            "/api/menu-items",
            params={"restaurantID": self.restaurant_id, "includeDiscontinued": "true"},
            headers=self.headers,
            name="GET /api/menu-items",
        )

    @task(3)
    def get_single_record(self):
        # Single-record view via targeted search expected to return one matching row.
        self.client.get(
            "/api/menu-items",
            params={
                "restaurantID": self.restaurant_id,
                "search": "Paneer Butter Masala",
                "includeDiscontinued": "true",
            },
            headers=self.headers,
            name="GET /api/menu-items?search=single",
        )

    @task(2)
    def create_record(self):
        unique = int(time.time() * 1000) % 1_000_000_000
        payload = {
            "restaurantID": self.restaurant_id,
            "name": f"Locust_Item_{unique}",
            "description": "locust temp record",
            "menuCategory": "Stress",
            "restaurantPrice": 99.0,
            "isVegetarian": True,
            "preparationTime": 12,
            "isAvailable": True,
        }

        with self.client.post(
            "/api/menu-items",
            json=payload,
            headers=self.headers,
            name="POST /api/menu-items",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"create_failed status={response.status_code}")
                return

            try:
                item_id = int(((response.json() or {}).get("data") or {}).get("itemID"))
                self.item_id = item_id
                self.temp_created_item_ids.add(item_id)
                with _CREATED_LOCK:
                    _CREATED_ITEMS.add((self.restaurant_id, item_id))
                response.success()
            except Exception as exc:
                response.failure(f"create_parse_failed {exc}")

    @task(1)
    def update_record(self):
        payload = {"name": f"Locust_Update_{int(time.time() * 1000) % 1_000_000_000}"}
        with self.client.put(
            f"/api/menu-items/{self.restaurant_id}/{self.item_id}",
            json=payload,
            headers=self.headers,
            name="PUT /api/menu-items/<rid>/<iid>",
            catch_response=True,
        ) as response:
            # In this mixed CRUD workload, a record may be deleted by a prior task.
            if response.status_code in (200, 404):
                response.success()
            else:
                response.failure(f"update_failed status={response.status_code}")

    @task(1)
    def delete_record(self):
        with self.client.delete(
            f"/api/menu-items/{self.restaurant_id}/{self.item_id}",
            headers=self.headers,
            name="DELETE /api/menu-items/<rid>/<iid>",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 404):
                if self.item_id in self.temp_created_item_ids:
                    self.temp_created_item_ids.discard(self.item_id)
                response.success()
            else:
                response.failure(f"delete_failed status={response.status_code}")
