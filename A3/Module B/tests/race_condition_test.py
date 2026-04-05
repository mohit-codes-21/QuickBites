import threading
import time
from datetime import datetime

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


DELIVERY_PARTNER_CREDENTIALS = [
    {"email": "driver1@example.com", "password": "drv1", "loginAs": "DeliveryPartner"},
    {"email": "driver2@example.com", "password": "drv2", "loginAs": "DeliveryPartner"},
    {"email": "driver3@example.com", "password": "drv3", "loginAs": "DeliveryPartner"},
    {"email": "driver4@example.com", "password": "drv4", "loginAs": "DeliveryPartner"},
    {"email": "driver5@example.com", "password": "drv5", "loginAs": "DeliveryPartner"},
    {"email": "driver6@example.com", "password": "drv6", "loginAs": "DeliveryPartner"},
    {"email": "driver7@example.com", "password": "drv7", "loginAs": "DeliveryPartner"},
    {"email": "driver8@example.com", "password": "drv8", "loginAs": "DeliveryPartner"},
    {"email": "driver9@example.com", "password": "drv9", "loginAs": "DeliveryPartner"},
    {"email": "driver10@example.com", "password": "drv10", "loginAs": "DeliveryPartner"},
]


def _print_and_log(name, passed, reason):
    tag = "PASS" if passed else "FAIL"
    print(f"[{tag}] {name}: {reason}")
    append_test_result(name, passed, reason, suite="race")


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
        suite="race",
    )


def _cleanup_created_member(member_id):
    if member_id is None:
        return
    token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)
    requests.delete(
        f"{BASE_URL}/api/admin/customer/{member_id}",
        headers=auth_headers(token),
        timeout=10,
    )


def run_signup_race(thread_count=50):
    started_at = time.perf_counter()
    test_name = "Race Condition - 50 concurrent signup attempts"

    # Critical write operation: account creation.
    # The backend is expected to enforce transactional integrity and unique-email consistency.
    unique = int(time.time() * 1000)
    email = f"race_user_{unique}@example.com"
    phone = "8" + str(unique)[-9:]
    payload = {
        "signupAs": "Member",
        "member": {
            "name": "Race User",
            "email": email,
            "password": "racePwd@123",
            "phoneNumber": phone,
        },
    }

    barrier = threading.Barrier(thread_count)
    responses = []
    lock = threading.Lock()

    def worker():
        status = 0
        body = None
        last_error = None

        try:
            barrier.wait()
        except Exception:
            pass

        # Retry once to avoid marking transient transport timeouts as race failures.
        for _ in range(2):
            try:
                resp = requests.post(
                    f"{BASE_URL}/api/auth/signup",
                    json=payload,
                    timeout=20,
                )
                status = resp.status_code
                try:
                    body = resp.json()
                except Exception:
                    body = None
                break
            except requests.RequestException as exc:
                status = 0
                body = None
                last_error = str(exc)
                time.sleep(0.05)

        if status == 0 and last_error:
            body = {"transportError": last_error}

        with lock:
            responses.append((status, body))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [(s, b) for s, b in responses if s == 201]
    rollbacks = [(s, b) for s, b in responses if s in (400, 409, 500)]
    network_failures = [(s, b) for s, b in responses if s == 0]

    created_member_id = None
    if successes:
        first_payload = (successes[0][1] or {}).get("data") or {}
        created_member_id = first_payload.get("memberID")

    # Verify final state through HTTP only.
    admin_token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)
    customers_resp = requests.get(
        f"{BASE_URL}/api/admin/customers",
        headers=auth_headers(admin_token),
        timeout=10,
    )

    matching_rows = 0
    if customers_resp.status_code == 200:
        rows = (customers_resp.json() or {}).get("data") or []
        matching = [row for row in rows if row.get("email") == email and int(row.get("isDeleted", 0)) == 0]
        matching_rows = len(matching)
        if created_member_id is None and matching_rows == 1:
            created_member_id = matching[0].get("customerID")

    # Race invariant: at most one success response and exactly one active row in final state.
    passed = len(successes) <= 1 and matching_rows == 1
    reason = (
        f"success={len(successes)}, rolled_back={len(rollbacks)}, "
        f"network_failures={len(network_failures)}, final_active_rows={matching_rows}"
    )

    _print_and_log_metrics(
        test_name,
        passed,
        reason,
        started_at,
        {
            "threadCount": thread_count,
            "successCount": len(successes),
            "rolledBackCount": len(rollbacks),
            "networkFailures": len(network_failures),
            "finalActiveRows": matching_rows,
        },
    )

    _cleanup_created_member(created_member_id)

    return passed


def _ensure_selected_address(customer_token):
    response = requests.get(
        f"{BASE_URL}/api/customer/addresses",
        headers=auth_headers(customer_token),
        timeout=10,
    )
    if response.status_code != 200:
        return False

    rows = (response.json() or {}).get("data") or []
    if any(int(row.get("isSaved", 0)) == 1 for row in rows):
        return True

    create_resp = requests.post(
        f"{BASE_URL}/api/customer/addresses",
        headers=auth_headers(customer_token),
        json={
            "addressLine": "Race Test Address",
            "city": "Ahmedabad",
            "zipCode": "380015",
            "label": "Race",
            "latitude": 23.03,
            "longitude": 72.52,
            "selected": True,
        },
        timeout=10,
    )
    return create_resp.status_code in (200, 201)


def run_delivery_acceptance_race(thread_count=10):
    started_at = time.perf_counter()
    test_name = "Race Condition - concurrent delivery acceptance"
    temp = create_temp_menu_record(BASE_URL, RESTAURANT_CREDENTIALS)
    customer_token = login_and_get_token(BASE_URL, REGULAR_USER_CREDENTIALS)

    order_id = None
    try:
        def fail_return(reason, metrics=None):
            _print_and_log_metrics(
                test_name,
                False,
                reason,
                started_at,
                metrics or {},
            )
            return False

        requests.delete(
            f"{BASE_URL}/api/customer/cart",
            headers=auth_headers(customer_token),
            timeout=10,
        )

        if not _ensure_selected_address(customer_token):
            return fail_return("could_not_prepare_selected_address", {"threadCount": thread_count})

        add_resp = requests.put(
            f"{BASE_URL}/api/customer/cart/item",
            headers=auth_headers(customer_token),
            json={"restaurantID": temp["restaurantID"], "itemID": temp["itemID"], "quantityDelta": 1},
            timeout=10,
        )
        if add_resp.status_code != 200:
            return fail_return(
                f"add_to_cart_status={add_resp.status_code}",
                {"threadCount": thread_count, "addToCartStatus": add_resp.status_code},
            )

        pay_resp = requests.post(
            f"{BASE_URL}/api/customer/cart/payment-demo",
            headers=auth_headers(customer_token),
            json={"status": "successful", "paymentMode": "online", "specialInstruction": "race-test"},
            timeout=15,
        )
        if pay_resp.status_code != 200:
            return fail_return(
                f"payment_demo_status={pay_resp.status_code}",
                {"threadCount": thread_count, "paymentDemoStatus": pay_resp.status_code},
            )

        orders_resp = requests.get(
            f"{BASE_URL}/api/customer/profile/orders",
            headers=auth_headers(customer_token),
            timeout=10,
        )
        if orders_resp.status_code != 200:
            return fail_return(
                f"customer_orders_status={orders_resp.status_code}",
                {"threadCount": thread_count, "customerOrdersStatus": orders_resp.status_code},
            )

        orders = (orders_resp.json() or {}).get("data") or []
        for entry in orders:
            items = entry.get("items") or []
            for item in items:
                if int(item.get("itemID", -1)) == int(temp["itemID"]):
                    order_id = int(entry["orderID"])
                    break
            if order_id is not None:
                break

        if order_id is None:
            return fail_return("order_not_found_after_checkout", {"threadCount": thread_count})

        to_preparing = requests.put(
            f"{BASE_URL}/api/restaurant/orders/{order_id}/status",
            headers=auth_headers(temp["token"]),
            json={"orderStatus": "Preparing"},
            timeout=10,
        )
        to_ready = requests.put(
            f"{BASE_URL}/api/restaurant/orders/{order_id}/status",
            headers=auth_headers(temp["token"]),
            json={"orderStatus": "ReadyForPickup"},
            timeout=10,
        )

        if to_preparing.status_code != 200 or to_ready.status_code != 200:
            return fail_return(
                f"status_prep={to_preparing.status_code}, status_ready={to_ready.status_code}",
                {
                    "threadCount": thread_count,
                    "prepStatus": to_preparing.status_code,
                    "readyStatus": to_ready.status_code,
                },
            )

        contenders = DELIVERY_PARTNER_CREDENTIALS[: max(2, min(thread_count, len(DELIVERY_PARTNER_CREDENTIALS)))]
        barrier = threading.Barrier(len(contenders))
        statuses = []
        lock = threading.Lock()

        def worker(credentials):
            status = 0
            try:
                token = login_and_get_token(BASE_URL, credentials)
                barrier.wait()
                resp = requests.post(
                    f"{BASE_URL}/api/delivery/orders/{order_id}/accept",
                    headers=auth_headers(token),
                    timeout=12,
                )
                status = resp.status_code
            except Exception:
                status = 0

            with lock:
                statuses.append(status)

        threads = [threading.Thread(target=worker, args=(cred,), daemon=True) for cred in contenders]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        success_count = sum(1 for status in statuses if status == 200)
        network_failures = sum(1 for status in statuses if status == 0)

        restaurant_orders_resp = requests.get(
            f"{BASE_URL}/api/restaurant/orders",
            headers=auth_headers(temp["token"]),
            timeout=10,
        )

        rows_for_order = 0
        if restaurant_orders_resp.status_code == 200:
            payload = (restaurant_orders_resp.json() or {}).get("data") or {}
            rows = payload.get("orders") or []
            rows_for_order = sum(1 for row in rows if int(row.get("orderID", -1)) == int(order_id))

        passed = success_count == 1 and rows_for_order == 1 and network_failures == 0
        reason = (
            f"success={success_count}, contenders={len(contenders)}, "
            f"rows_for_order={rows_for_order}, network_failures={network_failures}"
        )
        _print_and_log_metrics(
            test_name,
            passed,
            reason,
            started_at,
            {
                "threadCount": thread_count,
                "contenders": len(contenders),
                "successCount": success_count,
                "networkFailures": network_failures,
                "rowsForOrder": rows_for_order,
                "orderID": order_id,
            },
        )
        return passed
    finally:
        try:
            requests.delete(
                f"{BASE_URL}/api/customer/cart",
                headers=auth_headers(customer_token),
                timeout=10,
            )
        except Exception:
            pass

        delete_temp_menu_record(BASE_URL, temp["token"], temp["restaurantID"], temp["itemID"])


def main():
    ok = run_signup_race(thread_count=50)
    ok = run_delivery_acceptance_race(thread_count=10) and ok
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
