"""Wraps Gemini calls for SQL generation."""

from google import genai
from app.config.settings import settings

client = genai.Client(api_key=settings.gemini_api_key)

SQL_SYSTEM_INSTRUCTION = """You generate PostgreSQL queries from natural-language questions.

Rules:
- Use ONLY the tables and columns given in the schema below. Never invent tables or columns.
- Only generate SELECT or WITH queries. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE.
- Use explicit JOIN conditions based on the foreign keys shown.
- Add a reasonable LIMIT unless the question clearly needs all rows (e.g. an aggregate).
- Use deterministic ORDER BY when ranking or returning top-N results.
- Return ONLY the raw SQL query. No markdown fences, no explanation, no commentary.
"""


def generate_sql(question: str, schema_text: str, history: list[dict] = None) -> str:
    history_text = ""
    if history:
        recent = history[-3:]
        history_text = "\n".join(
            f"Q: {h['question']}\nSQL: {h['sql']}" for h in recent
        )
        history_text = f"\nPrevious questions in this conversation:\n{history_text}\n"

    prompt = f"Schema:\n{schema_text}\n{history_text}\nQuestion: {question}\n\nSQL:"

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config={
                "system_instruction": SQL_SYSTEM_INSTRUCTION,
                "temperature": 0,
                "http_options": {"timeout": 10000},  # 10 seconds, in ms
            },
        )
    except Exception as e:
        raise RuntimeError(f"SQL generation failed: {e}")

    sql = response.text.strip()
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").strip()
    return sql       

def generate_insights(question: str, rows: list[dict]) -> dict:
    """Turns raw query rows into a What happened / Why / What's next narrative."""
    if not rows:
        return {
            "what_happened": "No data matched this question.",
            "why": "",
            "next_steps": "Try rephrasing the question or check if the filters are too narrow."
        }

    prompt = f"""
    Question: {question}
    This data is the RESULT of a SQL query that already answers the question — it is not raw unfiltered data.
    Result rows (first 20): {rows[:20]}

    Answer in exactly this format, no extra text:
    WHAT HAPPENED: <1-2 sentence factual summary of the result>
    WHY: <1-2 sentence likely explanation, based only on the data shown>
    NEXT STEPS: <1-2 sentence actionable suggestion>
    """
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config={
                "temperature": 0,
                "http_options": {"timeout": 10000},  # 10 seconds, in ms
            },
        )
    except Exception as e:
        raise RuntimeError(f"Insight generation failed: {e}")

    text_out = response.text.strip()

    sections = {"what_happened": "", "why": "", "next_steps": ""}
    for line in text_out.splitlines():
        if line.startswith("WHAT HAPPENED:"):
            sections["what_happened"] = line.replace("WHAT HAPPENED:", "").strip()
        elif line.startswith("WHY:"):
            sections["why"] = line.replace("WHY:", "").strip()
        elif line.startswith("NEXT STEPS:"):
            sections["next_steps"] = line.replace("NEXT STEPS:", "").strip()

    return sections


import re

FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "grant", "revoke", "attach", "exec", "execute", "call"
}                                                                        # Blocks anything not starting with SELECT

def validate_sql(sql: str, valid_identifiers: set[str]) -> tuple[bool, str]:
    """Rejects anything that isn't a single, safe SELECT statement
    using only real tables/columns from the schema."""
    cleaned = sql.strip().rstrip(";")

    if not cleaned.lower().startswith("select"):
        return False, "Only SELECT statements are allowed."

    if ";" in cleaned:
        return False, "Multiple statements are not allowed."

    tokens = set(re.findall(r"[a-zA-Z_]+", cleaned.lower()))

    hit = tokens & FORBIDDEN
    if hit:
        return False, f"Disallowed keyword(s): {', '.join(hit)}"

    # SQL reserved words / functions that aren't schema identifiers,
    # so they shouldn't be flagged as "unknown"
    sql_keywords = {
        "select", "from", "where", "and", "or", "not", "in", "as",
        "join", "left", "right", "inner", "outer", "on", "group", "by",
        "order", "desc", "asc", "limit", "offset", "having", "distinct",
        "count", "sum", "avg", "min", "max", "null", "is", "between",
        "like", "with", "case", "when", "then", "else", "end", "cast",
        "extract", "date", "interval", "over", "partition", "coalesce"
    }

    unknown = tokens - FORBIDDEN - sql_keywords - valid_identifiers
    # Drop pure numbers/short tokens that regex may have caught (e.g. "e" from scientific notation)
    unknown = {t for t in unknown if len(t) > 2}

    if unknown:
        return False, f"Query references unknown table/column(s): {', '.join(unknown)}"

    if "limit" not in tokens:
        cleaned += " LIMIT 100"

    return True, cleaned



