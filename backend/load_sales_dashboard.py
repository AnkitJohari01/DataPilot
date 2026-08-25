"""One-off script: drops old tables, applies schema.sql, loads the new
Sales_Dashboard_Data star schema + data_dictionary into Neon. Run once.

Expects these files in the same folder as this script:
  schema.sql, dim_customer.csv, dim_product.csv, dim_location.csv,
  dim_ship_mode.csv, dim_date.csv, fact_sales.csv, data_dictionary.csv

Note: loads rows via plain SQLAlchemy INSERT (not pandas.to_sql) because
pandas.to_sql fails to detect the SQLAlchemy connection in this environment
(pandas/sqlalchemy version mismatch) and raises
'Engine/Connection object has no attribute cursor'.
"""

import csv
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()
engine = create_engine(os.environ["STAR_SCHEMA_DATABASE_URL"])

CHUNK_SIZE = 500

# 1. Apply DDL (drops old tables, creates the new star schema)
with engine.begin() as conn:
    with open("schema.sql") as f:
        conn.execute(text(f.read()))
    print("✓ Schema applied (old tables dropped, new tables created)")

# 2. Load CSVs in dependency order: dimensions -> fact -> data_dictionary
LOAD_ORDER = [
    ("dim_customer.csv", "dim_customer"),
    ("dim_product.csv", "dim_product"),
    ("dim_location.csv", "dim_location"),
    ("dim_ship_mode.csv", "dim_ship_mode"),
    ("dim_date.csv", "dim_date"),
    ("fact_sales.csv", "fact_sales"),
    ("data_dictionary.csv", "data_dictionary"),
]


def load_csv(conn, filename, table):
    with open(filename, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        col_list = ", ".join(columns)
        placeholders = ", ".join(f":{c}" for c in columns)
        insert_stmt = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})")

        rows = list(reader)
        total = 0
        for i in range(0, len(rows), CHUNK_SIZE):
            batch = rows[i:i + CHUNK_SIZE]
            conn.execute(insert_stmt, batch)
            total += len(batch)
        return total


with engine.begin() as conn:
    for filename, table in LOAD_ORDER:
        count = load_csv(conn, filename, table)
        print(f"✓ Loaded {count} rows into {table}")

print("Done.")