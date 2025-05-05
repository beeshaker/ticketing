import streamlit as st
from conn import Conn

def edit_admins():

    db = Conn()

    # Check role
    if st.session_state.get("admin_role") != "Super Admin":
        st.error("Access denied: Only Super Admins can view this page.")
        st.stop()

    st.title("🛠️ Edit or Delete Admin User")

    # Fetch admin users
    admins = db.get_all_admin_users()
    admin_options = {f"{a['name']} ({a['username']})": a for a in admins}
    selected_label = st.selectbox("Select Admin", list(admin_options.keys()))
    admin = admin_options[selected_label]

    # Pre-fill fields (excluding password)
    name = st.text_input("Name", admin['name'])
    username = st.text_input("Username", admin['username'])
    whatsapp_number = st.text_input("WhatsApp Number", admin['whatsapp_number'])
    admin_type = st.selectbox("Admin Type", ["Admin", "Property Manager", "Caretaker"], index=["Admin", "Property Manager", "Caretaker"].index(admin['admin_type']))
    property_id = st.text_input("Property ID", admin['property_id'] if admin['property_id'] is not None else "")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Update Admin"):
            db.update_admin_user(admin['id'], name, username, whatsapp_number, admin_type, property_id or None)
            st.success("✅ Admin updated.")

    with col2:
        if st.button("Delete Admin"):
            db.delete_admin_user(admin['id'])
            st.success("🗑️ Admin deleted.")
