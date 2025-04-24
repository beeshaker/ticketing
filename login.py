import streamlit as st
from sqlalchemy.sql import text
import bcrypt
from conn import Conn

db = Conn()

# Page Setup
st.set_page_config(page_title="Admin Login", layout="centered")

# Custom CSS for Dark Mode Styling
st.markdown("""
    <style>
    .main {
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        color: white;
    }
    .login-container {
        max-width: 500px;
        margin: 5rem auto;
        padding: 3rem 2rem;
        background-color: #1e1e1e;
        border-radius: 12px;
        box-shadow: 0 0 15px rgba(0,0,0,0.5);
    }
    .login-title {
        font-size: 2.5rem;
        font-weight: bold;
        color: #FFD93D;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stTextInput > div > input {
        background-color: #2c2c2c;
        color: #fff;
        border-radius: 0.5rem;
        padding: 0.75rem;
        border: 1px solid #444;
    }
    .stTextInput > label {
        color: #ccc;
    }
    .stButton button {
        background-color: #FFD93D;
        color: #000;
        border: none;
        border-radius: 0.5rem;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
    }
    .stButton button:hover {
        background-color: #ffc400;
        color: #000;
    }
    </style>
""", unsafe_allow_html=True)

def login():
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🔑 Admin Login</div>', unsafe_allow_html=True)

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
