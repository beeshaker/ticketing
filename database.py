import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
DB_URI = f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/licensing_db"

# Create SQLAlchemy engine
engine = create_engine(DB_URI)

# Create session factory
SessionLocal = sessionmaker(bind=engine)

# Base class for ORM models
Base = declarative_base()
