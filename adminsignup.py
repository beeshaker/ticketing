import streamlit as st
import bcrypt  
from sqlalchemy.sql import text
from conn import get_db_connection

st.title("📝 Admin Signup")

# Collect name, username, password
name = st.text_input("Full Name")
username = st.text_input("Username")
password = st.text_input("Password", type="password")

# Fetch properties for dropdown
engine = get_db_connection()
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, name FROM properties"))
    properties = result.fetchall()
    property_options = {row.property_name: row.id for row in properties}

# Show dropdown for property
selected_property_name = st.selectbox("Select Property", list(property_options.keys()))
property_id = property_options[selected_property_name]

if st.button("Sign Up"):
    if name and username and password:
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with engine.connect() as conn:
            try:
                check_query = text("SELECT id FROM admin_users WHERE username = :username")
                existing_user = conn.execute(check_query, {"username": username}).fetchone()
                
                if existing_user:
                    st.error("Username already exists. Choose another.")
                else:
                    insert_query = text("""
                        INSERT INTO admin_users (name, username, password, property_id)
                        VALUES (:name, :username, :password, :property_id)
                    """)
                    conn.execute(insert_query, {
                        "name": name,
                        "username": username,
                        "password": hashed_password,
                        "property_id": property_id
                    })
                    conn.commit()
                    st.success("Admin account created successfully! You can now log in.")
            except Exception as e:
                st.error(f"Error creating account: {e}")
    else:
        st.warning("Please fill in all fields.")
