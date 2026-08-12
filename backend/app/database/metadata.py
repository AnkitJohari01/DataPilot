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

NUMERIC_TYPES = ("INTEGER", "NUMERIC", "FLOAT", "DOUBLE", "BIGINT", "SMALLINT")
TIME_TYPES = ("DATE", "TIMESTAMP", "TIME")


def get_compact_schema() -> str:
    """Turn the raw schema into a short text block for Gemini, with each
    column tagged as a measure, dimension, or time field."""
    schema = get_schema_summary()
    lines = []

    for table_name, info in schema.items():
        fk_map = {fk["column"][0]: fk["references"] for fk in info["foreign_keys"]}
        col_descriptions = []

        for col in info["columns"]:
            name, col_type = col["name"], col["type"].upper()
            tags = []

            if name in info["primary_key"]:
                tags.append("PK")
            if name in fk_map:
                tags.append(f"FK->{fk_map[name]}")
            if any(t in col_type for t in TIME_TYPES):
                tags.append("time")
            elif any(t in col_type for t in NUMERIC_TYPES) and name not in info["primary_key"] and name not in fk_map:
                tags.append("measure")
            elif "PK" not in tags and "FK" not in "".join(tags):
                tags.append("dimension")

            tag_str = f" ({', '.join(tags)})" if tags else ""
            col_descriptions.append(f"{name}{tag_str}")

        lines.append(f"Table: {table_name}")
        lines.append(f"  Columns: {', '.join(col_descriptions)}")

    return "\n".join(lines)