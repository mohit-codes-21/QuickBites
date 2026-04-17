import os
import socket
import subprocess
import threading
import time

import mysql.connector
import requests

from conftest import (
    ADMIN_CREDENTIALS,
    RESTAURANT_CREDENTIALS,
    append_test_result,
    auth_headers,
    create_temp_menu_record,
    delete_temp_menu_record,
    login_and_get_token,
)


TEST_PORT = int(os.getenv("QB_ACID_SERVER_PORT", "5002"))
BASE_URL = os.getenv("QB_ACID_BASE_URL", f"http://127.0.0.1:{TEST_PORT}").rstrip("/")
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
PYTHON_BIN = os.getenv("QB_PYTHON_BIN", os.sys.executable)

DB_CONFIG = {
    "host": os.getenv("QB_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("QB_DB_PORT", "3306")),
    "user": os.getenv("QB_DB_USER", "qb_admin"),
    "password": os.getenv("QB_DB_PASSWORD", "qb_admin@123"),
    "database": os.getenv("QB_DB_NAME", "QB"),
}


class ServerManager:
    def __init__(self, port):
        self.port = port
        self.proc = None

    def start(self):
        cmd = [
            PYTHON_BIN,
            "-c",
            (
                "from app import app; "
                f"app.run(host='127.0.0.1', port={self.port}, debug=False, use_reloader=False)"
            ),
        ]
        self.proc = subprocess.Popen(
            cmd,
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        deadline = time.time() + 12
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("Managed Flask server failed to start")
            try:
                r = requests.get(f"http://127.0.0.1:{self.port}/api/auth/me", timeout=0.5)
                if r.status_code in (401, 403):
                    return
            except requests.RequestException:
                pass
            time.sleep(0.2)

        raise RuntimeError("Managed Flask server did not become ready in time")

    def stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)

    def restart(self):
        self.stop()
        self.start()


def _report(name, passed, reason, started_at=None, metrics=None):
    status = "PASS" if passed else "FAIL"
    duration_ms = None
    if started_at is not None:
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        print(f"[{status}] {name}: {reason} | duration_ms={duration_ms:.2f}")
    else:
        print(f"[{status}] {name}: {reason}")
    append_test_result(
        f"ACID {name}",
        passed,
        reason,
        duration_ms=duration_ms,
        metrics=metrics or {},
        suite="acid",
    )


def test_atomicity(base_url):
    started_at = time.perf_counter()
    name = "Atomicity"
    admin_token = login_and_get_token(base_url, ADMIN_CREDENTIALS)

    unique = int(time.time() * 1000)
    email = f"acid_atomic_{unique}@example.com"

    # Multi-step transactional flow in API: Member + role + delivery profile.
    # Trigger failure halfway by sending invalid delivery payload.
    payload = {
        "signupAs": "DeliveryPartner",
        "member": {
            "name": "Acid Atomic",
            "email": email,
            "password": "acidAtomic@123",
            "phoneNumber": "9" + str(unique)[-9:],
        },
        "deliveryPartner": {
            "vehicleNumber": "",
        },
    }
    response = requests.post(f"{base_url}/api/auth/signup", json=payload, timeout=10)

    # Verify via GET that nothing is visible.
    list_resp = requests.get(
        f"{base_url}/api/admin/customers",
        headers=auth_headers(admin_token),
        timeout=10,
    )
    found = False
    if list_resp.status_code == 200:
        rows = (list_resp.json() or {}).get("data") or []
        found = any(row.get("email") == email and int(row.get("isDeleted", 0)) == 0 for row in rows)

    passed = response.status_code in (400, 500) and not found
    reason = f"signup_status={response.status_code}, visible_after_failure={found}"
    _report(
        name,
        passed,
        reason,
        started_at=started_at,
        metrics={
            "signupStatus": response.status_code,
            "visibleAfterFailure": bool(found),
        },
    )
    return passed


def test_consistency(base_url):
    started_at = time.perf_counter()
    name = "Consistency"

    # Run a series of writes via API.
    temp = create_temp_menu_record(base_url, RESTAURANT_CREDENTIALS)
    token = temp["token"]
    rid = temp["restaurantID"]
    iid = temp["itemID"]

    try:
        requests.put(
            f"{base_url}/api/menu-items/{rid}/{iid}",
            json={"name": "ACID_Consistency_Update"},
            headers=auth_headers(token),
            timeout=10,
        )
        requests.delete(
            f"{base_url}/api/menu-items/{rid}/{iid}",
            headers=auth_headers(token),
            timeout=10,
        )
        requests.post(
            f"{base_url}/api/menu-items/{rid}/{iid}/restore",
            headers=auth_headers(token),
            timeout=10,
        )

        # Direct DB integrity check allowed in this stage.
        conn = mysql.connector.connect(**DB_CONFIG)
        try:
            cur = conn.cursor(dictionary=True)
            checks = {}

            cur.execute(
                """
                SELECT COUNT(*) AS c
                FROM Orders o
                LEFT JOIN Payment p ON p.paymentID = o.paymentID
                WHERE p.paymentID IS NULL
                """
            )
            checks["orphan_orders"] = int(cur.fetchone()["c"])

            cur.execute(
                """
                SELECT COUNT(*) AS c
                FROM OrderItem oi
                LEFT JOIN Orders o ON o.orderID = oi.orderID
                WHERE o.orderID IS NULL
                """
            )
            checks["orphan_order_items"] = int(cur.fetchone()["c"])

            cur.execute(
                """
                SELECT COUNT(*) AS c
                FROM Customer c
                LEFT JOIN Member m ON m.memberID = c.customerID
                WHERE m.memberID IS NULL
                """
            )
            checks["orphan_customers"] = int(cur.fetchone()["c"])

            cur.execute(
                """
                SELECT COUNT(*) AS c
                FROM Member
                WHERE name IS NULL OR email IS NULL OR password IS NULL OR phoneNumber IS NULL
                """
            )
            checks["null_member_criticals"] = int(cur.fetchone()["c"])
        finally:
            conn.close()

        passed = all(v == 0 for v in checks.values())
        reason = ", ".join([f"{k}={v}" for k, v in checks.items()])
        _report(name, passed, reason, started_at=started_at, metrics=checks)
        return passed
    finally:
        delete_temp_menu_record(base_url, token, rid, iid)


def test_isolation(base_url):
    started_at = time.perf_counter()
    name = "Isolation"
    admin_token = login_and_get_token(base_url, ADMIN_CREDENTIALS)

    unique = int(time.time() * 1000)
    email = f"acid_isolation_{unique}@example.com"

    started = threading.Event()
    release = threading.Event()

    def thread_a_partial_write():
        # Keep request body incomplete to hold server-side request processing window.
        body = (
            '{"signupAs":"Member","member":{'
            f'"name":"Iso User","email":"{email}","password":"iso@123","phoneNumber":"7{str(unique)[-9:]}"'
            "}}"
        )

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(4)
            s.connect(("127.0.0.1", TEST_PORT))
            headers = (
                "POST /api/auth/signup HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{TEST_PORT}\r\n"
                "Content-Type: application/json\r\n"
                "Connection: close\r\n"
                f"Content-Length: {len(body) + 200}\r\n"
                "\r\n"
            )
            partial = body[: max(1, len(body) // 2)]
            s.sendall((headers + partial).encode("utf-8"))
            started.set()
            release.wait(timeout=2)
        finally:
            try:
                s.close()
            except Exception:
                pass

    t = threading.Thread(target=thread_a_partial_write, daemon=True)
    t.start()

    started.wait(timeout=2)

    # Concurrent reader should not observe uncommitted/partial write.
    read_resp = requests.get(
        f"{base_url}/api/admin/customers",
        headers=auth_headers(admin_token),
        timeout=10,
    )

    seen = False
    if read_resp.status_code == 200:
        rows = (read_resp.json() or {}).get("data") or []
        seen = any(row.get("email") == email for row in rows)

    release.set()
    t.join(timeout=3)

    # After disconnect, still should not exist.
    read_resp2 = requests.get(
        f"{base_url}/api/admin/customers",
        headers=auth_headers(admin_token),
        timeout=10,
    )
    seen_after = False
    if read_resp2.status_code == 200:
        rows2 = (read_resp2.json() or {}).get("data") or []
        seen_after = any(row.get("email") == email for row in rows2)

    passed = (not seen) and (not seen_after)
    reason = f"seen_during_partial={seen}, seen_after_disconnect={seen_after}"
    _report(
        name,
        passed,
        reason,
        started_at=started_at,
        metrics={
            "seenDuringPartial": bool(seen),
            "seenAfterDisconnect": bool(seen_after),
        },
    )
    return passed


def test_durability(base_url, server_manager):
    started_at = time.perf_counter()
    name = "Durability"

    temp = create_temp_menu_record(base_url, RESTAURANT_CREDENTIALS)
    rid = temp["restaurantID"]
    iid = temp["itemID"]
    record_name = temp["name"]
    token = temp["token"]

    created_ok = rid is not None and iid is not None
    if not created_ok:
        _report(name, False, "create_record_failed", started_at=started_at, metrics={"createOk": False})
        return False

    # Restart Flask server process programmatically.
    server_manager.restart()

    # Re-login and verify record still exists after restart.
    admin_token = login_and_get_token(base_url, ADMIN_CREDENTIALS)
    get_resp = requests.get(
        f"{base_url}/api/menu-items",
        params={"restaurantID": rid, "includeDiscontinued": "true", "search": record_name},
        headers=auth_headers(admin_token),
        timeout=10,
    )

    exists_after_restart = False
    if get_resp.status_code == 200:
        items = (get_resp.json() or {}).get("data") or []
        exists_after_restart = any(item.get("itemID") == iid for item in items)

    # Cleanup.
    try:
        new_token = login_and_get_token(base_url, RESTAURANT_CREDENTIALS)
    except Exception:
        new_token = token
    delete_temp_menu_record(base_url, new_token, rid, iid)

    passed = exists_after_restart
    reason = f"create_ok={created_ok}, exists_after_restart={exists_after_restart}, get_status={get_resp.status_code}"
    _report(
        name,
        passed,
        reason,
        started_at=started_at,
        metrics={
            "createOk": bool(created_ok),
            "existsAfterRestart": bool(exists_after_restart),
            "getStatus": get_resp.status_code,
        },
    )
    return passed


def main():
    started_at = time.perf_counter()
    server_manager = ServerManager(TEST_PORT)
    server_manager.start()

    try:
        results = [
            ("Atomicity", test_atomicity(BASE_URL)),
            ("Consistency", test_consistency(BASE_URL)),
            ("Isolation", test_isolation(BASE_URL)),
            ("Durability", test_durability(BASE_URL, server_manager)),
        ]

        print("\nACID Summary")
        print("Property | Result")
        for prop, ok in results:
            print(f"{prop} | {'PASS' if ok else 'FAIL'}")

        pass_count = sum(1 for _, ok in results if ok)
        overall = pass_count == len(results)
        summary_reason = f"passed={pass_count}/{len(results)}"
        _report(
            "Summary",
            overall,
            summary_reason,
            started_at=started_at,
            metrics={"passedCount": pass_count, "total": len(results)},
        )

        if not overall:
            raise SystemExit(1)
    finally:
        server_manager.stop()


if __name__ == "__main__":
    main()
