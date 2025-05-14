import streamlit as st
from sqlalchemy.sql import text
import bcrypt
from conn import Conn

db = Conn()

def login():
    # Centered logo using columns
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("logo1.png", use_container_width=True)

    st.title("🎫 Ticketing System - Login")

    # Input fields
    username = st.text_input("Username").strip()
    password = st.text_input("Password", type="password").strip()

    if st.button("Login"):
        engine = db.engine
        with engine.connect() as conn:
            query = text("SELECT name, id, password, admin_type FROM admin_users WHERE username = :username")
            result = conn.execute(query, {"username": username}).fetchone()

            if result:
                name, admin_id, hashed_pw, admin_type = result

                # Ensure stored hash is bytes
                if isinstance(hashed_pw, str):
                    hashed_pw = hashed_pw.strip().encode()

                if bcrypt.checkpw(password.encode(), hashed_pw):
                    # Set session values
                    st.session_state.authenticated = True
                    st.session_state.admin_name = name
                    st.session_state.admin_id = admin_id
                    st.session_state.admin_role = admin_type
                    st.success(f"✅ Welcome, {name}!")
                    st.experimental_rerun()
                else:
                    st.error("❌ Invalid password.")
            else:
                st.error("❌ Username not found.")

    # Optionally show debug state (remove this in prod)
    # st.write("Session:", dict(st.session_state))
