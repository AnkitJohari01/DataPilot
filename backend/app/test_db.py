# Just to check whether the database connection is working or not

from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    result = conn.execute(text("SELECT version();"))
    print(result.fetchone())