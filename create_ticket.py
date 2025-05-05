import streamlit as st
from conn import Conn

db = Conn()

def create_ticket(admin_id):
    st.title("🛠️ Create Internal Ticket")

    # 1. Fetch and display property options
    properties = db.get_all_ticket_properties()
    property_names = [f"{p['name']} (ID: {p['id']})" for p in properties]
    selected_property_name = st.selectbox("Select Property", property_names)

    selected_property = next((p for p in properties if f"(ID: {p['id']})" in selected_property_name), None)
    property_id = selected_property['id'] if selected_property else None

    # 2. Get unit numbers based on selected property

    units = db.get_units_by_property(property_id) or []
    unit_numbers = ["None"] + [u['unit_number'] for u in units]
    selected_unit = st.selectbox("Select Unit", unit_numbers)


    # 3. Ticket info fields
    issue_description = st.text_area("Issue Description")
    category = st.selectbox("Category", ["Accounts", "Plumbing", "Electricity", "Other"])

    # 4. Admin selection (including self)
    admins = db.fetch_admin_users()
    admin_display = [f"{a['name']} (ID: {a['id']})" for a in admins]
    selected_admin = st.selectbox("Assign To", admin_display)
    assigned_admin_id = int(selected_admin.split("ID:")[-1].strip(")"))
    # 3. Determine user_id based on unit selection
    if selected_unit == "None":
        user_id = admin_id
    else:
        user_id = db.get_user_id_by_unit_and_property(selected_unit, property_id)
        if not user_id:
            user_id = admin_id
    if not user_id:
        st.error("No user found for this unit and property.")
               

    if st.button("Submit Ticket"):
        if property_id and selected_unit and issue_description and assigned_admin_id:
            
            
            st.write("Creating ticket with:", {
                "user_id": user_id,
                "property_id": property_id,
                "unit_number": selected_unit,
                "admin_id": assigned_admin_id
            })

            ticket_id = db.insert_ticket_and_get_id(
                user_id=user_id,
                description=issue_description,
                category=category,
                property=property_id,
                assigned_admin=assigned_admin_id
            )

            # ✅ Notify assigned admin via WhatsApp
            new_admin_info = next((admin for admin in admins if str(admin["id"]) == str(assigned_admin_id)), None)
            if new_admin_info:
                new_admin_name = new_admin_info["name"]
                new_admin_whatsapp = new_admin_info.get("whatsapp_number")
                if new_admin_whatsapp:
                    try:
                        db.send_template_notification(
                            to=new_admin_whatsapp,
                            template_name="ticket_reassignment",
                            template_parameters=[f"#{ticket_id}", new_admin_name, "New ticket assignment"]
                        )
                    except Exception as notify_err:
                        st.warning(f"⚠️ WhatsApp notification failed: {notify_err}")

            st.success(f"✅ Ticket #{ticket_id} created and assigned to {new_admin_info['name']}")
        else:
            st.error("Please complete all fields.")
