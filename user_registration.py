import streamlit as st
import pandas as pd
from sqlalchemy.sql import text
from conn import Conn
import requests
import os



db= Conn()
def register_user(name, whatsapp_number, property_id, unit_number):
    """Registers user and opts them into WhatsApp communication."""
    engine = db.engine
    with engine.connect() as conn:
        try:
            check_query = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number")
            existing_user = conn.execute(check_query, {"whatsapp_number": whatsapp_number}).fetchone()
            
            if existing_user:
                return False, "User already registered."

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

            # ✅ Automatically opt-in user
            print("trying to send opt-in")
            opt_in_message = send_whatsapp_opt_in(whatsapp_number)

            return True, f"User registered successfully! {opt_in_message}"
        except Exception as e:
            return False, f"Error registering user: {e}"
        
def send_whatsapp_opt_in(whatsapp_number):
    """Sends a request to Heroku backend to trigger WhatsApp opt-in."""
    url = st.secrets.URL + "/opt_in_user"  # Example: https://yourapp.herokuapp.com/opt_in_user
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.getenv("INTERNAL_API_KEY")
    }
    payload = {"whatsapp_number": whatsapp_number}

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return "Opt-in message sent via WhatsApp."
        else:
            return f"WhatsApp opt-in failed ({response.status_code})."
    except Exception as e:
        return f"Error sending WhatsApp opt-in: {e}"

        
        


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

