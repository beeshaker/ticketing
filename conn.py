import streamlit as st
from sqlalchemy import create_engine
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy.sql import text
import requests
import bcrypt
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

# -----------------------------------------------------------------------------
# Timezone: Kenya (Africa/Nairobi)
# -----------------------------------------------------------------------------
KENYA_TZ = ZoneInfo("Africa/Nairobi")

def kenya_now() -> datetime:
    """
    Returns timezone-aware Kenya datetime.
    Use this for ALL app-side timestamps instead of DB NOW() or server local time.
    """
    return datetime.now(KENYA_TZ)


class Conn:
    """Database helper class to manage all queries and connections."""

    def __init__(self):
        """Initialize database connection."""
        DB_URI = (
            f"mysql+mysqlconnector://{st.secrets.DB_USER}:{st.secrets.DB_PASSWORD}"
            f"@{st.secrets.DB_HOST}/{st.secrets.DB_NAME}"
        )
        self.engine = create_engine(DB_URI)

    # -------------------- FETCH TICKETS -------------------- #
    def fetch_tickets(self, property=None):
        """Fetches all non-resolved tickets with read status."""
        query = """
        SELECT t.id, u.whatsapp_number, u.name, t.issue_description, t.status, t.created_at, 
               p.name AS property, u.unit_number, t.category, a.name AS assigned_admin, 
               t.due_date AS Due_Date, t.is_read
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

    # -------------------- FETCH OPEN/ACTIVE TICKETS FOR AN ADMIN -------------------- #
    def fetch_tickets(self, property=None):
        """Fetches all non-resolved tickets with read status."""
        query = """
        SELECT t.id, u.whatsapp_number, u.name, t.issue_description, t.status, t.created_at, 
               p.name AS property, u.unit_number, t.category, a.name AS assigned_admin, 
               t.due_date AS Due_Date, t.is_read
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

    def fetch_open_tickets(self, admin_id=None):
        """Fetch tickets for an admin, including read status."""
        query = """
        SELECT t.id, u.whatsapp_number, u.name, t.issue_description, t.status, t.created_at, 
               p.name AS property, u.unit_number, t.category, a.name AS assigned_admin, 
               t.due_date AS Due_Date, t.is_read
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

    # -------------------- DATABASE MONITORING (FOR SILENT REFRESH) -------------------- #
    
    def get_tickets_hash(self):
        """
        Returns a composite string: 'Count-MaxID-UnreadCount'.
        This changes if a ticket is added, deleted, resolved, or marked as read.
        """
        from sqlalchemy import text
        # We only monitor active (non-resolved) tickets
        query = text("""
            SELECT 
                COUNT(id), 
                MAX(id), 
                SUM(CASE WHEN is_read = FALSE THEN 1 ELSE 0 END)
            FROM tickets 
            WHERE status != 'Resolved'
        """)
        
        with self.engine.connect() as conn:
            result = conn.execute(query).fetchone()
            
            # Fallback for empty table
            if not result or result[0] == 0:
                return "0-0-0"
            
            count = result[0]
            max_id = result[1] if result[1] is not None else 0
            unread = int(result[2]) if result[2] is not None else 0
            
            return f"{count}-{max_id}-{unread}"

    # -------------------- UPDATE TICKET STATUS -------------------- #

    def mark_ticket_as_read(self, ticket_id):
        """Updates the is_read status to true in the database."""
        from sqlalchemy import text
        query = text("UPDATE tickets SET is_read = TRUE WHERE id = :id")
        with self.engine.connect() as conn:
            conn.execute(query, {"id": ticket_id})
            conn.commit()

    # -------------------- FETCH ADMIN USERS -------------------- #
    def fetch_admin_users(self):
        """Fetches all admin users."""
        query = "SELECT id, name, whatsapp_number FROM admin_users"
        df = pd.read_sql(query, self.engine)
        return df.to_dict("records")

    def fetch_all_admin_users(self):
        """Fetches all admin users with type."""
        query = "SELECT id, name, whatsapp_number, admin_type FROM admin_users"
        df = pd.read_sql(query, self.engine)
        return df.to_dict("records")

    # -------------------- WHATSAPP HELPERS -------------------- #
    def send_whatsapp_notification(self, to, message):
        """Sends a WhatsApp message using the Flask backend API."""
        url = st.secrets.URL
        api_key = st.secrets.get("INTERNAL_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": api_key
        }
        payload = {"to": to, "message": message}

        try:
            response = requests.post(url, headers=headers, json=payload)
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def send_template_notification(self, to, template_name, template_parameters):
        """Sends a WhatsApp template message using the Flask backend API."""
        url = st.secrets.URL
        api_key = st.secrets.get("INTERNAL_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": api_key
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

    # -------------------- UPDATE TICKET STATUS -------------------- #
    def update_ticket_status(self, ticket_id, new_status):
        """
        Updates ticket status and notifies user.
        (No timestamp change here unless you add updated_at in DB.)
        """
        with self.engine.connect() as conn:
            conn.execute(
                text("UPDATE tickets SET status = :new_status WHERE id = :ticket_id"),
                {"new_status": new_status, "ticket_id": ticket_id}
            )
            conn.commit()

            result = conn.execute(
                text("""
                    SELECT u.whatsapp_number 
                    FROM users u 
                    JOIN tickets t ON u.id = t.user_id 
                    WHERE t.id = :ticket_id
                """),
                {"ticket_id": ticket_id}
            ).fetchone()

        if result:
            user_whatsapp = result[0]
            self.send_template_notification(
                to=user_whatsapp,
                template_name="ticket_status_change",
                template_parameters=[f"#{ticket_id}", new_status]
            )

    # -------------------- ADD TICKET UPDATE -------------------- #
    def add_ticket_update(self, ticket_id, update_text, admin_name):
        """Logs an update on a ticket and notifies the user (Kenya time)."""
        with self.engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO ticket_updates (ticket_id, update_text, updated_by, created_at)
                    VALUES (:ticket_id, :update_text, :admin_name, :created_at)
                """),
                {
                    "ticket_id": ticket_id,
                    "update_text": update_text,
                    "admin_name": admin_name,
                    "created_at": kenya_now()
                }
            )
            conn.commit()

            result = conn.execute(
                text("""
                    SELECT u.whatsapp_number
                    FROM users u
                    JOIN tickets t ON u.id = t.user_id
                    WHERE t.id = :ticket_id
                """),
                {"ticket_id": ticket_id}
            ).fetchone()

        if result:
            user_whatsapp = result[0]
            message = f"✍️ Your ticket #{ticket_id} has a new update from {admin_name}:\n\n\"{update_text}\""
            self.send_whatsapp_notification(user_whatsapp, message)

    # -------------------- Ticket history -------------------- #
    def fetch_ticket_history(self, ticket_id):
        with self.engine.connect() as conn:
            updates = conn.execute(
                text("""
                    SELECT
                        ticket_id,
                        'Update' AS action,
                        updated_by AS performed_by,
                        update_text AS details,
                        created_at AS performed_at
                    FROM ticket_updates
                    WHERE ticket_id = :ticket_id
                """),
                {"ticket_id": ticket_id}
            ).fetchall()

            # ✅ Reassignments: map old/new admin IDs -> names for display
            # Assumes your admin table is `admins` with columns: id, name
            reassignments = conn.execute(
                text("""
                    SELECT
                        acl.ticket_id,
                        'Reassignment' AS action,
                        acl.changed_by_admin AS performed_by,
                        CONCAT(
                            'Reassigned from ',
                            COALESCE(a_old.name, CONCAT('Admin #', acl.old_admin)),
                            ' to ',
                            COALESCE(a_new.name, CONCAT('Admin #', acl.new_admin)),
                            '. Reason: ',
                            acl.reason
                        ) AS details,
                        acl.changed_at AS performed_at
                    FROM admin_change_log acl
                    LEFT JOIN admin_users a_old ON a_old.id = acl.old_admin
                    LEFT JOIN admin_users a_new ON a_new.id = acl.new_admin
                    WHERE acl.ticket_id = :ticket_id
                """),
                {"ticket_id": ticket_id}
            ).fetchall()

        all_logs = updates + reassignments
        df = pd.DataFrame(all_logs, columns=["ticket_id", "action", "performed_by", "details", "performed_at"])
        df.sort_values(by="performed_at", inplace=True)
        return df


    # -------------------- REASSIGN ADMIN -------------------- #
    def reassign_ticket_admin(self, ticket_id, new_admin_id, old_admin_id, changed_by_admin, reason, is_super_admin=False):
        """
        Reassigns ticket, logs change, and sends WhatsApp notifications.
        Uses Kenya time for changed_at (instead of NOW()).
        """
        try:
            with self.engine.begin() as conn:
                reassign_count = conn.execute(
                    text("SELECT reassign_count FROM admin_change_log WHERE ticket_id = :ticket_id"),
                    {"ticket_id": ticket_id}
                ).scalar()

                # If no rows exist yet, scalar() returns None
                reassign_count = int(reassign_count or 0)

                if reassign_count >= 3 and not is_super_admin:
                    return False, "⚠️ Reassignment limit reached. Only a Super Admin can override."

                # Update ticket assignment
                conn.execute(
                    text("UPDATE tickets SET assigned_admin = :new_admin_id WHERE id = :ticket_id"),
                    {"new_admin_id": new_admin_id, "ticket_id": ticket_id}
                )

                # Insert log row with Kenya time
                conn.execute(
                    text("""
                        INSERT INTO admin_change_log (
                            ticket_id, old_admin, new_admin, changed_by_admin, reason,
                            reassign_count, changed_at, override_by_super_admin
                        ) VALUES (
                            :ticket_id, :old_admin_id, :new_admin_id, :changed_by_admin, :reason,
                            :reassign_count, :changed_at, :is_super_admin
                        )
                    """),
                    {
                        "ticket_id": ticket_id,
                        "old_admin_id": old_admin_id,
                        "new_admin_id": new_admin_id,
                        "changed_by_admin": changed_by_admin,
                        "reason": reason,
                        "reassign_count": reassign_count + 1,
                        "changed_at": kenya_now(),
                        "is_super_admin": is_super_admin
                    }
                )

            # Notify new admin (outside tx is fine)
            admin_users = self.fetch_admin_users()
            new_admin_info = next((a for a in admin_users if str(a["id"]) == str(new_admin_id)), None)
            if new_admin_info and new_admin_info.get("whatsapp_number"):
                self.send_template_notification(
                    to=new_admin_info["whatsapp_number"],
                    template_name="ticket_reassignment",
                    template_parameters=[f"#{ticket_id}", changed_by_admin, reason]
                )

            # (Optional) caretaker supervisor alert logic can be added back here if you want it too

            return True, "✅ Ticket reassigned successfully!"

        except Exception as e:
            print(f"❌ Unexpected error in reassign_ticket_admin: {e}")
            return False, "❌ An unexpected error occurred during reassignment."

    def get_admin_role_and_property(self, admin_id):
        """Returns admin_type and property_id for given admin."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT admin_type, property_id FROM admin_users WHERE id = :id"),
                {"id": admin_id}
            ).mappings().fetchone()
            return result if result else None

    # -------------------- FETCH ADMIN REASSIGNMENT LOG -------------------- #
    def fetch_admin_reassignment_log(self):
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

    # -------------------- MEDIA -------------------- #
    def fetch_ticket_media(self, ticket_id):
        query = """
            SELECT media_type, media_blob, media_path AS filename
            FROM ticket_media
            WHERE ticket_id = :ticket_id
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params={"ticket_id": ticket_id})
        return df

    # -------------------- DUE DATE -------------------- #
    def update_ticket_due_date(self, ticket_id, due_date):
        with self.engine.connect() as conn:
            conn.execute(
                text("UPDATE tickets SET due_date = :due_date WHERE id = :ticket_id"),
                {"due_date": due_date, "ticket_id": ticket_id}
            )
            conn.commit()

    # -------------------- BULK AUDIT -------------------- #
    def save_bulk_audit(self, audit_entries):
        with self.engine.connect() as conn:
            insert_query = text("""
                INSERT INTO bulk_message_audit (
                    property_id, property_name, user_name, whatsapp_number, status, template_name, notice_text
                )
                VALUES (:property_id, :property_name, :user_name, :whatsapp_number, :status, :template_name, :notice_text)
            """)
            for entry in audit_entries:
                conn.execute(insert_query, entry)
            conn.commit()

    def get_users_by_property(self, property_id):
        with self.engine.connect() as conn:
            query = text("""
                SELECT id, name, whatsapp_number
                FROM users
                WHERE property_id = :property_id
            """)
            result = conn.execute(query, {"property_id": property_id})
            users = [dict(row) for row in result.fetchall()]
        return users

    # -------------------- PROPERTIES -------------------- #
    def create_property(self, property_name, supervisor_id):
        """Create property and assign supervisor (also set supervisor's property_id)."""
        with self.engine.connect() as conn:
            existing = conn.execute(
                text("SELECT id FROM properties WHERE name = :name"),
                {"name": property_name}
            ).fetchone()

            if existing:
                return False, "❌ Property with this name already exists."

            try:
                conn.execute(
                    text("INSERT INTO properties (name, supervisor_id) VALUES (:name, :supervisor_id)"),
                    {"name": property_name, "supervisor_id": supervisor_id}
                )

                property_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

                conn.execute(
                    text("UPDATE admin_users SET property_id = :property_id WHERE id = :supervisor_id"),
                    {"property_id": property_id, "supervisor_id": supervisor_id}
                )

                conn.commit()
                return True, "✅ Property created and supervisor assigned successfully!"
            except Exception as e:
                return False, f"❌ Failed to create property: {e}"

    def get_available_property_managers(self):
        """Fetch all Property Managers."""
        query = """
        SELECT id, name
        FROM admin_users
        WHERE admin_type = 'Property Supervisor'
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df.to_dict("records")
    

    def get_units_by_property(self, property_id):
        """
        Returns a list of units for a property.
        Expected return shape: [{"unit_number": "A1"}, {"unit_number": "B2"}, ...]
        """
        if not property_id:
            return []

        with self.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT DISTINCT unit_number
                    FROM users
                    WHERE property_id = :property_id
                      AND unit_number IS NOT NULL
                      AND TRIM(unit_number) <> ''
                    ORDER BY unit_number
                """),
                {"property_id": property_id}
            ).mappings().all()

            return [dict(r) for r in result]


    def update_property(self, property_id, name, supervisor_id):
        """
        Updates property name and supervisor.
        supervisor_id can be None (unassigned).
        """
        update_query = text("""
            UPDATE properties
            SET name = :name, supervisor_id = :supervisor_id
            WHERE id = :property_id
        """)

        with self.engine.begin() as conn:
            if supervisor_id is None:
                conn.execute(update_query, {
                    "name": name,
                    "supervisor_id": None,
                    "property_id": property_id
                })
                return

            check_query = text("""
                SELECT id FROM admin_users
                WHERE id = :id AND admin_type = 'Property Supervisor'
            """)
            valid = conn.execute(check_query, {"id": supervisor_id}).fetchone()
            if not valid:
                raise ValueError("Supervisor must be a valid Property Supervisor.")

            conn.execute(update_query, {
                "name": name,
                "supervisor_id": supervisor_id,
                "property_id": property_id
            })

    def delete_property(self, property_id):
        query = text("DELETE FROM properties WHERE id = :property_id")
        with self.engine.begin() as conn:
            conn.execute(query, {"property_id": property_id})

    def get_all_properties(self):
        """Returns properties with supervisor info (supervisor_name None if unassigned)."""
        query = """
            SELECT
                p.id,
                p.name,
                p.supervisor_id,
                a.name AS supervisor_name
            FROM properties p
            LEFT JOIN admin_users a ON a.id = p.supervisor_id
            ORDER BY p.name
        """
        with self.engine.begin() as conn:
            result = conn.execute(text(query)).mappings().all()
        return result if result else []

    def get_property_supervisor_by_property(self, property_id):
        """Fetch supervisor details for a property."""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT supervisor_id FROM properties WHERE id = :property_id
            """), {"property_id": property_id}).fetchone()

            if not result or not result[0]:
                return None

            supervisor_id = result[0]

            result = conn.execute(text("""
                SELECT id, name, whatsapp_number
                FROM admin_users
                WHERE id = :supervisor_id
            """), {"supervisor_id": supervisor_id}).mappings().fetchone()

            return result if result else None

    def count_admin_users_by_property(self, property_id):
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT COUNT(*) FROM admin_users WHERE property_id = :pid"),
                {"pid": property_id}
            ).scalar()

    def count_tickets_by_property(self, property_id):
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT COUNT(*) FROM tickets WHERE property_id = :pid"),
                {"pid": property_id}
            ).scalar()

    def reassign_admin_users(self, old_property_id, new_property_id):
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE admin_users
                SET property_id = :new_pid
                WHERE property_id = :old_pid
            """), {"old_pid": old_property_id, "new_pid": new_property_id})

    def reassign_tickets(self, old_property_id, new_property_id):
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE tickets
                SET property_id = :new_pid
                WHERE property_id = :old_pid
            """), {"old_pid": old_property_id, "new_pid": new_property_id})

    def null_admins_by_property(self, property_id):
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE admin_users
                SET property_id = NULL
                WHERE property_id = :pid
            """), {"pid": property_id})

    def delete_tickets_by_property(self, property_id):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM tickets WHERE property_id = :pid"), {"pid": property_id})

    # -------------------- USERS -------------------- #
    def get_all_users(self):
        query = "SELECT * FROM users"
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df.to_dict("records")

    def update_user(self, user_id, name, whatsapp_number, property_id, unit_number):
        query = text("""
            UPDATE users
            SET name = :name,
                whatsapp_number = :whatsapp_number,
                property_id = :property_id,
                unit_number = :unit_number
            WHERE id = :user_id
        """)
        with self.engine.begin() as conn:
            conn.execute(query, {
                "name": name,
                "whatsapp_number": whatsapp_number,
                "property_id": property_id,
                "unit_number": unit_number,
                "user_id": user_id
            })

    def delete_user(self, user_id):
        query = text("DELETE FROM users WHERE id = :user_id")
        with self.engine.begin() as conn:
            conn.execute(query, {"user_id": user_id})

    # -------------------- ADMINS -------------------- #
    def get_all_admin_users(self):
        query = "SELECT * FROM admin_users"
        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
        return df.to_dict("records")

    def update_admin_user(self, admin_id, name, username, whatsapp_number, admin_type, property_id):
        if str(property_id).lower() == 'nan' or property_id in ('', None):
            property_id = None
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

    def reset_admin_password(self, admin_id, plain_password):
        hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()
        query = text("UPDATE admin_users SET password = :password WHERE id = :admin_id")
        with self.engine.begin() as conn:
            conn.execute(query, {"password": hashed, "admin_id": admin_id})

    # -------------------- TICKET CREATION (ADMIN PORTAL SIDE) -------------------- #
    def insert_ticket_and_get_id(self, user_id, description, category, property_id, assigned_admin):
        """
        Inserts a new ticket and returns its ID.
        IMPORTANT: Uses Kenya time instead of NOW() (server time).
        """
        insert_query = text("""
            INSERT INTO tickets 
            (user_id, issue_description, status, created_at, category, property_id, assigned_admin)
            VALUES (:user_id, :description, 'Open', :created_at, :category, :property_id, :assigned_admin)
        """)
        select_query = text("SELECT LAST_INSERT_ID() AS id")

        with self.engine.connect() as conn:
            conn.execute(insert_query, {
                "user_id": user_id,
                "description": description,
                "category": category,
                "property_id": property_id,
                "assigned_admin": assigned_admin,
                "created_at": kenya_now()
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

    def get_all_ticket_properties(self):
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT id, name FROM properties"))
            return [dict(row._mapping) for row in result]
