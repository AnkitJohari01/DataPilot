from sqlalchemy import inspect
from app.database.connection import engine


def get_schema_summary() -> dict:
    """Inspect the connected database and return a compact schema map."""
    inspector = inspect(engine)
    schema = {}

    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        fks = inspector.get_foreign_keys(table_name)

        schema[table_name] = {
            "columns": [
                {"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"]}
                for c in columns
            ],
            "primary_key": pk,
            "foreign_keys": [
                {
                    "column": fk["constrained_columns"],
                    "references": f"{fk['referred_table']}({fk['referred_columns']})",
                }
                for fk in fks
            ],
        }

    return schema