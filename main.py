import streamlit as st
import pandas as pd
import bcrypt
from conn import Conn
from sqlalchemy.sql import text
from license import LicenseManager
from user_registration import user_registration_page
from io import BytesIO
from streamlit_timeline import timeline


db = Conn()
# Session State for Authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.admin_name = ""
    st.session_state.admin_role = ""

# Page Configuration
st.set_page_config(page_title="CRM Admin Portal", layout="wide")

valid_license, license_message = LicenseManager.validate_license()
if not valid_license:
    st.error(license_message)
    st.stop()

# ------------------ LOGIN FUNCTIONALITY ------------------ #
def login():
    st.title("🔑 Admin Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        engine = db.engine
        with engine.connect() as conn:
            query = text("SELECT name, id, password, admin_type FROM admin_users WHERE username = :username")
            result = conn.execute(query, {"username": username}).fetchone()
            
            if result and bcrypt.checkpw(password.encode(), result[2].encode()):
                st.session_state.authenticated = True
                st.session_state.admin_name = result[0]
                st.session_state.admin_id = result[1]
                st.session_state.admin_role = result[3]  # Store admin property access
                st.success(f"Welcome, {st.session_state.admin_name}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")

# Force login if not authenticated
if not st.session_state.authenticated:
    login()
    st.stop()

# ------------------ STREAMLIT UI SETUP ------------------ #
menu_options = ["CRM Main Dashboard", "Logout"]
if st.session_state.admin_role == "Admin":
    menu_options.insert(1, "Admin User Creation")  # Show admin creation only if user manages "All"
    menu_options.insert(2, "Register User")

menu_option = st.sidebar.radio("Navigation", menu_options)

# ------------------ LOGOUT FUNCTION ------------------ #
if menu_option == "Logout":
    st.session_state.authenticated = False
    st.session_state.admin_name = ""
    st.session_state.admin_id = ""
    st.session_state.admin_role = ""
    st.success("Logged out successfully.")
    st.rerun()

# -------------------- CRM MAIN DASHBOARD -------------------- #
if menu_option == "CRM Main Dashboard":
    st.title("📊 Operations CRM Dashboard")
    
    

    # Fetch tickets
    if st.session_state.admin_role == "Admin":
        all_tickets_df = db.fetch_tickets("All")
        tickets_df = all_tickets_df
    else:
        all_tickets_df = db.fetch_open_tickets( st.session_state.admin_id)
    tickets_df = all_tickets_df  

    if not tickets_df.empty:
        st.subheader("🎟️ Open Tickets")
        st.dataframe(tickets_df)

        ticket_id = st.selectbox("Select Ticket ID to update", tickets_df["id"].tolist())
        selected_ticket = tickets_df[tickets_df["id"] == ticket_id].iloc[0]

        # Display Ticket Details
        st.write(f"**Issue:** {selected_ticket['issue_description']}")
        st.write(f"**Category:** {selected_ticket['category']}")  # New: Show category
        st.write(f"**Property:** {selected_ticket['property']}")
        st.write(f"**Unit Number:** {selected_ticket['unit_number']}")
        st.write(f"**Status:** {selected_ticket['status']}")
        st.write(f"**Assigned Admin:** {selected_ticket['assigned_admin']}")  # New: Show assigned admin
        
        # -------------------- SHOW ATTACHED MEDIA -------------------- #
        st.markdown("### 📎 Attached Files")
        media_df = db.fetch_ticket_media(ticket_id)  # Should return media_type, media_blob, and optionally filename

        if not media_df.empty:
            for _, row in media_df.iterrows():
                media_type = row["media_type"]
                media_blob = row["media_blob"]
                filename = row.get("filename", "attachment")

                if media_type == "image":
                    st.image(BytesIO(media_blob), caption="Attached Image", use_container_width=True)

                elif media_type == "video":
                    st.video(BytesIO(media_blob))

                elif media_type == "document":
                    st.download_button(
                        label="📄 Download Document",
                        data=media_blob,
                        file_name=filename,
                        mime="application/pdf"
                    )
                else:
                    st.download_button(
                        label=f"📎 Download {media_type.capitalize()}",
                        data=media_blob,
                        file_name=filename,
                        mime="application/octet-stream"
                    )
        else:
            st.info("No media files attached to this ticket.")

        # -------------------- STATUS UPDATE -------------------- #
        
        
        with st.expander("📜 Ticket History", expanded=False):
            # Inject CSS for background and text color
            st.markdown("""
                <style>
                    .timeline {
                        background-color: #f0f0f0 !important;
                    }

                    .tl-text-content, .tl-headline, .tl-title {
                        color: black !important;
                        font-weight: bold !important;
                    }

                    .tl-text-content p {
                        color: black !important;
                        font-size: 16px !important;
                    }

                    /* Improve visibility for bottom timeline items (event preview texts) */
                    .tl-timegroup .tl-time .tl-time-display,
                    .tl-event-title,
                    .tl-headline-date {
                        color: #8B0000 !important;
                        font-weight: 700 !important;
                    }
                </style>
            """, unsafe_allow_html=True)

            history_df = db.fetch_ticket_history(ticket_id)

            if not history_df.empty:
                events = []
                for _, row in history_df.iterrows():
                    dt = row["performed_at"]
                    bg_color = "#E0E0E0"
                    text_color = "#000000"

                    events.append({
                        "start_date": {
                            "year": dt.year,
                            "month": dt.month,
                            "day": dt.day,
                            "hour": dt.hour,
                            "minute": dt.minute,
                        },
                        "text": {
                            "headline": f"{row['action']} by {row['performed_by']}",
                            "text": f"""
                                <div style='
                                    background-color:{bg_color};
                                    color:{text_color};
                                    padding:12px;
                                    border-radius:10px;
                                    font-size:15px;
                                    font-family:sans-serif;
                                '>
                                    {row['details']}
                                </div>
                            """
                        }
                    })

                timeline({
                    "title": {
                        "text": {
                            "headline": f"🕒 Ticket #{ticket_id} History",
                            "text": "Full record of updates and reassignments"
                        }
                    },
                    "events": events
                })
            else:
                st.info("No ticket history available.")
            
        new_status = st.selectbox("Update Status", ["Open", "In Progress", "Resolved"], 
                                  index=["Open", "In Progress", "Resolved"].index(selected_ticket["status"]))
        
        if st.button("Update Status"):
            db.update_ticket_status(ticket_id, new_status)
            st.success(f"✅ Ticket #{ticket_id} status updated to {new_status}!")
            st.rerun()

        # -------------------- TICKET UPDATES -------------------- #
        update_text = st.text_area("Add Update")
        admin_name = st.session_state.admin_name  # Automatically assign logged-in admin name

        if st.button("Submit Update"):
            if update_text:
                db.add_ticket_update(ticket_id, update_text, admin_name)
                st.success("✅ Update added successfully!")
                st.rerun()
            else:
                st.error("⚠️ Please provide update text.")

        # -------------------- ADMIN REASSIGNMENT -------------------- #
        if st.session_state.admin_role != "Caretaker":
    
            st.subheader("🔄 Reassign Admin")

            # Fetch all admin users from the database
            admin_users = db.fetch_admin_users()  # Function to get admin list
            admin_options = {admin["id"]: admin["name"] for admin in admin_users}
            
            # Exclude the currently assigned admin
            available_admins = {k: v for k, v in admin_options.items() if v != selected_ticket["assigned_admin"]}
            
            new_admin_id = st.selectbox("Select New Admin", list(available_admins.keys()), format_func=lambda x: available_admins[x])

            reassign_reason = st.text_area("Reason for Reassignment")
            
            

            if st.button("Reassign Ticket"):
                if new_admin_id and reassign_reason:
                    db.reassign_ticket_admin(ticket_id, new_admin_id, selected_ticket["assigned_admin"], admin_name, reassign_reason)
                    st.success(f"✅ Ticket #{ticket_id} reassigned to {available_admins[new_admin_id]}!")
                    st.rerun()
                else:
                    st.error("⚠️ Please select a new admin and provide a reason.")

            
                
            
            # -------------------- DUE DATE SECTION -------------------- #
            st.subheader("📅 Set Due Date")

            current_due_date = selected_ticket.get("due_date")

            due_date = st.date_input("Select Due Date", value=pd.to_datetime(current_due_date) if current_due_date else None)

            if st.button("Update Due Date"):
                db.update_ticket_due_date(ticket_id, due_date)
                st.success(f"✅ Due date updated to {due_date.strftime('%Y-%m-%d')}")
                st.rerun()
                
        
    else:
        st.warning("⚠️ No tickets found.")
    
        
        
# ------------------  USER registration ------------------ #
elif menu_option == "Register User":
    
    def is_registered_user(whatsapp_number):
        """Checks if the WhatsApp number is registered in the database."""
        engine = db.engine
        with engine.connect() as conn:
            query = text("SELECT id FROM users WHERE whatsapp_number = :whatsapp_number")
            result = conn.execute(query, {"whatsapp_number": whatsapp_number}).fetchone()
        return result is not None
    
    user_registration_page() 
        
# -------------------- ADMIN USER CREATION -------------------- #
if menu_option == "Admin User Creation":
    st.title("👤 Admin User Creation")
    
    def create_admin_user(name, username, password, property):
        engine = db.engine
        with engine.connect() as conn:
            try:
                check_query = text("SELECT id FROM admin_users WHERE username = :username")
                existing_admin = conn.execute(check_query, {"username": username}).fetchone()
                
                if existing_admin:
                    return False, "Admin user already exists."
                
                hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                
                insert_query = text("""
                    INSERT INTO admin_users (name, username, password, property) 
                    VALUES (:name, :username, :password, :property)
                """)
                conn.execute(insert_query, {
                    "name": name,
                    "username": username,
                    "password": hashed_password,
                    "property": property
                })
                conn.commit()
                
                return True, "Admin user created successfully!"
            except Exception as e:
                return False, f"Error creating admin user: {e}"
            
    properties = db.get_all_properties()
    
    with st.form("admin_user_form"):
        name = st.text_input("Full Name", placeholder="Enter admin's full name")
        username = st.text_input("Username", placeholder="Enter a unique username")
        password = st.text_input("Password", type="password", placeholder="Enter a strong password")
        property_selection = st.selectbox("Select Property", properties)
        admin_type = st.selectbox("Admin Type", ["Admin", "Property Manager", "Caretaker"])
        submit_button = st.form_submit_button("Create Admin User")
    
    if submit_button:
        if name and username and password and property:
            success, message = create_admin_user(name, username, password, property_selection,admin_type)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
        else:
            st.warning("Please fill in all fields.")
    
    st.subheader("Registered Admin Users")
    
    def fetch_admin_users():
        engine = db.engine
        with engine.connect() as conn:
            query = text("SELECT id, name, username, property FROM admin_users")
            result = conn.execute(query)
            admins = result.fetchall()
        return admins
    
    admins = fetch_admin_users()
    
    if admins:
        df = pd.DataFrame(admins, columns=["ID", "Name", "Username", "Property"])
        st.dataframe(df)
    else:
        st.warning("No admin users registered yet.")
        
    
# -------------------- ADMIN REASSIGNMENT HISTORY PAGE -------------------- #
if menu_option == "Admin Reassignment History":
    st.title("📜 Admin Reassignment History")

    reassign_log_df = db.fetch_admin_reassignment_log()

    if not reassign_log_df.empty:
        st.dataframe(reassign_log_df)
    else:
        st.warning("⚠️ No reassignments have been logged yet.")

# -------------------- Property Creation PAGE -------------------- #
if menu_option == "Create Property":
    st.title("🏘️ Create New Property")

    # 🔐 Check if user is an admin
    if st.session_state.get("admin_type") != "Admin":
        st.warning("Only admins can access this page.")
        st.stop()

    conn = Conn()

    # Fetch available property managers (supervisors)
    supervisors = conn.get_available_property_managers()
    supervisor_options = {f"{s['name']} (ID: {s['id']})": s['id'] for s in supervisors}

    with st.form("create_property_form"):
        name = st.text_input("Property Name", placeholder="e.g., Westview Apartments")
        selected_supervisor = st.selectbox("Assign Property Manager", options=supervisor_options.keys())
        submit = st.form_submit_button("Create Property")

    if submit:
        success, msg = conn.create_property(name, supervisor_options[selected_supervisor])
        if success:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)