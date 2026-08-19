"""Loads updated sales/returns data and new shipment/support-ticket tables into Neon."""

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

TABLES_TO_REPLACE = [
    ("data/fact_returns_1_.csv", "fact_returns"),
    ("data/fact_sales_1_.csv", "fact_sales"),
    ("data/fact_shipments.csv", "fact_shipments"),
    ("data/fact_support_tickets.csv", "fact_support_tickets"),
]
for file_path, table in TABLES_TO_REPLACE:
    print(f"Loading {file_path} into {table}...")
    df = pd.read_csv(file_path)
    df.to_sql(table, engine, if_exists="replace", index=False)
    print(f"✓ Loaded {len(df)} rows into {table}")

print("Done.")