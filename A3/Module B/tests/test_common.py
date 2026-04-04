import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import mysql.connector


BASE_URL = os.getenv("QB_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
DB_CONFIG = {
    "host": os.getenv("QB_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("QB_DB_PORT", "3306")),
    "user": os.getenv("QB_DB_USER", "qb_admin"),
    "password": os.getenv("QB_DB_PASSWORD", "qb_admin@123"),
    "database": os.getenv("QB_DB_NAME", "QB"),
}

DEFAULT_ADMIN = {
    "email": os.getenv("QB_ADMIN_EMAIL", "aman.shah1@example.com"),
    "password": os.getenv("QB_ADMIN_PASSWORD", "pwd1"),
    "role": "Admin",
}

DEFAULT_CUSTOMERS = [
    {"email": "riya.patel2@example.com", "password": "pwd2", "role": "Customer"},
    {"email": "sameer.k3@example.com", "password": "pwd3", "role": "Customer"},
    {"email": "priya.g4@example.com", "password": "pwd4", "role": "Customer"},
    {"email": "mohit.v5@example.com", "password": "pwd5", "role": "Customer"},
    {"email": "neha.j6@example.com", "password": "pwd6", "role": "Customer"},
    {"email": "tarun.m7@example.com", "password": "pwd7", "role": "Customer"},
    {"email": "sana.r8@example.com", "password": "pwd8", "role": "Customer"},
    {"email": "vikram.r9@example.com", "password": "pwd9", "role": "Customer"},
    {"email": "isha.n10@example.com", "password": "pwd10", "role": "Customer"},
    {"email": "extra1@example.com", "password": "pwd21", "role": "Customer"},
]


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def http_json(method, path, payload=None, token=None, timeout=15.0):
    url = BASE_URL + path
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = "Bearer " + token

    req = urllib.request.Request(url=url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, _safe_json(raw), None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        return exc.code, _safe_json(raw), str(exc)
    except Exception as exc:
        return 0, None, str(exc)


def _safe_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def login(email, password, role):
    status, data, err = http_json(
        "POST",
        "/api/auth/login",
        payload={"email": email, "password": password, "loginAs": role},
    )
    if status != 200:
        return None, f"login failed status={status} err={err} body={data}"
    token = ((data or {}).get("data") or {}).get("token")
    if not token:
        return None, "login succeeded but no token returned"
    return token, None


def db_connect(autocommit=True):
    conn = mysql.connector.connect(**DB_CONFIG)
    conn.autocommit = autocommit
    return conn


def ensure_order_ready_for_pickup(order_id):
    conn = db_connect(autocommit=False)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE Orders SET orderStatus = 'ReadyForPickup' WHERE orderID = %s", (order_id,))
        conn.commit()
    finally:
        conn.close()


def print_result(name, ok, details=""):
    verdict = "PASS" if ok else "FAIL"
    print(f"[{verdict}] {name}{': ' + details if details else ''}")


def thread_run(worker, count):
    results = [None] * count
    threads = []

    def wrapped(index):
        results[index] = worker(index)

    for i in range(count):
        t = threading.Thread(target=wrapped, args=(i,), daemon=True)
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results


def percentile(sorted_values, p):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * p
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return float(sorted_values[low] + (sorted_values[high] - sorted_values[low]) * frac)


def monotonic_ms():
    return time.perf_counter() * 1000.0
