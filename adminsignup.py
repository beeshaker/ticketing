import streamlit as st
import pandas as pd
import bcrypt
from sqlalchemy.sql import text

from conn import Conn  # ✅ use your Conn class


def admin_signup():
    st.title("👤 Admin User Creation")

    db = Conn()

    def create_admin_user(name, username, password, whatsapp_number, property_id, admin_type):
        engine = db.engine
        try:
            with engine.begin() as conn:
                existing_admin = conn.execute(
                    text("SELECT id FROM admin_users WHERE username = :username"),
                    {"username": username},
                ).fetchone()

                if existing_admin:
                    return False, "Admin user already exists."

                hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

                # ✅ Only caretakers get property_id here (as per your logic)
                final_property_id = (
                    property_id
                    if (admin_type == "Caretaker" and property_id is not None)
                    else None
                )

                conn.execute(
                    text("""
                        INSERT INTO admin_users (name, username, password, whatsapp_number, property_id, admin_type)
                        VALUES (:name, :username, :password, :whatsapp_number, :property_id, :admin_type)
                    """),
                    {
                        "name": name,
                        "username": username,
                        "password": hashed_password,
                        "whatsapp_number": whatsapp_number,
                        "property_id": final_property_id,
                        "admin_type": admin_type,
                    },
                )

            return True, "✅ Admin user created successfully!"

        except Exception as e:
            return False, f"❌ Error creating admin user: {e}"

    # -------------------- Properties for dropdown -------------------- #
    property_list = db.get_all_properties() or []
    property_options = {f"{p['name']} (ID {p['id']})": p["id"] for p in property_list}
    property_label_list = ["None"] + list(property_options.keys())

    # -------------------- Form -------------------- #
    with st.form("admin_user_form"):
        name = st.text_input("Full Name", placeholder="Enter admin's full name")
        whatsapp_number = st.text_input("WhatsApp Number", placeholder="Eg 254724123456")
        username = st.text_input("Username", placeholder="Enter a unique username")
        password = st.text_input("Password", type="password", placeholder="Enter a strong password")

        # ✅ CHANGED LABEL: Property Manager -> Property Supervisor
        if st.session_state.get("admin_role") == "Super Admin":
            admin_type = st.selectbox(
                "Admin Type",
                ["Super Admin", "Admin", "Property Supervisor", "Caretaker"],
            )
        else:
            admin_type = st.selectbox(
                "Admin Type",
                ["Admin", "Property Supervisor", "Caretaker"],
            )

        selected_label = st.selectbox("Assign Property (Caretakers only)", property_label_list)
        property_id = property_options.get(selected_label) if selected_label != "None" else None

        submit_button = st.form_submit_button("Create Admin User")

    if submit_button:
        if not (name and username and password and whatsapp_number):
            st.warning("Please fill in all fields.")
        else:
            success, message = create_admin_user(
                name=name,
                username=username,
                password=password,
                whatsapp_number=whatsapp_number,
                property_id=property_id,
                admin_type=admin_type,
            )
            st.success(message) if success else st.error(message)
            if success:
                st.rerun()

    # -------------------- Registered Admin Users -------------------- #
    st.subheader("Registered Admin Users")

    with db.engine.connect() as conn:
        admins = conn.execute(
            text("""
                SELECT a.id, a.name, a.username, a.admin_type, p.name AS property
                FROM admin_users a
                LEFT JOIN properties p ON a.property_id = p.id
                ORDER BY a.id DESC
            """)
        ).fetchall()

    if admins:
        df = pd.DataFrame(admins, columns=["ID", "Name", "Username", "Type"])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.warning("No admin users registered yet.")
