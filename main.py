import streamlit as st
st.set_page_config(page_title="CRM Admin Portal", layout="wide")

import os
import pandas as pd
import bcrypt
from io import BytesIO
from sqlalchemy.sql import text
from streamlit_timeline import timeline
from streamlit_option_menu import option_menu
from streamlit_autorefresh import st_autorefresh
from conn import Conn
from license import LicenseManager
from login import login
from user_registration import user_registration_page
from create_ticket import create_ticket
from edit_admins import edit_admins
from edit_properties import edit_properties
from edit_users import edit_user


# -----------------------------------------------------------------------------
# Init
# -----------------------------------------------------------------------------
db = Conn()

# Session State for Authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.admin_name = ""
    st.session_state.admin_role = ""
    st.session_state.admin_id = None

# License check
valid_license, license_message = LicenseManager.validate_license()
if not valid_license:
    st.error(license_message)
    st.stop()

# Force login if not authenticated
if not st.session_state.authenticated:
    login()
    st.stop()

# -----------------------------------------------------------------------------
# Sidebar Menu
# -----------------------------------------------------------------------------
st.sidebar.write("Current role:", st.session_state.get("admin_role", ""))

menu_options = ["Dashboard", "Create Ticket", "Logout"]
menu_icons = ["bar-chart", "file-earmark-plus", "box-arrow-right"]

# Admin role menus
if st.session_state.admin_role == "Admin":
    menu_options.insert(1, "Admin User Creation")
    menu_icons.insert(1, "person-gear")

    menu_options.insert(2, "Register User")
    menu_icons.insert(2, "person-plus")

    menu_options.insert(3, "Create Property")
    menu_icons.insert(3, "building")

elif st.session_state.admin_role == "Super Admin":
    menu_options.insert(1, "Admin User Creation")
    menu_icons.insert(1, "person-plus")

    menu_options.insert(2, "Edit/Delete Admin")
    menu_icons.insert(2, "person-x")

    menu_options.insert(3, "Register User")
    menu_icons.insert(3, "person-fill-add")

    menu_options.insert(4, "Edit/Delete User")
    menu_icons.insert(4, "person-fill-x")

    menu_options.insert(5, "Create Property")
    menu_icons.insert(5, "building-add")

    menu_options.insert(6, "Edit/Delete Property")
    menu_icons.insert(6, "building-gear")

    menu_options.insert(7, "Send Bulk Message")
    menu_icons.insert(7, "envelope-paper-fill")

    # If you actually want this page, keep it in menu:
    menu_options.insert(8, "Admin Reassignment History")
    menu_icons.insert(8, "clock-history")

with st.sidebar:
    selected = option_menu(
        menu_title="Main Menu",
        options=menu_options,
        icons=menu_icons,
        menu_icon="cast",
        default_index=0,
        orientation="vertical",
        styles={
            "container": {"padding": "5px", "background-color": "#1e1e1e"},
            "icon": {"color": "#91cfff", "font-size": "20px"},
            "nav-link": {
                "font-size": "16px",
                "text-align": "left",
                "margin": "5px 0",
                "--hover-color": "#2a2a2a",
                "color": "#dddddd",
            },
            "nav-link-selected": {
                "background-color": "#0a84ff",
                "color": "white",
                "font-weight": "bold",
            },
        },
    )

# -----------------------------------------------------------------------------
# Logout
# -----------------------------------------------------------------------------
if selected == "Logout":
    st.session_state.authenticated = False
    st.session_state.admin_name = ""
    st.session_state.admin_id = None
    st.session_state.admin_role = ""
    st.success("Logged out successfully.")
    st.rerun()

# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------

elif selected == "Dashboard":
    st.title("📊 Operations CRM Dashboard")

    # 1. SILENT TIMER: Runs every 15 seconds to check for DB changes
    st_autorefresh(interval=15000, key="silent_check") 

    # 2. HASH CHECK: Get the current state (Count-MaxID-UnreadCount)
    current_hash = db.get_tickets_hash()
    
    # Initialize session state tracking
    if "last_hash" not in st.session_state:
        st.session_state.last_hash = current_hash
        # Extract Max ID from the hash (the middle number)
        try:
            st.session_state.last_max_id = int(current_hash.split("-")[1])
        except (IndexError, ValueError):
            st.session_state.last_max_id = 0

    # 3. CHANGE DETECTION & NOTIFICATION
    if current_hash != st.session_state.last_hash:
        try:
            new_max_id = int(current_hash.split("-")[1])
        except (IndexError, ValueError):
            new_max_id = st.session_state.last_max_id

        # 🔔 NEW TICKET TOAST: Only if the highest ID increased
        if new_max_id > st.session_state.last_max_id:
            st.toast("🔔 New Ticket Received!", icon="🎫")
        
        # Update state and rerun the app to show new data
        st.session_state.last_hash = current_hash
        st.session_state.last_max_id = new_max_id
        st.rerun()

    # 4. DATA FETCHING: Only happens on first load or after a valid rerun
    if st.session_state.admin_role in ("Admin", "Super Admin"):
        tickets_df = db.fetch_tickets("All")
    else:
        tickets_df = db.fetch_open_tickets(st.session_state.admin_id)

    if tickets_df is None or tickets_df.empty:
        st.info("✅ No open tickets found.")
        st.stop()

    st.subheader("🎟️ Open Tickets")
    
    # Updated to 'stretch' per your requirement
    st.dataframe(tickets_df, width="stretch")

    # 5. TICKET SELECTION LOGIC
    def create_ticket_label(row):
        is_read = row.get("is_read", True) 
        status_icon = "👁️ READ" if is_read else "🔴 NEW"
        desc_snippet = str(row.get('issue_description', 'No Description'))[:40]
        return f"{status_icon} | #{row['id']} - {desc_snippet}..."

    tickets_df['display_label'] = tickets_df.apply(create_ticket_label, axis=1)
    label_to_id_map = dict(zip(tickets_df['display_label'], tickets_df['id']))

    selected_label = st.selectbox(
        "Select Ticket to View", 
        options=tickets_df['display_label'].tolist(),
        key="active_selection" # Persists selection across refreshes
    )

    ticket_id = label_to_id_map[selected_label]

    # 6. AUTO-MARK AS READ
    if 'is_read' in tickets_df.columns:
        selected_row = tickets_df[tickets_df['id'] == ticket_id].iloc[0]
        if not selected_row['is_read']:
            db.mark_ticket_as_read(ticket_id)
            # Update hash immediately so the next silent check doesn't trigger a double refresh
            st.session_state.last_hash = db.get_tickets_hash()
            st.rerun()

    # -------------------------------------------------------------------------
    # Display Details (Existing Logic)
    # -------------------------------------------------------------------------
    
    selected_ticket = tickets_df[tickets_df["id"] == ticket_id].iloc[0]

    # Ticket details
    st.divider()
    st.markdown(f"### 🎫 Ticket #{ticket_id} Details")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Issue:** {selected_ticket['issue_description']}")
        st.write(f"**Category:** {selected_ticket['category']}")
        st.write(f"**Property:** {selected_ticket['property']}")
    with col2:
        st.write(f"**Unit Number:** {selected_ticket['unit_number']}")
        st.write(f"**Status:** {selected_ticket['status']}")
        st.write(f"**Assigned Admin:** {selected_ticket['assigned_admin']}")

    # -------------------- Attached Media -------------------- #
    with st.expander("📎 Attached Files", expanded=False):
        media_df = db.fetch_ticket_media(ticket_id)
        if media_df is None or media_df.empty:
            st.info("No media files attached to this ticket.")
        else:
            for _, row in media_df.iterrows():
                media_type = row["media_type"]
                media_blob = row["media_blob"]
                filename = row.get("filename", "attachment")

                if media_type == "image":
                    st.image(BytesIO(media_blob), caption=filename, width=True)
                elif media_type == "video":
                    st.video(BytesIO(media_blob))
                elif media_type == "document":
                    st.download_button(
                        label=f"📄 Download {filename}",
                        data=media_blob,
                        file_name=filename,
                        mime="application/pdf",
                    )
                else:
                    st.download_button(
                        label=f"📎 Download {filename}",
                        data=media_blob,
                        file_name=filename,
                        mime="application/octet-stream",
                    )

    # -------------------- Ticket History -------------------- #
    with st.expander("📜 Ticket History", expanded=False):
        # ... (Keep your existing CSS and Timeline logic here) ...
        # (I omitted the huge CSS block for brevity, but keep it in your file)
        
        history_df = db.fetch_ticket_history(ticket_id)
        if history_df is None or history_df.empty:
            st.info("No ticket history available.")
        else:
            # ... (Keep your existing timeline event loop) ...
            events = [] 
            # Placeholder for your existing timeline loop logic
            # Be sure to copy your existing loop back in here
            for _, row in history_df.iterrows():
                dt = row["performed_at"]
                events.append({
                    "start_date": {"year": dt.year, "month": dt.month, "day": dt.day, "hour": dt.hour, "minute": dt.minute},
                    "text": {"headline": f"{row['action']}", "text": row['details']}
                })
            
            timeline({"events": events})

    # -------------------- Status Update -------------------- #
    st.markdown("### ✅ Update Status")
    new_status = st.selectbox(
        "Status",
        ["Open", "In Progress", "Resolved"],
        index=["Open", "In Progress", "Resolved"].index(selected_ticket["status"]),
        key="status_select",
    )
    if st.button("Update Status", key="btn_update_status"):
        db.update_ticket_status(ticket_id, new_status)
        st.success(f"✅ Ticket #{ticket_id} status updated to {new_status}!")
        st.rerun()

    # -------------------- Add Update -------------------- #
    st.markdown("### ✍️ Add Ticket Update")
    update_text = st.text_area("Update text", key="update_text")
    admin_name = st.session_state.admin_name
    if st.button("Submit Update", key="btn_submit_update"):
        if not update_text.strip():
            st.error("⚠️ Please provide update text.")
        else:
            db.add_ticket_update(ticket_id, update_text.strip(), admin_name)
            st.success("✅ Update added successfully!")
            st.rerun()

    # -------------------- Reassign Admin -------------------- #
    if st.session_state.admin_role != "Caretaker":
        st.markdown("### 🔄 Reassign Admin")
        admin_users = db.fetch_admin_users()
        admin_options = {admin["id"]: admin["name"] for admin in admin_users}

        current_assigned_name = selected_ticket["assigned_admin"]
        current_assigned_id = None
        for aid, aname in admin_options.items():
            if aname == current_assigned_name:
                current_assigned_id = aid
                break

        available_admins = {k: v for k, v in admin_options.items() if v != current_assigned_name}

        if not available_admins:
            st.info("No other admins available to reassign to.")
        else:
            new_admin_id = st.selectbox(
                "Select New Admin",
                list(available_admins.keys()),
                format_func=lambda x: available_admins[x],
                key="new_admin_select",
            )

            reassign_reason = st.text_area("Reason for Reassignment", key="reassign_reason")

            if st.button("Reassign Ticket", key="btn_reassign"):
                if not reassign_reason.strip():
                    st.error("⚠️ Please provide a reason.")
                elif current_assigned_id is None:
                    st.error("⚠️ Could not resolve current assigned admin ID.")
                else:
                    ok, msg = db.reassign_ticket_admin(
                        ticket_id=ticket_id,
                        new_admin_id=new_admin_id,
                        old_admin_id=current_assigned_id,
                        changed_by_admin=admin_name,
                        reason=reassign_reason.strip(),
                        is_super_admin=(st.session_state.admin_role == "Super Admin"),
                    )
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    # -------------------- Due Date -------------------- #
    st.markdown("### 📅 Set Due Date")
    current_due_date = selected_ticket.get("Due_Date")

    default_due = None
    if current_due_date:
        try:
            default_due = pd.to_datetime(current_due_date).date()
        except Exception:
            default_due = None

    due_date = st.date_input(
        "Select Due Date",
        value=default_due if default_due else pd.Timestamp.today().date(),
        key="due_date_input",
    )

    if st.button("Update Due Date", key="btn_due_date"):
        db.update_ticket_due_date(ticket_id, due_date)
        st.success(f"✅ Due date updated to {due_date.strftime('%Y-%m-%d')}")
        st.rerun()
# -----------------------------------------------------------------------------
# Register User
# -----------------------------------------------------------------------------
elif selected == "Register User":
    user_registration_page()

# -----------------------------------------------------------------------------
# Admin User Creation
# -----------------------------------------------------------------------------
elif selected == "Admin User Creation":
    st.title("👤 Admin User Creation")

    def create_admin_user(name, username, password, whatsapp_number, property_id, admin_type):
        engine = db.engine
        with engine.connect() as conn:
            try:
                existing_admin = conn.execute(
                    text("SELECT id FROM admin_users WHERE username = :username"),
                    {"username": username},
                ).fetchone()

                if existing_admin:
                    return False, "Admin user already exists."

                hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

                # Only caretakers get property_id here (as per your logic)
                final_property_id = property_id if (admin_type == "Caretaker" and property_id is not None) else None

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
                conn.commit()
                return True, "✅ Admin user created successfully!"
            except Exception as e:
                return False, f"❌ Error creating admin user: {e}"

    property_list = db.get_all_properties()
    property_options = {f"{p['name']} (ID {p['id']})": p["id"] for p in property_list}
    property_label_list = ["None"] + list(property_options.keys())

    with st.form("admin_user_form"):
        name = st.text_input("Full Name", placeholder="Enter admin's full name")
        whatsapp_number = st.text_input("WhatsApp Number", placeholder="Eg 254724123456")
        username = st.text_input("Username", placeholder="Enter a unique username")
        password = st.text_input("Password", type="password", placeholder="Enter a strong password")

        if st.session_state.admin_role == "Super Admin":
            admin_type = st.selectbox("Admin Type", ["Super Admin", "Admin", "Property Manager", "Caretaker"])
        else:
            admin_type = st.selectbox("Admin Type", ["Admin", "Property Manager", "Caretaker"])

        selected_label = st.selectbox("Assign Property (Caretakers only)", property_label_list)
        property_id = property_options.get(selected_label) if selected_label != "None" else None

        submit_button = st.form_submit_button("Create Admin User")

    if submit_button:
        if not (name and username and password and whatsapp_number):
            st.warning("Please fill in all fields.")
        else:
            success, message = create_admin_user(name, username, password, whatsapp_number, property_id, admin_type)
            st.success(message) if success else st.error(message)
            if success:
                st.rerun()

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
        df = pd.DataFrame(admins, columns=["ID", "Name", "Username", "Type", "Property"])
        st.dataframe(df, width=True)
    else:
        st.warning("No admin users registered yet.")

# -----------------------------------------------------------------------------
# Create Ticket
# -----------------------------------------------------------------------------
elif selected == "Create Ticket":
    create_ticket(st.session_state.admin_id)

# -----------------------------------------------------------------------------
# Send Bulk Message
# -----------------------------------------------------------------------------
elif selected == "Send Bulk Message":
    st.title("📨 Send 'Notice' Template Message to Property Users")

    property_list = db.get_all_properties()
    if not property_list:
        st.warning("No properties found.")
        st.stop()

    property_options = {f"{p['name']} (ID {p['id']})": p["id"] for p in property_list}
    selected_property_label = st.selectbox("Select Property", list(property_options.keys()))
    selected_property_id = property_options[selected_property_label]
    property_name = selected_property_label.split(" (ID")[0]

    notice_text = st.text_area("Notice Text", placeholder="Write your notice content here")

    if st.button("Send Notice Template"):
        if not notice_text.strip():
            st.error("⚠️ Please enter the notice text.")
            st.stop()

        users = db.get_users_by_property(selected_property_id)
        if not users:
            st.warning("⚠️ No users found for this property.")
            st.stop()

        sent_results = []
        audit_entries = []
        progress = st.progress(0)
        total_users = len(users)

        for idx, user in enumerate(users):
            params = [notice_text.strip(), property_name]
            response = db.send_template_notification(
                to=user["whatsapp_number"],
                template_name="notice",
                template_parameters=params,
            )

            if "error" not in response:
                status = "✅ Success"
            else:
                status = f"❌ Failed - {response['error']}"

            sent_results.append({"Name": user.get("name", "N/A"), "WhatsApp": user["whatsapp_number"], "Status": status})

            audit_entries.append(
                {
                    "property_id": selected_property_id,
                    "property_name": property_name,
                    "user_name": user.get("name", "N/A"),
                    "whatsapp_number": user["whatsapp_number"],
                    "status": status,
                    "template_name": "notice",
                    "notice_text": notice_text.strip(),
                }
            )

            progress.progress((idx + 1) / total_users)

        db.save_bulk_audit(audit_entries)

        st.subheader("📋 Send Status Report")
        report_df = pd.DataFrame(sent_results)
        st.dataframe(report_df, width=True)

        csv_data = report_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇ Download Report as CSV",
            data=csv_data,
            file_name=f"notice_send_report_{property_name.replace(' ', '_')}.csv",
            mime="text/csv",
        )

# -----------------------------------------------------------------------------
# Admin Reassignment History
# -----------------------------------------------------------------------------
elif selected == "Admin Reassignment History":
    st.title("📜 Admin Reassignment History")
    reassign_log_df = db.fetch_admin_reassignment_log()
    if reassign_log_df is not None and not reassign_log_df.empty:
        st.dataframe(reassign_log_df, width=True)
    else:
        st.warning("⚠️ No reassignments have been logged yet.")

# -----------------------------------------------------------------------------
# Create Property
# -----------------------------------------------------------------------------
elif selected == "Create Property":
    st.title("🏘️ Create New Property")

    supervisors = db.get_available_property_managers()
    if not supervisors:
        st.warning("No Property Managers found. Create one first.")
        st.stop()

    supervisor_options = {f"{s['name']} (ID: {s['id']})": s["id"] for s in supervisors}

    with st.form("create_property_form"):
        name = st.text_input("Property Name", placeholder="e.g., Westview Apartments")
        selected_supervisor = st.selectbox("Assign Property Manager", options=list(supervisor_options.keys()))
        submit = st.form_submit_button("Create Property")

    if submit:
        if not name.strip():
            st.error("Please enter a property name.")
        else:
            success, msg = db.create_property(name.strip(), supervisor_options[selected_supervisor])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# -----------------------------------------------------------------------------
# Edit/Delete User
# -----------------------------------------------------------------------------
elif selected == "Edit/Delete User":
    edit_user()

# -----------------------------------------------------------------------------
# Edit/Delete Property
# -----------------------------------------------------------------------------
elif selected == "Edit/Delete Property":
    edit_properties()

# -----------------------------------------------------------------------------
# Edit/Delete Admin
# -----------------------------------------------------------------------------
elif selected == "Edit/Delete Admin":
    edit_admins()
