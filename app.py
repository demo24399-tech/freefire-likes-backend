
import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1004112006696")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "message": "Free Fire Likes Backend is running"
    })


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
            "ok": False,
            "error": "Order details missing"
        }), 400

    if not BOT_TOKEN:
        return jsonify({
            "ok": False,
            "error": "Server token not configured"
        }), 500

    message = (
        "🛒 NEW FREE FIRE ORDER\n\n"
        f"Order ID: {order_id}\n"
        f"UID: {uid}\n"
        f"Region: {region}\n"
        f"Package: {package}\n"
        f"Duration: {duration}\n"
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
                "ok": False,
                "error": "Telegram notification failed"
            }), 502

        return jsonify({
            "ok": True,
            "order_id": order_id,
            "message": "Order notification sent"
        })

    except requests.RequestException:
        return jsonify({
            "ok": False,
            "error": "Telegram connection failed"
        }), 502