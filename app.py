
import os
import sqlite3
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004112006696")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_SECRET = os.environ.get("ADMIN_SESSION_SECRET", "")
WEBSITE_ORIGIN = os.environ.get("WEBSITE_ORIGIN", "").rstrip("/")

# Set DATABASE_PATH=/var/data/prices.db when using a Render
# persistent disk mounted at /var/data.
DATABASE_PATH = os.environ.get("DATABASE_PATH", "prices.db")

serializer = (
    URLSafeTimedSerializer(SESSION_SECRET, salt="admin-session")
    if SESSION_SECRET else None
)

DEFAULT_PACKAGES = [
    ("instant_100", "instant", "100 Likes", 10, ""),
    ("instant_220", "instant", "220 Likes", 20, ""),
    ("instant_500", "instant", "500 Likes", 40, ""),
    ("instant_1000", "instant", "1000 Likes", 70, ""),
    ("auto_3", "auto", "3 Days", 20, "3 days"),
    ("auto_7", "auto", "7 Days", 40, "7 days"),
    ("auto_15", "auto", "15 Days", 70, "15 days"),
    ("auto_30", "auto", "30 Days", 120, "30 days"),
    ("auto_permanent", "auto", "Permanent", 250, "Permanent"),
]


def connect_db():
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    folder = os.path.dirname(DATABASE_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)

    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS packages (
                id TEXT PRIMARY KEY,
                service TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0),
                duration TEXT NOT NULL DEFAULT ''
            )
        """)

        for item in DEFAULT_PACKAGES:
            conn.execute("""
                INSERT OR IGNORE INTO packages
                (id, service, name, price, duration)
                VALUES (?, ?, ?, ?, ?)
            """, item)


init_db()


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if WEBSITE_ORIGIN and origin == WEBSITE_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = WEBSITE_ORIGIN
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization"
        )
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, OPTIONS"
        )
    return response


@app.route("/<path:path>", methods=["OPTIONS"])
@app.route("/", methods=["OPTIONS"])
def options_request(path=""):
    return "", 204


def admin_required():
    if not serializer:
        return None, (jsonify({
            "ok": False,
            "error": "Admin session secret is not configured"
        }), 500)

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, (jsonify({
            "ok": False, "error": "Admin login required"
        }), 401)

    token = header[7:].strip()
    try:
        data = serializer.loads(token, max_age=3600)
        if data.get("role") != "admin":
            raise BadSignature("Invalid role")
        return True, None
    except (BadSignature, SignatureExpired):
        return None, (jsonify({
            "ok": False, "error": "Session expired. Please log in again."
        }), 401)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "Free Fire Likes Backend is running"
    })


@app.route("/api/packages", methods=["GET"])
def get_packages():
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT id, service, name, price, duration
            FROM packages ORDER BY service, rowid
        """).fetchall()

    return jsonify({
        "ok": True,
        "packages": [dict(row) for row in rows]
    })


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    password = str(data.get("password", ""))

    if not ADMIN_PASSWORD or not SESSION_SECRET or not serializer:
        return jsonify({
            "ok": False,
            "error": "Admin environment variables are not configured"
        }), 500

    if password != ADMIN_PASSWORD:
        return jsonify({
            "ok": False, "error": "Incorrect password"
        }), 401

    token = serializer.dumps({"role": "admin"})
    return jsonify({"ok": True, "token": token})


@app.route("/api/admin/packages", methods=["GET"])
def admin_get_packages():
    _, error = admin_required()
    if error:
        return error

    with connect_db() as conn:
        rows = conn.execute("""
            SELECT id, service, name, price, duration
            FROM packages ORDER BY service, rowid
        """).fetchall()

    return jsonify({
        "ok": True,
        "packages": [dict(row) for row in rows]
    })


@app.route("/api/admin/packages", methods=["PUT"])
def admin_update_packages():
    _, error = admin_required()
    if error:
        return error

    data = request.get_json(silent=True) or {}
    updates = data.get("packages")

    if not isinstance(updates, list) or not updates:
        return jsonify({
            "ok": False,
            "error": "Provide a non-empty packages list"
        }), 400

    try:
        with connect_db() as conn:
            for item in updates:
                if not isinstance(item, dict):
                    raise ValueError("Invalid package entry")

                package_id = str(item.get("id", "")).strip()
                price = item.get("price")

                if not package_id:
                    raise ValueError("Package ID is missing")
                if isinstance(price, bool) or not isinstance(price, (int, float)):
                    raise ValueError("Price must be a number")
                if price < 0 or price > 100000000:
                    raise ValueError("Price is out of range")

                cursor = conn.execute(
                    "UPDATE packages SET price = ? WHERE id = ?",
                    (price, package_id)
                )
                if cursor.rowcount != 1:
                    raise ValueError("Unknown package ID: " + package_id)

    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except sqlite3.Error:
        return jsonify({
            "ok": False, "error": "Database update failed"
        }), 500

    return jsonify({"ok": True, "message": "Prices saved"})


@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}

    uid = str(data.get("uid", "")).strip()
    region = str(data.get("region", "BD")).strip()
    package = str(data.get("package", "")).strip()
    duration = str(data.get("duration", "")).strip()
    order_id = str(data.get("order_id", "")).strip()

    if not all([uid, region, package, duration, order_id]):
        return jsonify({
            "ok": False, "error": "Order details missing"
        }), 400

    if not BOT_TOKEN:
        return jsonify({
            "ok": False, "error": "Server token not configured"
        }), 500

    message = (
        "🛒 NEW FREE FIRE ORDER\n\n"
        f"Order ID: {order_id}\n"
        f"UID: {uid}\n"
        f"Region: {region}\n"
        f"Package: {package}\n"
        f"Duration: {duration}\n"
        f"Received: {datetime.now(timezone.utc).isoformat()}\n"
        "Status: Pending manual fulfillment"
    )

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message},
            timeout=10
        )
        result = response.json()

        if not response.ok or not result.get("ok"):
            return jsonify({
                "ok": False, "error": "Telegram notification failed"
            }), 502

        return jsonify({
            "ok": True,
            "order_id": order_id,
            "message": "Order notification sent"
        })

    except (requests.RequestException, ValueError):
        return jsonify({
            "ok": False, "error": "Telegram connection failed"
        }), 502
