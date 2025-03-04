import streamlit as st
import json
import os

LICENSE_FILE = "license.json"

def save_license(license_key):
    """Save the license key locally on the client system."""
    with open(LICENSE_FILE, "w") as f:
        json.dump({"license_key": license_key}, f)

def load_license():
    """Load the saved license key if it exists."""
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            return json.load(f).get("license_key")
    return None

st.title("Activate Your CRM Software")

if not load_license():
    license_key = st.text_input("Enter your license key:", type="password")
    if st.button("Activate"):
        save_license(license_key)
        st.success("License key saved! Restart the application.")
        st.stop()  # Prevent further execution until restart
else:
    st.info("License is already activated.")
