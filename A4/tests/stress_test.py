import csv
import os
import random
import threading
import time
from datetime import datetime

import requests

from conftest import (
    BASE_URL,
    RESTAURANT_CREDENTIALS,
    append_test_result,
    auth_headers,
    login_and_get_token,
)


TOTAL_REQUESTS = int(os.getenv("QB_STRESS_TOTAL_REQUESTS", "1000"))
THREADS = int(os.getenv("QB_STRESS_THREADS", "40"))
RESTAURANT_ID = int(os.getenv("QB_STRESS_RESTAURANT_ID", "202"))

CSV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs", "stress_results.csv"))


def _bounded_total_requests(raw_total):
    return max(1000, raw_total)


def _percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * frac)


def _req(session, method, path, token, **kwargs):
    headers = kwargs.pop("headers", {})
    merged = auth_headers(token)
    merged.update(headers)
    start = time.perf_counter()
    try:
        resp = session.request(method, BASE_URL + path, headers=merged, timeout=8, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return resp.status_code, elapsed_ms
    except requests.RequestException:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return 0, elapsed_ms


def main():
    total_requests = _bounded_total_requests(TOTAL_REQUESTS)
    token = login_and_get_token(BASE_URL, RESTAURANT_CREDENTIALS)

    created_items = []
    created_lock = threading.Lock()

    all_times = []
    total_errors = 0
    completed = 0
    lock = threading.Lock()
    counter = {"value": 0}

    # endpoint -> [count, errors, [response_times]]
    metrics = {
        "GET /api/menu-items": [0, 0, []],
        "GET /api/menu-items?search=single": [0, 0, []],
        "POST /api/menu-items": [0, 0, []],
        "PUT /api/menu-items/<rid>/<iid>": [0, 0, []],
        "DELETE /api/menu-items/<rid>/<iid>": [0, 0, []],
    }

    def record(name, status, elapsed):
        nonlocal total_errors, completed
        with lock:
            completed += 1
            all_times.append(elapsed)
            metrics[name][0] += 1
            metrics[name][2].append(elapsed)
            if status == 0 or status >= 400:
                total_errors += 1
                metrics[name][1] += 1

    def worker():
        session = requests.Session()
        local_item_id = 1

        while True:
            with lock:
                if counter["value"] >= total_requests:
                    break
                counter["value"] += 1

            pick = random.random()

            if pick < 0.30:
                status, elapsed = _req(
                    session,
                    "GET",
                    "/api/menu-items",
                    token,
                    params={"restaurantID": RESTAURANT_ID, "includeDiscontinued": "true"},
                )
                record("GET /api/menu-items", status, elapsed)
                continue

            if pick < 0.60:
                status, elapsed = _req(
                    session,
                    "GET",
                    "/api/menu-items",
                    token,
                    params={
                        "restaurantID": RESTAURANT_ID,
                        "includeDiscontinued": "true",
                        "search": "Paneer Butter Masala",
                    },
                )
                record("GET /api/menu-items?search=single", status, elapsed)
                continue

            if pick < 0.80:
                unique = int(time.time() * 1000) % 1_000_000_000
                payload = {
                    "restaurantID": RESTAURANT_ID,
                    "name": f"StressItem_{unique}",
                    "description": "stress temp",
                    "menuCategory": "Stress",
                    "restaurantPrice": 99.0,
                    "isVegetarian": True,
                    "preparationTime": 10,
                    "isAvailable": True,
                }
                start = time.perf_counter()
                try:
                    response = session.post(
                        BASE_URL + "/api/menu-items",
                        json=payload,
                        headers=auth_headers(token),
                        timeout=8,
                    )
                    elapsed = (time.perf_counter() - start) * 1000.0
                    status = response.status_code
                    if response.status_code == 201:
                        try:
                            item_id = int(((response.json() or {}).get("data") or {}).get("itemID"))
                            local_item_id = item_id
                            with created_lock:
                                created_items.append(item_id)
                        except Exception:
                            pass
                except requests.RequestException:
                    elapsed = (time.perf_counter() - start) * 1000.0
                    status = 0

                record("POST /api/menu-items", status, elapsed)
                continue

            if pick < 0.90:
                status, elapsed = _req(
                    session,
                    "PUT",
                    f"/api/menu-items/{RESTAURANT_ID}/{local_item_id}",
                    token,
                    json={"name": f"StressUpdate_{int(time.time() * 1000) % 1_000_000_000}"},
                )
                record("PUT /api/menu-items/<rid>/<iid>", status, elapsed)
                continue

            status, elapsed = _req(
                session,
                "DELETE",
                f"/api/menu-items/{RESTAURANT_ID}/{local_item_id}",
                token,
            )
            record("DELETE /api/menu-items/<rid>/<iid>", status, elapsed)

        session.close()

    thread_count = min(THREADS, total_requests)
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(thread_count)]

    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed_s = max(time.perf_counter() - started, 0.0001)

    # Cleanup created records.
    with created_lock:
        cleanup_ids = list(set(created_items))
    cleanup_session = requests.Session()
    for item_id in cleanup_ids:
        try:
            cleanup_session.delete(
                BASE_URL + f"/api/menu-items/{RESTAURANT_ID}/{item_id}",
                headers=auth_headers(token),
                timeout=6,
            )
        except requests.RequestException:
            pass
    cleanup_session.close()

    avg_ms = (sum(all_times) / len(all_times)) if all_times else 0.0
    median_ms = _percentile(all_times, 0.50)
    p95_ms = _percentile(all_times, 0.95)
    error_rate = (total_errors / completed * 100.0) if completed else 0.0
    rps = completed / elapsed_s

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["endpoint", "avg_response_ms", "p95_response_ms", "error_rate_percent", "rps"])

        for endpoint, (count, errors, times) in metrics.items():
            endpoint_avg = (sum(times) / len(times)) if times else 0.0
            endpoint_p95 = _percentile(times, 0.95)
            endpoint_error = (errors / count * 100.0) if count else 0.0
            endpoint_rps = count / elapsed_s
            writer.writerow(
                [
                    endpoint,
                    round(endpoint_avg, 3),
                    round(endpoint_p95, 3),
                    round(endpoint_error, 3),
                    round(endpoint_rps, 3),
                ]
            )

    print("\nStress Summary")
    print("endpoint | count | avg_ms | p95_ms | error_% | rps")
    for endpoint, (count, errors, times) in metrics.items():
        endpoint_avg = (sum(times) / len(times)) if times else 0.0
        endpoint_p95 = _percentile(times, 0.95)
        endpoint_error = (errors / count * 100.0) if count else 0.0
        endpoint_rps = count / elapsed_s
        print(
            f"{endpoint} | {count} | {endpoint_avg:.2f} | {endpoint_p95:.2f} | {endpoint_error:.2f} | {endpoint_rps:.2f}"
        )

    print("\nOverall")
    print(f"total_requests={completed}")
    print(f"avg_response_time_ms={avg_ms:.3f}")
    print(f"median_response_time_ms={median_ms:.3f}")
    print(f"p95_response_time_ms={p95_ms:.3f}")
    print(f"error_rate_percent={error_rate:.3f}")
    print(f"requests_per_second={rps:.3f}")
    print(f"csv_saved={CSV_PATH}")

    endpoint_summary = {}
    for endpoint, (count, errors, times) in metrics.items():
        endpoint_summary[endpoint] = {
            "count": int(count),
            "errors": int(errors),
            "avgMs": round((sum(times) / len(times)) if times else 0.0, 3),
            "p95Ms": round(_percentile(times, 0.95), 3),
            "errorRatePercent": round((errors / count * 100.0) if count else 0.0, 3),
            "rps": round(count / elapsed_s, 3),
        }

    append_test_result(
        "Stress Test (threading fallback)",
        completed >= 1000,
        (
            f"total={completed}, avg_ms={avg_ms:.3f}, p95_ms={p95_ms:.3f}, median_ms={median_ms:.3f}, "
            f"error_rate={error_rate:.3f}, rps={rps:.3f}, cleaned={len(cleanup_ids)}"
        ),
        duration_ms=elapsed_s * 1000.0,
        metrics={
            "totalRequests": completed,
            "avgMs": round(avg_ms, 3),
            "medianMs": round(median_ms, 3),
            "p95Ms": round(p95_ms, 3),
            "errorRatePercent": round(error_rate, 3),
            "rps": round(rps, 3),
            "cleanedRecords": len(cleanup_ids),
            "endpointSummary": endpoint_summary,
        },
        suite="stress",
    )

    if completed == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
