import streamlit as st
import pandas as pd
import requests
import os
from sqlalchemy import create_engine, text
from database import get_db_connection  # Import the function to connect to the database

# WhatsApp API Credentials
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

# Function to send WhatsApp message
def send_whatsapp_message(to, message):
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
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
    return response.json()

# Function to register a user using raw SQL
def register_user(name, whatsapp_number, property_name, unit_number):
    """Register a new WhatsApp user in the system."""
    engine = get_db_connection()
    with engine.connect() as conn:
        try:
            # Check if the user already exists
            check_query = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number")
            existing_user = conn.execute(check_query, {"whatsapp_number": whatsapp_number}).fetchone()

            if existing_user:
                return False, "User already registered."

            # Insert new user
            insert_query = text("""
                INSERT INTO users (name, whatsapp_number, property, unit_number) 
                VALUES (:name, :whatsapp_number, :property, :unit_number)
            """)
            conn.execute(insert_query, {
                "name": name,
                "whatsapp_number": whatsapp_number,
                "property": property_name,
                "unit_number": unit_number
            })
            conn.commit()

            # Send a welcome message on WhatsApp
            welcome_message = f"Hello {name}, you have been successfully registered at {property_name}, Unit {unit_number}."
            send_whatsapp_message(whatsapp_number, welcome_message)

            return True, "User registered successfully!"

        except Exception as e:
            return False, f"Error registering user: {e}"

# Streamlit UI
st.title("WhatsApp User Registration")

with st.form("register_user_form"):
    name = st.text_input("User Name", placeholder="Enter user full name")
    whatsapp_number = st.text_input("WhatsApp Number", placeholder="e.g. +1234567890")
    property_name = st.text_input("Property Name", placeholder="Enter property name")
    unit_number = st.text_input("Unit Number", placeholder="Enter unit number")
    
    submit_button = st.form_submit_button("Register User")

if submit_button:
    if name and whatsapp_number and property_name and unit_number:
        success, message = register_user(name, whatsapp_number, property_name, unit_number)
        if success:
            st.success(message)
        else:
            st.error(message)
    else:
        st.warning("Please fill in all fields.")

# Fetch and display registered users
st.subheader("Registered Users")

def fetch_users():
    """Retrieve all registered users from the database."""
    engine = get_db_connection()
    with engine.connect() as conn:
        query = text("SELECT id, name, whatsapp_number, property, unit_number FROM users")
        result = conn.execute(query)
        users = result.fetchall()
    return users

users = fetch_users()

if users:
    df = pd.DataFrame(users, columns=["ID", "Name", "WhatsApp", "Property", "Unit"])
    st.dataframe(df)
else:
    st.warning("No users registered yet.")
