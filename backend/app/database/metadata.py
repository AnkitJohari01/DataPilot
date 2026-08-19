from sqlalchemy import inspect
from app.database.connection import engine
from datetime import date, datetime
from decimal import Decimal
import re
from sqlalchemy import MetaData, Table, inspect, select

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

def get_valid_identifiers() -> set[str]:
    """Returns a lowercase set of every real table and column name in the DB."""
    inspector = inspect(engine)
    identifiers = set()

    for table_name in inspector.get_table_names():
        identifiers.add(table_name.lower())
        for col in inspector.get_columns(table_name):
            identifiers.add(col["name"].lower())

    return identifiers


NUMERIC_TYPES = ("INTEGER", "NUMERIC", "FLOAT", "DOUBLE", "BIGINT", "SMALLINT")
TIME_TYPES = ("DATE", "TIMESTAMP", "TIME")

SENSITIVE_COLUMN_WORDS = (
    "password",
    "token",
    "secret",
    "email",
    "phone",
    "mobile",
    "address",
)


def _get_column_role(column_name: str, column_type: str, primary_key: list, foreign_keys: list) -> str:
    """Classify a column without relying on any specific business database."""
    if column_name in primary_key:
        return "primary_key"

    foreign_key_columns = {
        column
        for fk in foreign_keys
        for column in fk["constrained_columns"]
    }

    if column_name in foreign_key_columns:
        return "foreign_key"

    upper_type = column_type.upper()

    if any(data_type in upper_type for data_type in TIME_TYPES):
        return "time"

    if any(data_type in upper_type for data_type in NUMERIC_TYPES):
        return "measure"

    return "dimension"


def _is_sensitive_column(column_name: str) -> bool:
    """Avoid exposing likely personal or secret values in the catalog."""
    name = column_name.lower()
    return any(word in name for word in SENSITIVE_COLUMN_WORDS)


def _make_json_safe(value):
    """Convert database values into JSON-safe values."""
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)

    return value


def get_schema_catalog(sample_limit: int = 5) -> dict:
    """
    Build a dynamic catalog for any connected database.

    It discovers tables, columns, relationships, inferred column roles,
    and safe example values. No table or column names are hardcoded.
    """
    inspector = inspect(engine)
    metadata = MetaData()
    catalog_tables = []

    with engine.connect() as connection:
        for table_name in inspector.get_table_names():
            table = Table(table_name, metadata, autoload_with=engine)

            columns = inspector.get_columns(table_name)
            primary_key = inspector.get_pk_constraint(table_name).get(
                "constrained_columns", []
            )
            foreign_keys = inspector.get_foreign_keys(table_name)

            catalog_columns = []

            for column_info in columns:
                column_name = column_info["name"]
                column_type = str(column_info["type"])

                role = _get_column_role(
                    column_name,
                    column_type,
                    primary_key,
                    foreign_keys,
                )

                sample_values = []

                # Only collect examples from normal descriptive fields.
                # Never expose likely sensitive columns.
                if role in ("dimension", "time") and not _is_sensitive_column(column_name):
                    column = table.c[column_name]

                    statement = (
                        select(column)
                        .where(column.is_not(None))
                        .distinct()
                        .limit(sample_limit)
                    )

                    try:
                        sample_values = [
                            _make_json_safe(row[0])
                            for row in connection.execute(statement).all()
                        ]
                    except Exception:
                        sample_values = []

                catalog_columns.append(
                    {
                        "name": column_name,
                        "type": column_type,
                        "nullable": column_info["nullable"],
                        "role": role,
                        "sample_values": sample_values,
                    }
                )

            relationships = [
                {
                    "column": fk["constrained_columns"],
                    "references_table": fk["referred_table"],
                    "references_column": fk["referred_columns"],
                }
                for fk in foreign_keys
            ]

            catalog_tables.append(
                {
                    "name": table_name,
                    "primary_key": primary_key,
                    "relationships": relationships,
                    "columns": catalog_columns,
                }
            )

    return {"tables": catalog_tables}


def _normalise_word(word: str) -> str:
    """Make simple singular/plural words match: products -> product."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    if word.endswith("s") and len(word) > 3:
        return word[:-1]

    return word


def _get_words(text: str) -> set[str]:
    """Turn normal text, table names, and column names into matching words."""
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {_normalise_word(word) for word in words if len(word) > 1}


def _catalog_tables_to_llm_text(tables: list[dict]) -> str:
    """Convert selected catalog tables into text that Gemini can use."""
    lines = [
        "Use only the database information below.",
        "Do not invent tables, columns, or relationships.",
        "",
    ]

    for table in tables:
        lines.append(f"Table: {table['name']}")

        if table["primary_key"]:
            lines.append(f"Primary key: {', '.join(table['primary_key'])}")

        for relationship in table["relationships"]:
            local_column = ", ".join(relationship["column"])
            target_column = ", ".join(relationship["references_column"])

            lines.append(
                f"Relationship: {local_column} -> "
                f"{relationship['references_table']}({target_column})"
            )

        lines.append("Columns:")

        for column in table["columns"]:
            line = (
                f"- {column['name']} "
                f"({column['type']}, {column['role']})"
            )

            if column["sample_values"]:
                examples = ", ".join(
                    str(value) for value in column["sample_values"]
                )
                line += f" | examples: {examples}"

            lines.append(line)

        lines.append("")

    return "\n".join(lines)


def get_catalog_for_llm() -> str:
    """Return the complete dynamic catalog for Gemini."""
    catalog = get_schema_catalog()
    return _catalog_tables_to_llm_text(catalog["tables"])


def get_relevant_catalog_for_llm(question: str, max_tables: int = 4) -> str:
    """
    Select the database tables most relevant to the user's question.

    It is fully dynamic: it scores table names, column names, and safe
    sample values from whichever database is connected.
    """
    catalog = get_schema_catalog()
    question_words = _get_words(question)
    scored_tables = []

    for table in catalog["tables"]:
        score = 0

        table_words = _get_words(table["name"])
        score += len(question_words & table_words) * 5

        for column in table["columns"]:
            column_words = _get_words(column["name"])
            score += len(question_words & column_words) * 4

            for sample_value in column["sample_values"]:
                sample_words = _get_words(str(sample_value))
                score += len(question_words & sample_words) * 2

        scored_tables.append((score, table))

    relevant_tables = [
        table
        for score, table in sorted(
            scored_tables,
            key=lambda item: item[0],
            reverse=True,
        )
        if score > 0
    ][:max_tables]

    # If nothing matches, provide the full catalog so Gemini can still help.
    if not relevant_tables:
        relevant_tables = catalog["tables"]

    return _catalog_tables_to_llm_text(relevant_tables)