import streamlit as st
import bcrypt  
from sqlalchemy.sql import text
from conn import get_db_connection

st.title("📝 Admin Signup")
name = st.text_input("Full Name")
username = st.text_input("Username")
password = st.text_input("Password", type="password")
property_name = st.text_input("Property Name")

if st.button("Sign Up"):
    if name and username and password and property_name:
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        engine = get_db_connection()
        with engine.connect() as conn:
            try:
                check_query = text("SELECT id FROM admin_users WHERE username = :username")
                existing_user = conn.execute(check_query, {"username": username}).fetchone()
                
                if existing_user:
                    st.error("Username already exists. Choose another.")
                else:
                    insert_query = text("""
                        INSERT INTO admin_users (name, username, password, property)
                        VALUES (:name, :username, :password, :property)
                    """)
                    conn.execute(insert_query, {
                        "name": name,
                        "username": username,
                        "password": hashed_password,
                        "property": property_name
                    })
                    conn.commit()
                    st.success("Admin account created successfully! You can now log in.")
            except Exception as e:
                st.error(f"Error creating account: {e}")
    else:
        st.warning("Please fill in all fields.")