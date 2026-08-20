from math import sqrt
import re
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


DIRECT_MATCH_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "business",
    "by",
    "data",
    "did",
    "do",
    "does",
    "doing",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "in",
    "is",
    "least",
    "me",
    "most",
    "of",
    "on",
    "or",
    "overall",
    "performance",
    "show",
    "tell",
    "the",
    "to",
    "top",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def _normalise_catalog_word(word: str) -> str:
    """Make simple singular and plural schema words match."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    if word.endswith("s") and len(word) > 3:
        return word[:-1]

    return word


def _meaningful_words(text: str) -> set[str]:
    """Return non-generic words from a question or schema name."""
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())

    return {
        _normalise_catalog_word(word)
        for word in words
        if word not in DIRECT_MATCH_STOP_WORDS and len(word) > 1
    }


def has_direct_catalog_match(
    question: str,
    candidate_tables: list[dict],
) -> bool:
    """
    Return True when the user used a table or column term directly.

    Example: 'products' and 'returns' directly match product and return
    schema elements, so DataPilot should query instead of asking again.
    """
    question_words = _meaningful_words(question)

    for table in candidate_tables:
        schema_words = _meaningful_words(table["name"])

        for column in table.get("columns", []):
            schema_words.update(
                _meaningful_words(column["name"])
            )

        if question_words & schema_words:
            return True

    return False

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



def get_clarification_candidates(
    candidate_tables: list[dict],
) -> list[str]:
    """
    Prefer tables with relationships for clarification choices.

    These are usually the main business-data tables, while tables without
    relationships are often supporting reference tables.
    """
    business_table_names = [
        table["name"]
        for table in candidate_tables
        if table.get("relationships")
    ]

    if len(business_table_names) >= 2:
        return business_table_names[:3]

    return [
        table["name"]
        for table in candidate_tables[:3]
    ]





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


def get_semantic_catalog_selection(
    question: str,
    max_tables: int = 4,
) -> dict:
    """
    Select the closest database tables and return their confidence scores.
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

    candidate_table_names = [
        match["name"]
        for match in matches
    ]

    candidate_tables = [
        match["table"]
        for match in matches
    ]

    best_score = (
        matches[0]["similarity_score"]
        if matches
        else 0.0
    )

    second_best_score = (
        matches[1]["similarity_score"]
        if len(matches) > 1
        else None
    )

    return {
        "schema_text": _tables_to_llm_text(selected_tables),
        "candidate_table_names": candidate_table_names,
        "best_score": best_score,
        "second_best_score": second_best_score,
        "candidate_tables": candidate_tables,
    }


def get_semantically_relevant_catalog_for_llm(
    question: str,
    max_tables: int = 4,
) -> str:
    """Return only the selected database context for Gemini."""
    selection = get_semantic_catalog_selection(question, max_tables)
    return selection["schema_text"]