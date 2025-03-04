import tkinter as tk
from tkinter import messagebox
import uuid
from datetime import datetime, timedelta
import pandas as pd
from pandastable import Table
from sqlalchemy.orm import Session
from database import SessionLocal
from models import License

# Function to Generate a License
def create_license():
    """Generate a license key and save it to the database."""
    company_name = company_name_entry.get()
    days = duration_entry.get()

    if not company_name or not days.isdigit():
        messagebox.showerror("Error", "Please enter a valid company name and duration (in days).")
        return

    expires_at = datetime.now() + timedelta(days=int(days))
    license_key = str(uuid.uuid4())  # Generate a unique key

    session = SessionLocal()
    
    try:
        new_license = License(
            company_name=company_name,
            license_key=license_key,
            expires_at=expires_at,
            is_active=True
        )
        session.add(new_license)
        session.commit()

        messagebox.showinfo("Success", f"License Key Generated:\n{license_key}")
        fetch_licenses()

    except Exception as e:
        session.rollback()
        messagebox.showerror("Database Error", str(e))
    
    finally:
        session.close()

# Function to Fetch Licenses
def fetch_licenses():
    """Retrieve all licenses from the database and display them in the table."""
    session = SessionLocal()
    
    try:
        licenses = session.query(License).all()
        df = pd.DataFrame([
            {"ID": l.id, "Company": l.company_name, "License Key": l.license_key, "Expires At": l.expires_at, "Active": l.is_active}
            for l in licenses
        ])
        update_table(df)

    except Exception as e:
        messagebox.showerror("Database Error", str(e))
    
    finally:
        session.close()

# Function to Update the Pandas Table
def update_table(df):
    """Display data in a PandasTable inside the Tkinter GUI."""
    for widget in table_frame.winfo_children():
        widget.destroy()

    table = Table(table_frame, dataframe=df, showtoolbar=True, showstatusbar=True)
    table.show()

# Function to Deactivate a License
def deactivate_license():
    """Deactivate a license by setting is_active to False."""
    license_id = deactivate_entry.get()

    if not license_id.isdigit():
        messagebox.showerror("Error", "Please enter a valid License ID.")
        return

    session = SessionLocal()
    
    try:
        license_record = session.query(License).filter(License.id == int(license_id)).first()

        if not license_record:
            messagebox.showerror("Error", f"License ID {license_id} not found.")
            return
        
        license_record.is_active = False
        session.commit()

        messagebox.showinfo("Success", f"License ID {license_id} deactivated.")
        fetch_licenses()

    except Exception as e:
        session.rollback()
        messagebox.showerror("Database Error", str(e))

    finally:
        session.close()

# Function to Reactivate a License
def reactivate_license():
    """Reactivate a license by setting is_active to True."""
    license_id = reactivate_entry.get()

    if not license_id.isdigit():
        messagebox.showerror("Error", "Please enter a valid License ID.")
        return

    session = SessionLocal()
    
    try:
        license_record = session.query(License).filter(License.id == int(license_id)).first()

        if not license_record:
            messagebox.showerror("Error", f"License ID {license_id} not found.")
            return
        
        if license_record.is_active:
            messagebox.showinfo("Info", f"License ID {license_id} is already active.")
            return

        license_record.is_active = True
        license_record.expires_at = datetime.utcnow() + timedelta(days=365)  # Extend by 1 year
        session.commit()

        messagebox.showinfo("Success", f"License ID {license_id} reactivated.")
        fetch_licenses()

    except Exception as e:
        session.rollback()
        messagebox.showerror("Database Error", str(e))

    finally:
        session.close()

# Initialize GUI
root = tk.Tk()
root.title("License Generator")
root.geometry("700x500")

# Company Name
tk.Label(root, text="Company Name:").grid(row=0, column=0, padx=10, pady=5)
company_name_entry = tk.Entry(root, width=30)
company_name_entry.grid(row=0, column=1, padx=10, pady=5)

# Duration (in days)
tk.Label(root, text="Duration (Days):").grid(row=1, column=0, padx=10, pady=5)
duration_entry = tk.Entry(root, width=10)
duration_entry.grid(row=1, column=1, padx=10, pady=5)
duration_entry.insert(0, "365")  # Default to 1 year

# Generate License Button
generate_button = tk.Button(root, text="Generate License", command=create_license)
generate_button.grid(row=2, column=0, columnspan=2, pady=10)

# License Table
table_frame = tk.Frame(root)
table_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10)

# Deactivate License Section
tk.Label(root, text="Deactivate License ID:").grid(row=4, column=0, padx=10, pady=5)
deactivate_entry = tk.Entry(root, width=10)
deactivate_entry.grid(row=4, column=1, padx=10, pady=5)

deactivate_button = tk.Button(root, text="Deactivate", command=deactivate_license)
deactivate_button.grid(row=5, column=0, columnspan=2, pady=10)

# Reactivate License Section
tk.Label(root, text="Reactivate License ID:").grid(row=6, column=0, padx=10, pady=5)
reactivate_entry = tk.Entry(root, width=10)
reactivate_entry.grid(row=6, column=1, padx=10, pady=5)

reactivate_button = tk.Button(root, text="Reactivate", command=reactivate_license)
reactivate_button.grid(row=7, column=0, columnspan=2, pady=10)

# Fetch Licenses at Startup
fetch_licenses()

# Run the GUI
root.mainloop()
