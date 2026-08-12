"""One-off script: loads the star-schema CSVs into Neon. Run once, then delete."""

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

load_dotenv()

# Create SQLAlchemy engine
engine = create_engine(os.environ["DATABASE_URL"])

LOAD_ORDER = [
    ("dim_date.csv", "dim_date"),
    ("dim_product.csv", "dim_product"),
    ("dim_customer.csv", "dim_customer"),
    ("fact_sales.csv", "fact_sales"),
    ("fact_returns.csv", "fact_returns"),
]

DATA_DIR = "data"

# Use connection object, not engine
with engine.connect() as conn:
    for filename, table in LOAD_ORDER:
        file_path = os.path.join(DATA_DIR, filename)
        print(f"Loading {file_path}...")
        df = pd.read_csv(file_path)
        # Pass connection object (conn), not engine
        df.to_sql(table, conn, if_exists="append", index=False)
        conn.commit()
        print(f"✓ Loaded {len(df)} rows into {table}")