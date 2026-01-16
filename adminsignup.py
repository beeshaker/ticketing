import streamlit as st
import bcrypt
from sqlalchemy.sql import text
from conn import Conn  # use your Conn class


def admin_signup():
    st.title("📝 Admin Signup")

    db = Conn()

    # --- UI role labels (DB stays the same) ---
    ROLE_LABELS = {
        "Property Supervisor": "Property Supervisor",  # UI label only
        "Super Admin": "Super Admin",
        "Procurement Admin": "Procurement Admin",
    }
    ROLE_LABELS_REV = {v: k for k, v in ROLE_LABELS.items()}

    # Collect name, username, password
    name = st.text_input("Full Name")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Choose role in UI (optional, you can hardcode if you want)
    role_ui = st.selectbox(
        "Admin Role",
        ["Property Supervisor", "Super Admin", "Procurement Admin"],
        index=0
    )
    admin_type_db = ROLE_LABELS_REV.get(role_ui, role_ui)  # convert UI -> DB value

    # Fetch properties for dropdown
    with db.engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM properties ORDER BY name")).mappings().all()

    property_options = {r["name"]: r["id"] for r in rows}

    # If no properties exist
    if not property_options:
        st.warning("No properties found. Create a property first.")
        st.stop()

    selected_property_name = st.selectbox("Select Property", list(property_options.keys()))
    property_id = property_options[selected_property_name]

    if st.button("Sign Up"):
        if not (name and username and password):
            st.warning("Please fill in all fields.")
            st.stop()

        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        try:
            with db.engine.begin() as conn:
                existing_user = conn.execute(
                    text("SELECT id FROM admin_users WHERE username = :username"),
                    {"username": username}
                ).fetchone()

                if existing_user:
                    st.error("Username already exists. Choose another.")
                    st.stop()

                conn.execute(
                    text("""
                        INSERT INTO admin_users (name, username, password, property_id, admin_type)
                        VALUES (:name, :username, :password, :property_id, :admin_type)
                    """),
                    {
                        "name": name,
                        "username": username,
                        "password": hashed_password,
                        "property_id": property_id,
                        "admin_type": admin_type_db  # ✅ stored as DB canonical role
                    }
                )

            st.success("Admin account created successfully! You can now log in.")

        except Exception as e:
            st.error(f"Error creating account: {e}")
