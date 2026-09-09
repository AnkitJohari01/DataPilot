from sqlalchemy import inspect
from app.database.connection import engine
from datetime import date, datetime
from decimal import Decimal
import re
from sqlalchemy import MetaData, Table, inspect, select, text

from app.database.connection import engine

import json
import pandas as pd

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


from sqlalchemy.exc import OperationalError
import time


def get_schema_catalog(sample_limit: int = 5) -> dict:
    """
    Build a dynamic catalog for any connected database.

    Retries once if the connection was killed mid-reflection (e.g. a
    serverless Postgres provider like Neon suspending/cold-starting).
    """
    for attempt in range(2):
        try:
            return _build_schema_catalog(sample_limit)
        except OperationalError:
            if attempt == 0:
                time.sleep(1)  # give the DB a beat to finish waking up
                continue
            raise


def _build_schema_catalog(sample_limit: int) -> dict:
    """
    Build a dynamic catalog for any connected database.

    It discovers tables, columns, relationships, inferred column roles,
    and safe example values. No table or column names are hardcoded.
    """
    inspector = inspect(engine)
    metadata = MetaData()
    catalog_tables = []

    with engine.connect() as connection:
        # Build a (table_name, column_name) -> description lookup from
        # data_dictionary, if it exists, so real column descriptions can be
        # shown instead of raw sample values.
        description_lookup: dict[tuple[str, str], str] = {}
        if "data_dictionary" in inspector.get_table_names():
            try:
                rows = connection.execute(
                    text(
                        "SELECT table_name, column_name, column_description "
                        "FROM data_dictionary"
                    )
                ).all()
                description_lookup = {
                    (row[0], row[1]): row[2] for row in rows if row[2]
                }
            except Exception:
                description_lookup = {}

        for table_name in inspector.get_table_names():
            if table_name == "data_dictionary":
                continue

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
                        "description": description_lookup.get(
                            (table_name, column_name), ""
                        ),
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


from sqlalchemy import text

META_INTENT_WORDS = {
    "table", "tables", "column", "columns", "field", "fields", "schema",
    "description", "descriptions", "describe", "definition", "define",
    "meaning", "means", "documentation", "docs", "dictionary",
}

def is_data_dictionary_question(question: str) -> bool:
    words = set(re.findall(r"[a-zA-Z]+", question.lower()))
    return bool(words & META_INTENT_WORDS)


def _named_identifiers(question: str) -> list[str]:
    """Every real table/column name literally present in the question,
    longest match first so 'dim_ship_mode' isn't shadowed by 'ship_mode'."""
    lowered = question.lower()
    return [
        identifier
        for identifier in sorted(get_valid_identifiers(), key=len, reverse=True)
        if re.search(rf"\b{re.escape(identifier)}\b", lowered)
    ]


def answer_data_dictionary_question(question: str) -> tuple[str, str] | None:
    named = _named_identifiers(question)
    if not named:
        return None

    target = named[0]
    table_names = {t.lower() for t in inspect(engine).get_table_names()}

    with engine.connect() as connection:
        if target in table_names:
            sql_display = (
                "SELECT column_name, table_description, column_description "
                f"FROM data_dictionary WHERE table_name = '{target}' ORDER BY column_name"
            )
            rows = connection.execute(
                text(
                    "SELECT column_name, table_description, column_description "
                    "FROM data_dictionary WHERE table_name = :t ORDER BY column_name"
                ),
                {"t": target},
            ).all()
            if not rows:
                return None
            lines = [f"{target}: {rows[0][1]}", ""]
            lines += [f"- {r[0]}: {r[2]}" for r in rows]
            return "\n".join(lines), sql_display

        sql_display = (
            "SELECT table_name, column_description "
            f"FROM data_dictionary WHERE column_name = '{target}'"
        )
        rows = connection.execute(
            text(
                "SELECT table_name, column_description "
                "FROM data_dictionary WHERE column_name = :c"
            ),
            {"c": target},
        ).all()
        if not rows:
            return None
        return "\n".join(f"- {r[0]}.{target}: {r[1]}" for r in rows), sql_display


# --- Dataset import registry (shared, user-uploaded CSV/Excel datasets) ---
#
# Imported data lives in its own Postgres schema (DATASET_SCHEMA) so it can
# never collide with the app's existing business tables, and never shows up
# in get_valid_identifiers()/get_schema_catalog() scans of the default
# schema. Two small registry tables (dp_datasets, dp_dataset_tables) track
# dataset name, creation time, imported table names, row counts, and the
# display-label -> db-identifier column mapping, so the catalog UI can show
# the original labels even though the actual columns are normalized.
#
# Table creation + row inserts use plain DDL and batched parameterized
# INSERTs (not pandas.to_sql) for the same reason load_sales_dashboard.py
# does: pandas.to_sql doesn't detect the SQLAlchemy Connection object in
# this environment (pandas/sqlalchemy version mismatch).

DATASET_SCHEMA = "imported"
IMPORT_CHUNK_SIZE = 500


def ensure_registry_tables() -> None:
    """Create the imported-data schema and registry tables if they don't
    already exist. Safe to call on every import/list request."""
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DATASET_SCHEMA}"'))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dp_datasets (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dp_dataset_tables (
                    id SERIAL PRIMARY KEY,
                    dataset_id INTEGER NOT NULL REFERENCES dp_datasets(id),
                    display_table_name TEXT NOT NULL,
                    db_table_name TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    column_map JSONB NOT NULL
                )
                """
            )
        )


def normalize_identifier(label: str, existing: set[str]) -> str:
    """Turn an arbitrary display label into a unique, valid Postgres
    identifier. `existing` is mutated to include the returned name, so
    callers normalizing a batch of labels (e.g. all columns in one sheet)
    can pass the same set through and get unique results."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        slug = "col"
    if slug[0].isdigit():
        slug = f"_{slug}"
    slug = slug[:63]

    candidate = slug
    suffix = 2
    while candidate in existing:
        suffix_str = f"_{suffix}"
        candidate = slug[: 63 - len(suffix_str)] + suffix_str
        suffix += 1

    existing.add(candidate)
    return candidate


def _pg_type_for_dtype(dtype) -> str:
    """Map a pandas/numpy dtype to a Postgres column type."""
    kind = dtype.kind
    if kind in ("i", "u"):
        return "BIGINT"
    if kind == "f":
        return "DOUBLE PRECISION"
    if kind == "b":
        return "BOOLEAN"
    if kind == "M":
        return "TIMESTAMP"
    return "TEXT"


def create_dataset_import(dataset_name: str, tables: dict[str, "pd.DataFrame"]) -> dict:
    """
    Create one table per entry in `tables` (display_table_name -> DataFrame,
    already filtered to non-empty) inside DATASET_SCHEMA, plus the registry
    rows describing them, all in a single transaction. On any failure the
    whole import (DDL, data, registry rows) is rolled back — no partial
    dataset is left visible.

    Table and column names are normalized and de-duplicated before
    creation; the original labels are preserved in the registry's
    display_table_name / column_map for the catalog UI.
    """
    ensure_registry_tables()

    with engine.begin() as connection:
        table_name_taken: set[str] = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": DATASET_SCHEMA},
            ).all()
        }

        dataset_id = connection.execute(
            text("INSERT INTO dp_datasets (name) VALUES (:name) RETURNING id"),
            {"name": dataset_name},
        ).scalar_one()

        created_tables = []

        for display_table_name, df in tables.items():
            db_table_name = normalize_identifier(display_table_name, table_name_taken)

            column_seen: set[str] = set()
            column_map: dict[str, str] = {}
            db_columns: list[tuple[str, str]] = []
            for original_col in df.columns:
                db_col = normalize_identifier(str(original_col), column_seen)
                column_map[str(original_col)] = db_col
                db_columns.append((db_col, _pg_type_for_dtype(df[original_col].dtype)))

            column_ddl = ", ".join(f'"{name}" {pg_type}' for name, pg_type in db_columns)
            connection.execute(
                text(f'CREATE TABLE "{DATASET_SCHEMA}"."{db_table_name}" ({column_ddl})')
            )

            renamed_df = df.rename(
                columns={orig: column_map[str(orig)] for orig in df.columns}
            )
            records = renamed_df.where(pd.notnull(renamed_df), None).to_dict("records")

            if records:
                col_list = ", ".join(f'"{c}"' for c, _ in db_columns)
                placeholders = ", ".join(f":{c}" for c, _ in db_columns)
                insert_stmt = text(
                    f'INSERT INTO "{DATASET_SCHEMA}"."{db_table_name}" ({col_list}) '
                    f"VALUES ({placeholders})"
                )
                for i in range(0, len(records), IMPORT_CHUNK_SIZE):
                    connection.execute(insert_stmt, records[i : i + IMPORT_CHUNK_SIZE])

            connection.execute(
                text(
                    "INSERT INTO dp_dataset_tables "
                    "(dataset_id, display_table_name, db_table_name, row_count, column_map) "
                    "VALUES (:dataset_id, :display_table_name, :db_table_name, :row_count, :column_map)"
                ),
                {
                    "dataset_id": dataset_id,
                    "display_table_name": display_table_name,
                    "db_table_name": db_table_name,
                    "row_count": len(df),
                    "column_map": json.dumps(column_map),
                },
            )

            created_tables.append(
                {
                    "display_table_name": display_table_name,
                    "db_table_name": db_table_name,
                    "row_count": len(df),
                    "column_map": column_map,
                }
            )

    return {"id": dataset_id, "name": dataset_name, "tables": created_tables}


def delete_dataset(dataset_id: int) -> bool:
    """Delete a dataset: drop its imported tables and remove its registry
    rows (dp_dataset_tables then dp_datasets), all in one transaction.
    Returns False without changing anything if the dataset id doesn't
    exist; True on success."""
    ensure_registry_tables()
    with engine.begin() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM dp_datasets WHERE id = :id"),
            {"id": dataset_id},
        ).first()
        if not exists:
            return False

        table_rows = connection.execute(
            text(
                "SELECT db_table_name FROM dp_dataset_tables WHERE dataset_id = :id"
            ),
            {"id": dataset_id},
        ).all()

        for (db_table_name,) in table_rows:
            connection.execute(
                text(f'DROP TABLE IF EXISTS "{DATASET_SCHEMA}"."{db_table_name}"')
            )

        connection.execute(
            text("DELETE FROM dp_dataset_tables WHERE dataset_id = :id"),
            {"id": dataset_id},
        )
        connection.execute(
            text("DELETE FROM dp_datasets WHERE id = :id"), {"id": dataset_id}
        )

    return True


def get_dataset_tables_by_ids(dataset_ids: list[int]) -> tuple[list[dict], set[int]]:
    """Resolve the given dataset ids against the registry.

    Returns (table_rows, existing_dataset_ids). table_rows is one entry per
    imported table belonging to any of the requested datasets (a dataset
    with several sheets/tables contributes several rows). existing_dataset_ids
    is the subset of `dataset_ids` that actually exist in dp_datasets, so
    callers can detect and reject any unknown id even though a dataset with
    zero tables can't otherwise occur (create_dataset_import always creates
    at least one non-empty table).
    """
    ensure_registry_tables()
    if not dataset_ids:
        return [], set()

    with engine.connect() as connection:
        existing_rows = connection.execute(
            text("SELECT id FROM dp_datasets WHERE id = ANY(:ids)"),
            {"ids": list(dataset_ids)},
        ).all()
        existing_dataset_ids = {row[0] for row in existing_rows}

        table_rows = connection.execute(
            text(
                "SELECT dt.dataset_id, d.name, dt.display_table_name, "
                "dt.db_table_name, dt.column_map "
                "FROM dp_dataset_tables dt "
                "JOIN dp_datasets d ON d.id = dt.dataset_id "
                "WHERE dt.dataset_id = ANY(:ids) "
                "ORDER BY dt.dataset_id, dt.id"
            ),
            {"ids": list(dataset_ids)},
        ).all()

    tables = [
        {
            "dataset_id": row[0],
            "dataset_name": row[1],
            "display_table_name": row[2],
            "db_table_name": row[3],
            "column_map": row[4] if isinstance(row[4], dict) else json.loads(row[4]),
        }
        for row in table_rows
    ]
    return tables, existing_dataset_ids


def get_all_imported_identifiers() -> set[str]:
    """Every table/column identifier across ALL imported datasets, regardless
    of selection. Used only to distinguish "this table exists but isn't in
    your selected datasets" from "this table doesn't exist at all" in the
    strict-ask validation error message."""
    identifiers: set[str] = set()
    for dataset in list_datasets():
        for table in dataset["tables"]:
            identifiers.add(table["db_table_name"].lower())
            for db_col in table["column_map"].values():
                identifiers.add(db_col.lower())
    return identifiers


def list_datasets() -> list[dict]:
    """Live read of the dataset registry — no cache, so a freshly imported
    dataset is always visible on the next call."""
    ensure_registry_tables()
    with engine.connect() as connection:
        dataset_rows = connection.execute(
            text("SELECT id, name, created_at FROM dp_datasets ORDER BY created_at")
        ).all()

        datasets = []
        for dataset_id, name, created_at in dataset_rows:
            table_rows = connection.execute(
                text(
                    "SELECT display_table_name, db_table_name, row_count, column_map "
                    "FROM dp_dataset_tables WHERE dataset_id = :id ORDER BY id"
                ),
                {"id": dataset_id},
            ).all()
            datasets.append(
                {
                    "id": dataset_id,
                    "name": name,
                    "created_at": created_at.isoformat() if created_at else None,
                    "tables": [
                        {
                            "display_table_name": r[0],
                            "db_table_name": r[1],
                            "row_count": r[2],
                            "column_map": r[3] if isinstance(r[3], dict) else json.loads(r[3]),
                        }
                        for r in table_rows
                    ],
                }
            )
        return datasets