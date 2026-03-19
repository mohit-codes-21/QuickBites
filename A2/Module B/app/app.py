import json
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps

import bcrypt
import mysql.connector
from flask import Flask, jsonify, render_template, request
from mysql.connector import Error


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "logs"))
LOG_FILE_PATH = os.path.join(LOG_DIR, "audit.log")
ACTIVITY_LOG_FILE_PATH = os.path.join(LOG_DIR, "activity.log")

app = Flask(__name__)


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("QB_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("QB_DB_PORT", "3306")),
        user=os.getenv("QB_DB_USER", "qb_admin"), # qb_admin
        password=os.getenv("QB_DB_PASSWORD", "qb_admin@123"), # qb_admin@123
        database=os.getenv("QB_DB_NAME", "QB"),
    )


def json_response(data=None, status=200, message=None):
    payload = {}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def write_audit_log(connection, member_id, action, table_name, record_id, details):
    os.makedirs(LOG_DIR, exist_ok=True)

    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "memberID": member_id,
        "action": action,
        "tableName": table_name,
        "recordID": record_id,
        "details": details,
        "path": request.path,
        "method": request.method,
        "ip": request.remote_addr,
    }

    with open(LOG_FILE_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(log_entry) + "\n")

    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO AuditLog(memberID, action, tableName, recordID, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (member_id, action, table_name, str(record_id), json.dumps(details)),
    )


def write_activity_log(event_type, details):
    os.makedirs(LOG_DIR, exist_ok=True)
    activity_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": event_type,
        "details": details,
    }
    with open(ACTIVITY_LOG_FILE_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(activity_entry) + "\n")


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_and_migrate_password(connection, member_id, raw_password, stored_password):
    # Support existing plaintext seeds and transparently upgrade to bcrypt.
    if stored_password.startswith("$2a$") or stored_password.startswith("$2b$") or stored_password.startswith("$2y$"):
        return bcrypt.checkpw(raw_password.encode("utf-8"), stored_password.encode("utf-8"))

    if raw_password != stored_password:
        return False

    upgraded = hash_password(raw_password)
    cursor = connection.cursor()
    cursor.execute("UPDATE Member SET password = %s WHERE memberID = %s", (upgraded, member_id))
    connection.commit()
    return True


def get_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header[7:].strip()


def get_current_user(connection):
    token = get_bearer_token()
    if not token:
        return None

    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT s.sessionToken, s.memberID, s.expiresAt, m.name, m.email
        FROM Sessions s
        JOIN Member m ON m.memberID = s.memberID
        WHERE s.sessionToken = %s AND s.expiresAt > NOW() AND m.isDeleted = 0
        """,
        (token,),
    )
    user = cursor.fetchone()
    if not user:
        return None

    cursor.execute(
        """
        SELECT r.roleName
        FROM MemberRoleMapping mg
        JOIN Roles r ON r.roleID = mg.roleID
        WHERE mg.memberID = %s
        """,
        (user["memberID"],),
    )
    user["roles"] = [row["roleName"] for row in cursor.fetchall()]
    user["sessionToken"] = token
    return user


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        connection = None
        try:
            connection = get_db_connection()
            user = get_current_user(connection)
            if not user:
                return json_response(status=401, message="Unauthorized")

            request.current_user = user
            request.db_connection = connection
            return fn(*args, **kwargs)
        except Error as exc:
            return json_response(status=500, message=f"Database error: {exc}")
        finally:
            if connection and connection.is_connected() and not getattr(request, "db_connection", None):
                connection.close()

    return wrapper


def require_roles(*roles):
    def decorator(fn):
        @wraps(fn)
        @require_auth
        def wrapper(*args, **kwargs):
            user_roles = set(request.current_user.get("roles", []))
            if not user_roles.intersection(set(roles)):
                conn = request.db_connection
                request.db_connection = None
                conn.close()
                return json_response(status=403, message="Forbidden")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def close_request_connection():
    conn = getattr(request, "db_connection", None)
    if conn and conn.is_connected():
        conn.close()
        request.db_connection = None


def get_restaurant_by_member_email(connection, member_email):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT restaurantID, name, contactPhone, email, isOpen, isVerified, averageRating,
               addressLine, city, zipCode, latitude, longitude, discontinued
        FROM Restaurant
        WHERE email = %s AND isDeleted = 0
        LIMIT 1
        """,
        (member_email,),
    )
    return cursor.fetchone()


def calculate_customer_cart_total(connection, customer_id):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT COALESCE(SUM(ci.quantity * mi.appPrice), 0) AS total
        FROM CartItem ci
        JOIN MenuItem mi ON mi.restaurantID = ci.restaurantID AND mi.itemID = ci.itemID
        WHERE ci.customerID = %s
        """,
        (customer_id,),
    )
    return float(cursor.fetchone()["total"])


def update_customer_cart_total(connection, customer_id):
    total = calculate_customer_cart_total(connection, customer_id)
    cursor = connection.cursor()
    cursor.execute("UPDATE Customer SET cartTotalAmount = %s WHERE customerID = %s", (total, customer_id))
    return total


def get_selected_address_id(connection, customer_id):
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT addressID
        FROM Address
        WHERE customerID = %s AND isSaved = 1
        ORDER BY addressID
        LIMIT 1
        """,
        (customer_id,),
    )
    row = cursor.fetchone()
    return row["addressID"] if row else None


def expire_pending_order_payments(connection, customer_id=None):
    cursor = connection.cursor()
    if customer_id is None:
        cursor.execute(
            """
            UPDATE Payment
            SET status = 'Failed'
            WHERE paymentFor = 'Order'
              AND status = 'Pending'
              AND transactionTime <= (NOW() - INTERVAL 2 MINUTE)
            """
        )
    else:
        cursor.execute(
            """
            UPDATE Payment
            SET status = 'Failed'
            WHERE paymentFor = 'Order'
              AND status = 'Pending'
              AND customerID = %s
              AND transactionTime <= (NOW() - INTERVAL 2 MINUTE)
            """,
            (customer_id,),
        )
    return cursor.rowcount


@app.before_request
def log_request_start():
    if request.path.startswith("/static/"):
        return
    write_activity_log(
        "REQUEST",
        {
            "method": request.method,
            "path": request.path,
            "ip": request.remote_addr,
        },
    )


@app.route("/")
def index():
    return render_template("index.html", admin_portal=False)


@app.route("/admin")
def admin_index():
    return render_template("index.html", admin_portal=True)


@app.route("/signup")
def signup_page():
    return render_template("signup.html")


def render_customer_page(page_title, page_name):
    return render_template("customer_page.html", page_title=page_title, page_name=page_name)


@app.route("/customer")
def customer_home():
    return render_customer_page("Discover Great Food", "home")


@app.route("/customer/profile")
def customer_profile_page():
    return render_customer_page("Your Profile", "profile")


@app.route("/customer/restaurants")
def customer_restaurants_page():
    return render_customer_page("Restaurants", "restaurants")


@app.route("/customer/browse")
def customer_browse_page():
    return render_customer_page("Browse Menu", "browse")


@app.route("/customer/cart")
def customer_cart_page():
    return render_customer_page("Your Cart", "cart")


@app.route("/restaurant")
def restaurant_dashboard_page():
    return render_template("restaurant_page.html")


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")
    login_as = data.get("loginAs", "").strip()

    allowed_login_roles = {"Customer", "RestaurantManager", "DeliveryPartner", "Admin"}

    if not email or not password:
        return json_response(status=400, message="Email and password are required")

    if login_as and login_as not in allowed_login_roles:
        return json_response(status=400, message="Invalid login role")

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT memberID, name, email, password, isDeleted FROM Member WHERE email = %s",
            (email,),
        )
        member = cursor.fetchone()

        if not member:
            write_activity_log("LOGIN_FAILED", {"email": email, "reason": "member_not_found", "ip": request.remote_addr})
            return json_response(status=401, message="Invalid credentials")

        if int(member.get("isDeleted", 0)) == 1:
            write_activity_log("LOGIN_FAILED", {"email": email, "reason": "account_deleted", "ip": request.remote_addr})
            return json_response(status=403, message="This account has been deleted")

        if not verify_and_migrate_password(connection, member["memberID"], password, member["password"]):
            write_activity_log("LOGIN_FAILED", {"email": email, "reason": "wrong_password", "ip": request.remote_addr})
            return json_response(status=401, message="Invalid credentials")

        cursor.execute(
            """
            SELECT r.roleName
            FROM MemberRoleMapping mg
            JOIN Roles r ON r.roleID = mg.roleID
            WHERE mg.memberID = %s
            """,
            (member["memberID"],),
        )
        roles = [row["roleName"] for row in cursor.fetchall()]

        if login_as == "Admin" and "Admin" not in roles:
            write_activity_log("LOGIN_FAILED", {"email": email, "reason": "admin_access_denied", "ip": request.remote_addr})
            return json_response(status=403, message="Admin access denied")

        if login_as in {"Customer", "RestaurantManager", "DeliveryPartner"}:
            if login_as not in roles:
                write_activity_log("LOGIN_FAILED", {"email": email, "reason": f"role_mismatch:{login_as}", "ip": request.remote_addr})
                return json_response(status=403, message=f"This account is not a {login_as}")

        if not login_as:
            login_as = roles[0] if roles else ""

        token = secrets.token_hex(32)
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=int(os.getenv("QB_SESSION_HOURS", "8")))

        cursor.execute(
            "INSERT INTO Sessions(sessionToken, memberID, createdAt, expiresAt) VALUES (%s, %s, %s, %s)",
            (token, member["memberID"], now, expires_at),
        )
        connection.commit()

        write_activity_log(
            "LOGIN_SUCCESS",
            {
                "memberID": member["memberID"],
                "email": member["email"],
                "activeRole": login_as,
                "ip": request.remote_addr,
            },
        )

        return json_response(
            {
                "token": token,
                "expiresAt": expires_at.isoformat() + "Z",
                "member": {
                    "memberID": member["memberID"],
                    "name": member["name"],
                    "email": member["email"],
                    "roles": roles,
                    "activeRole": login_as,
                },
            },
            message="Login successful",
        )
    except Error as exc:
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        if connection and connection.is_connected():
            connection.close()


@app.post("/api/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}
    signup_as = data.get("signupAs", "").strip()
    restaurant_fields = data.get("restaurant", {}) if signup_as == "Restaurant" else {}

    allowed_types = {"Member", "DeliveryPartner", "Restaurant"}
    if signup_as not in allowed_types:
        return json_response(status=400, message="Invalid signup type")

    member_fields = data.get("member", {})
    if signup_as == "Restaurant":
        member_name = str(restaurant_fields.get("name", "")).strip()
        member_email = str(restaurant_fields.get("email", "")).strip()
        member_password = str(restaurant_fields.get("password", ""))
        member_phone = str(restaurant_fields.get("contactPhone", "")).strip()
    else:
        member_name = str(member_fields.get("name", "")).strip()
        member_email = str(member_fields.get("email", "")).strip()
        member_password = str(member_fields.get("password", ""))
        member_phone = str(member_fields.get("phoneNumber", "")).strip()

    if not member_name or not member_email or not member_password or not member_phone:
        return json_response(status=400, message="Member fields are required: name, email, password, phoneNumber")

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT memberID, isDeleted FROM Member WHERE email = %s", (member_email,))
        existing_member = cursor.fetchone()

        is_reactivated = False
        if existing_member and int(existing_member.get("isDeleted", 0)) == 0:
            return json_response(status=409, message="Email already exists")

        if existing_member and int(existing_member.get("isDeleted", 0)) == 1:
            next_member_id = existing_member["memberID"]
            is_reactivated = True
            cursor.execute(
                """
                UPDATE Member
                SET name = %s, password = %s, phoneNumber = %s, isDeleted = 0
                WHERE memberID = %s
                """,
                (member_name, hash_password(member_password), member_phone, next_member_id),
            )
        else:
            cursor.execute("SELECT COALESCE(MAX(memberID), 0) + 1 AS nextID FROM Member")
            next_member_id = cursor.fetchone()["nextID"]

            cursor.execute(
                """
                INSERT INTO Member(memberID, name, email, password, phoneNumber, createdAt)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (
                    next_member_id,
                    member_name,
                    member_email,
                    hash_password(member_password),
                    member_phone,
                ),
            )

        role_name = "Customer"
        if signup_as == "DeliveryPartner":
            role_name = "DeliveryPartner"
        elif signup_as == "Restaurant":
            role_name = "RestaurantManager"

        cursor.execute("SELECT roleID FROM Roles WHERE roleName = %s", (role_name,))
        role_row = cursor.fetchone()
        if not role_row:
            connection.rollback()
            return json_response(status=500, message=f"Role not found: {role_name}")

        cursor.execute(
            "INSERT IGNORE INTO MemberRoleMapping(memberID, roleID) VALUES (%s, %s)",
            (next_member_id, role_row["roleID"]),
        )

        created_payload = {
            "memberID": next_member_id,
            "signupAs": signup_as,
            "roleAssigned": role_name,
        }

        if signup_as == "Member":
            cursor.execute(
                """
                INSERT INTO Customer(customerID, loyaltyTier, membershipDiscount, cartTotalAmount, membershipDueDate, membership, isDeleted)
                VALUES (%s, 1, 0, 0, NULL, 0, 0)
                ON DUPLICATE KEY UPDATE
                    loyaltyTier = VALUES(loyaltyTier),
                    membershipDiscount = VALUES(membershipDiscount),
                    cartTotalAmount = VALUES(cartTotalAmount),
                    membershipDueDate = VALUES(membershipDueDate),
                    membership = VALUES(membership),
                    isDeleted = 0
                """,
                (next_member_id,),
            )

        elif signup_as == "DeliveryPartner":
            partner = data.get("deliveryPartner", {})
            required_partner_fields = ["vehicleNumber", "licenseID", "dateOfBirth", "currentLatitude", "currentLongitude"]
            missing = [field for field in required_partner_fields if partner.get(field) in (None, "")]
            if missing:
                connection.rollback()
                return json_response(status=400, message=f"Missing delivery fields: {', '.join(missing)}")

            try:
                dob = datetime.strptime(str(partner["dateOfBirth"]), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                connection.rollback()
                return json_response(status=400, message="Invalid dateOfBirth format. Use YYYY-MM-DD")

            today = datetime.utcnow().date()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                connection.rollback()
                return json_response(status=400, message="Delivery partner must be at least 18 years old")

            cursor.execute(
                """
                INSERT INTO DeliveryPartner(
                    partnerID, vehicleNumber, licenseID, dateOfBirth,
                    currentLatitude, currentLongitude, isOnline, averageRating, image, isDeleted
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, x'00', 0)
                ON DUPLICATE KEY UPDATE
                    vehicleNumber = VALUES(vehicleNumber),
                    licenseID = VALUES(licenseID),
                    dateOfBirth = VALUES(dateOfBirth),
                    currentLatitude = VALUES(currentLatitude),
                    currentLongitude = VALUES(currentLongitude),
                    isOnline = VALUES(isOnline),
                    averageRating = VALUES(averageRating),
                    image = VALUES(image),
                    isDeleted = 0
                """,
                (
                    next_member_id,
                    partner["vehicleNumber"],
                    partner["licenseID"],
                    partner["dateOfBirth"],
                    partner["currentLatitude"],
                    partner["currentLongitude"],
                    int(bool(partner.get("isOnline", False))),
                ),
            )

        elif signup_as == "Restaurant":
            restaurant = data.get("restaurant", {})
            required_restaurant_fields = [
                "name",
                "contactPhone",
                "email",
                "password",
                "addressLine",
                "city",
                "zipCode",
                "latitude",
                "longitude",
            ]
            missing = [field for field in required_restaurant_fields if restaurant.get(field) in (None, "")]
            if missing:
                connection.rollback()
                return json_response(status=400, message=f"Missing restaurant fields: {', '.join(missing)}")

            cursor.execute("SELECT COALESCE(MAX(restaurantID), 0) + 1 AS nextID FROM Restaurant")
            next_restaurant_id = cursor.fetchone()["nextID"]
            created_payload["restaurantID"] = next_restaurant_id

            cursor.execute(
                """
                INSERT INTO Restaurant(
                    restaurantID, name, contactPhone, email, password, isOpen, isVerified, averageRating,
                    addressLine, city, zipCode, latitude, longitude, discontinued
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    next_restaurant_id,
                    restaurant["name"],
                    restaurant["contactPhone"],
                    restaurant["email"],
                    hash_password(str(restaurant["password"])),
                    1,
                    0,
                    None,
                    restaurant["addressLine"],
                    restaurant["city"],
                    restaurant["zipCode"],
                    restaurant["latitude"],
                    restaurant["longitude"],
                    0,
                ),
            )

        write_audit_log(
            connection,
            None,
            "UPDATE" if is_reactivated else "INSERT",
            "Member",
            next_member_id,
            {"signupAs": signup_as, "email": member_email, "role": role_name, "reactivated": is_reactivated},
        )
        write_activity_log(
            "SIGNUP_SUCCESS",
            {
                "memberID": next_member_id,
                "signupAs": signup_as,
                "email": member_email,
                "reactivated": is_reactivated,
                "ip": request.remote_addr,
            },
        )

        token = secrets.token_hex(32)
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=int(os.getenv("QB_SESSION_HOURS", "8")))
        cursor.execute(
            "INSERT INTO Sessions(sessionToken, memberID, createdAt, expiresAt) VALUES (%s, %s, %s, %s)",
            (token, next_member_id, now, expires_at),
        )

        write_activity_log(
            "AUTO_LOGIN_AFTER_SIGNUP",
            {
                "memberID": next_member_id,
                "activeRole": role_name,
                "ip": request.remote_addr,
            },
        )

        connection.commit()
        return json_response(
            status=201,
            message="Account reactivated successfully" if is_reactivated else "Signup successful",
            data={
                **created_payload,
                "token": token,
                "expiresAt": expires_at.isoformat() + "Z",
                "member": {
                    "memberID": next_member_id,
                    "name": member_name,
                    "email": member_email,
                    "roles": [role_name],
                    "activeRole": role_name,
                },
            },
        )

    except Error as exc:
        if connection:
            connection.rollback()
        write_activity_log("SIGNUP_FAILED", {"signupAs": signup_as, "email": member_email, "error": str(exc), "ip": request.remote_addr})
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        if connection and connection.is_connected():
            connection.close()


@app.post("/api/auth/logout")
@require_auth
def logout():
    connection = request.db_connection
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM Sessions WHERE sessionToken = %s", (request.current_user["sessionToken"],))
        connection.commit()
        write_activity_log(
            "LOGOUT",
            {
                "memberID": request.current_user["memberID"],
                "ip": request.remote_addr,
            },
        )
        return json_response(message="Logged out")
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.get("/api/auth/me")
@require_auth
def get_me():
    user = request.current_user
    close_request_connection()
    return json_response(
        {
            "memberID": user["memberID"],
            "name": user["name"],
            "email": user["email"],
            "roles": user["roles"],
            "sessionExpires": user["expiresAt"].isoformat() if hasattr(user["expiresAt"], "isoformat") else str(user["expiresAt"]),
        }
    )


@app.get("/api/portfolio/<int:member_id>")
@require_auth
def get_portfolio(member_id):
    connection = request.db_connection
    current_user = request.current_user
    is_admin = "Admin" in current_user.get("roles", [])

    if not is_admin and current_user["memberID"] != member_id:
        close_request_connection()
        return json_response(status=403, message="You can only view your own portfolio")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT memberID, name, email, phoneNumber, createdAt FROM Member WHERE memberID = %s",
            (member_id,),
        )
        member = cursor.fetchone()
        if not member:
            close_request_connection()
            return json_response(status=404, message="Member not found")

        cursor.execute(
            """
            SELECT r.roleName
            FROM MemberRoleMapping mg
            JOIN Roles r ON r.roleID = mg.roleID
            WHERE mg.memberID = %s
            """,
            (member_id,),
        )
        roles = [row["roleName"] for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM Customer WHERE customerID = %s", (member_id,))
        customer_data = cursor.fetchone()

        cursor.execute("SELECT * FROM DeliveryPartner WHERE partnerID = %s", (member_id,))
        partner_data = cursor.fetchone()
        if partner_data and isinstance(partner_data.get("image"), (bytes, bytearray)):
            partner_data["image"] = None

        close_request_connection()
        return json_response(
            {
                "member": member,
                "roles": roles,
                "customerProfile": customer_data,
                "deliveryPartnerProfile": partner_data,
            }
        )
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/customer/orders")
@require_roles("Customer", "Admin")
def customer_orders():
    connection = request.db_connection
    current_user = request.current_user

    target_member_id = current_user["memberID"]
    if "Admin" in current_user.get("roles", []):
        target_member_id = request.args.get("memberID", default=target_member_id, type=int)

    try:
        expired_count = expire_pending_order_payments(connection, target_member_id)
        if expired_count > 0:
            connection.commit()

        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT o.orderID, o.orderTime, o.orderStatus, o.totalAmount,
                   r.name AS restaurantName, p.status AS paymentStatus
            FROM Orders o
            JOIN Restaurant r ON r.restaurantID = o.restaurantID
            LEFT JOIN Payment p ON p.paymentID = o.paymentID
            WHERE o.customerID = %s
            ORDER BY o.orderTime DESC
            LIMIT 50
            """,
            (target_member_id,),
        )
        rows = cursor.fetchall()
        close_request_connection()
        return json_response(rows)
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.put("/api/customer/profile")
@require_roles("Customer")
def update_customer_profile():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip()
    phone_number = str(payload.get("phoneNumber", "")).strip()
    password = str(payload.get("password", ""))

    updates = []
    values = []

    try:
        cursor = connection.cursor(dictionary=True)

        if name:
            updates.append("name = %s")
            values.append(name)

        if email:
            cursor.execute(
                "SELECT COUNT(*) AS countVal FROM Member WHERE email = %s AND memberID <> %s",
                (email, member_id),
            )
            if cursor.fetchone()["countVal"] > 0:
                close_request_connection()
                return json_response(status=409, message="Email already in use")
            updates.append("email = %s")
            values.append(email)

        if phone_number:
            updates.append("phoneNumber = %s")
            values.append(phone_number)

        if password:
            updates.append("password = %s")
            values.append(hash_password(password))

        if not updates:
            close_request_connection()
            return json_response(status=400, message="No profile fields provided for update")

        values.append(member_id)
        cursor.execute(f"UPDATE Member SET {', '.join(updates)} WHERE memberID = %s", tuple(values))

        write_audit_log(
            connection,
            member_id,
            "UPDATE",
            "Member",
            member_id,
            {"name": bool(name), "email": bool(email), "phoneNumber": bool(phone_number), "password": bool(password)},
        )
        connection.commit()
        return json_response(message="Profile updated successfully")
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.delete("/api/customer/profile")
@require_roles("Customer")
def delete_customer_profile():
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM Sessions WHERE memberID = %s", (member_id,))
        cursor.execute("UPDATE Customer SET isDeleted = 1 WHERE customerID = %s", (member_id,))
        cursor.execute("UPDATE DeliveryPartner SET isDeleted = 1 WHERE partnerID = %s", (member_id,))
        cursor.execute("UPDATE Member SET isDeleted = 1 WHERE memberID = %s", (member_id,))

        if cursor.rowcount == 0:
            connection.rollback()
            close_request_connection()
            return json_response(status=404, message="Profile not found")

        write_audit_log(
            connection,
            member_id,
            "DELETE",
            "Member",
            member_id,
            {"selfDelete": True, "softDelete": True},
        )
        connection.commit()
        close_request_connection()
        return json_response(message="Profile successfully deleted")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/customer/profile/orders")
@require_roles("Customer")
def customer_profile_orders():
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT o.orderID, o.orderTime, o.orderStatus, o.totalAmount,
                   r.name AS restaurantName, p.status AS paymentStatus,
                   orr.restaurantRating, orr.deliveryRating, orr.comment AS orderComment
            FROM Orders o
            JOIN Restaurant r ON r.restaurantID = o.restaurantID
            LEFT JOIN Payment p ON p.paymentID = o.paymentID
            LEFT JOIN OrderRating orr ON orr.orderID = o.orderID
            WHERE o.customerID = %s
            ORDER BY o.orderTime DESC
            LIMIT 100
            """,
            (member_id,),
        )
        orders = cursor.fetchall()

        order_map = {}
        order_ids = []
        for row in orders:
            order_ids.append(row["orderID"])
            row["items"] = []
            order_map[row["orderID"]] = row

        if order_ids:
            placeholders = ",".join(["%s"] * len(order_ids))
            cursor.execute(
                f"""
                SELECT oi.orderID, oi.restaurantID, oi.itemID, oi.quantity, oi.priceAtPurchase,
                       mi.name AS itemName, mir.rating AS itemRating, mir.comment AS itemComment
                FROM OrderItem oi
                JOIN MenuItem mi ON mi.restaurantID = oi.restaurantID AND mi.itemID = oi.itemID
                LEFT JOIN MenuItemRating mir
                    ON mir.orderID = oi.orderID AND mir.restaurantID = oi.restaurantID AND mir.itemID = oi.itemID
                WHERE oi.orderID IN ({placeholders})
                ORDER BY oi.orderID DESC, oi.itemID
                """,
                tuple(order_ids),
            )
            for item in cursor.fetchall():
                order_map[item["orderID"]]["items"].append(item)

        close_request_connection()
        return json_response(orders)
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/customer/profile/reviews")
@require_roles("Customer")
def customer_profile_reviews():
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT orr.orderID, o.orderTime, r.name AS restaurantName,
                   orr.restaurantRating, orr.deliveryRating, orr.comment
            FROM OrderRating orr
            JOIN Orders o ON o.orderID = orr.orderID
            JOIN Restaurant r ON r.restaurantID = o.restaurantID
            WHERE o.customerID = %s
            ORDER BY o.orderTime DESC
            """,
            (member_id,),
        )
        order_reviews = cursor.fetchall()

        cursor.execute(
            """
            SELECT mir.orderID, mir.restaurantID, mir.itemID, mir.rating, mir.comment,
                   o.orderTime, r.name AS restaurantName, mi.name AS itemName
            FROM MenuItemRating mir
            JOIN Orders o ON o.orderID = mir.orderID
            JOIN Restaurant r ON r.restaurantID = mir.restaurantID
            JOIN MenuItem mi ON mi.restaurantID = mir.restaurantID AND mi.itemID = mir.itemID
            WHERE o.customerID = %s
            ORDER BY o.orderTime DESC, mir.orderID DESC, mir.itemID
            """,
            (member_id,),
        )
        item_reviews = cursor.fetchall()

        close_request_connection()
        return json_response({"orderReviews": order_reviews, "itemReviews": item_reviews})
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.post("/api/customer/reviews/order/<int:order_id>")
@app.put("/api/customer/reviews/order/<int:order_id>")
@require_roles("Customer")
def upsert_order_review(order_id):
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    restaurant_rating = payload.get("restaurantRating")
    delivery_rating = payload.get("deliveryRating")
    comment = str(payload.get("comment", "")).strip() or None

    if restaurant_rating is None and delivery_rating is None and comment is None:
        close_request_connection()
        return json_response(status=400, message="Provide at least one review field")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM Orders WHERE orderID = %s AND customerID = %s", (order_id, member_id))
        if not cursor.fetchone():
            close_request_connection()
            return json_response(status=404, message="Order not found for this customer")

        cursor.execute(
            """
            INSERT INTO OrderRating(orderID, restaurantRating, deliveryRating, comment)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                restaurantRating = VALUES(restaurantRating),
                deliveryRating = VALUES(deliveryRating),
                comment = VALUES(comment)
            """,
            (order_id, restaurant_rating, delivery_rating, comment),
        )

        write_audit_log(
            connection,
            member_id,
            "UPDATE",
            "OrderRating",
            order_id,
            {"restaurantRating": restaurant_rating, "deliveryRating": delivery_rating, "comment": comment},
        )
        connection.commit()
        close_request_connection()
        return json_response(message="Order review saved")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.delete("/api/customer/reviews/order/<int:order_id>")
@require_roles("Customer")
def delete_order_review(order_id):
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM Orders WHERE orderID = %s AND customerID = %s", (order_id, member_id))
        if not cursor.fetchone():
            close_request_connection()
            return json_response(status=404, message="Order not found for this customer")

        cursor.execute("DELETE FROM OrderRating WHERE orderID = %s", (order_id,))
        if cursor.rowcount == 0:
            connection.rollback()
            close_request_connection()
            return json_response(status=404, message="Order review not found")

        write_audit_log(connection, member_id, "DELETE", "OrderRating", order_id, {"deleted": True})
        connection.commit()
        close_request_connection()
        return json_response(message="Order review deleted")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.post("/api/customer/reviews/item")
@app.put("/api/customer/reviews/item")
@require_roles("Customer")
def upsert_item_review():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    order_id = payload.get("orderID")
    restaurant_id = payload.get("restaurantID")
    item_id = payload.get("itemID")
    rating = payload.get("rating")
    comment = str(payload.get("comment", "")).strip() or None

    if order_id is None or restaurant_id is None or item_id is None or rating is None:
        close_request_connection()
        return json_response(status=400, message="orderID, restaurantID, itemID, rating are required")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT 1
            FROM Orders o
            JOIN OrderItem oi ON oi.orderID = o.orderID
            WHERE o.orderID = %s AND o.customerID = %s AND oi.restaurantID = %s AND oi.itemID = %s
            """,
            (order_id, member_id, restaurant_id, item_id),
        )
        if not cursor.fetchone():
            close_request_connection()
            return json_response(status=404, message="Order item not found for this customer")

        cursor.execute(
            """
            INSERT INTO MenuItemRating(restaurantID, itemID, orderID, rating, comment)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                rating = VALUES(rating),
                comment = VALUES(comment)
            """,
            (restaurant_id, item_id, order_id, rating, comment),
        )

        write_audit_log(
            connection,
            member_id,
            "UPDATE",
            "MenuItemRating",
            f"{order_id}:{restaurant_id}:{item_id}",
            {"rating": rating, "comment": comment},
        )
        connection.commit()
        close_request_connection()
        return json_response(message="Item review saved")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.delete("/api/customer/reviews/item")
@require_roles("Customer")
def delete_item_review():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    order_id = payload.get("orderID")
    restaurant_id = payload.get("restaurantID")
    item_id = payload.get("itemID")

    if order_id is None or restaurant_id is None or item_id is None:
        close_request_connection()
        return json_response(status=400, message="orderID, restaurantID, itemID are required")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT 1
            FROM Orders o
            JOIN OrderItem oi ON oi.orderID = o.orderID
            WHERE o.orderID = %s AND o.customerID = %s AND oi.restaurantID = %s AND oi.itemID = %s
            """,
            (order_id, member_id, restaurant_id, item_id),
        )
        if not cursor.fetchone():
            close_request_connection()
            return json_response(status=404, message="Order item not found for this customer")

        cursor.execute(
            "DELETE FROM MenuItemRating WHERE orderID = %s AND restaurantID = %s AND itemID = %s",
            (order_id, restaurant_id, item_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            close_request_connection()
            return json_response(status=404, message="Item review not found")

        write_audit_log(
            connection,
            member_id,
            "DELETE",
            "MenuItemRating",
            f"{order_id}:{restaurant_id}:{item_id}",
            {"deleted": True},
        )
        connection.commit()
        close_request_connection()
        return json_response(message="Item review deleted")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/customer/addresses")
@require_roles("Customer")
def list_customer_addresses():
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT addressID, addressLine, city, zipCode, label, latitude, longitude, isSaved
            FROM Address
            WHERE customerID = %s
            ORDER BY addressID
            """,
            (member_id,),
        )
        addresses = cursor.fetchall()
        close_request_connection()
        return json_response(addresses)
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.post("/api/customer/addresses")
@require_roles("Customer")
def create_customer_address():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    address_line = str(payload.get("addressLine", "")).strip()
    city = str(payload.get("city", "")).strip()
    zip_code = str(payload.get("zipCode", "")).strip()
    label = str(payload.get("label", "")).strip() or "Home"
    latitude = payload.get("latitude", 0)
    longitude = payload.get("longitude", 0)
    make_selected = bool(payload.get("selected", False))

    if not address_line or not city or not zip_code:
        close_request_connection()
        return json_response(status=400, message="addressLine, city, and zipCode are required")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT COALESCE(MAX(addressID), 0) + 1 AS nextID FROM Address WHERE customerID = %s", (member_id,))
        next_address_id = cursor.fetchone()["nextID"]

        if make_selected:
            cursor.execute("UPDATE Address SET isSaved = 0 WHERE customerID = %s", (member_id,))

        selected_value = 1 if make_selected else 0
        cursor.execute(
            """
            INSERT INTO Address(customerID, addressID, addressLine, city, zipCode, label, latitude, longitude, isSaved)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (member_id, next_address_id, address_line, city, zip_code, label, latitude, longitude, selected_value),
        )

        # Auto-select the first address if none is selected yet.
        if not make_selected:
            cursor.execute(
                """
                UPDATE Address
                SET isSaved = 1
                WHERE customerID = %s AND addressID = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM (
                          SELECT addressID FROM Address WHERE customerID = %s AND isSaved = 1
                      ) t
                  )
                """,
                (member_id, next_address_id, member_id),
            )

        write_audit_log(
            connection,
            member_id,
            "INSERT",
            "Address",
            f"{member_id}:{next_address_id}",
            {"selected": make_selected},
        )

        connection.commit()
        close_request_connection()
        return json_response(status=201, message="Address added", data={"addressID": next_address_id})
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.put("/api/customer/addresses/select")
@require_roles("Customer")
def select_customer_address():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}
    address_id = payload.get("addressID")

    if address_id is None:
        close_request_connection()
        return json_response(status=400, message="addressID is required")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM Address WHERE customerID = %s AND addressID = %s", (member_id, address_id))
        if not cursor.fetchone():
            close_request_connection()
            return json_response(status=404, message="Address not found")

        cursor.execute("UPDATE Address SET isSaved = 0 WHERE customerID = %s", (member_id,))
        cursor.execute("UPDATE Address SET isSaved = 1 WHERE customerID = %s AND addressID = %s", (member_id, address_id))

        write_audit_log(
            connection,
            member_id,
            "UPDATE",
            "Address",
            f"{member_id}:{address_id}",
            {"selected": True},
        )

        connection.commit()
        close_request_connection()
        return json_response(message="Delivery address selected")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/customer/cart")
@require_roles("Customer")
def get_customer_cart():
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        expired_count = expire_pending_order_payments(connection, member_id)
        if expired_count > 0:
            connection.commit()

        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT ci.customerID, ci.restaurantID, ci.itemID, ci.quantity,
                   mi.name AS itemName, mi.appPrice,
                   r.name AS restaurantName
            FROM CartItem ci
            JOIN MenuItem mi ON mi.restaurantID = ci.restaurantID AND mi.itemID = ci.itemID
            JOIN Restaurant r ON r.restaurantID = ci.restaurantID
            WHERE ci.customerID = %s
              AND mi.discontinued = 0
              AND r.isDeleted = 0
            ORDER BY ci.restaurantID, ci.itemID
            """,
            (member_id,),
        )
        rows = cursor.fetchall()

        items = []
        item_count = 0
        total_amount = 0.0
        for row in rows:
            quantity = int(row["quantity"])
            price = float(row["appPrice"])
            line_total = round(quantity * price, 2)
            item_count += quantity
            total_amount += line_total
            items.append(
                {
                    "restaurantID": row["restaurantID"],
                    "itemID": row["itemID"],
                    "name": row["itemName"],
                    "restaurantName": row["restaurantName"],
                    "price": price,
                    "quantity": quantity,
                    "lineTotal": line_total,
                }
            )

        total_amount = round(total_amount, 2)
        cursor.execute("UPDATE Customer SET cartTotalAmount = %s WHERE customerID = %s", (total_amount, member_id))
        connection.commit()

        close_request_connection()
        return json_response({"items": items, "itemCount": item_count, "totalAmount": total_amount})
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.put("/api/customer/cart/item")
@require_roles("Customer")
def upsert_customer_cart_item():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    restaurant_id = payload.get("restaurantID")
    item_id = payload.get("itemID")
    quantity_delta = payload.get("quantityDelta", 1)

    if restaurant_id is None or item_id is None:
        close_request_connection()
        return json_response(status=400, message="restaurantID and itemID are required")

    try:
        quantity_delta = int(quantity_delta)
    except (TypeError, ValueError):
        close_request_connection()
        return json_response(status=400, message="quantityDelta must be an integer")

    if quantity_delta == 0:
        close_request_connection()
        return json_response(status=400, message="quantityDelta cannot be 0")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT mi.restaurantID, mi.itemID
            FROM MenuItem mi
            JOIN Restaurant r ON r.restaurantID = mi.restaurantID
            WHERE mi.restaurantID = %s
              AND mi.itemID = %s
              AND mi.discontinued = 0
              AND mi.isAvailable = 1
              AND r.isDeleted = 0
            """,
            (restaurant_id, item_id),
        )
        if not cursor.fetchone():
            close_request_connection()
            return json_response(status=404, message="Menu item not found or unavailable")

        cursor.execute(
            "SELECT quantity FROM CartItem WHERE customerID = %s AND restaurantID = %s AND itemID = %s",
            (member_id, restaurant_id, item_id),
        )
        existing = cursor.fetchone()

        if not existing and quantity_delta > 0:
            cursor.execute(
                "SELECT restaurantID FROM CartItem WHERE customerID = %s LIMIT 1",
                (member_id,),
            )
            cart_anchor = cursor.fetchone()
            if cart_anchor and int(cart_anchor["restaurantID"]) != int(restaurant_id):
                close_request_connection()
                return json_response(
                    status=409,
                    message="Cart can contain items from only one restaurant at a time. Clear cart first.",
                )

        if existing:
            new_quantity = int(existing["quantity"]) + quantity_delta
            if new_quantity <= 0:
                cursor.execute(
                    "DELETE FROM CartItem WHERE customerID = %s AND restaurantID = %s AND itemID = %s",
                    (member_id, restaurant_id, item_id),
                )
                action = "DELETE"
            else:
                cursor.execute(
                    "UPDATE CartItem SET quantity = %s WHERE customerID = %s AND restaurantID = %s AND itemID = %s",
                    (new_quantity, member_id, restaurant_id, item_id),
                )
                action = "UPDATE"
        else:
            if quantity_delta < 0:
                close_request_connection()
                return json_response(status=400, message="Cannot decrease quantity for an item not in cart")
            cursor.execute(
                "INSERT INTO CartItem(customerID, restaurantID, itemID, quantity) VALUES (%s, %s, %s, %s)",
                (member_id, restaurant_id, item_id, quantity_delta),
            )
            action = "INSERT"

        total = update_customer_cart_total(connection, member_id)
        write_audit_log(
            connection,
            member_id,
            action,
            "CartItem",
            f"{member_id}:{restaurant_id}:{item_id}",
            {"quantityDelta": quantity_delta, "cartTotalAmount": total},
        )

        connection.commit()
        close_request_connection()
        return json_response(message="Cart updated successfully")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.delete("/api/customer/cart/item")
@require_roles("Customer")
def delete_customer_cart_item():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    restaurant_id = payload.get("restaurantID")
    item_id = payload.get("itemID")

    if restaurant_id is None or item_id is None:
        close_request_connection()
        return json_response(status=400, message="restaurantID and itemID are required")

    try:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM CartItem WHERE customerID = %s AND restaurantID = %s AND itemID = %s",
            (member_id, restaurant_id, item_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            close_request_connection()
            return json_response(status=404, message="Cart item not found")

        total = update_customer_cart_total(connection, member_id)
        write_audit_log(
            connection,
            member_id,
            "DELETE",
            "CartItem",
            f"{member_id}:{restaurant_id}:{item_id}",
            {"removed": True, "cartTotalAmount": total},
        )

        connection.commit()
        close_request_connection()
        return json_response(message="Cart item removed")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.delete("/api/customer/cart")
@require_roles("Customer")
def clear_customer_cart():
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM CartItem WHERE customerID = %s", (member_id,))
        total = update_customer_cart_total(connection, member_id)

        write_audit_log(
            connection,
            member_id,
            "DELETE",
            "CartItem",
            str(member_id),
            {"clearCart": True, "cartTotalAmount": total},
        )

        connection.commit()
        close_request_connection()
        return json_response(message="Cart cleared")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.post("/api/customer/cart/payment-demo")
@require_roles("Customer")
def customer_payment_demo():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    status_in = str(payload.get("status", "")).strip().lower()
    status_map = {
        "successful": "Success",
        "processing": "Pending",
        "failed": "Failed",
    }
    payment_mode_in = str(payload.get("paymentMode", "online")).strip().lower()
    payment_mode_map = {
        "online": "OnQuickBites",
        "cod": "COD",
        "onquickbites": "OnQuickBites",
    }
    if status_in not in status_map:
        close_request_connection()
        return json_response(status=400, message="Invalid payment status. Use successful, processing, or failed")
    if payment_mode_in not in payment_mode_map:
        close_request_connection()
        return json_response(status=400, message="Invalid payment mode. Use online or cod")

    try:
        expired_count = expire_pending_order_payments(connection, member_id)
        if expired_count > 0:
            connection.commit()

        cursor = connection.cursor(dictionary=True)
        cart_total = calculate_customer_cart_total(connection, member_id)
        if cart_total <= 0:
            close_request_connection()
            return json_response(status=400, message="Cart is empty")

        cursor.execute(
            """
            SELECT ci.restaurantID, ci.itemID, ci.quantity, mi.appPrice
            FROM CartItem ci
            JOIN MenuItem mi ON mi.restaurantID = ci.restaurantID AND mi.itemID = ci.itemID
            WHERE ci.customerID = %s
            ORDER BY ci.restaurantID, ci.itemID
            """,
            (member_id,),
        )
        cart_rows = cursor.fetchall()
        restaurant_ids = sorted({int(row["restaurantID"]) for row in cart_rows})

        if len(restaurant_ids) > 1:
            close_request_connection()
            return json_response(
                status=409,
                message="Cart must contain items from a single restaurant only",
            )

        cursor.execute("SELECT COALESCE(MAX(paymentID), 0) + 1 AS nextID FROM Payment")
        payment_id = cursor.fetchone()["nextID"]

        db_status = status_map[status_in]
        db_payment_mode = payment_mode_map[payment_mode_in]
        cursor.execute(
            """
            INSERT INTO Payment(paymentID, customerID, amount, paymentType, status, transactionTime, paymentFor)
            VALUES (%s, %s, %s, %s, %s, NOW(), 'Order')
            """,
            (payment_id, member_id, cart_total, db_payment_mode, db_status),
        )

        if status_in == "successful":
            selected_address_id = get_selected_address_id(connection, member_id)
            if selected_address_id is None:
                connection.rollback()
                close_request_connection()
                return json_response(
                    status=400,
                    message="Please add/select a delivery address before placing the order",
                    data={"redirectTo": "/customer/profile", "code": "ADDRESS_REQUIRED"},
                )

            if not restaurant_ids:
                connection.rollback()
                close_request_connection()
                return json_response(status=400, message="Cart is empty")

            cursor.execute("SELECT COALESCE(MAX(orderID), 0) + 1 AS nextID FROM Orders")
            next_order_id = cursor.fetchone()["nextID"]

            now = datetime.utcnow()
            estimated_time = now + timedelta(minutes=45)
            target_restaurant_id = restaurant_ids[0]

            cursor.execute(
                """
                INSERT INTO Orders(
                    orderID, orderTime, estimatedTime, totalAmount, orderStatus,
                    customerID, restaurantID, addressID, paymentID, specialInstruction
                )
                VALUES (%s, %s, %s, %s, 'Created', %s, %s, %s, %s, %s)
                """,
                (
                    next_order_id,
                    now,
                    estimated_time,
                    cart_total,
                    member_id,
                    target_restaurant_id,
                    selected_address_id,
                    payment_id,
                    str(payload.get("specialInstruction", "")).strip() or None,
                ),
            )

            for row in cart_rows:
                cursor.execute(
                    """
                    INSERT INTO OrderItem(orderID, restaurantID, itemID, quantity, priceAtPurchase)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        next_order_id,
                        row["restaurantID"],
                        row["itemID"],
                        row["quantity"],
                        row["appPrice"],
                    ),
                )

            cursor.execute("DELETE FROM CartItem WHERE customerID = %s", (member_id,))
            update_customer_cart_total(connection, member_id)

            cursor.execute(
                """
                SELECT COUNT(*) AS successful_orders
                FROM Orders o
                WHERE o.customerID = %s
                  AND EXISTS (
                    SELECT 1 FROM Payment p
                    WHERE p.paymentID = o.paymentID
                      AND p.status = 'Success'
                      AND p.paymentFor = 'Order'
                  )
                """,
                (member_id,),
            )
            successful_count = cursor.fetchone()["successful_orders"]
            
            if successful_count % 10 == 0 and successful_count > 0:
                cursor.execute(
                    """
                    UPDATE Customer
                    SET loyaltyTier = LEAST(5, loyaltyTier + 1)
                    WHERE customerID = %s AND membership = 1
                    """,
                    (member_id,),
                )
                write_audit_log(
                    connection,
                    member_id,
                    "UPDATE",
                    "Customer",
                    member_id,
                    {"reason": "loyalty_tier_increment", "successful_orders": successful_count},
                )

            write_audit_log(
                connection,
                member_id,
                "INSERT",
                "Orders",
                next_order_id,
                {
                    "restaurantID": target_restaurant_id,
                    "addressID": selected_address_id,
                    "paymentID": payment_id,
                    "status": "Created",
                },
            )

        write_audit_log(
            connection,
            member_id,
            "INSERT",
            "Payment",
            payment_id,
            {"status": db_status, "amount": cart_total, "paymentMode": db_payment_mode, "demo": True},
        )

        connection.commit()
        close_request_connection()
        return json_response(
            {
                "paymentID": payment_id,
                "status": db_status,
                "paymentType": db_payment_mode,
                "amount": round(cart_total, 2),
                "orderPlaced": status_in == "successful",
                "notifyRestaurant": status_in == "successful",
            },
            message=(
                "Order placed successfully. Restaurant has been notified."
                if status_in == "successful"
                else f"Demo payment marked as {status_in}"
            ),
        )
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.post("/api/customer/cart/payment-demo/recheck")
@require_roles("Customer")
def recheck_processing_payment():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}
    payment_id = payload.get("paymentID")

    if payment_id is None:
        close_request_connection()
        return json_response(status=400, message="paymentID is required")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT paymentID, status, transactionTime
            FROM Payment
            WHERE paymentID = %s AND customerID = %s AND paymentFor = 'Order'
            """,
            (payment_id, member_id),
        )
        payment_row = cursor.fetchone()
        if not payment_row:
            close_request_connection()
            return json_response(status=404, message="Payment not found")

        if payment_row["status"] != "Pending":
            close_request_connection()
            return json_response(
                {"paymentID": payment_id, "status": payment_row["status"]},
                message="Payment is no longer processing",
            )

        cursor.execute(
            """
            SELECT TIMESTAMPDIFF(SECOND, transactionTime, NOW()) AS elapsedSeconds
            FROM Payment
            WHERE paymentID = %s AND customerID = %s
            """,
            (payment_id, member_id),
        )
        elapsed = int(cursor.fetchone()["elapsedSeconds"] or 0)
        if elapsed >= 120:
            cursor.execute(
                "UPDATE Payment SET status = 'Failed' WHERE paymentID = %s AND customerID = %s",
                (payment_id, member_id),
            )
            write_audit_log(
                connection,
                member_id,
                "UPDATE",
                "Payment",
                payment_id,
                {"status": "Failed", "reason": "processing_timeout"},
            )
            connection.commit()
            close_request_connection()
            return json_response(
                {"paymentID": payment_id, "status": "Failed"},
                message="Processing timeout reached. Payment marked as failed.",
            )

        remaining = max(0, 120 - elapsed)
        close_request_connection()
        return json_response(
            {"paymentID": payment_id, "status": "Pending", "secondsRemaining": remaining},
            message="Payment is still processing",
        )
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/customer/payments/last")
@require_roles("Customer")
def get_last_customer_payment_status():
    connection = request.db_connection
    member_id = request.current_user["memberID"]

    try:
        expired_count = expire_pending_order_payments(connection, member_id)
        if expired_count > 0:
            connection.commit()

        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT paymentID, amount, paymentType, status, transactionTime
            FROM Payment
            WHERE customerID = %s AND paymentFor = 'Order'
            ORDER BY transactionTime DESC, paymentID DESC
            LIMIT 1
            """,
            (member_id,),
        )
        payment_row = cursor.fetchone()
        close_request_connection()

        if not payment_row:
            return json_response(
                {
                    "hasPayment": False,
                },
                message="No order payments found yet",
            )

        return json_response(
            {
                "hasPayment": True,
                "paymentID": payment_row["paymentID"],
                "amount": float(payment_row["amount"]),
                "paymentType": payment_row["paymentType"],
                "status": payment_row["status"],
                "transactionTime": (
                    payment_row["transactionTime"].isoformat()
                    if hasattr(payment_row["transactionTime"], "isoformat")
                    else str(payment_row["transactionTime"])
                ),
            }
        )
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.post("/api/customer/membership/purchase")
@require_roles("Customer")
def purchase_membership():
    connection = request.db_connection
    member_id = request.current_user["memberID"]
    payload = request.get_json(silent=True) or {}

    payment_mode_in = str(payload.get("paymentMode", "online")).strip().lower()
    
    if payment_mode_in != "online":
        close_request_connection()
        return json_response(status=400, message="Membership purchase only available via Online (QuickBites) payment")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT membership, membershipDueDate
            FROM Customer
            WHERE customerID = %s
            """,
            (member_id,),
        )
        customer_row = cursor.fetchone()
        if not customer_row:
            close_request_connection()
            return json_response(status=404, message="Customer not found")

        if customer_row["membership"] == 1:
            close_request_connection()
            return json_response(
                status=409,
                message="You are already a member",
                data={"membershipDueDate": (
                    customer_row["membershipDueDate"].isoformat()
                    if hasattr(customer_row["membershipDueDate"], "isoformat")
                    else str(customer_row["membershipDueDate"])
                )}
            )

        cursor.execute("SELECT COALESCE(MAX(paymentID), 0) + 1 AS nextID FROM Payment")
        payment_id = cursor.fetchone()["nextID"]

        membership_amount = 500
        db_payment_mode = "OnQuickBites"

        cursor.execute(
            """
            INSERT INTO Payment(paymentID, customerID, amount, paymentType, status, transactionTime, paymentFor)
            VALUES (%s, %s, %s, %s, 'Success', NOW(), 'Membership')
            """,
            (payment_id, member_id, membership_amount, db_payment_mode),
        )

        membership_due = datetime.utcnow() + timedelta(days=365)
        
        cursor.execute(
            """
            UPDATE Customer
            SET membership = 1, membershipDueDate = %s, loyaltyTier = 2
            WHERE customerID = %s
            """,
            (membership_due, member_id),
        )

        write_audit_log(
            connection,
            member_id,
            "INSERT",
            "Payment",
            payment_id,
            {"amount": membership_amount, "paymentMode": db_payment_mode, "paymentFor": "Membership"},
        )
        
        write_audit_log(
            connection,
            member_id,
            "UPDATE",
            "Customer",
            member_id,
            {"membership": 1, "membershipDueDate": membership_due.isoformat(), "loyaltyTier": 2},
        )

        connection.commit()
        close_request_connection()
        return json_response(
            {
                "paymentID": payment_id,
                "status": "Success",
                "amount": membership_amount,
                "membershipDueDate": membership_due.isoformat(),
                "loyaltyTier": 2,
            },
            message="Membership purchased successfully! You now have access to loyalty tier benefits.",
        )
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/delivery/assignments")
@require_roles("DeliveryPartner", "Admin")
def delivery_assignments():
    connection = request.db_connection
    current_user = request.current_user

    target_member_id = current_user["memberID"]
    if "Admin" in current_user.get("roles", []):
        target_member_id = request.args.get("memberID", default=target_member_id, type=int)

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT da.AssignmentID, da.OrderID, da.acceptanceTime, da.pickupTime, da.deliveryTime,
                   o.orderStatus, r.name AS restaurantName
            FROM Delivery_Assignments da
            JOIN Orders o ON o.orderID = da.OrderID
            JOIN Restaurant r ON r.restaurantID = o.restaurantID
            WHERE da.PartnerID = %s
            ORDER BY da.acceptanceTime DESC
            LIMIT 50
            """,
            (target_member_id,),
        )
        rows = cursor.fetchall()
        close_request_connection()
        return json_response(rows)
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/restaurants")
@require_auth
def list_restaurants():
    connection = request.db_connection
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT restaurantID, name, city, isOpen, isVerified, averageRating
            FROM Restaurant
            WHERE discontinued = 0 AND isDeleted = 0
            ORDER BY name
            """
        )
        rows = cursor.fetchall()
        close_request_connection()
        return json_response(rows)
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/restaurant/me")
@require_roles("RestaurantManager", "Admin")
def get_restaurant_profile():
    connection = request.db_connection
    user = request.current_user

    try:
        target_restaurant_id = request.args.get("restaurantID", type=int) if "Admin" in user.get("roles", []) else None
        cursor = connection.cursor(dictionary=True)

        if target_restaurant_id is not None:
            cursor.execute(
                """
                SELECT restaurantID, name, contactPhone, email, isOpen, isVerified, averageRating,
                       addressLine, city, zipCode, latitude, longitude, discontinued
                FROM Restaurant
                WHERE restaurantID = %s AND isDeleted = 0
                LIMIT 1
                """,
                (target_restaurant_id,),
            )
            restaurant = cursor.fetchone()
        else:
            restaurant = get_restaurant_by_member_email(connection, user["email"])

        if not restaurant:
            close_request_connection()
            return json_response(status=404, message="Restaurant profile not found for this account")

        cursor.execute(
            """
            SELECT COUNT(*) AS totalItems,
                   COALESCE(SUM(CASE WHEN isAvailable = 1 AND discontinued = 0 THEN 1 ELSE 0 END), 0) AS availableItems
            FROM MenuItem
            WHERE restaurantID = %s
            """,
            (restaurant["restaurantID"],),
        )
        menu_stats = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*) AS totalOrders,
                   COALESCE(SUM(CASE WHEN orderStatus = 'Created' THEN 1 ELSE 0 END), 0) AS createdOrders,
                   COALESCE(SUM(CASE WHEN orderStatus = 'Preparing' THEN 1 ELSE 0 END), 0) AS preparingOrders,
                   COALESCE(SUM(CASE WHEN orderStatus = 'ReadyForPickup' THEN 1 ELSE 0 END), 0) AS readyOrders,
                   COALESCE(SUM(CASE WHEN orderStatus = 'OutForDelivery' THEN 1 ELSE 0 END), 0) AS outOrders,
                   COALESCE(SUM(CASE WHEN orderStatus = 'Delivered' THEN 1 ELSE 0 END), 0) AS deliveredOrders
            FROM Orders
            WHERE restaurantID = %s
            """,
            (restaurant["restaurantID"],),
        )
        order_stats = cursor.fetchone()

        close_request_connection()
        return json_response({
            "restaurant": restaurant,
            "stats": {
                "menu": menu_stats,
                "orders": order_stats,
            },
        })
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.put("/api/restaurant/me")
@require_roles("RestaurantManager", "Admin")
def update_restaurant_profile():
    connection = request.db_connection
    user = request.current_user
    payload = request.get_json(silent=True) or {}

    allowed_fields = {
        "name": "name = %s",
        "contactPhone": "contactPhone = %s",
        "isOpen": "isOpen = %s",
        "addressLine": "addressLine = %s",
        "city": "city = %s",
        "zipCode": "zipCode = %s",
        "latitude": "latitude = %s",
        "longitude": "longitude = %s",
        "discontinued": "discontinued = %s",
        "email": "email = %s",
        "password": "password = %s",
    }

    try:
        cursor = connection.cursor(dictionary=True)
        target_restaurant_id = request.args.get("restaurantID", type=int) if "Admin" in user.get("roles", []) else None

        if target_restaurant_id is not None:
            cursor.execute(
                "SELECT restaurantID, email FROM Restaurant WHERE restaurantID = %s AND isDeleted = 0 LIMIT 1",
                (target_restaurant_id,),
            )
            row = cursor.fetchone()
            if not row:
                close_request_connection()
                return json_response(status=404, message="Restaurant profile not found")
            restaurant_id = row["restaurantID"]
            restaurant_email = row["email"]
        else:
            own_restaurant = get_restaurant_by_member_email(connection, user["email"])
            if not own_restaurant:
                close_request_connection()
                return json_response(status=404, message="Restaurant profile not found for this account")
            restaurant_id = own_restaurant["restaurantID"]
            restaurant_email = own_restaurant["email"]

        cursor.execute(
            "SELECT memberID FROM Member WHERE email = %s AND isDeleted = 0 LIMIT 1",
            (restaurant_email,),
        )
        member_row = cursor.fetchone()
        if not member_row:
            close_request_connection()
            return json_response(status=404, message="Member account linked to this restaurant not found")
        target_member_id = member_row["memberID"]

        updated_email = str(payload.get("email", "")).strip() if "email" in payload else ""
        updated_password = str(payload.get("password", "")) if "password" in payload else ""

        if "email" in payload:
            if not updated_email:
                close_request_connection()
                return json_response(status=400, message="email cannot be empty")

            cursor.execute(
                "SELECT COUNT(*) AS countVal FROM Member WHERE email = %s AND memberID <> %s",
                (updated_email, target_member_id),
            )
            if cursor.fetchone()["countVal"] > 0:
                close_request_connection()
                return json_response(status=409, message="Email already in use")

        if "password" in payload and not updated_password:
            close_request_connection()
            return json_response(status=400, message="password cannot be empty")

        hashed_password = hash_password(updated_password) if "password" in payload else None

        set_parts = []
        values = []
        for field, expr in allowed_fields.items():
            if field in payload:
                value = payload[field]
                if field in {"isOpen", "discontinued"}:
                    value = int(bool(value))
                if field == "email":
                    value = updated_email
                if field == "password":
                    value = hashed_password
                set_parts.append(expr)
                values.append(value)

        if not set_parts:
            close_request_connection()
            return json_response(status=400, message="No valid fields provided for update")

        values.append(restaurant_id)
        cursor = connection.cursor()
        cursor.execute(
            f"UPDATE Restaurant SET {', '.join(set_parts)} WHERE restaurantID = %s",
            tuple(values),
        )

        member_updates = []
        member_values = []
        if "email" in payload:
            member_updates.append("email = %s")
            member_values.append(updated_email)
        if "password" in payload:
            member_updates.append("password = %s")
            member_values.append(hashed_password)

        if member_updates:
            member_values.append(target_member_id)
            cursor.execute(
                f"UPDATE Member SET {', '.join(member_updates)} WHERE memberID = %s",
                tuple(member_values),
            )

        audit_payload = dict(payload)
        if "password" in audit_payload:
            audit_payload["password"] = "***"

        write_audit_log(
            connection,
            user["memberID"],
            "UPDATE",
            "Restaurant",
            restaurant_id,
            audit_payload,
        )
        connection.commit()
        close_request_connection()
        return json_response(message="Restaurant profile updated")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/restaurant/orders")
@require_roles("RestaurantManager", "Admin")
def restaurant_orders():
    connection = request.db_connection
    user = request.current_user

    try:
        cursor = connection.cursor(dictionary=True)
        target_restaurant_id = request.args.get("restaurantID", type=int) if "Admin" in user.get("roles", []) else None

        if target_restaurant_id is not None:
            cursor.execute(
                "SELECT restaurantID FROM Restaurant WHERE restaurantID = %s AND isDeleted = 0 LIMIT 1",
                (target_restaurant_id,),
            )
            row = cursor.fetchone()
            if not row:
                close_request_connection()
                return json_response(status=404, message="Restaurant profile not found")
            restaurant_id = row["restaurantID"]
        else:
            own_restaurant = get_restaurant_by_member_email(connection, user["email"])
            if not own_restaurant:
                close_request_connection()
                return json_response(status=404, message="Restaurant profile not found for this account")
            restaurant_id = own_restaurant["restaurantID"]

        cursor.execute(
            """
            SELECT o.orderID, o.orderTime, o.estimatedTime, o.totalAmount, o.orderStatus,
                   o.customerID, o.addressID,
                   p.status AS paymentStatus,
                   da.AssignmentID, da.PartnerID, da.acceptanceTime, da.pickupTime, da.deliveryTime
            FROM Orders o
            LEFT JOIN Payment p ON p.paymentID = o.paymentID
            LEFT JOIN Delivery_Assignments da ON da.OrderID = o.orderID
            WHERE o.restaurantID = %s
            ORDER BY o.orderTime DESC
            LIMIT 200
            """,
            (restaurant_id,),
        )
        orders = cursor.fetchall()

        order_ids = [row["orderID"] for row in orders]
        order_map = {row["orderID"]: row for row in orders}
        for row in orders:
            row["items"] = []

        if order_ids:
            placeholders = ",".join(["%s"] * len(order_ids))
            cursor.execute(
                f"""
                SELECT oi.orderID, oi.itemID, oi.quantity, oi.priceAtPurchase, mi.name AS itemName
                FROM OrderItem oi
                JOIN MenuItem mi ON mi.restaurantID = oi.restaurantID AND mi.itemID = oi.itemID
                WHERE oi.orderID IN ({placeholders})
                ORDER BY oi.orderID DESC, oi.itemID
                """,
                tuple(order_ids),
            )
            for item in cursor.fetchall():
                order_map[item["orderID"]]["items"].append(item)

        close_request_connection()
        return json_response({"restaurantID": restaurant_id, "orders": orders})
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.put("/api/restaurant/orders/<int:order_id>/status")
@require_roles("RestaurantManager", "Admin")
def update_restaurant_order_status(order_id):
    connection = request.db_connection
    user = request.current_user
    payload = request.get_json(silent=True) or {}

    new_status = str(payload.get("orderStatus", "")).strip()
    is_restaurant_manager_only = "RestaurantManager" in user.get("roles", []) and "Admin" not in user.get("roles", [])
    allowed_status = {"Preparing", "ReadyForPickup"} if is_restaurant_manager_only else {
        "Created",
        "Preparing",
        "ReadyForPickup",
        "OutForDelivery",
        "Delivered",
    }
    if new_status not in allowed_status:
        close_request_connection()
        return json_response(status=400, message="Invalid order status")

    try:
        cursor = connection.cursor(dictionary=True)
        target_restaurant_id = request.args.get("restaurantID", type=int) if "Admin" in user.get("roles", []) else None

        if target_restaurant_id is not None:
            cursor.execute(
                "SELECT restaurantID FROM Restaurant WHERE restaurantID = %s AND isDeleted = 0 LIMIT 1",
                (target_restaurant_id,),
            )
            row = cursor.fetchone()
            if not row:
                close_request_connection()
                return json_response(status=404, message="Restaurant profile not found")
            restaurant_id = row["restaurantID"]
        else:
            own_restaurant = get_restaurant_by_member_email(connection, user["email"])
            if not own_restaurant:
                close_request_connection()
                return json_response(status=404, message="Restaurant profile not found for this account")
            restaurant_id = own_restaurant["restaurantID"]

        cursor.execute(
            "SELECT orderStatus FROM Orders WHERE orderID = %s AND restaurantID = %s",
            (order_id, restaurant_id),
        )
        order_row = cursor.fetchone()
        if not order_row:
            close_request_connection()
            return json_response(status=404, message="Order not found")

        if is_restaurant_manager_only and order_row["orderStatus"] in {"OutForDelivery", "Delivered"}:
            close_request_connection()
            return json_response(status=403, message="This order status is managed by delivery partners")

        cursor = connection.cursor()
        cursor.execute(
            "UPDATE Orders SET orderStatus = %s WHERE orderID = %s AND restaurantID = %s",
            (new_status, order_id, restaurant_id),
        )

        write_audit_log(
            connection,
            user["memberID"],
            "UPDATE",
            "Orders",
            order_id,
            {"orderStatus": new_status, "previousStatus": order_row["orderStatus"]},
        )
        connection.commit()
        close_request_connection()
        return json_response(message="Order status updated")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/menu-items")
@require_auth
def list_menu_items():
    connection = request.db_connection
    current_user = request.current_user
    restaurant_id = request.args.get("restaurantID", type=int)
    search = request.args.get("search", "").strip()
    include_discontinued = str(request.args.get("includeDiscontinued", "")).strip().lower() in {"1", "true", "yes"}

    if "RestaurantManager" in current_user.get("roles", []) and "Admin" not in current_user.get("roles", []):
        own_restaurant = get_restaurant_by_member_email(connection, current_user["email"])
        if not own_restaurant:
            close_request_connection()
            return json_response(status=404, message="Restaurant profile not found for this account")
        restaurant_id = own_restaurant["restaurantID"]

    # Restaurant dashboard should be able to view discontinued items for re-enable actions.
    if "RestaurantManager" in current_user.get("roles", []) and "Admin" not in current_user.get("roles", []):
        include_discontinued = True

    clauses = ["r.isDeleted = 0"]
    if not include_discontinued:
        clauses.append("mi.discontinued = 0")
    params = []

    if restaurant_id is not None:
        clauses.append("mi.restaurantID = %s")
        params.append(restaurant_id)
    if search:
        clauses.append("mi.name LIKE %s")
        params.append(f"%{search}%")

    where_sql = " AND ".join(clauses)

    query = f"""
         SELECT mi.restaurantID, mi.itemID, mi.name, mi.description, mi.menuCategory,
             mi.restaurantPrice, mi.appPrice, mi.isVegetarian, mi.preparationTime,
                         mi.isAvailable, mi.discontinued,
               r.name AS restaurantName
        FROM MenuItem mi
        JOIN Restaurant r ON r.restaurantID = mi.restaurantID
        WHERE {where_sql}
        ORDER BY mi.restaurantID, mi.itemID
    """

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        close_request_connection()
        return json_response(rows)
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.post("/api/menu-items")
@require_roles("Admin", "RestaurantManager")
def create_menu_item():
    connection = request.db_connection
    current_user = request.current_user
    payload = request.get_json(silent=True) or {}

    required_fields = [
        "restaurantID",
        "name",
        "restaurantPrice",
        "isVegetarian",
        "preparationTime",
        "isAvailable",
    ]

    missing = [field for field in required_fields if field not in payload]
    if missing:
        close_request_connection()
        return json_response(status=400, message=f"Missing fields: {', '.join(missing)}")

    if "RestaurantManager" in current_user.get("roles", []) and "Admin" not in current_user.get("roles", []):
        own_restaurant = get_restaurant_by_member_email(connection, current_user["email"])
        if not own_restaurant:
            close_request_connection()
            return json_response(status=404, message="Restaurant profile not found for this account")
        payload["restaurantID"] = own_restaurant["restaurantID"]

    try:
        restaurant_price = float(payload["restaurantPrice"])
    except (TypeError, ValueError):
        close_request_connection()
        return json_response(status=400, message="restaurantPrice must be a valid number")

    computed_app_price = round(restaurant_price * 1.3, 2)

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT COALESCE(MAX(itemID), -1) + 1 AS nextItemID FROM MenuItem WHERE restaurantID = %s",
            (payload["restaurantID"],),
        )
        payload["itemID"] = int(cursor.fetchone()["nextItemID"])

        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO MenuItem(
                restaurantID, itemID, name, description, menuCategory,
                restaurantPrice, appPrice, isVegetarian, averageRating,
                preparationTime, isAvailable, discontinued
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, 0)
            """,
            (
                payload["restaurantID"],
                payload["itemID"],
                payload["name"],
                payload.get("description"),
                payload.get("menuCategory"),
                restaurant_price,
                computed_app_price,
                int(bool(payload["isVegetarian"])),
                payload["preparationTime"],
                int(bool(payload["isAvailable"])),
            ),
        )

        payload["restaurantPrice"] = restaurant_price
        payload["appPrice"] = computed_app_price

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "INSERT",
            "MenuItem",
            f"{payload['restaurantID']}:{payload['itemID']}",
            payload,
        )
        connection.commit()
        return json_response(message="Menu item created", data=payload, status=201)
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.put("/api/menu-items/<int:restaurant_id>/<int:item_id>")
@require_roles("Admin", "RestaurantManager")
def update_menu_item(restaurant_id, item_id):
    connection = request.db_connection
    current_user = request.current_user
    payload = request.get_json(silent=True) or {}

    if "RestaurantManager" in current_user.get("roles", []) and "Admin" not in current_user.get("roles", []):
        own_restaurant = get_restaurant_by_member_email(connection, current_user["email"])
        if not own_restaurant:
            close_request_connection()
            return json_response(status=404, message="Restaurant profile not found for this account")
        if int(own_restaurant["restaurantID"]) != int(restaurant_id):
            close_request_connection()
            return json_response(status=403, message="You can only modify your own restaurant menu")

    allowed_fields = {
        "name": "name = %s",
        "description": "description = %s",
        "menuCategory": "menuCategory = %s",
        "restaurantPrice": "restaurantPrice = %s",
        "isVegetarian": "isVegetarian = %s",
        "preparationTime": "preparationTime = %s",
        "isAvailable": "isAvailable = %s",
    }

    set_parts = []
    values = []
    for field, expr in allowed_fields.items():
        if field in payload:
            value = payload[field]
            if field in {"isVegetarian", "isAvailable"}:
                value = int(bool(value))
            set_parts.append(expr)
            values.append(value)

    if "restaurantPrice" in payload:
        try:
            restaurant_price = float(payload["restaurantPrice"])
        except (TypeError, ValueError):
            close_request_connection()
            return json_response(status=400, message="restaurantPrice must be a valid number")

        # App price is always derived from restaurant price.
        payload["restaurantPrice"] = restaurant_price
        payload["appPrice"] = round(restaurant_price * 1.3, 2)
        set_parts.append("appPrice = %s")
        values.append(payload["appPrice"])

    if not set_parts:
        close_request_connection()
        return json_response(status=400, message="No valid fields provided for update")

    values.extend([restaurant_id, item_id])

    try:
        cursor = connection.cursor()
        cursor.execute(
            f"UPDATE MenuItem SET {', '.join(set_parts)} WHERE restaurantID = %s AND itemID = %s",
            tuple(values),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return json_response(status=404, message="Menu item not found")

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "UPDATE",
            "MenuItem",
            f"{restaurant_id}:{item_id}",
            payload,
        )
        connection.commit()
        return json_response(message="Menu item updated")
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.delete("/api/menu-items/<int:restaurant_id>/<int:item_id>")
@require_roles("Admin", "RestaurantManager")
def delete_menu_item(restaurant_id, item_id):
    connection = request.db_connection
    current_user = request.current_user

    if "RestaurantManager" in current_user.get("roles", []) and "Admin" not in current_user.get("roles", []):
        own_restaurant = get_restaurant_by_member_email(connection, current_user["email"])
        if not own_restaurant:
            close_request_connection()
            return json_response(status=404, message="Restaurant profile not found for this account")
        if int(own_restaurant["restaurantID"]) != int(restaurant_id):
            close_request_connection()
            return json_response(status=403, message="You can only modify your own restaurant menu")
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE MenuItem SET discontinued = 1, isAvailable = 0 WHERE restaurantID = %s AND itemID = %s",
            (restaurant_id, item_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return json_response(status=404, message="Menu item not found")

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "DELETE",
            "MenuItem",
            f"{restaurant_id}:{item_id}",
            {"softDelete": True},
        )
        connection.commit()
        return json_response(message="Menu item deleted")
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.post("/api/menu-items/<int:restaurant_id>/<int:item_id>/restore")
@require_roles("Admin", "RestaurantManager")
def restore_menu_item(restaurant_id, item_id):
    connection = request.db_connection
    current_user = request.current_user

    if "RestaurantManager" in current_user.get("roles", []) and "Admin" not in current_user.get("roles", []):
        own_restaurant = get_restaurant_by_member_email(connection, current_user["email"])
        if not own_restaurant:
            close_request_connection()
            return json_response(status=404, message="Restaurant profile not found for this account")
        if int(own_restaurant["restaurantID"]) != int(restaurant_id):
            close_request_connection()
            return json_response(status=403, message="You can only modify your own restaurant menu")

    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE MenuItem SET discontinued = 0, isAvailable = 1 WHERE restaurantID = %s AND itemID = %s",
            (restaurant_id, item_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return json_response(status=404, message="Menu item not found")

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "UPDATE",
            "MenuItem",
            f"{restaurant_id}:{item_id}",
            {"restore": True},
        )
        connection.commit()
        return json_response(message="Menu item re-enabled")
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.post("/api/admin/members")
@require_roles("Admin")
def create_member():
    connection = request.db_connection
    payload = request.get_json(silent=True) or {}

    required = ["name", "email", "password", "phoneNumber", "roleID"]
    missing = [field for field in required if field not in payload]
    if missing:
        close_request_connection()
        return json_response(status=400, message=f"Missing fields: {', '.join(missing)}")

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT COALESCE(MAX(memberID), 0) + 1 AS nextID FROM Member")
        next_id = cursor.fetchone()["nextID"]

        cursor.execute(
            """
            INSERT INTO Member(memberID, name, email, password, phoneNumber, createdAt)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                next_id,
                payload["name"],
                payload["email"],
                hash_password(payload["password"]),
                payload["phoneNumber"],
            ),
        )

        cursor.execute(
            "INSERT INTO MemberRoleMapping(memberID, roleID) VALUES (%s, %s)",
            (next_id, payload["roleID"]),
        )

        profile_type = payload.get("profileType")
        if profile_type == "Customer":
            cursor.execute(
                """
                INSERT INTO Customer(customerID, loyaltyTier, membershipDiscount, cartTotalAmount, membershipDueDate, membership)
                VALUES (%s, 1, 0, 0, NULL, 0)
                """,
                (next_id,),
            )
        elif profile_type == "DeliveryPartner":
            required_partner = ["vehicleNumber", "licenseID", "dateOfBirth", "currentLatitude", "currentLongitude"]
            missing_partner = [field for field in required_partner if field not in payload]
            if missing_partner:
                connection.rollback()
                return json_response(status=400, message=f"Missing delivery fields: {', '.join(missing_partner)}")

            try:
                dob = datetime.strptime(str(payload["dateOfBirth"]), "%Y-%m-%d").date()
            except (TypeError, ValueError):
                connection.rollback()
                return json_response(status=400, message="Invalid dateOfBirth format. Use YYYY-MM-DD")

            today = datetime.utcnow().date()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                connection.rollback()
                return json_response(status=400, message="Delivery partner must be at least 18 years old")

            cursor.execute(
                """
                INSERT INTO DeliveryPartner(
                    partnerID, vehicleNumber, licenseID, dateOfBirth,
                    currentLatitude, currentLongitude, isOnline, averageRating, image
                )
                VALUES (%s, %s, %s, %s, %s, %s, 0, NULL, x'00')
                """,
                (
                    next_id,
                    payload["vehicleNumber"],
                    payload["licenseID"],
                    payload["dateOfBirth"],
                    payload["currentLatitude"],
                    payload["currentLongitude"],
                ),
            )

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "INSERT",
            "Member",
            next_id,
            {"email": payload["email"], "roleID": payload["roleID"], "profileType": profile_type},
        )
        connection.commit()
        return json_response(status=201, message="Member created", data={"memberID": next_id})
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.delete("/api/admin/members/<int:member_id>")
@require_roles("Admin")
def delete_member(member_id):
    connection = request.db_connection

    if member_id == request.current_user["memberID"]:
        close_request_connection()
        return json_response(status=400, message="Admin cannot delete own account")

    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM Sessions WHERE memberID = %s", (member_id,))
        cursor.execute("UPDATE Customer SET isDeleted = 1 WHERE customerID = %s", (member_id,))
        cursor.execute("UPDATE DeliveryPartner SET isDeleted = 1 WHERE partnerID = %s", (member_id,))
        cursor.execute("UPDATE Member SET isDeleted = 1 WHERE memberID = %s", (member_id,))

        if cursor.rowcount == 0:
            connection.rollback()
            return json_response(status=404, message="Member not found")

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "DELETE",
            "Member",
            member_id,
            {"softDelete": True},
        )
        connection.commit()
        return json_response(message="Member deleted (soft delete)")
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


@app.post("/api/admin/members/<int:member_id>/restore")
@require_roles("Admin")
def restore_member(member_id):
    connection = request.db_connection

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT memberID, isDeleted FROM Member WHERE memberID = %s", (member_id,))
        member_row = cursor.fetchone()
        if not member_row:
            close_request_connection()
            return json_response(status=404, message="Member not found")

        if int(member_row.get("isDeleted", 0)) == 0:
            close_request_connection()
            return json_response(message="Member is already active")

        cursor.execute("UPDATE Member SET isDeleted = 0 WHERE memberID = %s", (member_id,))
        cursor.execute("UPDATE Customer SET isDeleted = 0 WHERE customerID = %s", (member_id,))
        cursor.execute("UPDATE DeliveryPartner SET isDeleted = 0 WHERE partnerID = %s", (member_id,))

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "UPDATE",
            "Member",
            member_id,
            {"restored": True, "softDelete": False},
        )

        connection.commit()
        close_request_connection()
        return json_response(message="Member restored successfully")
    except Error as exc:
        connection.rollback()
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
