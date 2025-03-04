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

# Load environment variables
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
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "Welcome to our service! You are now registered."}
                    ]
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    print("Status code ", response.status_code)
    
    if response.status_code == 200:
        print("worked")
        return True, "User opted in successfully!"
    else:
        print(f"Error: {response.json()}")
        return False, f"Error: {response.json()}"

# Function to connect to MySQL and execute queries
def query_database(query, params=(), commit=False):
    try:
        conn = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        cursor = conn.cursor(dictionary=True)
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

# Prevent duplicate message processing
def is_message_processed(message_id):
    """Check if a message ID has already been processed."""
    if message_id in processed_message_ids:
        return True
    query = "SELECT id FROM processed_messages WHERE id = %s"
    result = query_database(query, (message_id,))
    return bool(result)

def mark_message_as_processed(message_id):
    """Mark a message as processed (in-memory & database)."""
    processed_message_ids.add(message_id)  # ✅ Immediate in-memory tracking
    query = "INSERT IGNORE INTO processed_messages (id) VALUES (%s)"
    query_database(query, (message_id,), commit=True)

def should_process_message(sender_id, message_text):
    """Check if the last message was identical within 3 seconds."""
    global last_messages
    current_time = time.time()

    if sender_id in last_messages:
        last_text, last_time = last_messages[sender_id]
        
        # Ignore duplicate messages within 3 seconds
        if last_text == message_text and (current_time - last_time) < 3:
            logging.info(f"⚠️ Ignoring duplicate message from {sender_id} within 3 seconds.")
            return False

    # ✅ Store this message as the last message
    last_messages[sender_id] = (message_text, current_time)
    return True

def is_registered_user(whatsapp_number):
        """Checks if the WhatsApp number is registered in the database."""
        engine = get_db_connection1()
        with engine.connect() as conn:
            query = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number")
            result = conn.execute(query, {"whatsapp_number": whatsapp_number}).fetchone()
        return result is not None


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
                    {
                        "type": "reply",
                        "reply": {
                            "id": "create_ticket",
                            "title": "📝 Create Ticket",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "check_ticket",
                            "title": "📌 Check Status",
                        },
                    },
                ]
            },
        },
    }
    response = requests.post(url, headers=headers, json=payload)
    logging.info(f"Sent WhatsApp interactive buttons: {response.json()}")
    return response.json()

# Send a WhatsApp message
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


def send_whatsapp_tickets(to):
    """Fetches and sends open tickets for the client via WhatsApp."""
    message = ""
    # Fetch open tickets for the given WhatsApp number
    query = """
        SELECT id, LEFT(issue_description, 50) AS short_description, updated_at as last_update
        FROM tickets 
        WHERE user_id = (SELECT id FROM users WHERE whatsapp_number = %s) 
        AND status = 'Open'
    """
    tickets = query_database(query, (to,))

    # If no open tickets found
    if not tickets:
        message = "You have no open tickets at the moment."
        
    else:
        message = "Your open tickets:\n"
        for ticket in tickets:
            message += f"Ticket ID: {ticket['id']}\nDescription: {ticket['short_description']}\nLast Update on: {ticket['last_update']}\n\n"
    
    send_whatsapp_message(to, message) 
    


# Webhook route to handle incoming messages
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(f"Incoming webhook data: {json.dumps(data, indent=2)}")

    # ✅ Immediately return 200 OK to prevent WhatsApp retries
    response = jsonify({"status": "received"})
    
    # ✅ Process messages asynchronously
    threading.Thread(target=process_webhook, args=(data,)).start()

    return response, 200




def process_webhook(data):
    """Handles message processing separately from the main webhook response."""
    if "entry" in data:
        for entry in data["entry"]:
            for change in entry.get("changes", []):
                if "statuses" in change["value"]:
                    logging.info(f"Status update received for message ID {change['value']['statuses'][0]['id']}. Ignoring.")
                    continue

                if "messages" in change["value"]:
                    for message in change["value"]["messages"]:
                        message_id = message.get("id")
                        sender_id = message["from"]
                        message_text = message.get("text", {}).get("body", "").strip()
                        
                        if not is_registered_user(sender_id):
                            logging.info(f"Blocked unregistered user: {sender_id}")
                            send_whatsapp_message(sender_id, "You are not registered. Please register first.")
                            continue
                        
                        success, opt_in_message = opt_in_user(sender_id)
                        if success:
                            logging.info(f"User {sender_id} successfully opted in.")
                        else:
                            logging.warning(f"Failed to opt-in user {sender_id}: {opt_in_message}")

                        # ✅ Prevent duplicate messages
                        if is_message_processed(message_id) or not should_process_message(sender_id, message_text):
                            logging.info(f"⚠️ Skipping duplicate message {message_id}")
                            continue

                        # ✅ Mark message as processed
                        mark_message_as_processed(message_id)

                        # ✅ Handle button replies
                        if "interactive" in message and "button_reply" in message["interactive"]:
                            button_id = message["interactive"]["button_reply"]["id"]

                            if button_id == "create_ticket":
                                user = query_database("SELECT id FROM users WHERE whatsapp_number = %s", (sender_id,))
                                if not user:
                                    send_whatsapp_message(sender_id, "You are not registered. Please contact support.")
                                    continue  

                                query_database("UPDATE users SET last_action = 'awaiting_issue_description' WHERE whatsapp_number = %s", (sender_id,), commit=True)
                                send_whatsapp_message(sender_id, "Please describe your issue, and we will create a ticket for you.")
                                continue

                            elif button_id == "check_ticket":
                                send_whatsapp_tickets(sender_id)
                                continue

                        # ✅ Handle text-based ticket creation
                        user_status = query_database("SELECT last_action FROM users WHERE whatsapp_number = %s", (sender_id,))
                        if user_status and user_status[0]["last_action"] == "awaiting_issue_description":
                            user_id_result = query_database("SELECT id FROM users WHERE whatsapp_number = %s", (sender_id,))
                            if user_id_result:
                                user_id = user_id_result[0]["id"]
                                query_database("INSERT INTO tickets (user_id, issue_description, status, created_at) VALUES (%s, %s, 'Open', NOW())", (user_id, message_text), commit=True)
                                query_database("UPDATE users SET last_action = NULL WHERE whatsapp_number = %s", (sender_id,), commit=True)
                                send_whatsapp_message(sender_id, "Your ticket has been created. Our team will get back to you soon!")
                            else:
                                send_whatsapp_message(sender_id, "Error creating ticket. Please try again.")
                            continue  
                        
                        elif user_status and user_status[0]["last_action"] == "awaiting_issue_number":
                            ticket_id = message_text.strip()
                            ticket_result = query_database("SELECT status FROM tickets WHERE id = %s AND user_id = (SELECT id FROM users WHERE whatsapp_number = %s)", (ticket_id, sender_id))
                            query_database("UPDATE users SET last_action = NULL WHERE whatsapp_number = %s", (sender_id,), commit=True)

                            if ticket_result:
                                send_whatsapp_message(sender_id, f"Your ticket status: {ticket_result[0]['status']}")
                            else:
                                send_whatsapp_message(sender_id, "Ticket not found. Please check your Ticket ID.")
                            continue  

                        # ✅ Handle common messages
                        if message_text.lower() in ["hi", "hello", "help", "menu"]:
                            send_whatsapp_buttons(sender_id)


if __name__ == "__main__":
    app.run(port=5000, debug=False)  # ⚠️ Disabled debug mode to prevent duplicate processing
