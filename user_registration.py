import streamlit as st
import pandas as pd
from sqlalchemy.sql import text
from conn import Conn
import requests
import os



db= Conn()
def register_user(name, whatsapp_number, property_id, unit_number):
    """Triggers WhatsApp opt-in and registers user only if not already in the database."""
    try:
        # ✅ Step 1: Trigger WhatsApp opt-in
        opt_in_success, opt_in_message = send_whatsapp_opt_in(whatsapp_number)

        if not opt_in_success:
            return False, f"Opt-in failed: {opt_in_message}"

        # ✅ Step 2: If backend already says user is registered, stop here
        if "already registered" in opt_in_message.lower():
            return False, opt_in_message

        # ✅ Step 3: Proceed to insert new user
        engine = db.engine
        with engine.connect() as conn:
            insert_query = text("""
                INSERT INTO users (name, whatsapp_number, property_id, unit_number) 
                VALUES (:name, :whatsapp_number, :property_id, :unit_number)
            """)
            conn.execute(insert_query, {
                "name": name,
                "whatsapp_number": whatsapp_number,
                "property_id": property_id,
                "unit_number": unit_number
            })
            conn.commit()

        return True, f"User registered successfully! {opt_in_message}"

    except Exception as e:
        return False, f"Error registering user: {e}"


        
def send_whatsapp_opt_in(whatsapp_number):
    """Calls Flask backend to trigger WhatsApp opt-in. Waits for confirmation."""
    url = st.secrets.optinURL + "/opt_in_user"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.getenv("INTERNAL_API_KEY")
    }
    payload = {"whatsapp_number": whatsapp_number}

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            resp_json = response.json()
            if resp_json.get("status") == "terms_sent":
                return True, "Opt-in terms message sent via WhatsApp."
            elif resp_json.get("status") == "already_registered":
                return False, "User already registered — skipping opt-in."
            else:
                return False, f"Unexpected response: {resp_json}"
        else:
            return False, f"Opt-in request failed: {response.status_code} - {response.text}"
    
    except Exception as e:
        return False, f"Error sending WhatsApp opt-in: {e}"



        
        


def fetch_users():
    engine = db.engine
    with engine.connect() as conn:
        query = text("SELECT u.id, u.name, u.property_id, p.name AS property, u.unit_number FROM users u JOIN properties p ON u.property_id = p.id;")
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

