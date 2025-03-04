from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from database import Base, engine

class License(Base):
    """ORM model for the licenses table"""
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), unique=True, nullable=False)
    license_key = Column(String(100), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create the table if it doesn't exist
Base.metadata.create_all(engine)
