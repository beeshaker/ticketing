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
    prop = prop_options[selected_label]  # ✅ Now prop is a dict

    # Fetch available Property Managers (supervisors)
    managers = db.get_available_property_managers()
    manager_options = {f"{m['name']} (ID {m['id']})": m['id'] for m in managers}

    # Pre-fill fields
    name = st.text_input("Property Name", prop['name'])
    selected_supervisor_label = None
    if prop.get("supervisor_id"):
        selected_supervisor_label = next((k for k, v in manager_options.items() if v == prop['supervisor_id']), None)

    supervisor_id = st.selectbox("Supervisor (Property Manager)", list(manager_options.keys()), index=list(manager_options.keys()).index(selected_supervisor_label) if selected_supervisor_label else 0)
    supervisor_id_val = manager_options[supervisor_id]

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
            db.delete_property(prop['id'])
            st.success("🗑️ Property deleted.")
