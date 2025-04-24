import streamlit as st
from sqlalchemy.sql import text
import bcrypt
from conn import Conn

db = Conn()

def login():
    

    col1, col2, col3 = st.columns([1, 2, 1])  # Create 3 columns with the center one being wider
    with col2:
        st.image("logo1.png", use_container_width =True)  # Adjust the path to your logo file



    st.title("Ticketing System - Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        engine = db.engine
        with engine.connect() as conn:
            query = text("SELECT name, id, password, admin_type FROM admin_users WHERE username = :username")
            result = conn.execute(query, {"username": username}).fetchone()

            if result and bcrypt.checkpw(password.encode(), result[2].encode()):
                st.session_state.authenticated = True
                st.session_state.admin_name = result[0]
                st.session_state.admin_id = result[1]
                st.session_state.admin_role = result[3]
                st.success(f"Welcome, {st.session_state.admin_name}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
    
    st.markdown('</div>', unsafe_allow_html=True)
