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
        WHERE s.sessionToken = %s AND s.expiresAt > NOW()
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
            "SELECT memberID, name, email, password FROM Member WHERE email = %s",
            (email,),
        )
        member = cursor.fetchone()

        if not member:
            write_activity_log("LOGIN_FAILED", {"email": email, "reason": "member_not_found", "ip": request.remote_addr})
            return json_response(status=401, message="Invalid credentials")

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

    allowed_types = {"Member", "DeliveryPartner", "Restaurant"}
    if signup_as not in allowed_types:
        return json_response(status=400, message="Invalid signup type")

    member_fields = data.get("member", {})
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

        cursor.execute("SELECT COUNT(*) AS countVal FROM Member WHERE email = %s", (member_email,))
        if cursor.fetchone()["countVal"] > 0:
            return json_response(status=409, message="Email already exists")

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
            "INSERT INTO MemberRoleMapping(memberID, roleID) VALUES (%s, %s)",
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
                INSERT INTO Customer(customerID, loyaltyTier, membershipDiscount, cartTotalAmount, membershipDueDate, membership)
                VALUES (%s, 1, 0, 0, NULL, 0)
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
                    currentLatitude, currentLongitude, isOnline, averageRating, image
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, x'00')
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
                "isOpen",
                "isVerified",
                "addressLine",
                "city",
                "zipCode",
                "latitude",
                "longitude",
                "discontinued",
            ]
            missing = [field for field in required_restaurant_fields if field not in restaurant]
            if missing:
                connection.rollback()
                return json_response(status=400, message=f"Missing restaurant fields: {', '.join(missing)}")

            cursor.execute("SELECT COALESCE(MAX(restaurantID), 0) + 1 AS nextID FROM Restaurant")
            next_restaurant_id = cursor.fetchone()["nextID"]
            created_payload["restaurantID"] = next_restaurant_id

            cursor.execute(
                """
                INSERT INTO Restaurant(
                    restaurantID, name, contactPhone, isOpen, isVerified, averageRating,
                    addressLine, city, zipCode, latitude, longitude, discontinued
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    next_restaurant_id,
                    restaurant["name"],
                    restaurant["contactPhone"],
                    int(bool(restaurant["isOpen"])),
                    int(bool(restaurant["isVerified"])),
                    restaurant.get("averageRating"),
                    restaurant["addressLine"],
                    restaurant["city"],
                    restaurant["zipCode"],
                    restaurant["latitude"],
                    restaurant["longitude"],
                    int(bool(restaurant["discontinued"])),
                ),
            )

        write_audit_log(
            connection,
            None,
            "INSERT",
            "Member",
            next_member_id,
            {"signupAs": signup_as, "email": member_email, "role": role_name},
        )
        write_activity_log(
            "SIGNUP_SUCCESS",
            {
                "memberID": next_member_id,
                "signupAs": signup_as,
                "email": member_email,
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
            message="Signup successful",
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
        cursor.execute("DELETE FROM MemberRoleMapping WHERE memberID = %s", (member_id,))
        cursor.execute("DELETE FROM Customer WHERE customerID = %s", (member_id,))
        cursor.execute("DELETE FROM DeliveryPartner WHERE partnerID = %s", (member_id,))
        cursor.execute("DELETE FROM Member WHERE memberID = %s", (member_id,))

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
            {"selfDelete": True},
        )
        connection.commit()
        close_request_connection()
        return json_response(message="Profile successfully deleted")
    except Error as exc:
        connection.rollback()
        if getattr(exc, "errno", None) == 1451:
            close_request_connection()
            return json_response(
                status=409,
                message="Profile cannot be deleted because related records exist (orders/payments/addresses).",
            )
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
            WHERE discontinued = 0
            ORDER BY name
            """
        )
        rows = cursor.fetchall()
        close_request_connection()
        return json_response(rows)
    except Error as exc:
        close_request_connection()
        return json_response(status=500, message=f"Database error: {exc}")


@app.get("/api/menu-items")
@require_auth
def list_menu_items():
    connection = request.db_connection
    restaurant_id = request.args.get("restaurantID", type=int)
    search = request.args.get("search", "").strip()

    clauses = ["mi.discontinued = 0"]
    params = []

    if restaurant_id is not None:
        clauses.append("mi.restaurantID = %s")
        params.append(restaurant_id)
    if search:
        clauses.append("mi.name LIKE %s")
        params.append(f"%{search}%")

    where_sql = " AND ".join(clauses)

    query = f"""
        SELECT mi.restaurantID, mi.itemID, mi.name, mi.menuCategory, mi.appPrice, mi.isAvailable,
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
    payload = request.get_json(silent=True) or {}

    required_fields = [
        "restaurantID",
        "itemID",
        "name",
        "restaurantPrice",
        "appPrice",
        "isVegetarian",
        "preparationTime",
        "isAvailable",
    ]

    missing = [field for field in required_fields if field not in payload]
    if missing:
        close_request_connection()
        return json_response(status=400, message=f"Missing fields: {', '.join(missing)}")

    try:
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
                payload["restaurantPrice"],
                payload["appPrice"],
                int(bool(payload["isVegetarian"])),
                payload["preparationTime"],
                int(bool(payload["isAvailable"])),
            ),
        )

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
    payload = request.get_json(silent=True) or {}

    allowed_fields = {
        "name": "name = %s",
        "description": "description = %s",
        "menuCategory": "menuCategory = %s",
        "restaurantPrice": "restaurantPrice = %s",
        "appPrice": "appPrice = %s",
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
        cursor.execute("DELETE FROM MemberRoleMapping WHERE memberID = %s", (member_id,))
        cursor.execute("DELETE FROM Customer WHERE customerID = %s", (member_id,))
        cursor.execute("DELETE FROM DeliveryPartner WHERE partnerID = %s", (member_id,))
        cursor.execute("DELETE FROM Member WHERE memberID = %s", (member_id,))

        if cursor.rowcount == 0:
            connection.rollback()
            return json_response(status=404, message="Member not found")

        write_audit_log(
            connection,
            request.current_user["memberID"],
            "DELETE",
            "Member",
            member_id,
            {"cascadeCleanup": True},
        )
        connection.commit()
        return json_response(message="Member deleted")
    except Error as exc:
        connection.rollback()
        return json_response(status=500, message=f"Database error: {exc}")
    finally:
        close_request_connection()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
