import json
import os
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import License

LICENSE_FILE = "license.json"

class LicenseManager:
    """Handles license loading and validation."""

    @staticmethod
    def load_license():
        """Load the saved license key from a local file."""
        if os.path.exists(LICENSE_FILE):
            with open(LICENSE_FILE, "r") as f:
                return json.load(f).get("license_key")
        return None

    @staticmethod
    def validate_license():
        """Check if the license key is valid in the database."""
        license_key = LicenseManager.load_license()
        if not license_key:
            return False, "License key not found. Please activate."

        session = SessionLocal()

        try:
            # Fetch license details
            license_record = session.query(License).filter(License.license_key == license_key).first()

            if not license_record:
                return False, "Invalid license key."

            if not license_record.is_active:
                return False, "License has been deactivated."

            if license_record.expires_at < datetime.utcnow():
                return False, "License has expired."

            return True, "License is valid."

        except Exception as e:
            return False, f"Error validating license: {e}"

        finally:
            session.close()
            

    
            
    

