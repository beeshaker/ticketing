import streamlit as st
from sqlalchemy import create_engine
import pandas as pd
import os
from dotenv import load_dotenv
from sqlalchemy.sql import text
import requests


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
        SELECT t.id, u.whatsapp_number, u.name,  t.issue_description, t.status, t.created_at, 
               t.property, u.unit_number, t.category, a.name AS assigned_admin 
        FROM tickets t 
        JOIN users u ON t.user_id = u.id
        LEFT JOIN admin_users a ON t.assigned_admin = a.id
        WHERE t.status != 'Resolved';
        """

        params = {}

        if property and property != "All":
            query += " AND t.property = :property"
            params["property"] = property

        df = pd.read_sql(query, self.engine, params=params)
        return df

    # -------------------- FETCH OPEN TICKETS -------------------- #
    def fetch_open_tickets(self, admin_id=None):
        """Fetch all open tickets, including category and assigned admin."""
        query = """
        SELECT t.id, u.whatsapp_number, u.name, t.issue_description, t.status, t.created_at, 
               t.property, u.unit_number, t.category, a.name AS assigned_admin 
        FROM tickets t 
        JOIN users u ON t.user_id = u.id
        LEFT JOIN admin_users a ON t.assigned_admin = a.id
        WHERE (
            t.assigned_admin = %s 
            OR t.id IN (SELECT ticket_id FROM admin_change_log WHERE old_admin = %s)
        )
        AND t.status != 'Resolved';
        """

        df = pd.read_sql(query, self.engine, params=(admin_id, admin_id))
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
        url = "https://whatsapp-apricot-4dd582d192d1.herokuapp.com/send_message"  # 🔁 replace with actual
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


    # -------------------- REASSIGN ADMIN -------------------- #
    def reassign_ticket_admin(self, ticket_id, new_admin_id, old_admin_id, changed_by_admin, reason, is_super_admin=False):
        """Reassigns a ticket to a new admin, logs the change, and allows Super Admins to override reassignment limits."""
        with self.engine.connect() as conn:
            # Get current reassignment count
            reassign_count = conn.execute(
                text("SELECT COUNT(*) FROM admin_change_log WHERE ticket_id = :ticket_id"),
                {"ticket_id": ticket_id}
            ).scalar()

            # Limit reassignment to 3 times unless a Super Admin is performing the action
            if reassign_count >= 3 and not is_super_admin:
                return False, "⚠️ Reassignment limit reached. Only a Super Admin can override."

            # Update assigned admin
            conn.execute(
                text("UPDATE tickets SET assigned_admin = :new_admin_id WHERE id = :ticket_id"),
                {"new_admin_id": new_admin_id, "ticket_id": ticket_id}
            )
            conn.commit()

            # Log reassignment
            conn.execute(
                text("""
                    INSERT INTO admin_change_log (
                        ticket_id, old_admin, new_admin, changed_by_admin, reason, 
                        reassign_count, changed_at, override_by_super_admin
                    )
                    VALUES (
                        :ticket_id, :old_admin_id, :new_admin_id, :changed_by_admin, :reason, 
                        :new_reassign_count, NOW(), :is_super_admin
                    )
                """),
                {
                    "ticket_id": ticket_id,
                    "old_admin_id": old_admin_id,
                    "new_admin_id": new_admin_id,
                    "changed_by_admin": changed_by_admin,
                    "reason": reason,
                    "new_reassign_count": reassign_count + 1,
                    "is_super_admin": is_super_admin
                }
            )
            conn.commit()

        # Notify new admin via WhatsApp
        result = self.fetch_admin_users()
        for admin in result:
            if admin["id"] == new_admin_id:
                new_admin_whatsapp = admin["whatsapp_number"]
                self.send_template_notification(
                    to=new_admin_whatsapp,
                    template_name="ticket_reassignment",
                    template_parameters=[f"#{ticket_id}", changed_by_admin, reason]
                )
                break

        return True, "✅ Ticket reassigned successfully!"


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
    
    def get_all_properties(self):
        """Fetches the history of admin reassignments."""
        query = """
        SELECT name from properties where 1
        """

        df = pd.read_sql(query, self.engine)
        return df["name"].tolist() 



    
    
    
    def send_template_notification(self, to, template_name, template_parameters):
        
        """Sends a WhatsApp template message using the Flask backend API."""
        url = "https://whatsapp-apricot-4dd582d192d1.herokuapp.com/send_message"
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

