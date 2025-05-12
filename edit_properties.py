import streamlit as st
from conn import Conn

def edit_properties():
    db = Conn()

    # Super Admin check
    if st.session_state.get("admin_role") != "Super Admin":
        st.error("Access denied: Only Super Admins can view this page.")
        st.stop()

    st.title("🏢 Edit or Delete Property")

    # Fetch all properties
    properties = db.get_all_properties()
    prop_options = {f"{p['name']} (ID {p['id']})": p for p in properties}

    selected_label = st.selectbox("Select Property", list(prop_options.keys()))
    prop = prop_options[selected_label]

    # Fetch Property Managers
    managers = db.get_available_property_managers()
    manager_options = {f"{m['name']} (ID {m['id']})": m for m in managers}

    # Pre-fill fields
    name = st.text_input("Property Name", prop['name'])
    selected_supervisor_label = None
    if prop.get("supervisor_id"):
        selected_supervisor_label = next(
            (k for k, v in manager_options.items() if v['id'] == prop['supervisor_id']), None
        )

    selected_label = st.selectbox(
        "Supervisor (Property Manager)",
        list(manager_options.keys()),
        index=list(manager_options.keys()).index(selected_supervisor_label) if selected_supervisor_label else 0
    )
    supervisor_id_val = manager_options[selected_label]['id']

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Update Property"):
            try:
                db.update_property(prop['id'], name, supervisor_id_val)
                st.success("✅ Property updated successfully.")
            except ValueError as e:
                st.error(f"Error: {str(e)}")

    with col2:
        if st.button("Delete Property"):
            admin_count = db.count_admin_users_by_property(prop['id'])
            ticket_count = db.count_tickets_by_property(prop['id'])

            if admin_count > 0 or ticket_count > 0:
                st.warning(f"⚠️ This property has {admin_count} admin(s) and {ticket_count} ticket(s) linked.")

                reassignment_options = [p for p in properties if p['id'] != prop['id']]
                if reassignment_options:
                    reassign_map = {f"{p['name']} (ID {p['id']})": p['id'] for p in reassignment_options}
                    selected_reassign = st.selectbox("Reassign related records to:", list(reassign_map.keys()))
                    new_property_id = reassign_map[selected_reassign]

                    if st.button("Reassign & Delete"):
                        db.reassign_admin_users(prop['id'], new_property_id)
                        db.reassign_tickets(prop['id'], new_property_id)
                        db.delete_property(prop['id'])
                        st.success("✅ Property deleted after reassignment.")
                        st.rerun()
                else:
                    st.error("❌ No other property available for reassignment. Cannot delete.")
            else:
                if st.button("Confirm Delete"):
                    db.delete_property(prop['id'])
                    st.success("🗑️ Property deleted.")
                    st.rerun()
