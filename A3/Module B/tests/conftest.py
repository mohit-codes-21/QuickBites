import json
import os
import threading
import time
from datetime import datetime

import requests

try:
    import pytest
except ImportError:
    class _PytestCompat:
        @staticmethod
        def fixture(*args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

    pytest = _PytestCompat()


BASE_URL = os.getenv("QB_BASE_URL", "http://127.0.0.1:5001").rstrip("/")

ADMIN_CREDENTIALS = {
    "email": os.getenv("QB_ADMIN_EMAIL", "aman.shah1@example.com"),
    "password": os.getenv("QB_ADMIN_PASSWORD", "pwd1"),
    "loginAs": "Admin",
}

REGULAR_USER_CREDENTIALS = {
    "email": os.getenv("QB_USER_EMAIL", "riya.patel2@example.com"),
    "password": os.getenv("QB_USER_PASSWORD", "pwd2"),
    "loginAs": "Customer",
}

RESTAURANT_CREDENTIALS = {
    "email": os.getenv("QB_RESTAURANT_EMAIL", "restaurant202@quickbites.local"),
    "password": os.getenv("QB_RESTAURANT_PASSWORD", "rest202"),
    "loginAs": "RestaurantManager",
}

LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs", "test_results.log"))
METRICS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs", "test_metrics.jsonl"))

_log_lock = threading.Lock()


def append_test_result(test_name, passed, reason, duration_ms=None, metrics=None, suite=None):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    stamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    status = "PASS" if passed else "FAIL"
    duration_suffix = ""
    if duration_ms is not None:
        duration_suffix = f" | duration_ms={float(duration_ms):.3f}"
    line = f"[{stamp}] {test_name} | {status} | {reason}{duration_suffix}\n"

    metrics_entry = {
        "timestamp": stamp,
        "testName": test_name,
        "suite": suite or "unspecified",
        "status": status,
        "passed": bool(passed),
        "reason": str(reason),
        "durationMs": None if duration_ms is None else round(float(duration_ms), 3),
        "metrics": metrics or {},
    }

    with _log_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as fp:
            fp.write(line)
        with open(METRICS_FILE, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(metrics_entry) + "\n")


def login_and_get_token(base_url, credentials, timeout=10):
    response = requests.post(
        f"{base_url}/api/auth/login",
        json={
            "email": credentials["email"],
            "password": credentials["password"],
            "loginAs": credentials["loginAs"],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    token = ((payload or {}).get("data") or {}).get("token")
    if not token:
        raise RuntimeError("Login succeeded but JWT token is missing in response")
    return token


def auth_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def create_temp_menu_record(base_url, restaurant_credentials, timeout=10):
    token = login_and_get_token(base_url, restaurant_credentials, timeout=timeout)
    unique = int(time.time() * 1000)
    payload = {
        "restaurantID": 202,
        "name": f"Temp_Item_{unique}",
        "description": "temporary record for concurrency tests",
        "menuCategory": "Test",
        "restaurantPrice": 99.0,
        "isVegetarian": True,
        "preparationTime": 10,
        "isAvailable": True,
    }

    response = requests.post(
        f"{base_url}/api/menu-items",
        json=payload,
        headers=auth_headers(token),
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    data = (body or {}).get("data") or {}
    return {
        "token": token,
        "restaurantID": int(data["restaurantID"]),
        "itemID": int(data["itemID"]),
        "name": data["name"],
    }


def delete_temp_menu_record(base_url, token, restaurant_id, item_id, timeout=10):
    response = requests.delete(
        f"{base_url}/api/menu-items/{restaurant_id}/{item_id}",
        headers=auth_headers(token),
        timeout=timeout,
    )
    if response.status_code not in (200, 404):
        response.raise_for_status()


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def admin_credentials():
    return ADMIN_CREDENTIALS


@pytest.fixture(scope="session")
def regular_user_credentials():
    return REGULAR_USER_CREDENTIALS


@pytest.fixture(scope="session")
def restaurant_credentials():
    return RESTAURANT_CREDENTIALS


@pytest.fixture
def temp_menu_record(base_url, restaurant_credentials):
    record = create_temp_menu_record(base_url, restaurant_credentials)
    try:
        yield record
    finally:
        delete_temp_menu_record(base_url, record["token"], record["restaurantID"], record["itemID"])
