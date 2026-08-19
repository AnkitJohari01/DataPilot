from math import sqrt

from google import genai

from app.config.settings import settings
import time
from app.database.metadata import get_schema_catalog

client = genai.Client(api_key=settings.gemini_api_key)

EMBEDDING_MODEL = "gemini-embedding-2"

def create_embedding(text: str) -> list[float]:
    """Create a semantic embedding for a question or catalog item."""
    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )
    except Exception as error:
        raise RuntimeError(f"Embedding generation failed: {error}") from error

    if not response.embeddings:
        raise RuntimeError("Embedding generation returned no vector.")

    return list(response.embeddings[0].values)


def cosine_similarity(first: list[float], second: list[float]) -> float:
    """Return how semantically close two embedding vectors are."""
    if len(first) != len(second):
        raise ValueError("Embedding vectors must have the same length.")

    first_length = sqrt(sum(value * value for value in first))
    second_length = sqrt(sum(value * value for value in second))

    if first_length == 0 or second_length == 0:
        return 0.0

    dot_product = sum(
        first_value * second_value
        for first_value, second_value in zip(first, second)
    )

    return dot_product / (first_length * second_length)


def rank_by_similarity(
    question_embedding: list[float],
    candidates: list[dict],
    limit: int = 4,
) -> list[dict]:
    """Return the most semantically similar catalog candidates."""
    scored_candidates = []

    for candidate in candidates:
        score = cosine_similarity(
            question_embedding,
            candidate["embedding"],
        )

        scored_candidates.append(
            {
                **candidate,
                "similarity_score": score,
            }
        )

    return sorted(
        scored_candidates,
        key=lambda candidate: candidate["similarity_score"],
        reverse=True,
    )[:limit]



CATALOG_CACHE_SECONDS = 300

MIN_SEMANTIC_CONFIDENCE = 0.55
MIN_SEMANTIC_SCORE_GAP = 0.08


def needs_clarification(
    best_score: float,
    second_best_score: float | None = None,
) -> bool:
    """
    Return True when DataPilot cannot confidently choose one meaning.
    """
    if best_score < MIN_SEMANTIC_CONFIDENCE:
        return True

    if (
        second_best_score is not None
        and best_score - second_best_score < MIN_SEMANTIC_SCORE_GAP
    ):
        return True

    return False

_catalog_embedding_cache = {
    "created_at": 0.0,
    "candidates": [],
}

def _friendly_table_name(table_name: str) -> str:
    """Turn a database table name into a readable label."""
    words = table_name.replace("-", "_").split("_")

    if words and words[0].lower() in {"fact", "dim", "tbl", "table"}:
        words = words[1:]

    return " ".join(words).strip()


def build_clarification_question(candidate_table_names: list[str]) -> str:
    """Create one simple clarification question from dynamic table names."""
    options = [
        _friendly_table_name(table_name)
        for table_name in candidate_table_names[:3]
    ]

    options = [option for option in options if option]

    if not options:
        return (
            "I am not sure which part of the data you mean. "
            "Could you rephrase your question?"
        )

    if len(options) == 1:
        return (
            f"Could you clarify what you want to know about "
            f"{options[0]}?"
        )

    if len(options) == 2:
        choices = f"{options[0]} or {options[1]}"
    else:
        choices = f"{options[0]}, {options[1]}, or {options[2]}"

    return f"I found more than one possible data area. Do you mean {choices}?"

def _table_to_embedding_text(table: dict) -> str:
    """Create safe semantic text for one dynamically discovered table."""
    parts = [f"Table: {table['name']}"]

    for column in table["columns"]:
        parts.append(
            f"Column: {column['name']} "
            f"Type: {column['type']} "
            f"Role: {column['role']}"
        )

    for relationship in table["relationships"]:
        local_column = ", ".join(relationship["column"])
        target_column = ", ".join(relationship["references_column"])

        parts.append(
            f"Relationship: {local_column} links to "
            f"{relationship['references_table']}({target_column})"
        )

    return "\n".join(parts)


def _tables_to_llm_text(tables: list[dict]) -> str:
    """Turn only selected tables into database context for Gemini."""
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


def _get_catalog_candidates() -> list[dict]:
    """Create table embeddings once, then reuse them for five minutes."""
    now = time.monotonic()

    if (
        _catalog_embedding_cache["candidates"]
        and now - _catalog_embedding_cache["created_at"]
        < CATALOG_CACHE_SECONDS
    ):
        return _catalog_embedding_cache["candidates"]

    catalog = get_schema_catalog()
    candidates = []

    for table in catalog["tables"]:
        candidates.append(
            {
                "name": table["name"],
                "table": table,
                "embedding": create_embedding(
                    _table_to_embedding_text(table)
                ),
            }
        )

    _catalog_embedding_cache["created_at"] = now
    _catalog_embedding_cache["candidates"] = candidates

    return candidates


def get_semantically_relevant_catalog_for_llm(
    question: str,
    max_tables: int = 4,
) -> str:
    """
    Select the tables that are closest in meaning to the user's question.

    This works even when words differ, such as:
    'revenue' matching a column named 'net_sales'.
    """
    question_embedding = create_embedding(question)
    candidates = _get_catalog_candidates()

    matches = rank_by_similarity(
        question_embedding,
        candidates,
        limit=max_tables,
    )

    selected_tables = [
        match["table"]
        for match in matches
    ]

    return _tables_to_llm_text(selected_tables)