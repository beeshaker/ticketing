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
    if not admins:
        st.warning("No admin users found.")
        return

    admin_options = {f"{a['name']} ({a['username']})": a for a in admins}
    selected_label = st.selectbox("Select Admin", list(admin_options.keys()))
    admin = admin_options[selected_label]

    admin_type_options = [
        "Admin",
        "Property Supervisor",
        "Caretaker",
        "Technician",
        "Super Admin",
    ]

    current_admin_type = admin.get("admin_type", "Admin")
    if current_admin_type not in admin_type_options:
        current_admin_type = "Admin"

    # Pre-fill fields
    name = st.text_input("Name", admin["name"])
    username = st.text_input("Username", admin["username"])
    whatsapp_number = st.text_input("WhatsApp Number", admin["whatsapp_number"] or "")

    admin_type = st.selectbox(
        "Admin Type",
        admin_type_options,
        index=admin_type_options.index(current_admin_type),
    )

    # Only Caretaker and Property Supervisor should keep property_id
    property_disabled = admin_type not in ["Property Supervisor", "Caretaker"]
    property_id = st.text_input(
        "Property ID",
        str(admin["property_id"]) if admin["property_id"] is not None else "",
        disabled=property_disabled,
        help="Only Property Supervisors and Caretakers should have a Property ID.",
    )

    col1, col2 = st.columns(2)

    with st.expander("🔐 Reset Password"):
        new_pass = st.text_input("New Password", type="password")
        confirm_pass = st.text_input("Confirm Password", type="password")

        if st.button("Reset Password"):
            if new_pass != confirm_pass:
                st.error("❌ Passwords do not match.")
            elif len(new_pass) < 6:
                st.error("❌ Password must be at least 6 characters.")
            else:
                db.reset_admin_password(admin["id"], new_pass)
                st.success("✅ Password updated successfully.")

    with col1:
        if st.button("Update Admin"):
            final_property_id = property_id.strip() if not property_disabled and property_id else None
            db.update_admin_user(
                admin["id"],
                name,
                username,
                whatsapp_number,
                admin_type,
                final_property_id,
            )
            st.success("✅ Admin updated.")
            st.rerun()

    with col2:
        if st.button("Delete Admin"):
            db.delete_admin_user(admin["id"])
            st.success("🗑️ Admin deleted.")
            st.rerun()