import threading
import time

import requests

from conftest import (
    ADMIN_CREDENTIALS,
    BASE_URL,
    REGULAR_USER_CREDENTIALS,
    RESTAURANT_CREDENTIALS,
    append_test_result,
    auth_headers,
    create_temp_menu_record,
    delete_temp_menu_record,
    login_and_get_token,
)


def _print_and_log(name, passed, reason):
    tag = "PASS" if passed else "FAIL"
    print(f"[{tag}] {name}: {reason}")
    append_test_result(name, passed, reason, suite="concurrent")


def _print_and_log_metrics(name, passed, reason, started_at, metrics):
    duration_ms = (time.perf_counter() - started_at) * 1000.0
    tag = "PASS" if passed else "FAIL"
    print(f"[{tag}] {name}: {reason} | duration_ms={duration_ms:.2f}")
    append_test_result(
        name,
        passed,
        reason,
        duration_ms=duration_ms,
        metrics=metrics,
        suite="concurrent",
    )


def scenario_parallel_reads(thread_count=15):
    started_at = time.perf_counter()
    name = "Concurrent Scenario 1 - 15 parallel reads"
    temp = create_temp_menu_record(BASE_URL, RESTAURANT_CREDENTIALS)

    try:
        admin_token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)
        barrier = threading.Barrier(thread_count)
        results = []
        lock = threading.Lock()

        def worker():
            try:
                barrier.wait()
                response = requests.get(
                    f"{BASE_URL}/api/menu-items",
                    params={
                        "restaurantID": temp["restaurantID"],
                        "includeDiscontinued": "true",
                        "search": temp["name"],
                    },
                    headers=auth_headers(admin_token),
                    timeout=10,
                )
                if response.status_code != 200:
                    out = (False, f"status={response.status_code}")
                else:
                    payload = response.json()
                    items = (payload.get("data") or []) if isinstance(payload, dict) else []
                    found = [x for x in items if x.get("itemID") == temp["itemID"]]
                    out = (len(found) == 1, f"matched={len(found)}")
            except Exception as exc:
                out = (False, f"exception={exc}")

            with lock:
                results.append(out)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success = sum(1 for ok, _ in results if ok)
        passed = success == thread_count
        reason = f"successful_reads={success}/{thread_count}"
        _print_and_log_metrics(
            name,
            passed,
            reason,
            started_at,
            {
                "threadCount": thread_count,
                "successfulReads": success,
                "failedReads": thread_count - success,
            },
        )
        return passed
    finally:
        delete_temp_menu_record(BASE_URL, temp["token"], temp["restaurantID"], temp["itemID"])


def scenario_parallel_updates(thread_count=15):
    started_at = time.perf_counter()
    name = "Concurrent Scenario 2 - 15 parallel updates"
    temp = create_temp_menu_record(BASE_URL, RESTAURANT_CREDENTIALS)

    try:
        restaurant_token = temp["token"]
        admin_token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)

        barrier = threading.Barrier(thread_count)
        statuses = []
        attempted_names = set()
        lock = threading.Lock()

        def worker(index):
            new_name = f"Temp_Update_{temp['itemID']}_{index}"
            try:
                barrier.wait()
                response = requests.put(
                    f"{BASE_URL}/api/menu-items/{temp['restaurantID']}/{temp['itemID']}",
                    json={"name": new_name},
                    headers=auth_headers(restaurant_token),
                    timeout=10,
                )
                with lock:
                    attempted_names.add(new_name)
                    statuses.append(response.status_code)
            except Exception:
                with lock:
                    statuses.append(0)

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        read_response = requests.get(
            f"{BASE_URL}/api/menu-items",
            params={
                "restaurantID": temp["restaurantID"],
                "includeDiscontinued": "true",
            },
            headers=auth_headers(admin_token),
            timeout=10,
        )

        final_name = None
        if read_response.status_code == 200:
            payload = read_response.json()
            items = (payload.get("data") or []) if isinstance(payload, dict) else []
            match = next((x for x in items if x.get("itemID") == temp["itemID"]), None)
            final_name = match.get("name") if match else None

        all_ok = all(code == 200 for code in statuses)
        final_valid = final_name in attempted_names
        passed = all_ok and final_valid
        ok_count = sum(1 for x in statuses if x == 200)
        reason = f"updates_ok={sum(1 for x in statuses if x == 200)}/{thread_count}, final_name={final_name}"
        _print_and_log_metrics(
            name,
            passed,
            reason,
            started_at,
            {
                "threadCount": thread_count,
                "successfulUpdates": ok_count,
                "failedUpdates": thread_count - ok_count,
                "finalName": final_name,
            },
        )
        return passed
    finally:
        delete_temp_menu_record(BASE_URL, temp["token"], temp["restaurantID"], temp["itemID"])


def scenario_delete_while_reading(thread_count=15):
    started_at = time.perf_counter()
    name = "Concurrent Scenario 3 - delete while readers run"
    temp = create_temp_menu_record(BASE_URL, RESTAURANT_CREDENTIALS)

    try:
        admin_token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)
        reader_count = thread_count - 1
        start_evt = threading.Event()
        done_evt = threading.Event()

        outcomes = []
        lock = threading.Lock()

        def reader():
            try:
                start_evt.wait(timeout=5)
                response = requests.get(
                    f"{BASE_URL}/api/menu-items",
                    params={
                        "restaurantID": temp["restaurantID"],
                        "search": temp["name"],
                    },
                    headers=auth_headers(admin_token),
                    timeout=10,
                )

                if response.status_code != 200:
                    result = (False, f"status={response.status_code}")
                else:
                    payload = response.json()
                    items = (payload.get("data") or []) if isinstance(payload, dict) else []
                    # This API uses list semantics; deleted record disappears from list (404-equivalent).
                    result = (True, f"visible_count={len(items)}")
            except Exception as exc:
                result = (False, f"exception={exc}")

            with lock:
                outcomes.append(result)

        def deleter():
            start_evt.wait(timeout=5)
            time.sleep(0.05)
            response = requests.delete(
                f"{BASE_URL}/api/menu-items/{temp['restaurantID']}/{temp['itemID']}",
                headers=auth_headers(temp["token"]),
                timeout=10,
            )
            with lock:
                outcomes.append((response.status_code == 200, f"delete_status={response.status_code}"))
            done_evt.set()

        readers = [threading.Thread(target=reader, daemon=True) for _ in range(reader_count)]
        for t in readers:
            t.start()

        deleter_thread = threading.Thread(target=deleter, daemon=True)
        deleter_thread.start()

        start_evt.set()
        for t in readers:
            t.join()
        deleter_thread.join()
        done_evt.wait(timeout=2)

        read_ok = all(ok for ok, msg in outcomes[:-1] if "visible_count" in msg or "status=" in msg or "exception=" in msg)
        delete_ok = outcomes and outcomes[-1][0]

        # Confirm delete effect by checking item disappears from non-discontinued view.
        post = requests.get(
            f"{BASE_URL}/api/menu-items",
            params={"restaurantID": temp["restaurantID"], "search": temp["name"]},
            headers=auth_headers(admin_token),
            timeout=10,
        )
        post_items = []
        if post.status_code == 200:
            payload = post.json()
            post_items = (payload.get("data") or []) if isinstance(payload, dict) else []
        deleted_from_view = len(post_items) == 0

        passed = read_ok and delete_ok and deleted_from_view
        reason = f"readers={reader_count}, delete_ok={delete_ok}, post_visible={len(post_items)}"
        _print_and_log_metrics(
            name,
            passed,
            reason,
            started_at,
            {
                "threadCount": thread_count,
                "readerCount": reader_count,
                "deleteOk": bool(delete_ok),
                "postVisibleCount": len(post_items),
            },
        )
        return passed
    finally:
        # Best-effort cleanup for repeatability.
        requests.post(
            f"{BASE_URL}/api/menu-items/{temp['restaurantID']}/{temp['itemID']}/restore",
            headers=auth_headers(temp["token"]),
            timeout=10,
        )
        delete_temp_menu_record(BASE_URL, temp["token"], temp["restaurantID"], temp["itemID"])


def scenario_parallel_cart_same_item(thread_count=25):
    started_at = time.perf_counter()
    name = "Concurrent Scenario 4 - same cart item contention"
    temp = create_temp_menu_record(BASE_URL, RESTAURANT_CREDENTIALS)

    try:
        customer_token = login_and_get_token(BASE_URL, REGULAR_USER_CREDENTIALS)

        # Start from a known empty-cart baseline.
        requests.delete(
            f"{BASE_URL}/api/customer/cart",
            headers=auth_headers(customer_token),
            timeout=10,
        )

        barrier = threading.Barrier(thread_count)
        statuses = []
        lock = threading.Lock()

        def worker():
            try:
                barrier.wait()
                response = requests.put(
                    f"{BASE_URL}/api/customer/cart/item",
                    json={
                        "restaurantID": temp["restaurantID"],
                        "itemID": temp["itemID"],
                        "quantityDelta": 1,
                    },
                    headers=auth_headers(customer_token),
                    timeout=10,
                )
                status = response.status_code
            except Exception:
                status = 0

            with lock:
                statuses.append(status)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        read_response = requests.get(
            f"{BASE_URL}/api/customer/cart",
            headers=auth_headers(customer_token),
            timeout=10,
        )

        final_quantity = 0
        if read_response.status_code == 200:
            payload = read_response.json() if read_response.content else {}
            cart = (payload.get("data") or {}) if isinstance(payload, dict) else {}
            items = cart.get("items") or []
            for row in items:
                if int(row.get("restaurantID", -1)) == int(temp["restaurantID"]) and int(row.get("itemID", -1)) == int(temp["itemID"]):
                    final_quantity = int(row.get("quantity", 0) or 0)
                    break

        all_ok = all(code == 200 for code in statuses)
        passed = all_ok and final_quantity == thread_count
        ok_count = sum(1 for code in statuses if code == 200)
        reason = (
            f"updates_ok={ok_count}/{thread_count}, "
            f"final_quantity={final_quantity}"
        )
        _print_and_log_metrics(
            name,
            passed,
            reason,
            started_at,
            {
                "threadCount": thread_count,
                "successfulUpdates": ok_count,
                "failedUpdates": thread_count - ok_count,
                "finalQuantity": final_quantity,
            },
        )
        return passed
    finally:
        try:
            customer_token = login_and_get_token(BASE_URL, REGULAR_USER_CREDENTIALS)
            requests.delete(
                f"{BASE_URL}/api/customer/cart",
                headers=auth_headers(customer_token),
                timeout=10,
            )
        except Exception:
            pass

        delete_temp_menu_record(BASE_URL, temp["token"], temp["restaurantID"], temp["itemID"])


def main():
    scenarios = [
        scenario_parallel_reads,
        scenario_parallel_updates,
        scenario_delete_while_reading,
        scenario_parallel_cart_same_item,
    ]

    all_passed = True
    for fn in scenarios:
        all_passed = fn() and all_passed

    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
