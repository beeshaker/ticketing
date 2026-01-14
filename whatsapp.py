import os
import json
import time
import requests
import mysql.connector
import logging
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from conn1 import get_db_connection1
from sqlalchemy.sql import text
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

# -----------------------------------------------------------------------------
# Timezone helpers (Kenya)
# -----------------------------------------------------------------------------
KENYA_TZ = ZoneInfo("Africa/Nairobi")

def kenya_now():
    """Timezone-aware Kenya time (good for logs, comparisons)."""
    return datetime.now(tz=KENYA_TZ)

def kenya_now_db():
    """
    Naive Kenya time for DB inserts.
    Keeps stored timestamps consistent (no driver/DB timezone conversion).
    """
    return datetime.now(KENYA_TZ).replace(tzinfo=None)

# -----------------------------------------------------------------------------
# Load environment variables
# -----------------------------------------------------------------------------
load_dotenv()

# Meta WhatsApp API Credentials
WHATSAPP_ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# MySQL Database Connection
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Initialize Flask app
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# In-memory storage to track processed messages
processed_message_ids = set()
last_messages = {}  # { sender_id: (message_text, timestamp) }
user_timers = {}

# -----------------------------------------------------------------------------
# WhatsApp / DB helpers
# -----------------------------------------------------------------------------
def opt_in_user(whatsapp_number):
    """Adds the recipient number to the WhatsApp allowed list."""
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": whatsapp_number,
        "type": "template",
        "template": {
            "name": "registration_welcome",
            "language": {"code": "en_US"},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": "Welcome to our service! You are now registered."}]}
            ],
        },
    }

    response = requests.post(url, headers=headers, json=payload)
    logging.info(f"Opt-in response: {response.status_code} {response.text}")

    if response.status_code == 200:
        return True, "User opted in successfully!"
    return False, f"Error: {response.json()}"

def query_database(query, params=(), commit=False):
    """
    Connects to MySQL and executes queries.
    ✅ Change #1: Forces the MySQL session timezone to Kenya (+03:00)
    """
    try:
        conn = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        cursor = conn.cursor(dictionary=True)

        # ✅ Force Kenya timezone for this DB session (affects NOW(), CURRENT_TIMESTAMP, etc.)
        cursor.execute("SET time_zone = '+03:00'")

        cursor.execute(query, params)

        if commit:
            conn.commit()
            cursor.close()
            conn.close()
            return True

        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result

    except mysql.connector.Error as err:
        logging.error(f"Database error: {err}")
        return None

def send_whatsapp_message(to, message):
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    response = requests.post(url, headers=headers, json=payload)
    logging.info(f"Sent WhatsApp message: {response.json()}")
    return response.json()

def send_whatsapp_buttons(to):
    url = f"https://graph.facebook.com/v22.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "What would you like to do?"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "create_ticket", "title": "📝 Create Ticket"}},
                    {"type": "reply", "reply": {"id": "check_ticket", "title": "📌 Check Status"}},
                ]
            },
        },
    }
    response = requests.post(url, headers=headers, json=payload)
    logging.info(f"Sent WhatsApp interactive buttons: {response.json()}")
    return response.json()

# -----------------------------------------------------------------------------
# Ticket / category flow
# -----------------------------------------------------------------------------
def send_category_prompt(to):
    """Asks the user to select a category for the ticket."""
    message = "Please select a category:\n1️⃣ Accounts\n2️⃣ Maintenance\n3️⃣ Security\nReply with the number."
    send_whatsapp_message(to, message)

    # Set timeout to reset user status if they don't respond within 5 minutes
    user_timers[to] = kenya_now()
    threading.Thread(target=reset_category_selection, args=(to,), daemon=True).start()

def reset_category_selection(to):
    """Resets the category selection if the user takes more than 5 minutes to respond."""
    time.sleep(300)  # Wait for 5 minutes
    last_attempt_time = user_timers.get(to)

    if last_attempt_time:
        elapsed_time = (kenya_now() - last_attempt_time).total_seconds()
        if elapsed_time >= 300:
            logging.info(f"⏳ Resetting category selection for {to} due to timeout.")
            query_database("UPDATE users SET last_action = NULL WHERE whatsapp_number = %s", (to,), commit=True)
            send_whatsapp_message(
                to,
                "⏳ Your category selection request has expired. Please start again by selecting '📝 Create Ticket'."
            )
            user_timers.pop(to, None)

def get_category_name(category_number):
    categories = {"1": "Accounts", "2": "Maintenance", "3": "Security"}
    return categories.get(category_number)

def is_message_processed(message_id):
    if message_id in processed_message_ids:
        return True
    result = query_database("SELECT id FROM processed_messages WHERE id = %s", (message_id,))
    return bool(result)

def mark_message_as_processed(message_id):
    processed_message_ids.add(message_id)
    query_database("INSERT IGNORE INTO processed_messages (id) VALUES (%s)", (message_id,), commit=True)

def should_process_message(sender_id, message_text):
    current_time = time.time()

    if sender_id in last_messages:
        last_text, last_time = last_messages[sender_id]
        if last_text == message_text and (current_time - last_time) < 3:
            logging.info(f"⚠️ Ignoring duplicate message from {sender_id} within 3 seconds.")
            return False

    last_messages[sender_id] = (message_text, current_time)
    return True

def is_registered_user(whatsapp_number):
    engine = get_db_connection1()
    with engine.connect() as conn:
        q = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number")
        result = conn.execute(q, {"whatsapp_number": whatsapp_number}).fetchone()
    return result is not None

def send_whatsapp_tickets(to):
    message = ""
    query = """
        SELECT id, LEFT(issue_description, 50) AS short_description, updated_at as last_update
        FROM tickets
        WHERE user_id = (SELECT id FROM users WHERE whatsapp_number = %s)
        AND status = 'Open'
    """
    tickets = query_database(query, (to,))

    if not tickets:
        message = "You have no open tickets at the moment."
    else:
        message = "Your open tickets:\n"
        for ticket in tickets:
            message += (
                f"Ticket ID: {ticket['id']}\n"
                f"Description: {ticket['short_description']}\n"
                f"Last Update on: {ticket['last_update']}\n\n"
            )

    send_whatsapp_message(to, message)

# -----------------------------------------------------------------------------
# Webhook route
# -----------------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"Incoming webhook data: {json.dumps(data, indent=2)}")

    # Immediately return 200 OK to prevent WhatsApp retries
    response = jsonify({"status": "received"})

    # Process messages asynchronously
    threading.Thread(target=process_webhook, args=(data,), daemon=True).start()

    return response, 200

def process_webhook(data):
    """Handles incoming WhatsApp messages."""
    if "entry" not in data:
        return

    for entry in data["entry"]:
        for change in entry.get("changes", []):
            if "statuses" in change.get("value", {}):
                logging.info("Status update received. Ignoring.")
                continue

            if "messages" not in change.get("value", {}):
                continue

            for message in change["value"]["messages"]:
                message_id = message.get("id")
                sender_id = message.get("from")
                message_text = message.get("text", {}).get("body", "").strip()

                if not sender_id:
                    continue

                if not is_registered_user(sender_id):
                    logging.info(f"Blocked unregistered user: {sender_id}")
                    send_whatsapp_message(sender_id, "You are not registered. Please register first.")
                    continue

                # Prevent duplicates
                if is_message_processed(message_id) or not should_process_message(sender_id, message_text):
                    logging.info(f"⚠️ Skipping duplicate message {message_id}")
                    continue

                mark_message_as_processed(message_id)

                # Handle button replies
                if "interactive" in message and "button_reply" in message["interactive"]:
                    button_id = message["interactive"]["button_reply"]["id"]

                    if button_id == "create_ticket":
                        query_database(
                            "UPDATE users SET last_action = 'awaiting_category' WHERE whatsapp_number = %s",
                            (sender_id,),
                            commit=True,
                        )
                        send_category_prompt(sender_id)
                        continue

                    if button_id == "check_ticket":
                        send_whatsapp_tickets(sender_id)
                        continue

                # Fetch user last_action
                user_status = query_database(
                    "SELECT last_action FROM users WHERE whatsapp_number = %s",
                    (sender_id,),
                )

                # NOTE: leaving your property/admin mapping as-is, but time fixes are below.
                property_row = query_database(
                    "SELECT property FROM users WHERE whatsapp_number = %s",
                    (sender_id,),
                )
                property_val = property_row[0]["property"] if property_row else None

                assigned_admin_row = query_database(
                    "SELECT id FROM admin_users WHERE property = %s",
                    (property_val,),
                )
                assigned_admin = assigned_admin_row[0]["id"] if assigned_admin_row else None

                # Handle category selection
                if user_status and user_status[0]["last_action"] == "awaiting_category":
                    category_name = get_category_name(message_text)

                    if category_name:
                        query_database(
                            "UPDATE users SET last_action = 'awaiting_issue_description', temp_category = %s WHERE whatsapp_number = %s",
                            (category_name, sender_id),
                            commit=True,
                        )
                        send_whatsapp_message(sender_id, "Please describe your issue, and we will create a ticket for you.")
                        user_timers.pop(sender_id, None)
                    else:
                        send_whatsapp_message(sender_id, "⚠️ Invalid selection. Please reply with 1️⃣, 2️⃣, or 3️⃣.")
                        send_category_prompt(sender_id)
                    continue

                # Handle ticket creation
                if user_status and user_status[0]["last_action"] == "awaiting_issue_description":
                    user_info = query_database(
                        "SELECT id, temp_category FROM users WHERE whatsapp_number = %s",
                        (sender_id,),
                    )
                    if user_info:
                        user_id = user_info[0]["id"]
                        category = user_info[0]["temp_category"]

                        # ✅ Change #2: Stop using NOW() and insert Kenya time from Python
                        created_at = kenya_now_db()

                        query_database(
                            """
                            INSERT INTO tickets
                              (user_id, issue_description, status, created_at, category, property, assigned_admin)
                            VALUES
                              (%s, %s, 'Open', %s, %s, %s, %s)
                            """,
                            (user_id, message_text, created_at, category, property_val, assigned_admin),
                            commit=True,
                        )

                        query_database(
                            "UPDATE users SET last_action = NULL, temp_category = NULL WHERE whatsapp_number = %s",
                            (sender_id,),
                            commit=True,
                        )

                        send_whatsapp_message(
                            sender_id,
                            f"✅ Your ticket has been created under the *{category}* category. Our team will get back to you soon!"
                        )
                    else:
                        send_whatsapp_message(sender_id, "❌ Error creating ticket. Please try again.")
                    continue

                # Common messages
                if message_text.lower() in ["hi", "hello", "help", "menu"]:
                    send_whatsapp_buttons(sender_id)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=False)
