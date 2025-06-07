import streamlit as st
import pandas as pd
from sqlalchemy.sql import text
from conn import Conn
import requests
import os



db= Conn()
    
def register_user(name, whatsapp_number, property_id, unit_number):
    try:
        insert_temp_user(name, whatsapp_number, property_id, unit_number)
        opt_in_success, opt_in_message = send_whatsapp_opt_in(whatsapp_number, name, property_id, unit_number)

        if not opt_in_success:
            return False, f"Opt-in failed: {opt_in_message}"

        return True, f"Terms sent. User will be registered upon accepting them on WhatsApp."
    except Exception as e:
        return False, f"Error during opt-in process: {e}"


        
def send_whatsapp_opt_in(whatsapp_number, name, property_id, unit_number):
    url = st.secrets.optinURL + "/opt_in_user"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.getenv("INTERNAL_API_KEY")
    }
    payload = {
        "whatsapp_number": whatsapp_number,
        "name": name,
        "property_id": property_id,
        "unit_number": unit_number
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return True, response.json().get("status", "unknown")
        else:
            return False, f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return False, str(e)


def insert_temp_user(name, whatsapp_number, property_id, unit_number):
    engine = db.engine
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO temp_opt_in_users (name, whatsapp_number, property_id, unit_number)
            VALUES (:name, :whatsapp_number, :property_id, :unit_number)
            ON DUPLICATE KEY UPDATE name = VALUES(name), unit_number = VALUES(unit_number)
        """), {
            "name": name,
            "whatsapp_number": whatsapp_number,
            "property_id": property_id,
            "unit_number": unit_number
        })
        conn.commit()


        


def fetch_users():
    engine = db.engine
    with engine.connect() as conn:
        query = text("SELECT u.id, u.name, u.whatsapp_number, p.name AS property, u.unit_number FROM users u JOIN properties p ON u.property_id = p.id;")
        result = conn.execute(query)
        users = result.fetchall()
    return users

def user_registration_page():
    st.title("📲 WhatsApp User Registration")
    engine = db.engine
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, name FROM properties"))
        properties = result.fetchall()

    # Convert to a list of options
    property_options = {name: pid for pid, name in properties}

    

    
    with st.form("register_user_form"):
        name = st.text_input("User Name", placeholder="Enter user full name")
        whatsapp_number = st.text_input("WhatsApp Number", placeholder="e.g. 2547123456")
        # Show dropdown
        property_name = st.selectbox("Select Property", list(property_options.keys()))
        
        unit_number = st.text_input("Unit Number", placeholder="Enter unit number")
        submit_button = st.form_submit_button("Register User")
        property_id = property_options[property_name]

    if submit_button:
        if name and whatsapp_number and property_name and unit_number:
            success, message = register_user(name, whatsapp_number, property_id, unit_number)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
        else:
            st.warning("Please fill in all fields.")
    
    st.subheader("Registered Users")
    users = fetch_users()
    
    if users:
        df = pd.DataFrame(users, columns=["ID", "Name", "WhatsApp", "Property", "Unit"])
        st.dataframe(df)
    else:
        st.warning("No users registered yet.")

