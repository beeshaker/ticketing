import streamlit as st
from conn import Conn

def edit_user():

    db = Conn()

    # Super Admin check
    if st.session_state.get("admin_role") != "Super Admin":
        st.error("Access denied: Only Super Admins can view this page.")
        st.stop()

    st.title("🧑‍💻 Edit or Delete User")

    # Fetch users
    users = db.get_all_users()
    user_options = {f"{u['name']} ({u['whatsapp_number']})": u for u in users}
    selected_label = st.selectbox("Select User", list(user_options.keys()))
    user = user_options[selected_label]

    # Pre-fill editable fields
    name = st.text_input("Name", user['name'])
    whatsapp_number = st.text_input("WhatsApp Number", user['whatsapp_number'])
    property_id = st.text_input("Property ID", user['property_id'])
    unit_number = st.text_input("Unit Number", user['unit_number'] or "")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Update User"):
            db.update_user(user['id'], name, whatsapp_number, property_id, unit_number)
            st.success("✅ User updated successfully.")

    with col2:
        if st.button("Delete User"):
            db.delete_user(user['id'])
            st.success("🗑️ User deleted.")
