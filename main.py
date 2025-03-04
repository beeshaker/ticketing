import streamlit as st
import pandas as pd
import bcrypt
from conn import get_db_connection, fetch_tickets, update_ticket_status, add_ticket_update  # ✅ Import from conn.py
from sqlalchemy.sql import text
from whatsapp import send_whatsapp_message  # ✅ WhatsApp integration
from license import LicenseManager
from user_registration import user_registration_page


# Session State for Authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.admin_name = ""
    st.session_state.admin_property = ""

# Page Configuration
st.set_page_config(page_title="CRM Admin Portal", layout="wide")

valid_license, license_message = LicenseManager.validate_license()
if not valid_license:
    st.error(license_message)
    st.stop()

# ------------------ LOGIN FUNCTIONALITY ------------------ #
def login():
    st.title("🔑 Admin Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        engine = get_db_connection()
        with engine.connect() as conn:
            query = text("SELECT name, password, property FROM admin_users WHERE username = :username")
            result = conn.execute(query, {"username": username}).fetchone()
            
            if result and bcrypt.checkpw(password.encode(), result[1].encode()):
                st.session_state.authenticated = True
                st.session_state.admin_name = result[0]
                st.session_state.admin_property = result[2]  # Store admin property access
                st.success(f"Welcome, {st.session_state.admin_name}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

# Force login if not authenticated
if not st.session_state.authenticated:
    login()
    st.stop()

# ------------------ STREAMLIT UI SETUP ------------------ #
menu_options = ["CRM Main Dashboard", "Register User", "Logout"]
if st.session_state.admin_property == "All":
    menu_options.insert(1, "Admin User Creation")  # Show admin creation only if user manages "All"

menu_option = st.sidebar.radio("Navigation", menu_options)

# ------------------ LOGOUT FUNCTION ------------------ #
if menu_option == "Logout":
    st.session_state.authenticated = False
    st.session_state.admin_name = ""
    st.session_state.admin_property = ""
    st.success("Logged out successfully.")
    st.rerun()

# -------------------- CRM MAIN DASHBOARD -------------------- #
if menu_option == "CRM Main Dashboard":
    st.title("📊 CRM Dashboard")
    
    # Fetch tickets
    
    

    all_tickets_df = fetch_tickets(st.session_state.admin_property)
    tickets_df = all_tickets_df  
    
    if not tickets_df.empty:
        st.subheader("🎟️ Open Tickets")
        st.dataframe(tickets_df)
        
        ticket_id = st.selectbox("Select Ticket ID to update", tickets_df["id"].tolist())
        selected_ticket = tickets_df[tickets_df["id"] == ticket_id].iloc[0]
        
        st.write(f"**Issue:** {selected_ticket['issue_description']}")
        st.write(f"**Property:** {selected_ticket['property']}")
        st.write(f"**Status:** {selected_ticket['status']}")
        
        new_status = st.selectbox("Update Status", ["Open", "In Progress", "Resolved"], 
                                  index=["Open", "In Progress", "Resolved"].index(selected_ticket["status"]))
        
        if st.button("Update Status"):
            update_ticket_status(ticket_id, new_status)
            st.success(f"Ticket #{ticket_id} status updated to {new_status}!")
            st.rerun()
        
        update_text = st.text_area("Add Update")
        admin_name = st.session_state.admin_name  # Automatically assign logged-in admin name
        
        if st.button("Submit Update"):
            if update_text:
                add_ticket_update(ticket_id, update_text, admin_name)
                st.success("Update added successfully!")
                st.rerun()
            else:
                st.error("Please provide update text.")
    else:
        st.warning("No tickets found.")
 
        
        
# ------------------  USER registration ------------------ #
elif menu_option == "Register User":
    
    def is_registered_user(whatsapp_number):
        """Checks if the WhatsApp number is registered in the database."""
        engine = get_db_connection()
        with engine.connect() as conn:
            query = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number")
            result = conn.execute(query, {"whatsapp_number": whatsapp_number}).fetchone()
        return result is not None
    
    user_registration_page() 
        
# -------------------- ADMIN USER CREATION -------------------- #
if menu_option == "Admin User Creation":
    st.title("👤 Admin User Creation")
    
    def create_admin_user(name, username, password, property):
        engine = get_db_connection()
        with engine.connect() as conn:
            try:
                check_query = text("SELECT id FROM admin_users WHERE username = :username")
                existing_admin = conn.execute(check_query, {"username": username}).fetchone()
                
                if existing_admin:
                    return False, "Admin user already exists."
                
                hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                
                insert_query = text("""
                    INSERT INTO admin_users (name, username, password, property) 
                    VALUES (:name, :username, :password, :property)
                """)
                conn.execute(insert_query, {
                    "name": name,
                    "username": username,
                    "password": hashed_password,
                    "property": property
                })
                conn.commit()
                
                return True, "Admin user created successfully!"
            except Exception as e:
                return False, f"Error creating admin user: {e}"
    
    with st.form("admin_user_form"):
        name = st.text_input("Full Name", placeholder="Enter admin's full name")
        username = st.text_input("Username", placeholder="Enter a unique username")
        password = st.text_input("Password", type="password", placeholder="Enter a strong password")
        property = st.text_input("Property", placeholder="Enter property name (or 'All' for super admin)")
        submit_button = st.form_submit_button("Create Admin User")
    
    if submit_button:
        if name and username and password and property:
            success, message = create_admin_user(name, username, password, property)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
        else:
            st.warning("Please fill in all fields.")
    
    st.subheader("Registered Admin Users")
    
    def fetch_admin_users():
        engine = get_db_connection()
        with engine.connect() as conn:
            query = text("SELECT id, name, username, property FROM admin_users")
            result = conn.execute(query)
            admins = result.fetchall()
        return admins
    
    admins = fetch_admin_users()
    
    if admins:
        df = pd.DataFrame(admins, columns=["ID", "Name", "Username", "Property"])
        st.dataframe(df)
    else:
        st.warning("No admin users registered yet.")