"""
Deterministic, dataset-scoped question answering over imported CSV/Excel
datasets (see dataset_registry-style functions in app.database.metadata).

This intentionally does NOT reuse semantic_retrieval_service.py's
embedding-based table selection/clarification: the caller passes explicit
dataset_ids, so there is no ambiguity to resolve. It also never calls
gemini_service.generate_insights / generate_diagnostic_sql — this path
returns evidence (SQL + rows), never LLM-authored narrative, causal claims,
or recommendations.
"""
import re

from sqlalchemy import inspect, text

from app.database.connection import engine
from app.database.metadata import (
    DATASET_SCHEMA,
    get_all_imported_identifiers,
    get_dataset_tables_by_ids,
)
from app.services.gemini_service import validate_sql

# Questions phrased as "why did X happen" or "what should we do about Y" ask
# for causal explanation or advice, neither of which follows from rows alone.
# This path declines them outright rather than attempting SQL and attaching
# a narrative on top, which would blur "what the data shows" with "what an
# LLM inferred" — the exact ambiguity the strict-answer contract exists to
# avoid.
_CAUSAL_OR_RECOMMENDATION_PATTERNS = [
    r"\bwhy\b",
    r"\bwhat\s+(?:should|could)\b",
    r"\bhow\s+(?:should|can|could)\s+(?:we|i|you)\b",
    r"\bwhat\s+caused\b",
    r"\bwhat'?s\s+causing\b",
    r"\bwhat'?s\s+the\s+reason\b",
    r"\brecommend(?:ation)?s?\b",
    r"\bsuggest(?:ion)?s?\b",
    r"\badvi[cs]e\b",
]
_CAUSAL_OR_RECOMMENDATION_RE = re.compile(
    "|".join(_CAUSAL_OR_RECOMMENDATION_PATTERNS), re.IGNORECASE
)

NO_DATASETS_MESSAGE = "Select at least one dataset before asking a question."
DECLINED_CAUSAL_MESSAGE = (
    "This question asks for a cause or a recommendation. This mode only "
    "answers with direct evidence from your selected data (query results), "
    "not causal explanations or advice — try rephrasing to ask for the "
    "underlying numbers instead."
)
NO_EVIDENCE_MESSAGE = "No matching evidence was found in the selected datasets."


class DatasetSelectionError(Exception):
    """Raised when dataset_ids is empty or references unknown datasets."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def is_causal_or_recommendation_question(question: str) -> bool:
    return bool(_CAUSAL_OR_RECOMMENDATION_RE.search(question))


def resolve_selected_tables(dataset_ids: list[int]) -> list[dict]:
    """Look up the imported tables for the given dataset ids.

    Raises DatasetSelectionError if dataset_ids is empty or references any
    dataset id that doesn't exist in the registry.
    """
    if not dataset_ids:
        raise DatasetSelectionError(NO_DATASETS_MESSAGE)

    tables, existing_ids = get_dataset_tables_by_ids(dataset_ids)
    missing = sorted(set(dataset_ids) - existing_ids)
    if missing:
        raise DatasetSelectionError(
            "Unknown dataset id(s): " + ", ".join(str(i) for i in missing)
        )
    return tables


def build_allowlist(tables: list[dict]) -> set[str]:
    """The set of table/column identifiers the generated SQL is allowed to
    reference, scoped to exactly the selected datasets' tables."""
    identifiers: set[str] = set()
    for table in tables:
        identifiers.add(table["db_table_name"].lower())
        for db_col in table["column_map"].values():
            identifiers.add(db_col.lower())
    return identifiers


_ROLE_TIME_TYPES = ("DATE", "TIMESTAMP", "TIME")
_ROLE_NUMERIC_TYPES = ("INTEGER", "BIGINT", "SMALLINT", "NUMERIC", "DOUBLE", "REAL", "FLOAT")


def _column_role(pg_type: str) -> str:
    upper = pg_type.upper()
    if any(t in upper for t in _ROLE_TIME_TYPES):
        return "time"
    if any(t in upper for t in _ROLE_NUMERIC_TYPES):
        return "measure"
    return "dimension"


def build_dataset_schema_text(tables: list[dict], sample_limit: int = 5) -> str:
    """Build LLM-facing schema text for exactly the selected imported
    tables. Each column is shown under its real (normalized) db identifier
    — the one the generated SQL must use — alongside the original label the
    user's file had for it, since a business term in the question is more
    likely to match the original label than the normalized name.
    """
    inspector = inspect(engine)
    lines = [
        'Use only the tables and columns below, all in the "imported" schema.',
        "Always schema-qualify table references, e.g. imported.<table_name>.",
        "Do not invent tables, columns, or relationships.",
        "",
    ]

    with engine.connect() as connection:
        for table in tables:
            db_table_name = table["db_table_name"]
            lines.append(
                f"Table: {DATASET_SCHEMA}.{db_table_name} "
                f"(from dataset \"{table['dataset_name']}\", "
                f"uploaded as \"{table['display_table_name']}\")"
            )
            lines.append("Columns:")

            try:
                columns = inspector.get_columns(db_table_name, schema=DATASET_SCHEMA)
            except Exception:
                columns = []

            reverse_column_map = {
                db_col: label for label, db_col in table["column_map"].items()
            }

            for column in columns:
                col_name = column["name"]
                pg_type = str(column["type"])
                role = _column_role(pg_type)

                original_label = reverse_column_map.get(col_name, col_name)
                label_note = (
                    f' [uploaded as "{original_label}"]'
                    if original_label != col_name
                    else ""
                )

                sample_note = ""
                if role in ("dimension", "time"):
                    try:
                        sample_rows = connection.execute(
                            text(
                                f'SELECT DISTINCT "{col_name}" '
                                f'FROM "{DATASET_SCHEMA}"."{db_table_name}" '
                                f'WHERE "{col_name}" IS NOT NULL LIMIT {sample_limit}'
                            )
                        ).all()
                        samples = [str(r[0]) for r in sample_rows]
                        if samples:
                            sample_note = f" | examples: {', '.join(samples)}"
                    except Exception:
                        sample_note = ""

                lines.append(f"- {col_name} ({pg_type}, {role}){label_note}{sample_note}")

            lines.append("")

    return "\n".join(lines)


def validate_dataset_scoped_sql(
    raw_sql: str, allowlist: set[str]
) -> tuple[bool, str]:
    """validate_sql, but scoped to the selected datasets' allow-list, with a
    clearer rejection message when the query touches a real table that
    exists in the registry but wasn't selected (vs. one that's simply
    unknown)."""
    is_valid, result = validate_sql(raw_sql, allowlist)
    if is_valid:
        return True, result

    if result.startswith("Query references an unknown table:"):
        unknown = {t.strip() for t in result.split(":", 1)[1].split(",")}
        registered_elsewhere = unknown & get_all_imported_identifiers()
        if registered_elsewhere:
            return False, (
                "Query references a table outside the selected datasets: "
                + ", ".join(sorted(registered_elsewhere))
            )

    return False, result
