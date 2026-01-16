import streamlit as st
from conn import Conn

db = Conn()

def create_ticket(admin_id):
    st.title("🛠️ Create Internal Ticket")

    # 1) Fetch + display property options
    properties = db.get_all_ticket_properties() or []
    if not properties:
        st.warning("No properties found. Please create a property first.")
        return

    property_names = [f"{p['name']} (ID: {p['id']})" for p in properties]
    selected_property_name = st.selectbox("Select Property", property_names)

    selected_property = next(
        (p for p in properties if f"(ID: {p['id']})" in selected_property_name),
        None
    )
    property_id = selected_property["id"] if selected_property else None

    # 2) Get unit numbers for selected property
    units = db.get_units_by_property(property_id) or []
    unit_numbers = ["Internal"] + [u["unit_number"] for u in units]
    selected_unit = st.selectbox("Select Unit", unit_numbers)

    # 3) Ticket info fields
    issue_description = st.text_area("Issue Description")
    category = st.selectbox("Category", ["Accounts", "Plumbing", "Electricity", "Other"])

    # 4) Admin selection
    admins = db.fetch_all_admin_users() or []
    if not admins:
        st.error("No admins found. Please create an admin user first.")
        return

    admin_display = [f"{a['name']} (ID: {a['id']})" for a in admins]
    selected_admin = st.selectbox("Assign To", admin_display)
    assigned_admin_id = int(selected_admin.split("ID:")[-1].strip(")"))

    # 5) Determine user_id based on unit selection
    if selected_unit == "Internal":
        user_id = 15  # Internal admin placeholder user ID
    else:
        user_id = db.get_user_id_by_unit_and_property(selected_unit, property_id)
        if not user_id:
            st.error("⚠️ No user found for the selected unit and property.")
            st.stop()

    # 6) Submit
    if st.button("Submit Ticket"):
        if property_id and selected_unit and issue_description and assigned_admin_id:
            # ✅ FIXES:
            # - assigned_admin variable was undefined -> use assigned_admin_id
            # - pass property_id correctly
            ticket_id = db.insert_ticket_and_get_id(
                user_id=user_id,
                description=issue_description,
                category=category,
                property_id=property_id,
                assigned_admin=assigned_admin_id
            )

            # ✅ Notify assigned admin via WhatsApp
            new_admin_info = next(
                (admin for admin in admins if str(admin["id"]) == str(assigned_admin_id)),
                None
            )

            if new_admin_info:
                new_admin_name = new_admin_info.get("name", "Admin")
                new_admin_whatsapp = new_admin_info.get("whatsapp_number")

                admin_name = st.session_state.get("admin_name", "Admin")

                # Notify assigned admin (template)
                if new_admin_whatsapp:
                    try:
                        db.send_template_notification(
                            to=new_admin_whatsapp,
                            template_name="ticket_reassignment",
                            template_parameters=[f"#{ticket_id}", admin_name, "New ticket assignment"]
                        )
                    except Exception as notify_err:
                        st.warning(f"⚠️ WhatsApp notification failed: {notify_err}")

                # If assigned admin is a caretaker, notify supervisor if creator isn't the supervisor
                if new_admin_info.get("admin_type") == "Caretaker":
                    supervisor = db.get_property_supervisor_by_property(property_id)

                    if supervisor and supervisor.get("whatsapp_number"):
                        if str(supervisor.get("id")) != str(admin_id):
                            try:
                                db.send_template_notification(
                                    to=supervisor["whatsapp_number"],
                                    template_name="caretaker_task_alert",
                                    template_parameters=[f"#{ticket_id}", new_admin_name]
                                )
                                st.success("✅ Supervisor notified successfully.")
                            except Exception as sup_notify_err:
                                st.warning(f"❌ Supervisor alert failed: {sup_notify_err}")
                        else:
                            st.info("ℹ️ Supervisor is the one who created the ticket. No notification sent.")
                    else:
                        st.warning("⚠️ No supervisor found for this property (or supervisor has no WhatsApp number).")

                st.success(f"✅ Ticket #{ticket_id} created and assigned to {new_admin_name}")
            else:
                st.success(f"✅ Ticket #{ticket_id} created.")

        else:
            st.error("Please complete all fields.")
