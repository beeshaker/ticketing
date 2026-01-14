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
    if not properties:
        st.warning("No properties found.")
        st.stop()

    prop_options = {f"{p['name']} (ID {p['id']})": p for p in properties}

    selected_prop_label = st.selectbox("Select Property", list(prop_options.keys()))
    prop = prop_options[selected_prop_label]

    # Fetch Property Managers (returns all managers per your note)
    managers = db.get_available_property_managers() or []

    # ✅ Manager dropdown options WITH a None option
    manager_options = {"None (Unassigned)": None}
    manager_options.update({f"{m['name']} (ID {m['id']})": m["id"] for m in managers})

    # Pre-fill fields
    name = st.text_input("Property Name", prop.get("name", ""))

    # ✅ Show current supervisor clearly (even if NULL)
    current_supervisor_id = prop.get("supervisor_id")
    if current_supervisor_id is None:
        current_supervisor_label = "None (Unassigned)"
    else:
        match = next((m for m in managers if m.get("id") == current_supervisor_id), None)
        current_supervisor_label = (
            f"{match['name']} (ID {match['id']})" if match else f"Assigned (ID {current_supervisor_id})"
        )

    st.info(f"👤 Current Supervisor: **{current_supervisor_label}**")

    # ✅ Preselect the current supervisor (or None)
    labels = list(manager_options.keys())
    values = list(manager_options.values())
    default_index = values.index(current_supervisor_id) if current_supervisor_id in values else 0

    selected_supervisor_label = st.selectbox(
        "Supervisor (Property Manager)",
        labels,
        index=default_index
    )
    supervisor_id_val = manager_options[selected_supervisor_label]  # can be None

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Update Property"):
            try:
                db.update_property(prop["id"], name, supervisor_id_val)  # supervisor_id_val may be None (NULL)
                st.success("✅ Property updated successfully.")
                st.rerun()
            except ValueError as e:
                st.error(f"Error: {str(e)}")
            except Exception as e:
                st.error(f"Unexpected error: {str(e)}")

    with col2:
        if st.button("Delete Property"):
            st.session_state["delete_mode"] = prop["id"]  # Track property being deleted

        if st.session_state.get("delete_mode") == prop["id"]:
            admin_count = db.count_admin_users_by_property(prop["id"])
            ticket_count = db.count_tickets_by_property(prop["id"])

            with st.expander("⚙️ Advanced Delete Options"):
                st.warning(f"⚠️ This property has {admin_count} admin(s) and {ticket_count} ticket(s) linked.")

                option = st.radio(
                    "Choose delete strategy:",
                    [
                        "Reassign all linked data to another property",
                        "Delete all linked data and then delete this property",
                    ],
                    key="delete_strategy",
                )

                if option == "Reassign all linked data to another property":
                    reassignment_options = [p for p in properties if p["id"] != prop["id"]]

                    if reassignment_options:
                        reassign_map = {f"{p['name']} (ID {p['id']})": p["id"] for p in reassignment_options}
                        selected_reassign = st.selectbox(
                            "Reassign to:",
                            list(reassign_map.keys()),
                            key="reassign_choice",
                        )
                        new_property_id = reassign_map[selected_reassign]

                        if st.button("Reassign & Delete", key="reassign_delete_btn"):
                            db.reassign_admin_users(prop["id"], new_property_id)
                            db.reassign_tickets(prop["id"], new_property_id)
                            db.delete_property(prop["id"])
                            st.success("✅ Property deleted after reassignment.")
                            st.session_state["delete_mode"] = None
                            st.rerun()
                    else:
                        st.error("❌ No other property available for reassignment.")

                elif option == "Delete all linked data and then delete this property":
                    confirm_delete_all = st.checkbox(
                        "⚠️ I understand that all related tickets will be deleted and admin users will be unlinked.",
                        key="delete_confirm",
                    )
                    if confirm_delete_all and st.button("Delete All & Remove Property", key="delete_all_btn"):
                        db.null_admins_by_property(prop["id"])
                        db.delete_tickets_by_property(prop["id"])
                        db.delete_property(prop["id"])
                        st.success("🗑️ Property and all related data deleted.")
                        st.session_state["delete_mode"] = None
                        st.rerun()
