from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()

# Database Connection using SQLAlchemy
DB_URI = f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
def get_db_connection1():
    return create_engine(DB_URI)