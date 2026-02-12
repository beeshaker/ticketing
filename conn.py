# conn.py (FULL UPDATED — duplicates removed, WhatsApp inbox ready)

import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

import bcrypt
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.sql import text

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
        DB_URI = (
            f"mysql+mysqlconnector://{st.secrets.DB_USER}:{st.secrets.DB_PASSWORD}"
            f"@{st.secrets.DB_HOST}/{st.secrets.DB_NAME}"
        )
        self.engine = create_engine(DB_URI)

    # -------------------- FETCH TICKETS (ALL ACTIVE) -------------------- #
    def fetch_tickets(self, property=None):
        """Fetches all non-resolved tickets with read status."""
        query = """
        SELECT
            t.id,
            t.status,
            u.name,
            t.issue_description,
            t.due_date AS Due_Date,
            t.category,
            p.name AS property,
            u.unit_number,
            u.whatsapp_number,
            t.created_at,
            a.name AS assigned_admin,
            t.is_read
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
    def fetch_open_tickets(self, admin_id=None):
        """Fetch tickets for an admin, including read status."""
        query = """
        SELECT
            t.id,
            t.status,
            u.name,
            t.issue_description,
            t.due_date AS Due_Date,
            p.name AS property,
            u.unit_number,
            u.whatsapp_number,
            t.created_at,
            t.category,
            a.name AS assigned_admin,
            t.is_read
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
        q = text("""
            SELECT
                COUNT(id),
                MAX(id),
                SUM(CASE WHEN is_read = FALSE THEN 1 ELSE 0 END)
            FROM tickets
            WHERE status != 'Resolved'
        """)

        with self.engine.connect() as conn:
            result = conn.execute(q).fetchone()

            if not result or result[0] == 0:
                return "0-0-0"

            count = result[0]
            max_id = result[1] if result[1] is not None else 0
            unread = int(result[2]) if result[2] is not None else 0

            return f"{count}-{max_id}-{unread}"

    # -------------------- UPDATE TICKET READ STATUS -------------------- #
    def mark_ticket_as_read(self, ticket_id):
        q = text("UPDATE tickets SET is_read = TRUE WHERE id = :id")
        with self.engine.connect() as conn:
            conn.execute(q, {"id": ticket_id})
            conn.commit()

    # -------------------- FETCH ADMIN USERS -------------------- #
    def fetch_admin_users(self):
        q = "SELECT id, name, whatsapp_number FROM admin_users"
        df = pd.read_sql(q, self.engine)
        return df.to_dict("records")

    def fetch_all_admin_users(self):
        q = "SELECT id, name, whatsapp_number, admin_type FROM admin_users"
        df = pd.read_sql(q, self.engine)
        return df.to_dict("records")

    # -------------------- WHATSAPP HELPERS -------------------- #
    def send_whatsapp_notification(self, to, message):
        """Sends a WhatsApp message using the Flask backend API."""
        url = st.secrets.URL
        api_key = st.secrets.get("INTERNAL_API_KEY")
        headers = {"Content-Type": "application/json", "X-API-KEY": api_key}
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
        headers = {"Content-Type": "application/json", "X-API-KEY": api_key}
        payload = {
            "to": to,
            "template_name": template_name,
            "template_parameters": template_parameters,
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    # -------------------- UPDATE TICKET STATUS -------------------- #
    def update_ticket_status(self, ticket_id, new_status):
        """
        Updates ticket status and resolved_at.
        If Resolved:
        - Auto-create a Job Card (if missing)
        - Generate/ensure public token
        - Send tenant a public verification link (password is last 4 digits of WhatsApp)
        """
        PUBLIC_BASE_URL = st.secrets.get("PUBLIC_PORTAL_BASE_URL", "").rstrip("/")

        wa_number = None
        job_card_id = None

        with self.engine.begin() as conn:
            if new_status == "Resolved":
                conn.execute(
                    text("""
                        UPDATE tickets
                        SET status = :new_status,
                            resolved_at = NOW()
                        WHERE id = :ticket_id
                    """),
                    {"new_status": new_status, "ticket_id": ticket_id},
                )
            else:
                conn.execute(
                    text("""
                        UPDATE tickets
                        SET status = :new_status,
                            resolved_at = NULL
                        WHERE id = :ticket_id
                    """),
                    {"new_status": new_status, "ticket_id": ticket_id},
                )

            row = conn.execute(
                text("""
                    SELECT u.whatsapp_number
                    FROM users u
                    JOIN tickets t ON u.id = t.user_id
                    WHERE t.id = :ticket_id
                    LIMIT 1
                """),
                {"ticket_id": ticket_id},
            ).fetchone()

            if row and row[0]:
                wa_number = str(row[0]).strip()

        # Always send status-change template
        if wa_number:
            self.send_template_notification(
                to=wa_number,
                template_name="ticket_status_change",
                template_parameters=[f"#{ticket_id}", new_status],
            )

        # Only on Resolved: share Job Card public link
        if new_status != "Resolved":
            return

        if not PUBLIC_BASE_URL:
            return

        jc = self.get_job_card_by_ticket(ticket_id)
        if jc and jc.get("id"):
            job_card_id = int(jc["id"])
        else:
            job_card_id = int(
                self.create_job_card_from_ticket(
                    ticket_id=int(ticket_id),
                    created_by_admin_id=None,
                    assigned_admin_id=None,
                    title=None,
                    estimated_cost=None,
                    copy_media=True,
                )
            )

        token = self.ensure_job_card_public_token(job_card_id)
        public_link = f"{PUBLIC_BASE_URL}/verify_job_card?id={job_card_id}&t={token}"

        if wa_number:
            msg = (
                f"✅ Ticket #{ticket_id} resolved.\n\n"
                f"🧾 Your Job Card is ready:\n{public_link}\n\n"
                f"🔐 To view costs & attachments, enter the last 4 digits of your WhatsApp number."
            )

            try:
                self.send_whatsapp_notification(to=wa_number, message=msg)
            except Exception:
                self.send_template_notification(
                    to=wa_number,
                    template_name="job_card_ready",
                    template_parameters=[f"#{ticket_id}", public_link],
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
                    "created_at": kenya_now(),
                },
            )
            conn.commit()

            result = conn.execute(
                text("""
                    SELECT u.whatsapp_number
                    FROM users u
                    JOIN tickets t ON u.id = t.user_id
                    WHERE t.id = :ticket_id
                """),
                {"ticket_id": ticket_id},
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
                {"ticket_id": ticket_id},
            ).fetchall()

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
                {"ticket_id": ticket_id},
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
                    {"ticket_id": ticket_id},
                ).scalar()

                reassign_count = int(reassign_count or 0)

                if reassign_count >= 3 and not is_super_admin:
                    return False, "⚠️ Reassignment limit reached. Only a Super Admin can override."

                conn.execute(
                    text("UPDATE tickets SET assigned_admin = :new_admin_id WHERE id = :ticket_id"),
                    {"new_admin_id": new_admin_id, "ticket_id": ticket_id},
                )

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
                        "is_super_admin": is_super_admin,
                    },
                )

            admin_users = self.fetch_admin_users()
            new_admin_info = next((a for a in admin_users if str(a["id"]) == str(new_admin_id)), None)
            if new_admin_info and new_admin_info.get("whatsapp_number"):
                self.send_template_notification(
                    to=new_admin_info["whatsapp_number"],
                    template_name="ticket_reassignment",
                    template_parameters=[f"#{ticket_id}", changed_by_admin, reason],
                )

            return True, "✅ Ticket reassigned successfully!"

        except Exception as e:
            print(f"❌ Unexpected error in reassign_ticket_admin: {e}")
            return False, "❌ An unexpected error occurred during reassignment."

    def get_admin_role_and_property(self, admin_id):
        """Returns admin_type and property_id for given admin."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT admin_type, property_id FROM admin_users WHERE id = :id"),
                {"id": admin_id},
            ).mappings().fetchone()
            return result if result else None

    # -------------------- FETCH ADMIN REASSIGNMENT LOG -------------------- #
    def fetch_admin_reassignment_log(self):
        query = """
        SELECT
            l.ticket_id,
            t.issue_description,
            u1.name AS old_admin,
            u2.name AS new_admin,
            l.changed_by_admin,
            l.reason,
            l.reassign_count,
            l.changed_at,
            l.override_by_super_admin
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
        q = """
            SELECT media_type, media_blob, media_path AS filename
            FROM ticket_media
            WHERE ticket_id = :ticket_id
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(q), conn, params={"ticket_id": ticket_id})
        return df

    # -------------------- DUE DATE -------------------- #
    def update_ticket_due_date(self, ticket_id, due_date):
        with self.engine.connect() as conn:
            conn.execute(
                text("UPDATE tickets SET due_date = :due_date WHERE id = :ticket_id"),
                {"due_date": due_date, "ticket_id": ticket_id},
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
            q = text("""
                SELECT id, name, whatsapp_number
                FROM users
                WHERE property_id = :property_id
            """)
            result = conn.execute(q, {"property_id": property_id})
            users = [dict(row) for row in result.fetchall()]
        return users

    # -------------------- PROPERTIES -------------------- #
    def create_property(self, property_name, supervisor_id):
        """Create property and assign supervisor (also set supervisor's property_id)."""
        with self.engine.connect() as conn:
            existing = conn.execute(
                text("SELECT id FROM properties WHERE name = :name"),
                {"name": property_name},
            ).fetchone()

            if existing:
                return False, "❌ Property with this name already exists."

            try:
                conn.execute(
                    text("INSERT INTO properties (name, supervisor_id) VALUES (:name, :supervisor_id)"),
                    {"name": property_name, "supervisor_id": supervisor_id},
                )

                property_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

                conn.execute(
                    text("UPDATE admin_users SET property_id = :property_id WHERE id = :supervisor_id"),
                    {"property_id": property_id, "supervisor_id": supervisor_id},
                )

                conn.commit()
                return True, "✅ Property created and supervisor assigned successfully!"
            except Exception as e:
                return False, f"❌ Failed to create property: {e}"

    def get_available_property_managers(self):
        """Fetch all Property Managers."""
        q = """
        SELECT id, name
        FROM admin_users
        WHERE admin_type = 'Property Supervisor'
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(text(q), conn)
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
                {"property_id": property_id},
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
                conn.execute(update_query, {"name": name, "supervisor_id": None, "property_id": property_id})
                return

            check_query = text("""
                SELECT id FROM admin_users
                WHERE id = :id AND admin_type = 'Property Supervisor'
            """)
            valid = conn.execute(check_query, {"id": supervisor_id}).fetchone()
            if not valid:
                raise ValueError("Supervisor must be a valid Property Supervisor.")

            conn.execute(update_query, {"name": name, "supervisor_id": supervisor_id, "property_id": property_id})

    def delete_property(self, property_id):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM properties WHERE id = :property_id"), {"property_id": property_id})

    def get_all_properties(self):
        """Returns properties with supervisor info (supervisor_name None if unassigned)."""
        q = """
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
            result = conn.execute(text(q)).mappings().all()
        return result if result else []

    def get_property_supervisor_by_property(self, property_id):
        """Fetch supervisor details for a property."""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT supervisor_id FROM properties WHERE id = :property_id"),
                {"property_id": property_id},
            ).fetchone()

            if not result or not result[0]:
                return None

            supervisor_id = result[0]

            result = conn.execute(
                text("""
                    SELECT id, name, whatsapp_number
                    FROM admin_users
                    WHERE id = :supervisor_id
                """),
                {"supervisor_id": supervisor_id},
            ).mappings().fetchone()

            return result if result else None

    def count_admin_users_by_property(self, property_id):
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT COUNT(*) FROM admin_users WHERE property_id = :pid"),
                {"pid": property_id},
            ).scalar()

    def count_tickets_by_property(self, property_id):
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT COUNT(*) FROM tickets WHERE property_id = :pid"),
                {"pid": property_id},
            ).scalar()

    def reassign_admin_users(self, old_property_id, new_property_id):
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE admin_users
                    SET property_id = :new_pid
                    WHERE property_id = :old_pid
                """),
                {"old_pid": old_property_id, "new_pid": new_property_id},
            )

    def reassign_tickets(self, old_property_id, new_property_id):
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tickets
                    SET property_id = :new_pid
                    WHERE property_id = :old_pid
                """),
                {"old_pid": old_property_id, "new_pid": new_property_id},
            )

    def null_admins_by_property(self, property_id):
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE admin_users
                    SET property_id = NULL
                    WHERE property_id = :pid
                """),
                {"pid": property_id},
            )

    def delete_tickets_by_property(self, property_id):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM tickets WHERE property_id = :pid"), {"pid": property_id})

    # -------------------- USERS -------------------- #
    def get_all_users(self):
        q = "SELECT * FROM users"
        with self.engine.connect() as conn:
            df = pd.read_sql(text(q), conn)
        return df.to_dict("records")

    def update_user(self, user_id, name, whatsapp_number, property_id, unit_number):
        q = text("""
            UPDATE users
            SET name = :name,
                whatsapp_number = :whatsapp_number,
                property_id = :property_id,
                unit_number = :unit_number
            WHERE id = :user_id
        """)
        with self.engine.begin() as conn:
            conn.execute(
                q,
                {
                    "name": name,
                    "whatsapp_number": whatsapp_number,
                    "property_id": property_id,
                    "unit_number": unit_number,
                    "user_id": user_id,
                },
            )

    def delete_user(self, user_id):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})

    # -------------------- ADMINS -------------------- #
    def get_all_admin_users(self):
        q = "SELECT * FROM admin_users"
        with self.engine.connect() as conn:
            df = pd.read_sql(text(q), conn)
        return df.to_dict("records")

    def update_admin_user(self, admin_id, name, username, whatsapp_number, admin_type, property_id):
        if str(property_id).lower() == "nan" or property_id in ("", None):
            property_id = None

        q = text("""
            UPDATE admin_users
            SET name = :name,
                username = :username,
                whatsapp_number = :whatsapp_number,
                admin_type = :admin_type,
                property_id = :property_id
            WHERE id = :admin_id
        """)
        with self.engine.begin() as conn:
            conn.execute(
                q,
                {
                    "name": name,
                    "username": username,
                    "whatsapp_number": whatsapp_number,
                    "admin_type": admin_type,
                    "property_id": property_id,
                    "admin_id": admin_id,
                },
            )

    def delete_admin_user(self, admin_id):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM admin_users WHERE id = :admin_id"), {"admin_id": admin_id})

    def reset_admin_password(self, admin_id, plain_password):
        hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()
        q = text("UPDATE admin_users SET password = :password WHERE id = :admin_id")
        with self.engine.begin() as conn:
            conn.execute(q, {"password": hashed, "admin_id": admin_id})

    # -------------------- TICKET CREATION (ADMIN PORTAL SIDE) -------------------- #
    def insert_ticket_and_get_id(self, user_id, description, category, property_id, assigned_admin):
        """
        Inserts a new ticket and returns its ID.
        IMPORTANT: Uses Kenya time instead of NOW() (server time).
        """
        insert_q = text("""
            INSERT INTO tickets
            (user_id, issue_description, status, created_at, category, property_id, assigned_admin)
            VALUES (:user_id, :description, 'Open', :created_at, :category, :property_id, :assigned_admin)
        """)
        select_q = text("SELECT LAST_INSERT_ID() AS id")

        with self.engine.connect() as conn:
            conn.execute(
                insert_q,
                {
                    "user_id": user_id,
                    "description": description,
                    "category": category,
                    "property_id": property_id,
                    "assigned_admin": assigned_admin,
                    "created_at": kenya_now(),
                },
            )
            result = conn.execute(select_q).fetchone()
            conn.commit()
            return result[0]

    def get_user_id_by_unit_and_property(self, unit_number, property_id):
        with self.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id FROM users
                    WHERE unit_number = :unit_number AND property_id = :property_id
                """),
                {"unit_number": unit_number, "property_id": property_id},
            ).fetchone()
            return result[0] if result else None

    def get_all_ticket_properties(self):
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT id, name FROM properties"))
            return [dict(row._mapping) for row in result]

    # -------------------- KPI / REPORTS -------------------- #
    def kpi_summary(self, start_dt, end_dt):
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    WITH base AS (
                        SELECT id, created_at, status, resolved_at
                        FROM tickets
                        WHERE created_at >= :start_dt
                          AND created_at <  :end_dt
                    ),
                    first_action AS (
                        SELECT tu.ticket_id, MIN(tu.created_at) AS first_response_at
                        FROM ticket_updates tu
                        JOIN base b ON b.id = tu.ticket_id
                        GROUP BY tu.ticket_id
                    )
                    SELECT
                        SUM(CASE WHEN b.status IN ('Open','In Progress') THEN 1 ELSE 0 END) AS open_count,
                        SUM(CASE WHEN b.status = 'Resolved' THEN 1 ELSE 0 END) AS closed_count,
                        CASE
                            WHEN COUNT(*) = 0 THEN 0
                            ELSE ROUND(
                                (SUM(CASE WHEN b.status = 'Resolved' THEN 1 ELSE 0 END) / COUNT(*)) * 100,
                                0
                            )
                        END AS pct_closed,
                        AVG(
                            CASE
                                WHEN fa.first_response_at IS NULL THEN NULL
                                ELSE TIMESTAMPDIFF(SECOND, b.created_at, fa.first_response_at)
                            END
                        ) AS avg_first_response_seconds,
                        AVG(
                            CASE
                                WHEN b.resolved_at IS NULL THEN NULL
                                ELSE TIMESTAMPDIFF(SECOND, b.created_at, b.resolved_at)
                            END
                        ) AS avg_resolution_seconds
                    FROM base b
                    LEFT JOIN first_action fa ON fa.ticket_id = b.id
                """),
                {"start_dt": start_dt, "end_dt": end_dt},
            ).mappings().first()

        return dict(row) if row else {
            "open_count": 0,
            "closed_count": 0,
            "pct_closed": 0,
            "avg_first_response_seconds": None,
            "avg_resolution_seconds": None,
        }

    def tickets_per_day(self, start_dt, end_dt):
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        DATE(created_at) AS day,
                        SUM(CASE WHEN status IN ('Open','In Progress') THEN 1 ELSE 0 END) AS open_count,
                        SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS closed_count
                    FROM tickets
                    WHERE created_at >= :start_dt
                      AND created_at <  :end_dt
                    GROUP BY DATE(created_at)
                    ORDER BY day ASC
                """),
                {"start_dt": start_dt, "end_dt": end_dt},
            ).mappings().all()

        return pd.DataFrame(rows)

    def tickets_by_category(self, start_dt, end_dt):
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        COALESCE(NULLIF(TRIM(category), ''), 'Unspecified') AS category,
                        COUNT(*) AS tickets
                    FROM tickets
                    WHERE created_at >= :start_dt
                      AND created_at <  :end_dt
                    GROUP BY COALESCE(NULLIF(TRIM(category), ''), 'Unspecified')
                    ORDER BY tickets DESC
                """),
                {"start_dt": start_dt, "end_dt": end_dt},
            ).mappings().all()

        return pd.DataFrame(rows)

    def tickets_by_property(self, start_dt, end_dt):
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        COALESCE(p.name, 'Unassigned') AS property,
                        COUNT(*) AS tickets
                    FROM tickets t
                    LEFT JOIN properties p ON p.id = t.property_id
                    WHERE t.created_at >= :start_dt
                      AND t.created_at <  :end_dt
                    GROUP BY COALESCE(p.name, 'Unassigned')
                    ORDER BY tickets DESC
                """),
                {"start_dt": start_dt, "end_dt": end_dt},
            ).mappings().all()

        return pd.DataFrame(rows)

    # -------------------- JOB CARDS -------------------- #
    def get_job_card_by_ticket(self, ticket_id: int):
        q = text("""
            SELECT jc.*,
                p.name AS property_name,
                a1.name AS created_by_name,
                a2.name AS assigned_to_name
            FROM job_cards jc
            LEFT JOIN properties p ON p.id = jc.property_id
            LEFT JOIN admin_users a1 ON a1.id = jc.created_by_admin_id
            LEFT JOIN admin_users a2 ON a2.id = jc.assigned_admin_id
            WHERE jc.ticket_id = :ticket_id
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            row = conn.execute(q, {"ticket_id": ticket_id}).mappings().first()
        return dict(row) if row else None

    def get_job_card(self, job_card_id: int):
        q = text("""
            SELECT jc.*,
                p.name AS property_name,
                a1.name AS created_by_name,
                a2.name AS assigned_to_name
            FROM job_cards jc
            LEFT JOIN properties p ON p.id = jc.property_id
            LEFT JOIN admin_users a1 ON a1.id = jc.created_by_admin_id
            LEFT JOIN admin_users a2 ON a2.id = jc.assigned_admin_id
            WHERE jc.id = :id
        """)
        with self.engine.connect() as conn:
            row = conn.execute(q, {"id": job_card_id}).mappings().first()
        return dict(row) if row else None

    def fetch_job_cards(self, status=None, property_id=None, has_ticket=None):
        base = """
            SELECT
                jc.id,
                jc.ticket_id,
                jc.status,
                jc.title,
                jc.created_at,
                p.name AS property,
                jc.unit_number,
                a.name AS assigned_admin,
                jc.estimated_cost,
                jc.actual_cost
            FROM job_cards jc
            LEFT JOIN properties p ON p.id = jc.property_id
            LEFT JOIN admin_users a ON a.id = jc.assigned_admin_id
            WHERE 1=1
        """
        params = {}

        if status and status != "All":
            base += " AND jc.status = :status"
            params["status"] = status

        if property_id and str(property_id) != "All":
            base += " AND jc.property_id = :property_id"
            params["property_id"] = property_id

        if has_ticket == "Yes":
            base += " AND jc.ticket_id IS NOT NULL"
        elif has_ticket == "No":
            base += " AND jc.ticket_id IS NULL"

        base += " ORDER BY jc.id DESC"

        with self.engine.connect() as conn:
            df = pd.read_sql(text(base), conn, params=params)
        return df

    def fetch_job_card_media(self, job_card_id: int):
        q = text("""
            SELECT media_type, media_blob, filename
            FROM job_card_media
            WHERE job_card_id = :job_card_id
            ORDER BY id DESC
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(q, conn, params={"job_card_id": job_card_id})
        return df

    def fetch_ticket_updates_as_activities_text(self, ticket_id: int) -> str:
        with self.engine.connect() as conn:
            updates = conn.execute(
                text("""
                    SELECT updated_by, update_text, created_at
                    FROM ticket_updates
                    WHERE ticket_id = :ticket_id
                    ORDER BY created_at ASC
                """),
                {"ticket_id": ticket_id},
            ).mappings().all()

            reassigns = conn.execute(
                text("""
                    SELECT changed_by_admin, reason, changed_at
                    FROM admin_change_log
                    WHERE ticket_id = :ticket_id
                    ORDER BY changed_at ASC
                """),
                {"ticket_id": ticket_id},
            ).mappings().all()

        lines = []
        for u in updates:
            dt = u["created_at"]
            ts = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)
            lines.append(f"[UPDATE] {ts} • {u['updated_by']}: {u['update_text']}")

        for r in reassigns:
            dt = r["changed_at"]
            ts = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)
            lines.append(f"[REASSIGN] {ts} • {r['changed_by_admin']}: {r['reason']}")

        return "\n".join(lines) if lines else ""

    def create_job_card_from_ticket(
        self,
        ticket_id: int,
        created_by_admin_id: int | None,
        assigned_admin_id: int | None,
        title: str | None = None,
        estimated_cost: float | None = None,
        copy_media: bool = True,
    ):
        existing = self.get_job_card_by_ticket(ticket_id)
        if existing:
            return existing["id"]

        with self.engine.begin() as conn:
            t = conn.execute(
                text("""
                    SELECT t.id, t.issue_description, t.property_id, u.unit_number
                    FROM tickets t
                    JOIN users u ON u.id = t.user_id
                    WHERE t.id = :ticket_id
                """),
                {"ticket_id": ticket_id},
            ).mappings().first()

            if not t:
                raise ValueError("Ticket not found.")

            activities_text = self.fetch_ticket_updates_as_activities_text(ticket_id)

            conn.execute(
                text("""
                    INSERT INTO job_cards (
                        ticket_id, property_id, unit_number,
                        created_by_admin_id, assigned_admin_id,
                        title, description, activities,
                        estimated_cost, status, created_at
                    )
                    VALUES (
                        :ticket_id, :property_id, :unit_number,
                        :created_by, :assigned_to,
                        :title, :description, :activities,
                        :estimated_cost, 'Open', :created_at
                    )
                """),
                {
                    "ticket_id": ticket_id,
                    "property_id": t["property_id"],
                    "unit_number": t["unit_number"],
                    "created_by": created_by_admin_id,
                    "assigned_to": assigned_admin_id,
                    "title": title,
                    "description": t["issue_description"],
                    "activities": activities_text,
                    "estimated_cost": estimated_cost,
                    "created_at": kenya_now(),
                },
            )

            job_card_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

            if copy_media:
                conn.execute(
                    text("""
                        INSERT INTO job_card_media (job_card_id, media_type, media_blob, filename, source_ticket_media_id)
                        SELECT
                            :job_card_id,
                            tm.media_type,
                            tm.media_blob,
                            tm.media_path,
                            tm.id
                        FROM ticket_media tm
                        WHERE tm.ticket_id = :ticket_id
                    """),
                    {"job_card_id": job_card_id, "ticket_id": ticket_id},
                )

        return int(job_card_id)

    def create_job_card_standalone(
        self,
        description: str,
        property_id: int | None,
        unit_number: str | None,
        created_by_admin_id: int | None,
        assigned_admin_id: int | None,
        title: str | None = None,
        activities: str | None = None,
        estimated_cost: float | None = None,
    ):
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO job_cards (
                        ticket_id, property_id, unit_number,
                        created_by_admin_id, assigned_admin_id,
                        title, description, activities,
                        estimated_cost, status, created_at
                    )
                    VALUES (
                        NULL, :property_id, :unit_number,
                        :created_by, :assigned_to,
                        :title, :description, :activities,
                        :estimated_cost, 'Open', :created_at
                    )
                """),
                {
                    "property_id": property_id,
                    "unit_number": unit_number,
                    "created_by": created_by_admin_id,
                    "assigned_to": assigned_admin_id,
                    "title": title,
                    "description": description,
                    "activities": activities,
                    "estimated_cost": estimated_cost,
                    "created_at": kenya_now(),
                },
            )
            job_card_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        return int(job_card_id)

    def add_job_card_media(self, job_card_id: int, media_type: str, media_blob: bytes, filename: str | None):
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO job_card_media (job_card_id, media_type, media_blob, filename, uploaded_at)
                    VALUES (:job_card_id, :media_type, :media_blob, :filename, :uploaded_at)
                """),
                {
                    "job_card_id": job_card_id,
                    "media_type": media_type,
                    "media_blob": media_blob,
                    "filename": filename,
                    "uploaded_at": kenya_now(),
                },
            )

    def update_job_card_status(self, job_card_id: int, new_status: str):
        with self.engine.begin() as conn:
            if new_status == "Completed":
                conn.execute(
                    text("""
                        UPDATE job_cards
                        SET status = :status,
                            completed_at = :completed_at
                        WHERE id = :id
                    """),
                    {"status": new_status, "completed_at": kenya_now(), "id": job_card_id},
                )
            else:
                conn.execute(
                    text("""
                        UPDATE job_cards
                        SET status = :status
                        WHERE id = :id
                    """),
                    {"status": new_status, "id": job_card_id},
                )

    def update_job_card_costs(self, job_card_id: int, estimated_cost=None, actual_cost=None):
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE job_cards
                    SET estimated_cost = :estimated_cost,
                        actual_cost = :actual_cost
                    WHERE id = :id
                """),
                {"estimated_cost": estimated_cost, "actual_cost": actual_cost, "id": job_card_id},
            )

    def update_job_card(
        self,
        job_card_id: int,
        title: str | None,
        description: str | None,
        activities: str | None,
        status: str,
        estimated_cost: float | None,
        actual_cost: float | None,
        assigned_admin_id: int | None,
    ):
        q = text("""
            UPDATE job_cards
            SET
                title = :title,
                description = :description,
                activities = :activities,
                status = :status,
                estimated_cost = :estimated_cost,
                actual_cost = :actual_cost,
                assigned_admin_id = :assigned_admin_id,
                updated_at = :updated_at
            WHERE id = :id
        """)
        with self.engine.begin() as conn:
            conn.execute(
                q,
                {
                    "id": job_card_id,
                    "title": title,
                    "description": description,
                    "activities": activities,
                    "status": status,
                    "estimated_cost": estimated_cost,
                    "actual_cost": actual_cost,
                    "assigned_admin_id": assigned_admin_id,
                    "updated_at": kenya_now(),
                },
            )

    # ✅ keep ONE signoff method (the later, simpler version)
    def signoff_job_card(
        self,
        job_card_id: int,
        signed_by_name: str,
        signed_by_role: str,
        signoff_notes: str | None = None,
    ):
        q = text("""
            INSERT INTO job_card_signoff
            (job_card_id, signed_by_name, signed_by_role, signoff_notes, signed_at)
            VALUES (:job_card_id, :signed_by_name, :signed_by_role, :signoff_notes, :signed_at)
        """)
        with self.engine.begin() as conn:
            conn.execute(
                q,
                {
                    "job_card_id": job_card_id,
                    "signed_by_name": signed_by_name,
                    "signed_by_role": signed_by_role,
                    "signoff_notes": signoff_notes,
                    "signed_at": kenya_now(),
                },
            )

    def get_job_card_signoff(self, job_card_id: int):
        q = text("""
            SELECT signed_by_name, signed_by_role, signoff_notes, signed_at
            FROM job_card_signoff
            WHERE job_card_id = :id
            ORDER BY id DESC
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            row = conn.execute(q, {"id": job_card_id}).mappings().first()
        return dict(row) if row else None

    # -------------------- JOB CARD PUBLIC VERIFY -------------------- #
    def get_job_card_public(self, job_card_id: int, token: str):
        q = text("""
            SELECT
                jc.id,
                jc.ticket_id,
                jc.status,
                jc.title,
                jc.description,
                jc.activities,
                jc.estimated_cost,
                jc.actual_cost,
                jc.property_id,
                p.name AS property_name,
                jc.unit_number
            FROM job_cards jc
            LEFT JOIN properties p ON p.id = jc.property_id
            WHERE jc.id = :id
              AND jc.public_token = :t
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            row = conn.execute(q, {"id": job_card_id, "t": token}).mappings().first()
        return dict(row) if row else None

    def verify_job_card_pin(self, job_card_id: int, token: str, pin4: str) -> bool:
        q = text("""
            SELECT u.whatsapp_number
            FROM job_cards jc
            JOIN tickets t ON t.id = jc.ticket_id
            JOIN users u ON u.id = t.user_id
            WHERE jc.id = :id
              AND jc.public_token = :t
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            row = conn.execute(q, {"id": job_card_id, "t": token}).fetchone()
            if not row or not row[0]:
                return False

            wa = str(row[0]).strip()
            if len(wa) < 4:
                return False

            return wa[-4:] == str(pin4).strip()

    def ensure_job_card_public_token(self, job_card_id: int) -> str:
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT public_token FROM job_cards WHERE id = :id"),
                {"id": job_card_id},
            ).scalar()

            if existing and str(existing).strip():
                return str(existing)

            token = secrets.token_urlsafe(48)
            conn.execute(
                text("""
                    UPDATE job_cards
                    SET public_token = :t,
                        public_token_created_at = NOW()
                    WHERE id = :id
                """),
                {"t": token, "id": job_card_id},
            )
            return token

    # -------------------- WHATSAPP LOGGING (ONE VERSION) -------------------- #
    def log_whatsapp_message(
        self,
        job_card_id: int | None,
        ticket_id: int | None,
        direction: str,
        wa_to: str | None,
        message_type: str = "text",
        template_name: str | None = None,
        body_text: str | None = None,
        verify_url: str | None = None,
        meta_message_id: str | None = None,
        status: str | None = None,
        error_text: str | None = None,
        wa_from: str | None = None,
        wa_number: str | None = None,
    ):
        """
        Updated logger:
        - wa_number is the conversation key (use wa_to for outbound, wa_from for inbound)
        """
        wa_to_val = str(wa_to).strip() if wa_to else None
        wa_from_val = str(wa_from).strip() if wa_from else None

        wa_number_val = (
            (str(wa_number).strip() if wa_number else None)
            or (wa_to_val if direction == "outbound" else None)
            or (wa_from_val if direction == "inbound" else None)
        )

        q = text("""
            INSERT INTO whatsapp_message_log
            (job_card_id, ticket_id, direction, wa_number, wa_to, wa_from, message_type, template_name,
             body_text, verify_url, meta_message_id, status, error_text)
            VALUES
            (:job_card_id, :ticket_id, :direction, :wa_number, :wa_to, :wa_from, :message_type, :template_name,
             :body_text, :verify_url, :meta_message_id, :status, :error_text)
        """)
        with self.engine.begin() as conn:
            conn.execute(
                q,
                {
                    "job_card_id": job_card_id,
                    "ticket_id": ticket_id,
                    "direction": direction,
                    "wa_number": wa_number_val,
                    "wa_to": wa_to_val,
                    "wa_from": wa_from_val,
                    "message_type": message_type,
                    "template_name": template_name,
                    "body_text": body_text,
                    "verify_url": verify_url,
                    "meta_message_id": meta_message_id,
                    "status": status,
                    "error_text": error_text,
                },
            )

    def get_latest_job_card_whatsapp_message(self, job_card_id: int) -> dict | None:
        q = text("""
            SELECT id, wa_to, message_type, template_name, body_text, verify_url,
                   meta_message_id, status, error_text, created_at
            FROM whatsapp_message_log
            WHERE job_card_id = :job_card_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        with self.engine.begin() as conn:
            row = conn.execute(q, {"job_card_id": job_card_id}).mappings().first()
            return dict(row) if row else None

    # -------------------- WHATSAPP INBOX (GLOBAL) -------------------- #
    def get_ticket_whatsapp_number(self, ticket_id: int) -> str | None:
        q = text("""
            SELECT u.whatsapp_number
            FROM tickets t
            JOIN users u ON u.id = t.user_id
            WHERE t.id = :ticket_id
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            val = conn.execute(q, {"ticket_id": ticket_id}).scalar()
        return str(val).strip() if val else None

    def fetch_inbox_conversations(self, q_search: str | None = None, limit: int = 50) -> pd.DataFrame:
        """
        Returns one row per wa_number with last message + timestamp.
        """
        base = """
            WITH latest AS (
                SELECT wa_number, MAX(created_at) AS last_at
                FROM whatsapp_message_log
                WHERE wa_number IS NOT NULL AND TRIM(wa_number) <> ''
                GROUP BY wa_number
            )
            SELECT
                w.wa_number,
                w.direction,
                w.message_type,
                w.template_name,
                w.body_text,
                w.status,
                w.ticket_id,
                w.job_card_id,
                w.created_at AS last_at,
                0 AS unread_count
            FROM whatsapp_message_log w
            JOIN latest l
              ON l.wa_number = w.wa_number
             AND l.last_at = w.created_at
            WHERE 1=1
        """

        params = {}
        if q_search and q_search.strip():
            base += """
            AND (
                w.wa_number LIKE :qs
                OR (w.body_text IS NOT NULL AND w.body_text LIKE :qs)
            )
            """
            params["qs"] = f"%{q_search.strip()}%"

        base += " ORDER BY w.created_at DESC LIMIT :lim"
        params["lim"] = int(limit)

        with self.engine.connect() as conn:
            df = pd.read_sql(text(base), conn, params=params)
        return df

    def fetch_conversation_messages(self, wa_number: str, limit: int = 120, before_id: int | None = None) -> pd.DataFrame:
        if not wa_number:
            return pd.DataFrame()

        sql = """
            SELECT
                id,
                wa_number,
                direction,
                wa_to,
                wa_from,
                message_type,
                template_name,
                body_text,
                verify_url,
                meta_message_id,
                status,
                error_text,
                ticket_id,
                job_card_id,
                created_at
            FROM whatsapp_message_log
            WHERE wa_number = :wa
        """
        params = {"wa": wa_number, "lim": int(limit)}

        if before_id is not None:
            sql += " AND id < :before_id"
            params["before_id"] = int(before_id)

        sql += " ORDER BY id DESC LIMIT :lim"

        with self.engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
        return df

    # -------------------- PERFORMANCE -------------------- #
    def caretaker_performance(self, start_dt, end_dt):
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        a.name AS caretaker,
                        COUNT(*) AS tickets
                    FROM tickets t
                    LEFT JOIN admin_users a ON a.id = t.assigned_admin
                    WHERE t.created_at >= :start_dt
                      AND t.created_at <  :end_dt
                    GROUP BY a.name
                    ORDER BY tickets DESC
                    LIMIT 10
                """),
                {"start_dt": start_dt, "end_dt": end_dt},
            ).mappings().all()

        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df.insert(0, "#", range(1, len(df) + 1))
        return df
