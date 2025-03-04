import streamlit as st
from sqlalchemy import create_engine
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy.sql import text
from whatsapp import send_whatsapp_message  # ✅ Importing WhatsApp messaging function

load_dotenv()
if "admin_property" not in st.session_state:
    st.session_state.admin_property = "All"  # Default value
# Database Connection using SQLAlchemy
DB_URI = f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
def get_db_connection():
    return create_engine(DB_URI)

# Fetch all tickets using SQLAlchemy
def fetch_tickets(property=None):
    engine = get_db_connection()
    
    query = """
    SELECT t.id, u.whatsapp_number, u.name, t.issue_description, t.status, t.created_at, t.property 
    FROM tickets t 
    JOIN users u ON t.user_id = u.id
    """
    
    params = {}
    
    # Only filter if a specific property is provided
    if property and property != "All":
        query += " WHERE t.property = %(property)s"
        params["property"] = property

    df = pd.read_sql(query, engine, params=params)
    return df

# Check admin property and fetch tickets accordingly
if st.session_state.admin_property != "All":
    tickets_df = fetch_tickets(st.session_state.admin_property)  # Fetch only for specific property
else:
    tickets_df = fetch_tickets()  # Fetch all tickets (no filter)

# Update ticket status
def update_ticket_status(ticket_id, new_status):
    engine = get_db_connection()
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE tickets SET status = :new_status WHERE id = :ticket_id"),
            {"new_status": new_status, "ticket_id": ticket_id}
        )
        conn.commit()

    # Notify the user about the status update
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT u.whatsapp_number FROM users u JOIN tickets t ON u.id = t.user_id WHERE t.id = :ticket_id"),
            {"ticket_id": ticket_id}
        ).fetchone()
        
    if result:
        user_whatsapp = result[0]
        message = f"Your ticket #{ticket_id} has been updated to: {new_status}"
        send_whatsapp_message(user_whatsapp, message)  # ✅ Send WhatsApp notification

# Add ticket update with WhatsApp notification
def add_ticket_update(ticket_id, update_text, admin_name):
    engine = get_db_connection()
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO ticket_updates (ticket_id, update_text, updated_by) VALUES (:ticket_id, :update_text, :admin_name)"),
            {"ticket_id": ticket_id, "update_text": update_text, "admin_name": admin_name}
        )
        conn.commit()

    # Fetch the user's WhatsApp number
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT u.whatsapp_number FROM users u JOIN tickets t ON u.id = t.user_id WHERE t.id = :ticket_id"),
            {"ticket_id": ticket_id}
        ).fetchone()
        
    if result:
        user_whatsapp = result[0]
        message = f"Your ticket #{ticket_id} has a new update from {admin_name}:\n\n\"{update_text}\""
        send_whatsapp_message(user_whatsapp, message)  # ✅ Notify user about update



