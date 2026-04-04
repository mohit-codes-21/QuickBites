import json
import socket
import threading
import time

import requests

from conftest import (
    ADMIN_CREDENTIALS,
    BASE_URL,
    append_test_result,
    auth_headers,
    login_and_get_token,
)


def _print_and_log(name, passed, reason):
    tag = "PASS" if passed else "FAIL"
    print(f"[{tag}] {name}: {reason}")
    append_test_result(name, passed, reason, suite="failure")


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
        suite="failure",
    )


def _admin_find_customer_by_email(admin_token, email):
    response = requests.get(
        f"{BASE_URL}/api/admin/customers",
        headers=auth_headers(admin_token),
        timeout=10,
    )
    if response.status_code != 200:
        return None

    rows = (response.json() or {}).get("data") or []
    for row in rows:
        if row.get("email") == email:
            return row
    return None


def _admin_soft_delete_customer(admin_token, customer_id):
    requests.delete(
        f"{BASE_URL}/api/admin/customer/{customer_id}",
        headers=auth_headers(admin_token),
        timeout=10,
    )


def test_mid_transaction_failure_signup_rollback():
    started_at = time.perf_counter()
    name = "Failure Test 1 - Mid-transaction rollback"
    admin_token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)

    unique = int(time.time() * 1000)
    email = f"mid_fail_{unique}@example.com"

    # DeliveryPartner signup performs multiple writes in one transaction.
    # We force failure after early writes by omitting required deliveryPartner fields.
    payload = {
        "signupAs": "DeliveryPartner",
        "member": {
            "name": "Mid Fail User",
            "email": email,
            "password": "midFail@123",
            "phoneNumber": "9" + str(unique)[-9:],
        },
        "deliveryPartner": {
            # Deliberately incomplete to trigger server-side rollback.
            "vehicleNumber": "",
        },
    }

    resp = requests.post(f"{BASE_URL}/api/auth/signup", json=payload, timeout=10)

    # Expect failure status and verify no partial account data remains.
    row = _admin_find_customer_by_email(admin_token, email)
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "midFail@123", "loginAs": "DeliveryPartner"},
        timeout=10,
    )

    clean = (row is None) and (login_resp.status_code in (401, 403, 404))
    passed = resp.status_code in (400, 500) and clean
    reason = f"signup_status={resp.status_code}, present_in_admin={row is not None}, login_status={login_resp.status_code}"
    _print_and_log_metrics(
        name,
        passed,
        reason,
        started_at,
        {
            "signupStatus": resp.status_code,
            "presentInAdmin": row is not None,
            "loginStatus": login_resp.status_code,
        },
    )
    return passed


def test_api_timeout_simulation_no_partial_write():
    started_at = time.perf_counter()
    name = "Failure Test 2 - API timeout simulation"
    admin_token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)

    unique = int(time.time() * 1000)
    email = f"timeout_user_{unique}@example.com"

    payload = {
        "signupAs": "Member",
        "member": {
            "name": "Timeout User",
            "email": email,
            "password": "timeOut@123",
            "phoneNumber": "8" + str(unique)[-9:],
        },
    }

    timed_out = False
    try:
        requests.post(f"{BASE_URL}/api/auth/signup", json=payload, timeout=0.001)
    except requests.exceptions.Timeout:
        timed_out = True
    except requests.exceptions.RequestException:
        # Any request-layer failure here is acceptable for this simulation.
        timed_out = True

    # Give server a short window to finish if request actually reached backend.
    time.sleep(0.5)

    row = _admin_find_customer_by_email(admin_token, email)

    # No partial write means: either account does not exist, or it exists as a complete customer account.
    no_partial = True
    created_customer_id = None
    if row is not None:
        created_customer_id = row.get("customerID")
        detail = requests.get(
            f"{BASE_URL}/api/admin/customer/{created_customer_id}",
            headers=auth_headers(admin_token),
            timeout=10,
        )
        no_partial = detail.status_code == 200

    passed = timed_out and no_partial
    reason = f"timeout_caught={timed_out}, account_exists={row is not None}, no_partial={no_partial}"
    _print_and_log_metrics(
        name,
        passed,
        reason,
        started_at,
        {
            "timeoutCaught": bool(timed_out),
            "accountExists": row is not None,
            "noPartial": bool(no_partial),
        },
    )

    if created_customer_id is not None:
        _admin_soft_delete_customer(admin_token, int(created_customer_id))

    return passed


def test_forced_disconnect_mid_write():
    started_at = time.perf_counter()
    name = "Failure Test 3 - Forced disconnect mid-write"
    admin_token = login_and_get_token(BASE_URL, ADMIN_CREDENTIALS)

    unique = int(time.time() * 1000)
    email = f"disconnect_user_{unique}@example.com"

    body = {
        "signupAs": "Member",
        "member": {
            "name": "Disconnect User",
            "email": email,
            "password": "disc@123",
            "phoneNumber": "7" + str(unique)[-9:],
        },
    }
    full_json = json.dumps(body)

    parsed_host = "127.0.0.1"
    parsed_port = 5001

    done = {"sent": False, "error": None}

    def partial_sender():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(3)
            s.connect((parsed_host, parsed_port))
            # Intentionally declare a larger content-length and close early.
            req_headers = (
                "POST /api/auth/signup HTTP/1.1\r\n"
                f"Host: {parsed_host}:{parsed_port}\r\n"
                "Content-Type: application/json\r\n"
                "Connection: close\r\n"
                f"Content-Length: {len(full_json) + 200}\r\n"
                "\r\n"
            )
            partial_body = full_json[: max(1, len(full_json) // 3)]
            s.sendall((req_headers + partial_body).encode("utf-8"))
            done["sent"] = True
        except Exception as exc:
            done["error"] = str(exc)
        finally:
            try:
                s.close()
            except Exception:
                pass

    t = threading.Thread(target=partial_sender, daemon=True)
    t.start()
    t.join(timeout=2)
    time.sleep(0.5)

    row = _admin_find_customer_by_email(admin_token, email)

    passed = done["sent"] and row is None
    reason = f"sent_partial={done['sent']}, account_exists={row is not None}, sender_error={done['error']}"
    _print_and_log_metrics(
        name,
        passed,
        reason,
        started_at,
        {
            "sentPartial": bool(done["sent"]),
            "accountExists": row is not None,
            "senderError": done["error"],
        },
    )
    return passed


def main():
    started_at = time.perf_counter()
    outcomes = [
        test_mid_transaction_failure_signup_rollback(),
        test_api_timeout_simulation_no_partial_write(),
        test_forced_disconnect_mid_write(),
    ]

    passed_count = sum(1 for x in outcomes if x)
    summary_passed = passed_count == len(outcomes)
    summary_reason = f"passed={passed_count}/{len(outcomes)}"
    _print_and_log_metrics(
        "Failure Simulation Summary",
        summary_passed,
        summary_reason,
        started_at,
        {
            "passedCount": passed_count,
            "total": len(outcomes),
        },
    )

    if not summary_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
