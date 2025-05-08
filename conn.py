import streamlit as st
from sqlalchemy import create_engine
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy.sql import text
import requests
import bcrypt

load_dotenv()

class Conn:
    """Database helper class to manage all queries and connections."""
    
    def __init__(self):
        """Initialize database connection."""
        #DB_URI = f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
        DB_URI = f"mysql+mysqlconnector://{st.secrets.DB_USER}:{st.secrets.DB_PASSWORD}@{st.secrets.DB_HOST}/{st.secrets.DB_NAME}"  # Using Streamlit secrets('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
        self.engine = create_engine(DB_URI)

    # -------------------- FETCH TICKETS -------------------- #
    def fetch_tickets(self, property=None):
        """Fetches all tickets, ensuring previous admins can still view reassigned tickets."""
        query = """
        SELECT t.id, u.whatsapp_number, u.name, t.issue_description, t.status, t.created_at, 
            p.name AS property, u.unit_number, t.category, a.name AS assigned_admin, t.due_date AS Due_Date
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        LEFT JOIN admin_users a ON t.assigned_admin = a.id
        LEFT JOIN properties p ON t.property_id = p.id
        WHERE t.status != 'Resolved'
        """

        params = ()
        
        if property and property != "All":
            query += " AND p.name = %s"
            params = (property,)

        df = pd.read_sql(query, self.engine, params=params)
        df["Due_Date"] = df["Due_Date"].where(pd.notnull(df["Due_Date"]), None)
        
        return df


    # -------------------- FETCH OPEN TICKETS -------------------- #
    def fetch_open_tickets(self, admin_id=None):
        """Fetch all open tickets, including category and assigned admin."""
        query = """
        SELECT t.id, u.whatsapp_number, u.name, t.issue_description, t.status, t.created_at, 
            p.name AS property, u.unit_number, t.category, a.name AS assigned_admin, t.due_date AS Due_Date
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        LEFT JOIN admin_users a ON t.assigned_admin = a.id
        LEFT JOIN properties p ON t.property_id = p.id
        WHERE (
            t.assigned_admin = %s 
            OR t.id IN (SELECT ticket_id FROM admin_change_log WHERE old_admin = %s)
        )
        AND t.status != 'Resolved'
        """

        df = pd.read_sql(query, self.engine, params=(admin_id, admin_id))
        df["Due_Date"] = df["Due_Date"].where(pd.notnull(df["Due_Date"]), None)
        
        return df


    # -------------------- FETCH ADMIN USERS -------------------- #
    def fetch_admin_users(self):
        """Fetches all admin users."""
        query = "SELECT id, name, whatsapp_number FROM admin_users"
        df = pd.read_sql(query, self.engine)
      
        return df.to_dict("records")

    # -------------------- UPDATE TICKET STATUS -------------------- #
    def send_whatsapp_notification(self, to, message):
        """Sends a WhatsApp message using the Flask backend API."""
        url = st.secrets.URL  # 🔁 replace with actual
        #url = os.getenv("URL")
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": os.getenv("INTERNAL_API_KEY")  # 🔐 for secure requests
        }
        payload = {"to": to, "message": message}

        try:
            response = requests.post(url, headers=headers, json=payload)
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def update_ticket_status(self, ticket_id, new_status):
        """Updates the ticket status and notifies the user via WhatsApp."""
        with self.engine.connect() as conn:
            conn.execute(
                text("UPDATE tickets SET status = :new_status WHERE id = :ticket_id"),
                {"new_status": new_status, "ticket_id": ticket_id}
            )
            conn.commit()

            result = conn.execute(
                text("SELECT u.whatsapp_number FROM users u JOIN tickets t ON u.id = t.user_id WHERE t.id = :ticket_id"),
                {"ticket_id": ticket_id}
            ).fetchone()

        if result:
            user_whatsapp = result[0]
            # 📩 Use the ticket_status_change template instead
            self.send_template_notification(
                to=user_whatsapp,
                template_name="ticket_status_change",
                template_parameters=[f"#{ticket_id}", new_status]
            )


    # -------------------- ADD TICKET UPDATE -------------------- #
    def add_ticket_update(self, ticket_id, update_text, admin_name):
        """Logs an update on a ticket and notifies the user."""
        with self.engine.connect() as conn:
            # Insert the update into the DB
            conn.execute(
                text("INSERT INTO ticket_updates (ticket_id, update_text, updated_by) VALUES (:ticket_id, :update_text, :admin_name)"),
                {"ticket_id": ticket_id, "update_text": update_text, "admin_name": admin_name}
            )
            conn.commit()

            # Fetch user's WhatsApp number
            result = conn.execute(
                text("SELECT u.whatsapp_number FROM users u JOIN tickets t ON u.id = t.user_id WHERE t.id = :ticket_id"),
                {"ticket_id": ticket_id}
            ).fetchone()

        if result:
            user_whatsapp = result[0]
            message = f"✍️ Your ticket #{ticket_id} has a new update from {admin_name}:\n\n\"{update_text}\""
            self.send_whatsapp_notification(user_whatsapp, message)
            
            
    #---------------------Ticket history --------------------#
    
    def fetch_ticket_history(self, ticket_id):
        with self.engine.connect() as conn:
            # Fetch ticket updates
            updates = conn.execute(
                text("""
                    SELECT ticket_id, 'Update' AS action, updated_by AS performed_by,
                        update_text AS details, created_at AS performed_at
                    FROM ticket_updates
                    WHERE ticket_id = :ticket_id
                """),
                {"ticket_id": ticket_id}
            ).fetchall()

            # Fetch reassignment logs
            reassignments = conn.execute(
                text("""
                    SELECT ticket_id, 'Reassignment' AS action, changed_by_admin AS performed_by,
                        CONCAT('Reassigned from ', old_admin, ' to ', new_admin, '. Reason: ', reason) AS details,
                        changed_at AS performed_at
                    FROM admin_change_log
                    WHERE ticket_id = :ticket_id
                """),
                {"ticket_id": ticket_id}
            ).fetchall()

        # Combine and sort by performed_at
        all_logs = updates + reassignments
        df = pd.DataFrame(all_logs, columns=["ticket_id", "action", "performed_by", "details", "performed_at"])
        df.sort_values(by="performed_at", inplace=True)

        return df



    # -------------------- REASSIGN ADMIN -------------------- #
    def reassign_ticket_admin(self, ticket_id, new_admin_id, old_admin_id, changed_by_admin, reason, is_super_admin=False):
        """Reassigns a ticket to a new admin, logs the change, and sends WhatsApp notifications if needed."""
        try:
            with self.engine.connect() as conn:
                print("🔁 Starting ticket reassignment process...")

                # Step 1: Check reassignment count
                reassign_count = conn.execute(
                    text("SELECT reassign_count FROM admin_change_log WHERE ticket_id = :ticket_id"),
                    {"ticket_id": ticket_id}
                ).scalar()
                print(f"🔢 Reassign count for ticket #{ticket_id}: {reassign_count}")

                if reassign_count >= 3 and not is_super_admin:
                    print("🚫 Reassignment limit reached")
                    return False, "⚠️ Reassignment limit reached. Only a Super Admin can override."

                # Step 2: Update ticket with new admin
                conn.execute(
                    text("UPDATE tickets SET assigned_admin = :new_admin_id WHERE id = :ticket_id"),
                    {"new_admin_id": new_admin_id, "ticket_id": ticket_id}
                )
                print(f"✅ Updated ticket #{ticket_id} with new admin ID {new_admin_id}")

                # Step 3: Log reassignment
                conn.execute(
                    text("""
                        INSERT INTO admin_change_log (
                            ticket_id, old_admin, new_admin, changed_by_admin, reason,
                            reassign_count, changed_at, override_by_super_admin
                        ) VALUES (
                            :ticket_id, :old_admin_id, :new_admin_id, :changed_by_admin, :reason,
                            :reassign_count, NOW(), :is_super_admin
                        )
                    """),
                    {
                        "ticket_id": ticket_id,
                        "old_admin_id": old_admin_id,
                        "new_admin_id": new_admin_id,
                        "changed_by_admin": changed_by_admin,
                        "reason": reason,
                        "reassign_count": reassign_count + 1,
                        "is_super_admin": is_super_admin
                    }
                )
                conn.commit()
                print("📝 Reassignment logged and committed to database.")

                # Step 4: Fetch new admin details
                admin_users = self.fetch_admin_users()
                print("📥 Retrieved admin list.")

                new_admin_info = next((admin for admin in admin_users if str(admin["id"]) == str(new_admin_id)), None)
                if new_admin_info:
                    new_admin_name = new_admin_info["name"]
                    new_admin_whatsapp = new_admin_info.get("whatsapp_number")
                    if new_admin_whatsapp:
                        try:
                            print(f"📤 Sending WhatsApp to new admin {new_admin_name} ({new_admin_whatsapp})")
                            self.send_template_notification(
                                to=new_admin_whatsapp,
                                template_name="ticket_reassignment",
                                template_parameters=[f"#{ticket_id}", changed_by_admin, reason]
                            )
                        except Exception as notify_err:
                            print(f"❌ Failed to send WhatsApp to new admin: {notify_err}")
                    else:
                        print("⚠️ New admin has no WhatsApp number.")
                else:
                    print("❌ New admin not found in admin_users list.")

                # Step 5: If the new admin is a caretaker, notify their supervisor
                caretaker_info = self.get_admin_role_and_property(new_admin_id)
                print("👤 Caretaker role check result:", caretaker_info)

                if caretaker_info and caretaker_info["admin_type"] == "Caretaker":
                    property_id = caretaker_info["property_id"]

                    supervisor = conn.execute(
                        text("""
                            SELECT s.id AS supervisor_id, s.name AS supervisor_name, s.whatsapp_number
                            FROM properties p
                            JOIN admin_users s ON p.supervisor_id = s.id
                            WHERE p.id = :property_id
                        """),
                        {"property_id": property_id}
                    ).fetchone()

                    if supervisor:
                        if str(supervisor.supervisor_id) != str(changed_by_admin):
                            try:
                                print(f"📤 Notifying supervisor {supervisor.supervisor_name} ({supervisor.whatsapp_number})")
                                self.send_template_notification(
                                    to=supervisor.whatsapp_number,
                                    template_name="caretaker_task_alert",
                                    template_parameters=[f"#{ticket_id}", new_admin_name]
                                )
                            except Exception as sup_notify_err:
                                print(f"❌ Failed to notify supervisor: {sup_notify_err}")
                        else:
                            print("ℹ️ Supervisor performed the reassignment. No alert sent.")
                    else:
                        print("⚠️ Supervisor not found for caretaker’s property.")

            print("✅ Reassignment process completed.")
            return True, "✅ Ticket reassigned successfully!"

        except Exception as e:
            print(f"❌ Unexpected error in reassign_ticket_admin: {e}")
            return False, "❌ An unexpected error occurred during reassignment."



    def get_admin_role_and_property(self, admin_id):
        """Returns the admin_type and property_id for a given admin ID."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT admin_type, property_id FROM admin_users WHERE id = :id"),
                {"id": admin_id}
            ).mappings().fetchone()  # 👈 this returns a RowMapping (dict-like)
            return result if result else None



    # -------------------- FETCH ADMIN REASSIGNMENT LOG -------------------- #
    def fetch_admin_reassignment_log(self):
        """Fetches the history of admin reassignments."""
        query = """
        SELECT l.ticket_id, t.issue_description, u1.name AS old_admin, u2.name AS new_admin, 
               l.changed_by_admin, l.reason, l.reassign_count, l.changed_at, l.override_by_super_admin 
        FROM admin_change_log l
        JOIN tickets t ON l.ticket_id = t.id
        JOIN admin_users u1 ON l.old_admin = u1.id
        JOIN admin_users u2 ON l.new_admin = u2.id
        ORDER BY l.changed_at DESC
        """

        df = pd.read_sql(query, self.engine)
        return df
    
   


    def fetch_ticket_media(self, ticket_id):
        query = """
            SELECT media_type, media_blob, media_path AS filename FROM ticket_media WHERE ticket_id = :ticket_id
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params={"ticket_id": ticket_id})
        return df


    def update_ticket_due_date(self, ticket_id, due_date):
        """Updates the due date of a ticket."""
        with self.engine.connect() as conn:
            conn.execute(
                text("UPDATE tickets SET due_date = :due_date WHERE id = :ticket_id"),
                {"due_date": due_date, "ticket_id": ticket_id}
            )
            conn.commit()
        
    
    def send_template_notification(self, to, template_name, template_parameters):
        
        """Sends a WhatsApp template message using the Flask backend API."""
        url = st.secrets.URL
        #url = os.getenv("URL")
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": os.getenv("INTERNAL_API_KEY")
        }
        payload = {
            "to": to,
            "template_name": template_name,
            "template_parameters": template_parameters
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            return response.json()
        except Exception as e:
            return {"error": str(e)}
        
        
        
    def create_property(self, property_name, supervisor_id):
        """Create a new property with a unique name and assign a supervisor."""
        with self.engine.connect() as conn:
            # Check for duplicate property name
            existing = conn.execute(
                text("SELECT id FROM properties WHERE name = :name"),
                {"name": property_name}
            ).fetchone()

            if existing:
                return False, "❌ Property with this name already exists."

            try:
                # Insert new property
                result = conn.execute(
                    text("INSERT INTO properties (name, supervisor_id) VALUES (:name, :supervisor_id)"),
                    {"name": property_name, "supervisor_id": supervisor_id}
                )

                # Get the newly inserted property ID
                property_id = conn.execute(
                    text("SELECT LAST_INSERT_ID()")
                ).scalar()

                # Update admin_users table with this property_id for the supervisor
                conn.execute(
                    text("UPDATE admin_users SET property_id = :property_id WHERE id = :supervisor_id"),
                    {"property_id": property_id, "supervisor_id": supervisor_id}
                )

                conn.commit()
                return True, "✅ Property created and supervisor assigned successfully!"
            except Exception as e:
                return False, f"❌ Failed to create property: {e}"

            
            
    def get_available_property_managers(self):
        """Fetch all users who are Property Managers (supervisors)."""
        query = """
        SELECT id, name
        FROM admin_users
        WHERE admin_type = 'Property Manager'
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df.to_dict("records")
    


    def get_units_by_property(self, property_id):
        with self.engine.connect() as conn:
            return conn.execute(text(
                "SELECT unit_number FROM users WHERE property_id = :property_id"
            ), {"property_id": property_id}).fetchall()
            
    
    def get_all_ticket_properties(self):
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT id, name FROM properties"))
            return [dict(row._mapping) for row in result]
        
        
    def get_units_by_property(self, property_id):
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT unit_number FROM users WHERE property_id = :property_id
            """), {"property_id": property_id})
            return [dict(row._mapping) for row in result]
        
        
    
    def insert_ticket_and_get_id(self, user_id, description, category, property, assigned_admin):
        """Inserts a new ticket and returns the auto-incremented ticket ID."""
        insert_query = text("""
            INSERT INTO tickets 
            (user_id, issue_description, status, created_at, category, property_id, assigned_admin)
            VALUES (:user_id, :description, 'Open', NOW(), :category, :property, :assigned_admin)
        """)
        select_query = text("SELECT LAST_INSERT_ID() AS id")

        with self.engine.connect() as conn:
            conn.execute(insert_query, {
                "user_id": user_id,
                "description": description,
                "category": category,
                "property": property,
                "assigned_admin": assigned_admin
            })
            result = conn.execute(select_query).fetchone()
            conn.commit()
            return result[0]
        
        
    def get_user_id_by_unit_and_property(self, unit_number, property_id):
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id FROM users 
                WHERE unit_number = :unit_number AND property_id = :property_id
            """), {
                "unit_number": unit_number,
                "property_id": property_id
            }).fetchone()
            return result[0] if result else None
        
    
    def get_all_users(self):
        query = "SELECT * FROM users"
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df.to_dict("records")

    def update_user(self, user_id, name, whatsapp_number, property_id, unit_number, temp_category):
        query = text("""
            UPDATE users
            SET name = :name,
                whatsapp_number = :whatsapp_number,
                property_id = :property_id,
                unit_number = :unit_number,
                temp_category = :temp_category
            WHERE id = :user_id
        """)
        with self.engine.begin() as conn:
            conn.execute(query, {
                "name": name,
                "whatsapp_number": whatsapp_number,
                "property_id": property_id,
                "unit_number": unit_number,
                "temp_category": temp_category,
                "user_id": user_id
            })

    def delete_user(self, user_id):
        query = text("DELETE FROM users WHERE id = :user_id")
        with self.engine.begin() as conn:
            conn.execute(query, {"user_id": user_id})

    def get_all_admin_users(self):
        query = "SELECT * FROM admin_users"
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df.to_dict("records")

    def update_admin_user(self, admin_id, name, username, whatsapp_number, admin_type, property_id):
        query = text("""
            UPDATE admin_users
            SET name = :name,
                username = :username,
                whatsapp_number = :whatsapp_number,
                admin_type = :admin_type,
                property_id = :property_id
            WHERE id = :admin_id
        """)
        with self.engine.begin() as conn:
            conn.execute(query, {
                "name": name,
                "username": username,
                "whatsapp_number": whatsapp_number,
                "admin_type": admin_type,
                "property_id": property_id,
                "admin_id": admin_id
            })

    def delete_admin_user(self, admin_id):
        query = text("DELETE FROM admin_users WHERE id = :admin_id")
        with self.engine.begin() as conn:
            conn.execute(query, {"admin_id": admin_id})


    def get_available_property_managers(self):
        query = """
        SELECT id, name
        FROM admin_users
        WHERE admin_type = 'Property Manager'
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df.to_dict("records")

    def update_property(self, property_id, name, supervisor_id):
        # Check if supervisor is a valid Property Manager
        check_query = text("""
            SELECT id FROM admin_users
            WHERE id = :id AND admin_type = 'Property Manager'
        """)
        update_query = text("""
            UPDATE properties
            SET name = :name, supervisor_id = :supervisor_id
            WHERE id = :property_id
        """)
        with self.engine.begin() as conn:
            valid = conn.execute(check_query, {"id": supervisor_id}).fetchone()
            if not valid:
                raise ValueError("Supervisor must be a valid Property Manager.")
            conn.execute(update_query, {
                "name": name,
                "supervisor_id": supervisor_id,
                "property_id": property_id
            })

    def delete_property(self, property_id):
        query = text("DELETE FROM properties WHERE id = :property_id")
        with self.engine.begin() as conn:
            conn.execute(query, {"property_id": property_id})
            
    

    def reset_admin_password(self, admin_id, plain_password):
        hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()
        query = text("UPDATE admin_users SET password = :password WHERE id = :admin_id")
        with self.engine.begin() as conn:
            conn.execute(query, {"password": hashed, "admin_id": admin_id})

    
    def get_all_properties(self):
        """Returns a list of properties with id and name."""
        query = "SELECT id, name FROM properties"
        result = self.query_database(query)
        return result if result else []


