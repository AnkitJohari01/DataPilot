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


def generate_sql(question: str, schema_text: str) -> str:
    prompt = f"Schema:\n{schema_text}\n\nQuestion: {question}\n\nSQL:"

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"system_instruction": SQL_SYSTEM_INSTRUCTION, "temperature": 0},
    )

    sql = response.text.strip()
    # Strip markdown fences if Gemini adds them despite instructions
    if sql.startswith("```"):
        sql = sql.strip("`").removeprefix("sql").strip()
    return sql


import re

FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "grant", "revoke", "attach", "exec", "execute", "call"
}                                                                        # Blocks anything not starting with SELECT

def validate_sql(sql: str) -> tuple[bool, str]:
    """Rejects anything that isn't a single, safe SELECT statement."""
    cleaned = sql.strip().rstrip(";")                                    # Blocks stacked statements (;)

    if not cleaned.lower().startswith("select"):
        return False, "Only SELECT statements are allowed."              # Blocks DDL/DML keywords anywhere in the query 
    if ";" in cleaned:
        return False, "Multiple statements are not allowed."

    tokens = set(re.findall(r"[a-zA-Z_]+", cleaned.lower()))            # (word-boundary token check, so it won't false-positive on things like a column named created_at)
    hit = tokens & FORBIDDEN
    if hit:
        return False, f"Disallowed keyword(s): {', '.join(hit)}"

    if "limit" not in tokens:
        cleaned += " LIMIT 100"       # Auto-caps unbounded results at LIMIT 100 so a broad question can't pull the whole table

    return True, cleaned